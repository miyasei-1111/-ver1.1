# -*- coding: utf-8 -*-
"""設定・パス・定数。他のモジュールに依存しない(最下層)。Qt も使わない。"""

import json
import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False):          # PyInstaller でexe化した場合
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent   # mascot/ の1つ上 = main.py と assets/ のある場所


ASSET_DIR = BASE_DIR / "assets"


VOICE_DIR = ASSET_DIR / "voices"


CONFIG_PATH = BASE_DIR / "config.json"


LOG_PATH = BASE_DIR / "mascot.log"


DEBUG = bool(os.environ.get("NYN_DEBUG"))


# 音声イベント名(= assets/voices/<イベント名>/ フォルダ)
VOICE_EVENTS = {
    "start": "アプリ実行時",
    "exit": "アプリ終了時",
    "click": "左クリック時",
    "grab": "掴まれた時",
    "wall": "壁に激突時",
    "land": "着地時",
    "sleep": "睡眠開始時",
    "resize": "サイズ変更時",
}


AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}


# モーション(名前: 表示名)と継続時間(秒)
MOTIONS = {
    "none": "なし",
    "squash": "つぶれる",
    "hop": "ジャンプ",
    "spin": "回転",
    "shake": "震える",
    "wobble": "ゆらゆら",
    "random": "ランダム",
}


MOTION_DURATION = {"squash": 0.35, "hop": 0.45, "spin": 0.7, "shake": 0.5, "wobble": 0.7}


# 素材が「左向き」で作られている状態名。ここに入れた状態は左右の反転が逆になる
# (例: {"walk"} … 歩行素材が左向き / 空にすると全て右向き素材として扱う)
FLIP_INVERTED = {"walk"}


DEFAULTS = {
    "scale": 100,             # 表示サイズ(%)
    "walk_speed": 80,         # 歩く速さ(px/秒)
    "volume": 80,             # 音量(%)
    "sleep_sec": 45,          # 何秒操作しないと眠るか
    "always_on_top": False,   # 常に最前面に表示
    "anim_speed": 100,        # アニメーション速度(%)
    "react_sec": 2,           # クリック反応の表示時間(秒)
    "click_motion": "hop",    # クリック時のモーション
    "land_motion": "squash",  # 着地時のモーション
    "cache_core_mb": 160,     # 圧縮画像キャッシュの上限(通常アニメ用, MB)  ※設定画面には出ません
    "cache_bulk_mb": 96,      # 同上(睡眠など長いアニメ用, MB)
}


MB = 1024 * 1024


STATES = ["idle", "walk", "sleep", "grabbed", "react", "land", "getup", "start", "exit"]


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def ensure_dirs():
    for st in STATES:
        (ASSET_DIR / st).mkdir(parents=True, exist_ok=True)
    for ev in VOICE_EVENTS:
        (VOICE_DIR / ev).mkdir(parents=True, exist_ok=True)
