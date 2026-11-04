# -*- coding: utf-8 -*-
"""Мост Android для BeeWare (Briefcase + Chaquopy).

В отличие от python-for-android здесь Java-классы берутся через `jclass`,
а Java-интерфейсы реализуются через `dynamic_proxy`. Всё обёрнуто в try/except:
если на конкретной прошивке что-то недоступно, Nika не падает, а честно говорит,
что не получилось.
"""

import os
import re
import subprocess
import threading
import time

from .base import Bridge, Contact, Res
from ..wifi_parse import find_password, parse_wifi_config, parse_wpa_supplicant

try:
    from java import dynamic_proxy, jclass
    _JAVA = True
except Exception:  # на компьютере java-моста нет
    _JAVA = False

    def jclass(name):
        raise ImportError("java-мост доступен только на Android")

    def dynamic_proxy(interface):
        def deco(cls):
            return cls
        return deco


WIFI_CONFIG_PATHS = [
    "/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml",
    "/data/misc/wifi/WifiConfigStore.xml",
    "/data/misc/wifi/WifiConfigStore.xml.bak",
    "/data/misc/wifi/wpa_supplicant.conf",
    "/data/wifi/bcm_supp.conf",
]

REQ_PERMISSIONS = 0x4E4B


def _activity():
    """Текущая Activity: у Briefcase это MainActivity.singletonThis."""
    MainActivity = None
    try:
        MainActivity = jclass("org.beeware.android.MainActivity")
    except Exception:
        MainActivity = None
    if MainActivity is not None:
        for attribute in ("singletonThis", "singleton", "mActivity"):
            try:
                activity = getattr(MainActivity, attribute)
                if activity is not None:
                    return activity
            except Exception:
                continue
    try:
        import toga
        app = toga.App.app
        native = app._impl.native
        if native is not None:
            return native
    except Exception:
        pass
    return None


