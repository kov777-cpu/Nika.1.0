# -*- coding: utf-8 -*-
"""Фейковый «телефон» для тестов: записывает действия вместо реальных звонков."""

import time

from nika.bridge.base import Bridge, Contact, Res


class FakeBridge(Bridge):
    is_android = True
    platform_name = "android"
    can_call = True
    can_contacts = True
    can_apps = True
    can_voice = True
    can_notify = True
    can_wifi_passwords = True

    def __init__(self, installed=None, contacts=None, wifi=None, saved=None,
                 passwords=None, battery=None, permissions=True, torch_ok=True):
        super().__init__()
        self.installed = dict(installed or {
            "com.google.android.youtube": "YouTube",
            "org.telegram.messenger": "Telegram",
            "com.vkontakte.android": "VK",
            "com.android.settings": "Настройки",
        })
        self._contacts = list(contacts or [
            Contact("Мама", "+79990001122", "8 999 000-11-22"),
            Contact("Папа", "+79990003344", "8 999 000-33-44"),
            Contact("Мама работа", "+79995556677", "8 999 555-66-77"),
            Contact("Егор", "+79997778899", "8 999 777-88-99"),
        ])
        self.wifi = wifi if wifi is not None else {
            "connected": True, "ssid": "Home_5G", "rssi": -52,
            "ip": "192.168.1.42", "saved": ["Home_5G", "Office", "Cafe"],
        }
        self.saved = saved if saved is not None else ["Home_5G", "Office", "Cafe"]
        self.passwords = passwords if passwords is not None else {"Home_5G": "secret123"}
        self._battery = battery if battery is not None else {"percent": 42, "charging": False}
        self.permissions = permissions
        self.torch_ok = torch_ok

        # журнал действий
        self.opened_urls = []
        self.launched = []
        self.dialed = []
        self.sms = []
        self.media = []
        self.alarms = []
        self.volumes = []
        self.torch_states = []
        self.spoken = []
        self.notified = []
        self.permission_requests = []

    # ---------- права ----------
    def has_permission(self, name):
        return bool(self.permissions)

    def request_permissions(self, names, callback):
        self.permission_requests.append(list(names))
        callback(bool(self.permissions))
        return Res(True, "")

    # ---------- приложения ----------
    def app_installed(self, package):
        return package in self.installed

    def installed_apps(self):
        return [(label, package) for package, label in self.installed.items()]

    def launch_package(self, package):
        if package not in self.installed:
            return Res(False, "не установлено")
        self.launched.append(package)
        return Res(True)

    def open_play_store(self, package):
        self.opened_urls.append("market://details?id=" + package)
        return Res(True)

    def open_url(self, url):
        self.opened_urls.append(url)
        return Res(True, "", url)

    # ---------- звонки ----------
    def contacts(self):
        return list(self._contacts)

    def dial(self, number, direct=False):
        self.dialed.append((number, direct))
        return Res(True, "звоню" if direct else "набираю")

    def send_sms(self, number, text):
        self.sms.append((number, text))
        return Res(True, "")

    # ---------- медиа ----------
    def play_media(self, query="", video=False):
        self.media.append((query, video))
        if query:
            return Res(True, "", {"source": "local", "title": query})
        return Res(True, "", {"source": "youtube"})

    # ---------- система ----------
    def set_alarm(self, hour, minute, label=""):
        self.alarms.append((hour, minute, label))
        return Res(True, "")

    def torch(self, on):
        if not self.torch_ok:
            return Res(False, "не нашла вспышку.")
        self.torch_states.append(bool(on))
        return Res(True, "")

    def battery(self):
        return dict(self._battery)

    def volume(self, direction):
        self.volumes.append(direction)
        return Res(True, "50%" if direction != "mute" else "0%")

    def open_settings(self, page=""):
        self.opened_urls.append("settings:" + (page or "main"))
        return Res(True, "")

    def notify(self, title, text):
        self.notified.append((title, text))
        return Res(True, "")

    def speak(self, text):
        self.spoken.append(text)
        return Res(True, "")

    # ---------- wi-fi ----------
    def wifi_info(self):
        return dict(self.wifi)

    def wifi_saved(self):
        return list(self.saved)

    def wifi_password(self, ssid):
        for name, password in self.passwords.items():
            if name.lower() == (ssid or "").lower():
                return password, "root"
        return None, ""
