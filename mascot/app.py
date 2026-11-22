# -*- coding: utf-8 -*-
"""アプリのエントリポイント(組み立て)。run() が QApplication を作って起動する。"""

import sys

from PySide6.QtWidgets import QApplication

from mascot.config import ensure_dirs, load_config
from mascot.diagnostics import LOG, setup_logging
from mascot.startup.bootstrap import Bootstrap


def run():
    """アプリを起動する(main.py / python -m mascot から呼ばれる)。"""
    setup_logging()
    LOG.info("起動します (Python %s)", sys.version.split()[0])
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        ensure_dirs()
    except OSError:
        LOG.exception("素材フォルダを作成できませんでした")
    boot = Bootstrap(load_config())
    app.aboutToQuit.connect(boot.shutdown)
    boot.start()
    code = app.exec()
    boot.shutdown()
    sys.exit(code)
