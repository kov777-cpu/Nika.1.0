# -*- coding: utf-8 -*-
"""Смоук-тест Toga-интерфейса на заглушке: настоящий nika/app.py без BeeWare."""

import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import fake_toga  # noqa: E402
fake_toga.install()

from nika import app as app_module  # noqa: E402


def walk(widget):
    yield widget
    for child in getattr(widget, "children", []):
        yield from walk(child)


def texts(widget):
    return [w.text for w in walk(widget) if hasattr(w, "text")]


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.main()
        self.app.startup()

    def test_header_without_tagline(self):
        root = self.app.root
        header = root.children[0]
        # в шапке ровно три элемента: имя, голос, помощь
        self.assertEqual(len(header.children), 3)
        self.assertEqual(header.children[0].text, "Nika")
        self.assertNotIn("рядом", texts(root))

    def test_greeting_added(self):
        self.assertGreaterEqual(len(self.app.chat_box.children), 1)
        first = self.app.chat_box.children[0]
        self.assertTrue(first.children[0].text)

    def test_send_command(self):
        asyncio.run(self.app._send("позвони маме"))
        # последнее сообщение — ответ Nika
        last = self.app.chat_box.children[-1]
        self.assertTrue(last.children[0].text)
        self.assertFalse(self.app._busy)

    def test_timer_shows_and_fires(self):
        asyncio.run(self.app._send("засеки 10 минут"))
        self.assertTrue(self.app._timers)
        self.assertTrue(self.app._timer_shown)
        self.assertIn("таймер", self.app._timer_label.text)

        # сдвигаем время и проверяем срабатывание
        self.app._timers[0]["end"] = 0
        before = len(self.app.chat_box.children)
        self.app._tick()
        self.assertFalse(self.app._timers)
        self.assertGreater(len(self.app.chat_box.children), before)

    def test_stop_timer(self):
        asyncio.run(self.app._send("засеки 5 минут"))
        self.app._stop_timers(announce=True)
        self.assertFalse(self.app._timers)
        self.assertFalse(self.app._timer_shown)

    def test_chips_and_help(self):
        self.app._on_help(None)
        self.assertTrue(self.app.chips_box.children)
        self.assertEqual(self.app.input.value, "")

    def test_voice_toggle(self):
        start = self.app._voice
        self.app._on_voice(None)
        self.assertNotEqual(self.app._voice, start)
        self.assertIn(self.app.voice_button.text, ("голос", "тихо"))

    def test_input_cleared_after_send(self):
        self.app.input.value = "привет"
        asyncio.run(self.app._send(self.app.input.value))
        self.assertEqual(self.app.input.value, "")

    def test_typing_indicator_removed(self):
        asyncio.run(self.app._send("как дела"))
        self.assertIsNone(self.app._typing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
