# -*- coding: utf-8 -*-
"""assets/<状態>/ の連番を束ねて Animation を作る。サイズ変更・起動時の優先読み込みを仲介。依存: imaging, animation, config, diagnostics。"""

import json
import re
from pathlib import Path

from mascot.animation.animation import Animation
from mascot.animation.placeholder import placeholder_frames
from mascot.config import STATES as ALL_STATES, ASSET_DIR, DEFAULTS
from mascot.diagnostics import LOG
from mascot.imaging.backend import QtImageBackend
from mascot.imaging.store import FrameStore


STARTUP_IDLE_FRAMES = 12 # 起動時に必ず読む idle のコマ数


SLEEP_HEAD_FRAMES = 48   # 睡眠アニメは先頭だけ背景で読む(残りは再生時に読む)


def natural_key(path):
    """001.png, 2.png, 10.png ... を数字の大きさ順に並べるためのキー"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.stem)]


class Sprites:
    """
    assets/<状態>/ 内の PNG 連番を管理する(001.png, 002.png ...)。
    すべてのコマは同じキャンバスサイズで作ってください(基準は idle の1コマ目)。
    起動時に読むのは idle の先頭と start だけ。残りは背景で少しずつ読む。
    """
    STATES = list(ALL_STATES)
    LOOP = {"idle": True, "walk": True, "sleep": True, "grabbed": True,
            "react": False, "land": False, "getup": False,
            "start": False, "exit": False}
    DEFAULT_FPS = {"idle": 24, "walk": 24, "sleep": 24, "grabbed": 24, "react": 24, "land": 24,
                   "getup": 24, "start": 24, "exit": 24}
    BASE_H = 160   # scale=100% のときの高さ(px)
    # 起動後に背景で圧縮層へ入れておく順番(idle の残りと sleep の先頭は最後)
    WARM_ORDER = ["walk", "grabbed", "react", "land", "getup", "exit"]

    def __init__(self, scale, cfg=None, backend=None, use_assets=True, signals=None, asset_dir=None):
        cfg = cfg or DEFAULTS
        self.asset_dir = Path(asset_dir) if asset_dir else ASSET_DIR
        self.signals = signals
        self.be = backend or QtImageBackend()
        self.store = FrameStore(self.be, core_mb=cfg.get("cache_core_mb", 160),
                                bulk_mb=cfg.get("cache_bulk_mb", 96), signals=signals)
        fps = dict(self.DEFAULT_FPS)
        try:   # assets/animation.json で {"walk": 12} のようにfpsを上書き可能
            for k, v in json.loads((self.asset_dir / "animation.json").read_text("utf-8")).items():
                if k in fps and float(v) > 0:
                    fps[k] = float(v)
        except Exception:
            pass

        files = {s: (self._find_files(s) if use_assets else []) for s in self.STATES}
        has_idle = bool(files["idle"])

        self.anims = {}
        if has_idle:
            idle = Animation("idle", fps["idle"], True, store=self.store, files=files["idle"])
        else:
            idle = Animation("idle", 5.0, True, store=self.store, raw=placeholder_frames("idle"))
        self.anims["idle"] = idle
        for s in self.STATES[1:]:
            if files[s]:
                self.anims[s] = Animation(s, fps[s], self.LOOP[s], store=self.store,
                                          files=files[s])
            elif has_idle:                       # 素材が無い状態は idle で代用(絵は共用)
                self.anims[s] = Animation(s, fps["idle"], self.LOOP[s], store=self.store,
                                          base=idle)
            else:
                self.anims[s] = Animation(s, 5.0, self.LOOP[s], store=self.store,
                                          raw=placeholder_frames(s))
            self.anims[s].idle = idle
        self.W = self.H = 0
        self._apply_scale(scale)

    def _find_files(self, state):
        files = []
        try:
            d = self.asset_dir / state
            if d.is_dir():
                files = sorted(d.glob("*.png"), key=natural_key)
            if not files and (self.asset_dir / f"{state}.png").exists():
                files = [self.asset_dir / f"{state}.png"]   # 単体PNGも1コマとして許可
        except OSError:
            LOG.exception("素材フォルダを読めません: %s", state)
        return files

    def _apply_scale(self, scale):
        """表示サイズを決めて、古いサイズのキャッシュを捨てる(画像は読まない)。"""
        ref = self.anims["idle"].ref_size()
        ref_w, ref_h = ref if ref else (200, 200)
        self.H = max(16, round(self.BASE_H * scale / 100))
        self.W = max(16, round(ref_w * self.H / ref_h))
        self.store.set_target(self.W, self.H)
        for a in self.anims.values():
            a.set_target(self.W, self.H)

    def set_scale(self, scale):
        """サイズ変更。待たずに戻る。必要なコマは再生しながら背景で作り直す。"""
        self._apply_scale(scale)
        self.store.start()
        self.schedule_warm()

    def startup_items(self):
        """表示を始めるのに必要なコマ: idle の先頭と、起動アニメ(start)全部。"""
        items = []
        idle, start = self.anims["idle"], self.anims["start"]
        if idle.usable:
            items += [("idle", i) for i in range(min(STARTUP_IDLE_FRAMES, len(idle.files)))]
        if start.usable:
            items += [("start", i) for i in range(len(start.files))]
        return items

    def schedule_warm(self):
        items = []
        for name in self.WARM_ORDER:
            a = self.anims[name]
            if a.usable:
                items += [(name, i) for i in range(len(a.files))]
        idle, sleep = self.anims["idle"], self.anims["sleep"]
        if idle.usable:
            items += [("idle", i) for i in range(STARTUP_IDLE_FRAMES, len(idle.files))]
        if sleep.usable:
            items += [("sleep", i) for i in range(min(SLEEP_HEAD_FRAMES, len(sleep.files)))]
        self.store.warm(items)

    def begin_startup(self):
        """起動に必須のコマを最優先で、続けて背景ウォームアップを開始する。"""
        self.store.begin_startup(self.startup_items())
        self.store.start()
        self.schedule_warm()

    def shutdown(self):
        self.store.shutdown()
