# -*- coding: utf-8 -*-
"""Временные папки для тестов внутри проекта.

Системный %TEMP% иногда бывает недоступен на запись (песочница, чужой профиль),
а tempfile.mkdtemp на Python 3.14 создаёт папку с приватным ACL, в которую
здесь нельзя писать. Поэтому делаем папку сами и убираем при выходе.
"""

import atexit
import os
import shutil
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
TMP_ROOT = os.path.join(HERE, "_tmp")
_DIRS = []


def temp_dir(prefix="nika_"):
    os.makedirs(TMP_ROOT, exist_ok=True)
    path = os.path.join(TMP_ROOT, prefix + uuid.uuid4().hex[:8])
    os.makedirs(path, exist_ok=True)
    _DIRS.append(path)
    return path


def _cleanup():
    # OneDrive/антивирус могут держать файл пару секунд — пробуем ещё раз
    for path in _DIRS:
        for _attempt in range(3):
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.exists(path):
                break
            time.sleep(0.15)


atexit.register(_cleanup)
