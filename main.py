# -*- coding: utf-8 -*-
"""Запуск Nika на компьютере (BeeWare Toga).

    py -3.12 -m pip install -r requirements-desktop.txt
    python main.py

На телефоне приложение собирается через Briefcase и стартует из `nika/__main__.py`.
"""

import sys


def run():
    try:
        from nika.app import main
    except ImportError as exc:
        print("Для запуска на компьютере нужен BeeWare Toga (Python 3.10-3.12):")
        print("    py -3.12 -m pip install -r requirements-desktop.txt")
        print("    python main.py")
        print("Подробности:", exc)
        return 1

    main().main_loop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
