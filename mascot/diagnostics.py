# -*- coding: utf-8 -*-
"""ログの設定。依存: config のみ。"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from mascot.config import DEBUG, LOG_PATH


LOG = logging.getLogger("mascot")


def setup_logging():
    """ログを mascot.log に出す(書き込めない場所でも落ちない)。"""
    if LOG.handlers:
        return
    LOG.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    LOG.propagate = False
    try:
        h = RotatingFileHandler(LOG_PATH, maxBytes=256 * 1024, backupCount=1, encoding="utf-8")
    except Exception:
        h = logging.NullHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s %(message)s"))
    LOG.addHandler(h)
    if DEBUG and sys.stderr:
        LOG.addHandler(logging.StreamHandler(sys.stderr))
