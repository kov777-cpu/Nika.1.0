# -*- coding: utf-8 -*-
"""Nika для Android на BeeWare: Toga + Briefcase.

Интерфейс собран из нативных виджетов Toga: лента сообщений,
подсказки-кнопки, строка ввода, таймер сверху. Палитра — из Windows-версии.

Все вызовы bridge.* обёрнуты в getattr/fallback: если мост старый и чего-то
не умеет, приложение не падает, а просто теряет эту функцию.
"""

import asyncio
import functools
import os
import random
import time

import toga
from toga.style import Pack

from . import Engine, Reply, Store, nlp, theme
from .bridge import get_bridge


def _pack(**kwargs):
    try:
        return Pack(**kwargs)
    except Exception:
        for key in ("background_color", "gap", "text_align", "font_weight",
                    "color", "font_size", "padding", "margin", "width", "height",
                    "flex"):
            kwargs.pop(key, None)
        return Pack(**kwargs)


def _safe_bridge_call(bridge, name, *args, **kwargs):
    """Вызывает метод моста, если он есть и не падает. Возвращает None при ошибке."""
    if bridge is None:
        return None
    fn = getattr(bridge, name, None)
    if not callable(fn):
        return None
    try:
        return fn(*args, **kwargs)
    except TypeError:
        try:
            return fn(*args)
        except Exception:
            return None
    except Exception:
        return None