class AndroidBridge(Bridge):
    is_android = True
    platform_name = "android"
    can_call = True
    can_contacts = True
    can_apps = True
    can_wifi_passwords = True
    can_voice = True
    can_notify = True

    NOTIF_CHANNEL = "nika_messages"
    NOTIF_ID = 4101

    def __init__(self):
        super().__init__()
        self._ok = _JAVA
        self._ctx = _activity() if _JAVA else None
        self._tts = None
        self._tts_ready = False
        self._tts_voice_set = False
        self._listen_cb = None
        self._listener = None
        self._recognizer = None
        self._torch_id = None
        self._torch_on = False
        self._audio = None
        self._tone = None

        # звуки — только если есть Java и Activity
        if self._ok and self._ctx is not None:
            try:
                self._init_tts()
            except Exception as exc:
                self._emit("tts_init", exc)
            try:
                self._init_tap_sound()
            except Exception as exc:
                self._emit("tap_init", exc)

    # ------------------------------------------------------------------
    #  Служебное
    # ------------------------------------------------------------------
    @staticmethod
    def _emit(tag, message):
        try:
            print("[Nika/android] %s: %s" % (tag, message))
        except Exception:
            pass

    def ready(self):
        return bool(self._ok and self._ctx is not None)

    def info(self):
        model = ""
        version = ""
        try:
            Build = jclass("android.os.Build")
            model = "%s %s" % (Build.MANUFACTURER, Build.MODEL)
            version = "Android %s" % jclass("android.os.Build$VERSION").RELEASE
        except Exception:
            pass
        return {"platform": self.platform_name, "android": True,
                "model": model.strip(), "version": version}

    def _start(self, intent):
        try:
            Intent = jclass("android.content.Intent")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        except Exception:
            pass
        self._ctx.startActivity(intent)

    # ------------------------------------------------------------------
    #  Ссылки, приложения, магазин
    # ------------------------------------------------------------------
    def open_url(self, url):
        try:
            from urllib.parse import quote
            safe_url = quote(url, safe=":/?&=#%+@!$'()*,;[]~")
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            self._start(Intent(Intent.ACTION_VIEW, Uri.parse(safe_url)))
            return Res(True, "", url)
        except Exception as exc:
            return Res(False, "не смогла открыть ссылку: %s" % exc)

    def app_installed(self, package):
        if not package:
            return False
        try:
            self._ctx.getPackageManager().getPackageInfo(package, 0)
            return True
        except Exception:
            return False

    def installed_apps(self):
        cached = self.cached_apps()
        if cached is not None:
            return cached
        apps = []
        try:
            pm = self._ctx.getPackageManager()
            infos = pm.getInstalledApplications(0)
            count = infos.size() if infos is not None else 0
            for index in range(count):
                info = infos.get(index)
                try:
                    label = str(pm.getApplicationLabel(info))
                except Exception:
                    label = ""
                try:
                    package = str(info.packageName)
                except Exception:
                    package = ""
                if label and package:
                    apps.append((label, package))
        except Exception as exc:
            self._emit("apps", exc)
        self.touch_apps_cache(apps)
        return apps

    def launch_package(self, package):
        try:
            intent = self._ctx.getPackageManager().getLaunchIntentForPackage(package)
            if intent is None:
                return Res(False, "не установлено")
            self._start(intent)
            return Res(True)
        except Exception as exc:
            return Res(False, str(exc))

    def open_play_store(self, package):
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            self._start(Intent(Intent.ACTION_VIEW,
                               Uri.parse("market://details?id=%s" % package)))
            return Res(True)
        except Exception:
            return self.open_url("https://play.google.com/store/apps/details?id=%s" % package)

    # ------------------------------------------------------------------
    #  Контакты и звонки
    # ------------------------------------------------------------------
    def contacts(self):
        cached = self.cached_contacts()
        if cached is not None:
            return cached
        if not self.has_permission("READ_CONTACTS"):
            return []
        result = []
        seen = set()
        try:
            Phone = jclass("android.provider.ContactsContract$CommonDataKinds$Phone")
            resolver = self._ctx.getContentResolver()
            cursor = resolver.query(Phone.CONTENT_URI, None, None, None, None)
            if cursor is not None:
                idx_name = cursor.getColumnIndex("display_name")
                idx_number = cursor.getColumnIndex("data1")
                while cursor.moveToNext():
                    name = cursor.getString(idx_name) if idx_name >= 0 else ""
                    number = cursor.getString(idx_number) if idx_number >= 0 else ""
                    name = (name or "").strip()
                    number = (number or "").strip()
                    if not number:
                        continue
                    digits = re.sub(r"\D", "", number)
                    key = (name.lower(), digits[-10:])
                    if key in seen:
                        continue
                    seen.add(key)
                    from .. import nlp
                    result.append(Contact(
                        name=name or number,
                        number=nlp.normalize_phone(number) or number,
                        raw_number=number))
                cursor.close()
        except Exception as exc:
            self._emit("contacts", exc)
        self.touch_contacts_cache(result)
        return result

    def dial(self, number, direct=False):
        if not number:
            return Res(False, "не поняла номер.")
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            if direct and self.has_permission("CALL_PHONE"):
                try:
                    self._start(Intent(Intent.ACTION_CALL, Uri.parse("tel:" + number)))
                    return Res(True, "звоню")
                except Exception:
                    pass
            self._start(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + number)))
            return Res(True, "набираю")
        except Exception as exc:
            return Res(False, "не смогла открыть номеронабиратель: %s" % exc)

    def send_sms(self, number, text):
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            intent = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + number))
            if text:
                intent.putExtra("sms_body", text)
            self._start(intent)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть сообщения: %s" % exc)

    # ------------------------------------------------------------------
    #  Медиа
    # ------------------------------------------------------------------
    def _media_uri(self, query, video=False):
        try:
            resolver = self._ctx.getContentResolver()
            if video:
                Media = jclass("android.provider.MediaStore$Video$Media")
            else:
                Media = jclass("android.provider.MediaStore$Audio$Media")
            collection = Media.EXTERNAL_CONTENT_URI
            cursor = resolver.query(collection, None, "_display_name LIKE ?",
                                    ["%" + query + "%"], None)
            if cursor is None or not cursor.moveToFirst():
                if cursor is not None:
                    cursor.close()
                return None, ""
            idx_id = cursor.getColumnIndex("_id")
            idx_title = cursor.getColumnIndex("_display_name")
            media_id = cursor.getLong(idx_id) if idx_id >= 0 else 0
            title = str(cursor.getString(idx_title)) if idx_title >= 0 else query
            cursor.close()
            ContentUris = jclass("android.content.ContentUris")
            return ContentUris.withAppendedId(collection, media_id), title
        except Exception as exc:
            self._emit("media", exc)
            return None, ""

    def play_media(self, query="", video=False):
        uri = None
        title = ""
        if query:
            uri, title = self._media_uri(query, video)
        if uri is not None:
            try:
                Intent = jclass("android.content.Intent")
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, "video/*" if video else "audio/*")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                self._start(intent)
                return Res(True, "включаю", {"source": "local", "title": title})
            except Exception as exc:
                self._emit("play_media", exc)

        search = "https://m.youtube.com/results?search_query=" + (query or "").replace(" ", "+")
        if not query:
            search = "https://m.youtube.com"
        if video or not query:
            if self.app_installed("com.google.android.youtube"):
                if self.launch_package("com.google.android.youtube").ok:
                    return Res(True, "открываю ютуб", {"source": "youtube"})
        if not query:
            music = "com.google.android.apps.youtube.music"
            if self.app_installed(music):
                if self.launch_package(music).ok:
                    return Res(True, "открываю ютуб мьюзик", {"source": "youtube-music"})
        opened = self.open_url(search)
        if opened.ok:
            return Res(True, "ищу в ютубе", {"source": "web", "query": query})
        return Res(False, "не нашла «%s» ни в памяти, ни в ютубе." % query)

    # ------------------------------------------------------------------
    #  Будильник, фонарик, батарея, звук, настройки
    # ------------------------------------------------------------------
    def set_alarm(self, hour, minute, label=""):
        try:
            AlarmClock = jclass("android.provider.AlarmClock")
            Intent = jclass("android.content.Intent")
            intent = Intent(AlarmClock.ACTION_SET_ALARM)
            intent.putExtra(AlarmClock.EXTRA_HOUR, int(hour))
            intent.putExtra(AlarmClock.EXTRA_MINUTES, int(minute))
            intent.putExtra(AlarmClock.EXTRA_SKIP_UI, False)
            if label:
                intent.putExtra(AlarmClock.EXTRA_MESSAGE, label)
            self._start(intent)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть будильник: %s" % exc)

    def torch(self, on):
        try:
            Context = jclass("android.content.Context")
            CameraManager = jclass("android.hardware.camera2.CameraManager")
            manager = self._ctx.getSystemService(Context.CAMERA_SERVICE)
            if self._torch_id is None:
                ids = manager.getCameraIdList()
                self._torch_id = ids[0] if ids is not None and len(ids) else None
            if not self._torch_id:
                return Res(False, "не нашла вспышку.")
            manager.setTorchMode(self._torch_id, bool(on))
            self._torch_on = bool(on)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "фонарик не поддался: %s" % exc)

    def battery(self):
        try:
            Intent = jclass("android.content.Intent")
            IntentFilter = jclass("android.content.IntentFilter")
            sticky = self._ctx.registerReceiver(None, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if sticky is None:
                return {}
            level = sticky.getIntExtra("level", -1)
            scale = sticky.getIntExtra("scale", 100)
            status = sticky.getIntExtra("status", -1)
            plugged = sticky.getIntExtra("plugged", -1)
            if level < 0:
                return {}
            return {"percent": int(round(level * 100.0 / (scale or 100))),
                    "charging": status == 2 or plugged > 0}
        except Exception:
            return {}

    def volume(self, direction):
        try:
            Context = jclass("android.content.Context")
            AudioManager = jclass("android.media.AudioManager")
            manager = self._ctx.getSystemService(Context.AUDIO_SERVICE)
            if manager is None:
                return Res(False, "не нашла регулятор звука.")
            stream = AudioManager.STREAM_MUSIC
            if direction == "up":
                manager.adjustStreamVolume(stream, AudioManager.ADJUST_RAISE,
                                           AudioManager.FLAG_SHOW_UI)
            elif direction == "down":
                manager.adjustStreamVolume(stream, AudioManager.ADJUST_LOWER,
                                           AudioManager.FLAG_SHOW_UI)
            elif direction == "mute":
                manager.setStreamVolume(stream, 0, AudioManager.FLAG_SHOW_UI)
            elif direction == "max":
                manager.setStreamVolume(stream, manager.getStreamMaxVolume(stream),
                                        AudioManager.FLAG_SHOW_UI)
            level = int(manager.getStreamVolume(stream))
            top = int(manager.getStreamMaxVolume(stream)) or 1
            return Res(True, "%d%%" % int(round(level * 100.0 / top)))
        except Exception as exc:
            return Res(False, "звук не поддался: %s" % exc)

    def open_settings(self, page=""):
        try:
            Settings = jclass("android.provider.Settings")
            actions = {
                "wifi": "ACTION_WIFI_SETTINGS",
                "apps": "ACTION_APPLICATION_SETTINGS",
                "bluetooth": "ACTION_BLUETOOTH_SETTINGS",
                "display": "ACTION_DISPLAY_SETTINGS",
                "sound": "ACTION_SOUND_SETTINGS",
                "battery": "ACTION_BATTERY_SAVER_SETTINGS",
                "location": "ACTION_LOCATION_SOURCE_SETTINGS",
                "data": "ACTION_DATA_ROAMING_SETTINGS",
                "notification": "ACTION_NOTIFICATION_SETTINGS",
            }
            name = actions.get(page or "", "ACTION_SETTINGS")
            action = getattr(Settings, name, Settings.ACTION_SETTINGS)
            Intent = jclass("android.content.Intent")
            self._start(Intent(action))
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть настройки: %s" % exc)

    # ------------------------------------------------------------------
    #  Уведомления и вибрация
    # ------------------------------------------------------------------
    def notify(self, title, text):
        try:
            Build = jclass("android.os.Build$VERSION")
            sdk = int(Build.SDK_INT)
            Context = jclass("android.content.Context")
            manager = self._ctx.getSystemService(Context.NOTIFICATION_SERVICE)
            if manager is None:
                return Res(False, "")
            if sdk >= 33 and not self.has_permission("POST_NOTIFICATIONS"):
                return Res(False, "нет разрешения на уведомления")

            default_sound = None
            try:
                RingtoneManager = jclass("android.media.RingtoneManager")
                default_sound = RingtoneManager.getDefaultUri(
                    RingtoneManager.TYPE_NOTIFICATION)
            except Exception:
                default_sound = None

            if sdk >= 26:
                Channel = jclass("android.app.NotificationChannel")
                channel = Channel(self.NOTIF_CHANNEL, "Nika", 4)  # IMPORTANCE_HIGH
                try:
                    if default_sound is not None:
                        AudioAttributes = jclass("android.media.AudioAttributes")
                        attrs = AudioAttributes.Builder() \
                            .setUsage(AudioAttributes.USAGE_NOTIFICATION) \
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION) \
                            .build()
                        channel.setSound(default_sound, attrs)
                except Exception:
                    pass
                try:
                    channel.enableVibration(True)
                except Exception:
                    pass
                manager.createNotificationChannel(channel)
                Builder = jclass("android.app.Notification$Builder")
                builder = Builder(self._ctx, self.NOTIF_CHANNEL)
            else:
                Builder = jclass("android.app.Notification$Builder")
                builder = Builder(self._ctx)

            icon = self._ctx.getApplicationInfo().icon
            builder.setContentTitle(str(title))
            builder.setContentText(str(text))
            builder.setSmallIcon(icon)
            builder.setAutoCancel(True)
            try:
                if sdk < 26 and default_sound is not None:
                    builder.setSound(default_sound)
                builder.setDefaults(-1)  # ALL: звук + вибрация + свет
            except Exception:
                pass
            manager.notify(self.NOTIF_ID, builder.build())
            return Res(True, "")
        except Exception as exc:
            self._emit("notify", exc)
            return Res(False, str(exc))

    def vibrate(self, ms=40):
        try:
            Context = jclass("android.content.Context")
            vibrator = self._ctx.getSystemService(Context.VIBRATOR_SERVICE)
            if vibrator is None:
                return Res(False, "")
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) >= 26:
                VibrationEffect = jclass("android.os.VibrationEffect")
                vibrator.vibrate(VibrationEffect.createOneShot(int(ms), -1))
            else:
                vibrator.vibrate(int(ms))
            return Res(True, "")
        except Exception:
            return Res(False, "")

    # ------------------------------------------------------------------
    #  Короткие звуки
    # ------------------------------------------------------------------
    def _init_tap_sound(self):
        try:
            Context = jclass("android.content.Context")
            self._audio = self._ctx.getSystemService(Context.AUDIO_SERVICE)
        except Exception as exc:
            self._audio = None
            self._emit("tap_init", exc)

    def beep(self):
        """Один короткий звук уведомления."""
        try:
            RingtoneManager = jclass("android.media.RingtoneManager")
            uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            ringtone = RingtoneManager.getRingtone(self._ctx, uri)
            if ringtone is None:
                return Res(False, "")
            try:
                Build = jclass("android.os.Build$VERSION")
                if int(Build.SDK_INT) >= 21:
                    AudioAttributes = jclass("android.media.AudioAttributes")
                    attrs = AudioAttributes.Builder() \
                        .setUsage(AudioAttributes.USAGE_NOTIFICATION) \
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION) \
                        .build()
                    ringtone.setAudioAttributes(attrs)
            except Exception:
                pass
            ringtone.play()
            return Res(True, "")
        except Exception as exc:
            self._emit("beep", exc)
            return Res(False, "")

    def tap(self):
        """Короткий тихий клик нажатия (~20–30 мс)."""
        try:
            if self._audio is None:
                Context = jclass("android.content.Context")
                self._audio = self._ctx.getSystemService(Context.AUDIO_SERVICE)
            AudioManager = jclass("android.media.AudioManager")
            if self._audio is not None:
                self._audio.playSoundEffect(
                    AudioManager.FX_KEYPRESS_STANDARD, 0.35)
                return Res(True, "")
        except Exception:
            pass
        try:
            if self._tone is None:
                ToneGenerator = jclass("android.media.ToneGenerator")
                AudioManager = jclass("android.media.AudioManager")
                self._tone = ToneGenerator(AudioManager.STREAM_SYSTEM, 25)
            ToneGenerator = jclass("android.media.ToneGenerator")
            self._tone.startTone(ToneGenerator.TONE_PROP_BEEP, 15)
            return Res(True, "")
        except Exception:
            return Res(False, "")

    # ------------------------------------------------------------------
    #  Голос
    # ------------------------------------------------------------------
    def _init_tts(self):
        try:
            TextToSpeech = jclass("android.speech.tts.TextToSpeech")
            Listener = jclass("android.speech.tts.TextToSpeech$OnInitListener")

            class OnInit(dynamic_proxy(Listener)):
                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback

                def onInit(self, status):
                    try:
                        self.callback(status == 0)
                    except Exception:
                        pass

            self._tts = TextToSpeech(self._ctx, OnInit(self._on_tts_ready))
        except Exception as exc:
            self._emit("tts", exc)
            self._tts = None

    def _on_tts_ready(self, ok):
        self._tts_ready = bool(ok)
        if not ok or self._tts is None:
            return
        try:
            Locale = jclass("java.util.Locale")
            self._tts.setLanguage(Locale("ru", "RU"))
            self._tts.setSpeechRate(0.94)
            self._tts.setPitch(1.06)
        except Exception as exc:
            self._emit("tts_lang", exc)
        self._select_female_voice()

    def _select_female_voice(self):
        """Ищем ru-RU voice с признаком female (или по имени)."""
        if self._tts is None or self._tts_voice_set:
            return
        try:
            voices = self._tts.getVoices()
            if voices is None:
                return
            chosen = None
            fallback = None
            for voice in voices:
                try:
                    locale = voice.getLocale()
                    if locale is None:
                        continue
                    lang = str(locale.getLanguage() or "").lower()
                    if lang != "ru":
                        continue
                    name = str(voice.getName() or "").lower()
                    try:
                        features = set(str(f).lower() for f in voice.getFeatures())
                    except Exception:
                        features = set()
                    female_marker = ("female" in name or "жен" in name or
                                     "female" in features or
                                     name.endswith("-f") or "-f-" in name)
                    offline = True
                    try:
                        offline = not voice.isNetworkConnectionRequired()
                    except Exception:
                        pass
                    if female_marker and offline:
                        chosen = voice
                        break
                    if fallback is None and offline:
                        fallback = voice
                except Exception:
                    continue
            target = chosen or fallback
            if target is not None:
                self._tts.setVoice(target)
                self._tts_voice_set = True
                self._tts.setPitch(1.08 if chosen else 1.04)
                self._tts.setSpeechRate(0.94)
        except Exception as exc:
            self._emit("tts_voice", exc)

    def speak(self, text, female=True):
        if not text or self._tts is None or not self._tts_ready:
            return Res(False, "")
        try:
            if female and not self._tts_voice_set:
                self._select_female_voice()
            if female:
                try:
                    self._tts.setPitch(1.08)
                    self._tts.setSpeechRate(0.94)
                except Exception:
                    pass
            else:
                try:
                    self._tts.setPitch(0.96)
                    self._tts.setSpeechRate(1.0)
                except Exception:
                    pass
            self._tts.speak(text, 0, None, "nika-%d" % int(time.time() * 1000))
            return Res(True, "")
        except Exception as exc:
            self._emit("speak", exc)
            return Res(False, "")

    def stop_speak(self):
        try:
            if self._tts is not None:
                self._tts.stop()
            return Res(True, "")
        except Exception:
            return Res(False, "")

    def _run_on_ui(self, function):
        """Выполняет код в UI-потоке Android (нужно для SpeechRecognizer)."""
        try:
            Runnable = jclass("java.lang.Runnable")

            class Runner(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn

                def run(self):
                    try:
                        self.fn()
                    except Exception:
                        pass

            self._ctx.runOnUiThread(Runner(function))
            return True
        except Exception:
            try:
                function()
                return True
            except Exception as exc:
                self._emit("ui_thread", exc)
                return False

    def _make_listener(self, on_result):
        RecognitionListener = jclass("android.speech.RecognitionListener")

        class Listener(dynamic_proxy(RecognitionListener)):
            def onReadyForSpeech(self, params):
                pass

            def onBeginningOfSpeech(self):
                pass

            def onRmsChanged(self, rms):
                pass

            def onBufferReceived(self, buffer):
                pass

            def onEndOfSpeech(self):
                pass

            def onError(self, error):
                try:
                    on_result(None)
                except Exception:
                    pass

            def onResults(self, results):
                text = None
                try:
                    matches = results.getStringArrayList("results_recognition")
                    if matches is not None and matches.size() > 0:
                        text = str(matches.get(0))
                except Exception:
                    text = None
                try:
                    on_result(text)
                except Exception:
                    pass

            def onPartialResults(self, results):
                pass

            def onEvent(self, event_type, params):
                pass

        return Listener()

    def listen(self, callback):
        if not self.has_permission("RECORD_AUDIO"):
            def after_grant(ok):
                if ok:
                    self.listen(callback)
                else:
                    callback(None)
            self.request_permissions(["RECORD_AUDIO"], after_grant)
            return Res(True, "")

        try:
            RecognizerIntent = jclass("android.speech.RecognizerIntent")
            SpeechRecognizer = jclass("android.speech.SpeechRecognizer")
            Intent = jclass("android.content.Intent")

            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Говори, я слушаю")
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)

            listener = self._make_listener(callback)

            def start():
                if self._recognizer is None:
                    self._recognizer = SpeechRecognizer.createSpeechRecognizer(self._ctx)
                self._recognizer.setRecognitionListener(listener)
                self._recognizer.startListening(intent)

            self._listener = listener
            if not self._run_on_ui(start):
                return Res(False, "не смогла запустить микрофон.")
            return Res(True, "")
        except Exception as exc:
            self._emit("listen", exc)
            return Res(False, "не смогла включить микрофон: %s" % exc)

    # ------------------------------------------------------------------
    #  Wi-Fi
    # ------------------------------------------------------------------
    def _wifi_manager(self):
        try:
            Context = jclass("android.content.Context")
            return self._ctx.getApplicationContext().getSystemService(Context.WIFI_SERVICE)
        except Exception:
            return None

    def wifi_saved(self):
        manager = self._wifi_manager()
        if manager is None:
            return []
        names = []
        try:
            networks = manager.getConfiguredNetworks()
            if networks is None:
                return []
            for index in range(networks.size()):
                network = networks.get(index)
                ssid = str(network.SSID or "").strip().strip('"')
                if ssid and ssid not in names:
                    names.append(ssid)
        except Exception as exc:
            self._emit("wifi_saved", exc)
        return names

    def wifi_info(self):
        manager = self._wifi_manager()
        info = {}
        if manager is None:
            return info
        try:
            current = manager.getConnectionInfo()
            if current is not None:
                ssid = str(current.getSSID() or "").strip().strip('"')
                if ssid and ssid not in ("<unknown ssid>", "0x", "unknown"):
                    info["ssid"] = ssid
                rssi = int(current.getRssi())
                if rssi < 0:
                    info["rssi"] = rssi
                ip_int = int(current.getIpAddress())
                if ip_int:
                    info["ip"] = "%d.%d.%d.%d" % (
                        ip_int & 0xFF, (ip_int >> 8) & 0xFF,
                        (ip_int >> 16) & 0xFF, (ip_int >> 24) & 0xFF)
        except Exception as exc:
            self._emit("wifi_info", exc)
        info["connected"] = bool(info.get("ssid"))
        saved = self.wifi_saved()
        if saved:
            info["saved"] = saved
        return info

    def _root_cat(self, path):
        commands = [
            ["su", "-c", "cat '%s'" % path],
            ["su", "-c", "cat %s" % path],
        ]
        for command in commands:
            try:
                proc = subprocess.run(command, capture_output=True, timeout=8)
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout.decode("utf-8", errors="replace")
            except Exception:
                continue
        try:
            with os.popen("su -c 'cat %s' 2>/dev/null" % path) as handle:
                data = handle.read()
            if data and "No such file" not in data:
                return data
        except Exception:
            pass
        return ""

    def _read_wifi_config(self):
        for path in WIFI_CONFIG_PATHS:
            text = self._root_cat(path)
            if text and ("<Network>" in text or "network={" in text
                         or "network = {" in text):
                return text, path
        return "", ""

    def wifi_password(self, ssid):
        text, path = self._read_wifi_config()
        if not text:
            return None, ""
        try:
            if path.endswith(".xml"):
                mapping = parse_wifi_config(text)
            else:
                mapping = parse_wpa_supplicant(text)
        except Exception:
            return None, ""
        password = find_password(mapping, ssid)
        if password:
            return password, "root"
        return None, ""

    # ------------------------------------------------------------------
    #  Права
    # ------------------------------------------------------------------
    def has_permission(self, name):
        try:
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) < 23:
                return True
            full = name if name.startswith("android.permission.") else "android.permission." + name
            return int(self._ctx.checkSelfPermission(full)) == 0
        except Exception:
            return False

    def request_permissions(self, names, callback):
        try:
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) < 23:
                callback(True)
                return Res(True, "")
            full = [n if n.startswith("android.permission.") else "android.permission." + n
                    for n in names]
            if all(self.has_permission(n) for n in names):
                callback(True)
                return Res(True, "")

            self._run_on_ui(lambda: self._ctx.requestPermissions(full, REQ_PERMISSIONS))

            def wait():
                deadline = time.time() + 120
                while time.time() < deadline:
                    if all(self.has_permission(n) for n in names):
                        callback(True)
                        return
                    time.sleep(0.25)
                callback(False)

            threading.Thread(target=wait, daemon=True).start()
            return Res(True, "")
        except Exception as exc:
            try:
                callback(False)
            except Exception:
                pass
            return Res(False, str(exc))
