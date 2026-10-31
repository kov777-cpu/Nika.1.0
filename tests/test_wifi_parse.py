# -*- coding: utf-8 -*-
"""Тесты разбора wi-fi конфигов Android."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nika.wifi_parse import (  # noqa: E402
    find_password,
    parse_wifi_config,
    parse_wpa_supplicant,
)

XML_SAMPLE = """<?xml version='1.0'?>
<WifiConfigStoreData>
  <NetworkList>
    <Network>
      <string name="ConfigKey">&quot;Home_5G&quot;</string>
      <string name="SSID">&quot;Home_5G&quot;</string>
      <string name="PreSharedKey">&quot;secret123&quot;</string>
    </Network>
    <Network>
      <string name="SSID">&quot;Office 2.4&quot;</string>
      <string name="PreSharedKey">&quot;0x6f666669636570617373&quot;</string>
    </Network>
    <Network>
      <string name="SSID">&quot;FreeCafe&quot;</string>
      <boolean name="nm_config_key" value="false" />
    </Network>
  </NetworkList>
</WifiConfigStoreData>
"""

WPA_SAMPLE = """
network={
    ssid="Дом"
    psk="домовой_пароль"
    key_mgmt=WPA-PSK
}

network={
    ssid="Guest"
    key_mgmt=NONE
}
"""


class XmlTests(unittest.TestCase):
    def test_parsed(self):
        data = parse_wifi_config(XML_SAMPLE)
        self.assertEqual(data["Home_5G"], "secret123")
        self.assertEqual(data["Office 2.4"], "officepass")
        self.assertEqual(data["FreeCafe"], "")

    def test_find_case_insensitive(self):
        data = parse_wifi_config(XML_SAMPLE)
        self.assertEqual(find_password(data, "home_5g"), "secret123")
        self.assertEqual(find_password(data, '"Home_5G"'), "secret123")
        self.assertIsNone(find_password(data, "FreeCafe"))

    def test_empty(self):
        self.assertEqual(parse_wifi_config(""), {})
        self.assertEqual(parse_wifi_config(None), {})


class WpaTests(unittest.TestCase):
    def test_parsed(self):
        data = parse_wpa_supplicant(WPA_SAMPLE)
        self.assertEqual(data["Дом"], "домовой_пароль")
        self.assertEqual(data["Guest"], "")

    def test_hex_psk(self):
        text = 'network={\n ssid="hexnet"\n psk=0123456789abcdef0123456789abcdef\n}'
        data = parse_wpa_supplicant(text)
        self.assertEqual(data["hexnet"], "0123456789abcdef0123456789abcdef")


if __name__ == "__main__":
    unittest.main(verbosity=2)
