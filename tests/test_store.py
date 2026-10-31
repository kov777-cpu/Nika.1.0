# -*- coding: utf-8 -*-
"""Память Nika: сохранение, восстановление, повреждённый файл."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from nika.store import Store  # noqa: E402
from tmp_utils import temp_dir  # noqa: E402


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = temp_dir("nika_store_")
        self.path = os.path.join(self.folder, "nika.json")

    def test_roundtrip(self):
        store = Store(self.path)
        store.fact("name", "Егор")
        store.add_like("пиццу")
        store.add_note("купить хлеб")
        store.set_pref("voice", False)
        store.save()

        again = Store(self.path)
        self.assertEqual(again.fact("name"), "Егор")
        self.assertIn("пиццу", again.get("facts")["likes"])
        self.assertEqual(again.get("notes")[0]["text"], "купить хлеб")
        self.assertFalse(again.pref("voice"))

    def test_broken_file(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{это не json")
        store = Store(self.path)
        self.assertEqual(store.get("facts"), {})
        self.assertTrue(os.path.exists(self.path + ".broken"))

    def test_defaults_filled(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"facts": {"name": "Аня"}}, handle, ensure_ascii=False)
        store = Store(self.path)
        self.assertEqual(store.fact("name"), "Аня")
        self.assertIn("voice", store.get("prefs"))

    def test_reminders(self):
        store = Store(self.path)
        store.add_reminder(1000, "позвонить")
        self.assertEqual(len(store.due_reminders(now=999)), 0)
        due = store.due_reminders(now=1001)
        self.assertEqual(len(due), 1)
        store.mark_reminder_done(due[0])
        self.assertEqual(len(store.due_reminders(now=1002)), 0)

    def test_notes_ids(self):
        store = Store(self.path)
        self.assertEqual(store.add_note("a")["id"], 1)
        self.assertEqual(store.add_note("b")["id"], 2)
        self.assertEqual(store.drop_note(1)["text"], "a")
        self.assertIsNone(store.drop_note(99))


if __name__ == "__main__":
    unittest.main(verbosity=2)
