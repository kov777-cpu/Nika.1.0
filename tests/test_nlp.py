# -*- coding: utf-8 -*-
"""Тесты разбора речи. Запуск: python tests/test_nlp.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nika import nlp  # noqa: E402


class TestDuration(unittest.TestCase):
    def test_digits(self):
        self.assertEqual(nlp.parse_duration("10 минут"), 600)
        self.assertEqual(nlp.parse_duration("засеки 5 мин"), 300)
        self.assertEqual(nlp.parse_duration("2 часа"), 7200)
        self.assertEqual(nlp.parse_duration("30 секунд"), 30)
        self.assertEqual(nlp.parse_duration("1 ч 30 мин"), 5400)

    def test_words(self):
        self.assertEqual(nlp.parse_duration("двадцать пять минут"), 1500)
        self.assertEqual(nlp.parse_duration("через десять минут"), 600)
        self.assertEqual(nlp.parse_duration("два часа"), 7200)

    def test_fixed(self):
        self.assertEqual(nlp.parse_duration("полчаса"), 1800)
        self.assertEqual(nlp.parse_duration("полтора часа"), 5400)
        self.assertEqual(nlp.parse_duration("четверть часа"), 900)
        self.assertEqual(nlp.parse_duration("минуту"), 60)

    def test_none(self):
        self.assertIsNone(nlp.parse_duration("просто поболтать"))
        self.assertIsNone(nlp.parse_duration(""))


class TestClock(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(nlp.parse_clock("в 7:30"), (7, 30))
        self.assertEqual(nlp.parse_clock("на 18.45"), (18, 45))

    def test_hours_only(self):
        self.assertEqual(nlp.parse_clock("в 7"), (7, 0))

    def test_day_parts(self):
        self.assertEqual(nlp.parse_clock("в 7 вечера"), (19, 0))
        self.assertEqual(nlp.parse_clock("в 12 ночи"), (0, 0))
        self.assertEqual(nlp.parse_clock("в полдень"), (12, 0))
        self.assertEqual(nlp.parse_clock("в полночь"), (0, 0))

    def test_none(self):
        self.assertIsNone(nlp.parse_clock("без времени"))


class TestPhone(unittest.TestCase):
    def test_eight(self):
        self.assertEqual(nlp.normalize_phone("8 999 123-45-67"), "+79991234567")

    def test_ten(self):
        self.assertEqual(nlp.normalize_phone("9991234567"), "+79991234567")

    def test_plus(self):
        self.assertEqual(nlp.normalize_phone("+7 (999) 123-45-67"), "+79991234567")

    def test_short(self):
        self.assertEqual(nlp.normalize_phone("103"), "+103")


class TestUrl(unittest.TestCase):
    def test_yes(self):
        self.assertTrue(nlp.looks_like_url("youtube.com"))
        self.assertTrue(nlp.looks_like_url("https://ya.ru/maps"))
        self.assertTrue(nlp.looks_like_url("www.пример.рф/путь"))

    def test_no(self):
        self.assertFalse(nlp.looks_like_url("ютуб"))
        self.assertFalse(nlp.looks_like_url("открой ютуб"))
        self.assertFalse(nlp.looks_like_url(""))


class TestTypos(unittest.TestCase):
    def test_verb(self):
        self.assertTrue(nlp.fix_typos("аткрой ютуб").startswith("открой"))
        self.assertTrue(nlp.fix_typos("пазвони маме").startswith("позвони"))

    def test_no_change(self):
        self.assertEqual(nlp.fix_typos("открой ютуб"), "открой ютуб")
        self.assertEqual(nlp.fix_typos("мама"), "мама")


class TestStems(unittest.TestCase):
    def test_contact_cases(self):
        self.assertEqual(nlp.stem_ru("маме"), nlp.stem_ru("мама"))
        self.assertEqual(nlp.stem_ru("папу"), nlp.stem_ru("папа"))
        self.assertEqual(nlp.stem_ru("егору"), nlp.stem_ru("егор"))


class TestSplit(unittest.TestCase):
    def test_two_commands(self):
        parts = nlp.split_multi("открой ютуб и позвони маме")
        self.assertEqual(len(parts), 2)

    def test_no_split_chat(self):
        parts = nlp.split_multi("мне грустно и я не знаю что делать")
        self.assertEqual(len(parts), 1)

    def test_semicolon(self):
        parts = nlp.split_multi("засеки 5 минут; включи музыку")
        self.assertEqual(len(parts), 2)


class TestSpeech(unittest.TestCase):
    def test_clean(self):
        text = nlp.clean_for_speech("готово)\n• позвони маме https://x.ru")
        self.assertNotIn("•", text)
        self.assertNotIn("https://", text)

    def test_human_duration(self):
        self.assertEqual(nlp.human_duration(600), "10 мин")
        self.assertEqual(nlp.human_duration(5400), "1 ч 30 мин")


if __name__ == "__main__":
    unittest.main(verbosity=2)