class NikaApp(toga.App):
    def __init__(self):
        super().__init__("Nika", "org.nikaassistant.nika")
        self.store = None
        self.engine = None
        self.bridge = None
        self._loop = None
        self._busy = False
        self._voice = True
        self._timers = []
        self._typing = None
        self._typing_label = None
        self._timer_row = None
        self._timer_label = None
        self._timer_shown = False
        self._ticker_task = None
        self._ticker_active = False
        self._last_activity = time.time()
        self._next_idle = time.time() + random.randint(20 * 60, 40 * 60)
        self._screen_w = 360
        self._startup_error = ""

    # ------------------------------------------------------------------
    #  Запуск
    # ------------------------------------------------------------------
    def startup(self):
        try:
            self._prepare_data()
        except Exception as exc:
            self._startup_error = "данные: %s" % exc

        try:
            self.main_window = toga.MainWindow(title="Nika")
            self.main_window.content = self._build_ui()
            self.main_window.show()
        except Exception as exc:
            print("[Nika/startup] UI: %s" % exc)
            raise

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                self._loop = asyncio.get_event_loop_policy().get_event_loop()
            except Exception:
                self._loop = None

        try:
            self.add_background_task(self._ticker)
        except Exception:
            pass
        try:
            asyncio.get_running_loop().call_soon(self._ensure_ticker)
        except Exception:
            pass

        try:
            self._greet()
        except Exception as exc:
            self._add_message("не смогла поздороваться: %s" % exc, False)

        if self._startup_error:
            self._add_message("запуск с замечанием: %s" % self._startup_error, False)

        if getattr(self.bridge, "is_android", False):
            _safe_bridge_call(self.bridge, "request_permissions",
                              ["POST_NOTIFICATIONS"], lambda ok: None)

    def _prepare_data(self):
        path = None
        try:
            data_dir = self.paths.data
            os.makedirs(str(data_dir), exist_ok=True)
            path = os.path.join(str(data_dir), "nika_memory.json")
        except Exception:
            pass
        if not path:
            base = os.path.join(os.path.expanduser("~"), ".nika")
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, "nika_memory.json")

        self.store = Store(path)
        self._voice = bool(self.store.pref("voice", True))
        try:
            self.bridge, _note = get_bridge(verbose=True)
        except Exception as exc:
            print("[Nika] bridge: %s" % exc)
            self.bridge = None
        try:
            self.engine = Engine(self.bridge, self.store,
                                 status_cb=self._status_from_thread)
        except Exception as exc:
            print("[Nika] engine: %s" % exc)
            self.engine = None

    # ------------------------------------------------------------------
    #  Интерфейс
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.root = toga.Box(style=_pack(direction="column",
                                         background_color=theme.BG))

        # тонкая строка кнопок без заголовка «Nika»
        header = toga.Box(style=_pack(direction="row", padding=(4, 8, 4, 8), gap=6))
        self.voice_button = toga.Button(
            "голос" if self._voice else "тихо",
            on_press=self._on_voice,
            style=_pack(width=78, height=32, font_size=12,
                        background_color=theme.ACCENT if self._voice else theme.CHIP,
                        color=theme.ON_ACCENT if self._voice else theme.MUTED_LIGHT))
        help_button = toga.Button(
            "?", on_press=self._on_help,
            style=_pack(width=38, height=32, font_size=14,
                        background_color=theme.CHIP, color=theme.CHIP_TEXT))
        header.add(toga.Box(style=_pack(flex=1)))
        header.add(self.voice_button)
        header.add(help_button)
        self.root.add(header)

        # полоса таймера
        self._timer_row = toga.Box(style=_pack(direction="row",
                                               padding=(6, 10, 6, 10),
                                               background_color=theme.BUBBLE))
        self._timer_label = toga.Label("", style=_pack(
            flex=1, color=theme.ACCENT, font_size=14, padding=(4, 6, 4, 6)))
        self._timer_stop = toga.Button(
            "стоп", on_press=self._on_stop_timer,
            style=_pack(width=64, height=30, font_size=12,
                        background_color=theme.CHIP, color=theme.CHIP_TEXT))
        self._timer_row.add(self._timer_label)
        self._timer_row.add(self._timer_stop)

        # чат
        self.chat_box = toga.Box(style=_pack(direction="column", padding=6))
        self.scroll = toga.ScrollContainer(horizontal=False, vertical=True,
                                           style=_pack(flex=1))
        self.scroll.content = self.chat_box
        self.root.add(self.scroll)

        # подсказки в две строки
        self.chips_box = toga.Box(style=_pack(direction="column",
                                              padding=(4, 8, 4, 8), gap=4))
        self.root.add(self.chips_box)

        # ввод
        input_row = toga.Box(style=_pack(direction="row", padding=(8, 10, 8, 10),
                                         gap=6, background_color=theme.INPUT))
        self.input = toga.TextInput(
            placeholder="напиши или нажми «мик.»",
            on_confirm=self._on_confirm,
            style=_pack(flex=1, font_size=15, background_color=theme.INPUT,
                        color=theme.ACCENT))
        mic = toga.Button(
            "мик.", on_press=self._on_mic,
            style=_pack(width=58, height=40, font_size=13,
                        background_color=theme.CHIP, color=theme.CHIP_TEXT))
        send = toga.Button(
            "→", on_press=self._on_send,
            style=_pack(width=48, height=40, font_size=18,
                        background_color=theme.ACCENT, color=theme.ON_ACCENT))
        input_row.add(self.input)
        input_row.add(mic)
        input_row.add(send)
        self.root.add(input_row)

        return self.root

    # ------------------------------------------------------------------
    #  Звуки (всё через _safe_bridge_call)
    # ------------------------------------------------------------------
    def _tap(self):
        _safe_bridge_call(self.bridge, "tap")

    def _beep(self):
        _safe_bridge_call(self.bridge, "beep")

    # ------------------------------------------------------------------
    #  Сообщения
    # ------------------------------------------------------------------
    def _add_message(self, text, mine=False):
        row = toga.Box(style=_pack(direction="row", padding=(3, 6, 3, 6)))
        label = toga.Label(
            text or "",
            style=_pack(flex=1, padding=(9, 11, 9, 11), font_size=15,
                        color=theme.USER_TEXT if mine else theme.ACCENT,
                        background_color=theme.BUBBLE_MINE if mine else theme.BUBBLE,
                        text_align="right" if mine else "left"))
        try:
            label.multiline = True
        except Exception:
            pass
        row.add(label)
        self.chat_box.add(row)
        self._scroll_end()

    def _scroll_end(self):
        try:
            self.scroll.vertical_position = 1.0
        except Exception:
            pass

    def _show_typing(self, text="печатает…"):
        if self._typing is None:
            row = toga.Box(style=_pack(direction="row", padding=(3, 6, 3, 6)))
            self._typing_label = toga.Label(
                text, style=_pack(flex=1, padding=(6, 10, 6, 10), font_size=13,
                                  color=theme.MUTED_LIGHT))
            row.add(self._typing_label)
            self._typing = row
            self.chat_box.add(row)
        else:
            self._typing_label.text = text
        self._scroll_end()

    def _hide_typing(self):
        if self._typing is not None:
            try:
                self.chat_box.remove(self._typing)
            except Exception:
                pass
            self._typing = None
            self._typing_label = None

    def _set_status(self, text):
        if self._typing is not None and self._typing_label is not None:
            self._typing_label.text = text

    def _set_chips(self, items):
        for child in list(self.chips_box.children):
            try:
                self.chips_box.remove(child)
            except Exception:
                pass
        items = [i for i in list(items)[:6] if i]
        if not items:
            return
        rows = [items[:3], items[3:6]]
        for row_items in rows:
            if not row_items:
                continue
            row = toga.Box(style=_pack(direction="row", gap=4))
            for item in row_items:
                width = max(64, min(int(self._screen_w / 3) - 8,
                                    28 + 7 * len(item)))
                button = toga.Button(
                    item,
                    on_press=functools.partial(self._on_chip, item),
                    style=_pack(width=width, height=34, font_size=12,
                                background_color=theme.CHIP,
                                color=theme.CHIP_TEXT))
                row.add(button)
            self.chips_box.add(row)

    # ------------------------------------------------------------------
    #  Действия пользователя
    # ------------------------------------------------------------------
    def _spawn(self, coro):
        self._ensure_ticker()
        try:
            asyncio.get_running_loop().create_task(coro)
            return
        except RuntimeError:
            pass
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(coro))
                return
            except Exception:
                pass
        try:
            asyncio.run(coro)
        except Exception:
            pass

    def _ensure_ticker(self):
        if self._ticker_task is not None or self._ticker_active:
            return
        try:
            self._ticker_task = asyncio.get_running_loop().create_task(self._ticker())
        except Exception:
            pass

    def _on_confirm(self, widget, **kwargs):
        self._tap()
        self._spawn(self._send(self.input.value))

    def _on_send(self, widget, **kwargs):
        self._tap()
        self._spawn(self._send(self.input.value))

    def _on_chip(self, text, widget, **kwargs):
        self._tap()
        self._spawn(self._send(text))

    def _on_help(self, widget, **kwargs):
        self._tap()
        self._spawn(self._send("что ты умеешь"))

    def _on_voice(self, widget, **kwargs):
        self._tap()
        self._voice = not self._voice
        try:
            self.store.set_pref("voice", self._voice)
            self.store.save()
        except Exception:
            pass
        if not self._voice:
            _safe_bridge_call(self.bridge, "stop_speak")
        try:
            self.voice_button.text = "голос" if self._voice else "тихо"
        except Exception:
            pass
        self._add_message(
            "снова говорю вслух)" if self._voice else
            "ок, буду молчать. пиши — я отвечу текстом)", False)
        self._remember_activity()

    def _on_stop_timer(self, widget, **kwargs):
        self._tap()
        self._stop_timers(announce=True)

    def _on_mic(self, widget, **kwargs):
        self._tap()
        self._spawn(self._mic_flow())

    async def _mic_flow(self):
        if self.bridge is None or not getattr(self.bridge, "can_voice", False):
            self._add_message("голосовой ввод работает на телефоне.", False)
            return
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def on_text(text):
            def put():
                if not future.done():
                    future.set_result(text)
            loop.call_soon_threadsafe(put)

        self._show_typing("слушаю…")
        try:
            result = self.bridge.listen(on_text)
        except Exception as exc:
            self._hide_typing()
            self._add_message("микрофон не отвечает: %s" % exc, False)
            return
        if result is not None and not getattr(result, "ok", False):
            self._hide_typing()
            self._add_message(getattr(result, "message", "") or
                              "не смогла включить микрофон.", False)
            return

        try:
            text = await asyncio.wait_for(future, timeout=60)
        except asyncio.TimeoutError:
            text = None
        self._hide_typing()
        if not text:
            self._add_message("не расслышала. повтори, пожалуйста.", False)
            return
        self.input.value = text
        await self._send(text)

    # ------------------------------------------------------------------
    #  Обработка фразы
    # ------------------------------------------------------------------
    async def _send(self, text):
        text = (text or "").strip()
        if not text or self._busy or self.engine is None:
            return
        self._remember_activity()
        self.input.value = ""
        self._add_message(text, mine=True)
        self._set_chips([])
        self._busy = True
        self._show_typing("думает…")
        try:
            reply = await asyncio.to_thread(self.engine.respond, text)
        except Exception as exc:
            reply = Reply("что-то сломалось: %s" % exc)
        self._busy = False
        self._hide_typing()
        self._deliver(reply)

    def _deliver(self, reply):
        if not isinstance(reply, Reply):
            return
        if reply.text:
            self._add_message(reply.text, mine=False)
        if reply.chips:
            self._set_chips(reply.chips)
        self._run_actions(reply.actions)
        if reply.speak and reply.text and self._voice:
            self._speak(reply.text)
        try:
            self.store.save()
        except Exception:
            pass

    def _remember_activity(self):
        self._last_activity = time.time()
        self._next_idle = time.time() + random.randint(20 * 60, 40 * 60)

    # ------------------------------------------------------------------
    #  Голос
    # ------------------------------------------------------------------
    def _speak(self, text):
        phrase = nlp.clean_for_speech(text)
        if not phrase:
            return
        _safe_bridge_call(self.bridge, "speak", phrase, female=True)

    def _status_from_thread(self, text):
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._set_status, text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    #  Таймеры и напоминания
    # ------------------------------------------------------------------
    def _run_actions(self, actions):
        for action in actions or []:
            kind = action.get("type")
            if kind == "timer":
                self._timers.append({"label": action.get("label", "таймер"),
                                     "end": time.time() + max(1, action.get("seconds", 60))})
                self._update_timer()
            elif kind == "timer_stop":
                self._stop_timers(announce=False)
            elif kind == "reminder":
                self._check_reminders()

    def _stop_timers(self, announce=True):
        had = bool(self._timers)
        self._timers = []
        self._update_timer()
        if had and announce:
            self._add_message("остановила таймер.", False)

    def _update_timer(self):
        if not self._timers:
            self._show_timer(False)
            return
        left = int(max(0, min(item["end"] for item in self._timers) - time.time()))
        try:
            self._timer_label.text = "таймер  %02d:%02d" % (left // 60, left % 60)
        except Exception:
            pass
        self._show_timer(True)

    def _show_timer(self, visible):
        if visible == self._timer_shown:
            return
        self._timer_shown = visible
        if visible:
            try:
                self.root.insert(1, self._timer_row)
            except Exception:
                try:
                    self.root.add(self._timer_row)
                except Exception:
                    pass
        else:
            try:
                self.root.remove(self._timer_row)
            except Exception:
                pass

    def _fire_timer(self, item):
        self._add_message("время вышло)", False)
        self._beep()
        _safe_bridge_call(self.bridge, "notify", "Nika — таймер",
                          item.get("label", "таймер") + ": время вышло")
        _safe_bridge_call(self.bridge, "vibrate", 200)
        self._speak("Время вышло")

    def _check_reminders(self):
        if self.store is None:
            return
        try:
            due = self.store.due_reminders()
        except Exception:
            return
        for reminder in due:
            text = reminder.get("text", "напоминание")
            self._add_message("напоминаю: %s" % text, False)
            self._beep()
            _safe_bridge_call(self.bridge, "notify", "Nika напоминает", text)
            _safe_bridge_call(self.bridge, "vibrate", 200)
            self._speak("Напоминаю: " + text)
            try:
                self.store.mark_reminder_done(reminder)
            except Exception:
                pass
        if due:
            try:
                self.store.save()
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  Фоновый цикл
    # ------------------------------------------------------------------
    async def _ticker(self, *args, **kwargs):
        if self._ticker_active:
            return
        self._ticker_active = True
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        while True:
            await asyncio.sleep(1)
            try:
                self._tick()
            except Exception:
                pass

    def _tick(self):
        now = time.time()

        if self._timers:
            alive = []
            for item in self._timers:
                if item["end"] <= now:
                    self._fire_timer(item)
                else:
                    alive.append(item)
            if len(alive) != len(self._timers):
                self._timers = alive
            self._update_timer()

        self._flush_deferred()
        self._check_reminders()

        if now > self._next_idle:
            if now - self._last_activity > 10 * 60 and self.engine is not None:
                try:
                    reply = self.engine.idle_message()
                except Exception:
                    reply = None
                if reply:
                    self._add_message(reply.text, False)
                    self._set_chips(reply.chips)
            self._next_idle = now + random.randint(20 * 60, 40 * 60)

    def _flush_deferred(self):
        if self.engine is None:
            return
        try:
            items = self.engine.take_deferred()
        except Exception:
            return
        for item in items:
            try:
                asyncio.create_task(self._run_deferred(item))
            except Exception:
                pass

    async def _run_deferred(self, item):
        try:
            reply = await asyncio.to_thread(item)
        except Exception as exc:
            reply = Reply("не получилось: %s" % exc)
        if isinstance(reply, Reply):
            self._deliver(reply)

    # ------------------------------------------------------------------
    #  Приветствие
    # ------------------------------------------------------------------
    def _greet(self):
        if self.engine is None:
            self._add_message("движок не запустился — смотри консоль.", False)
            return
        try:
            reply = self.engine.startup()
        except Exception as exc:
            self._add_message("не смогла запуститься: %s" % exc, False)
            return
        self._add_message(reply.text, False)
        self._set_chips(reply.chips)
        try:
            self.store.save()
        except Exception:
            pass


def main():
    return NikaApp()
