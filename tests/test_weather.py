# -*- coding: utf-8 -*-
"""Тесты погоды на подменённом HTTP."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nika.weather import Weather  # noqa: E402

GEO = {"results": [{"name": "Москва", "country": "Россия",
                    "latitude": 55.75, "longitude": 37.62}]}
FORECAST = {
    "current": {"temperature_2m": -7.4, "apparent_temperature": -12.0,
                "relative_humidity_2m": 80, "weather_code": 71,
                "wind_speed_10m": 11.5, "is_day": 0, "precipitation": 0.4},
    "daily": {"temperature_2m_max": [-3.0, -5.0], "temperature_2m_min": [-11.0, -13.0],
              "weather_code": [71, 3]},
}


class WeatherTests(unittest.TestCase):
    def test_report_and_text(self):
        calls = []

        def http(url):
            calls.append(url)
            return json.dumps(GEO if "geocoding" in url else FORECAST)

        weather = Weather(http_get=http)
        data = weather.report("Москва")
        self.assertIsNotNone(data)
        self.assertEqual(data["city"], "Москва")
        text = weather.format_report(data)
        self.assertIn("Москва", text)
        self.assertIn("-7", text)
        self.assertIn("снег", text.lower())
        # второй раз город берётся из кеша
        weather.report("Москва")
        self.assertEqual(len([c for c in calls if "geocoding" in c]), 1)

    def test_city_not_found(self):
        def http(url):
            return json.dumps({"results": []}) if "geocoding" in url else "{}"

        weather = Weather(http_get=http)
        self.assertIsNone(weather.report("Атлантида"))

    def test_network_error(self):
        def http(url):
            raise OSError("нет сети")

        weather = Weather(http_get=http)
        self.assertIsNone(weather.report("Москва"))

    def test_empty_report(self):
        self.assertEqual(Weather().format_report(None), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
