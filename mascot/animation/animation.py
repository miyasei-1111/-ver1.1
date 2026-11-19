# -*- coding: utf-8 -*-
"""連番アニメ1セット。FrameStore に問い合わせて、いま表示するコマを返す。依存: imaging, animation.placeholder。"""

import math

from PySide6.QtCore import Qt

from mascot.animation.placeholder import placeholder_frames
from mascot.imaging.store import MIN_AHEAD


class Animation:
    """
    PNG連番1セット。loop=False の場合は最後のコマで止まる。
    画像そのものは持たず、FrameStore に「何番のコマが欲しいか」を問い合わせる。
    まだ用意できていないコマは idle の絵で代用して表示する(止まらない)。
    """

    def __init__(self, name, fps, loop, store=None, files=None, raw=None, base=None):
        self.name = name
        self.fps = fps
        self.loop = loop
        self.store = store
        self.files = files or []      # 連番ファイルのパス
        self.raw = raw or []          # 簡易キャラ(プログラム描画)用
        self.base = base              # 他のアニメの絵を共用する場合(idle代用)
        self.fallback = base is not None
        self.idle = None              # コマが未用意のときに代わりに表示する idle
        self.usable = False           # 連番を FrameStore から読める状態か
        self.target = (1, 1)
        self._ph = None               # 簡易キャラの縮小済みコマ
        self._ph_flip = None
        if self.files and store is not None:
            self.usable = store.register(name, self.files).usable

    def _src(self):
        return self.base if self.base is not None else self

    def set_target(self, w, h):
        self.target = (w, h)
        self._ph = None               # 古い画像を捨てる
        self._ph_flip = None
        if self.base is None and not self.usable:
            self._build_placeholder()

    def ref_size(self):
        """連番の元画像サイズ(取得できなければ None)。"""
        if self.usable:
            s = self.store.sources[self.name]
            return s.w0, s.h0
        return None

    def _build_placeholder(self):
        w, h = self.target
        raw = self.raw or placeholder_frames("idle")
        f = min(w / max(pm.width() for pm in raw), h / max(pm.height() for pm in raw))
        self._ph = [pm.scaled(max(1, round(pm.width() * f)), max(1, round(pm.height() * f)),
                              Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation) for pm in raw]
        self._ph_flip = None

    def prefetch_all(self, front=True):
        """全コマを先に読んでおくよう予約する(待たない)。終了アニメ用。"""
        s = self._src()
        if s.usable:
            self.store.warm([(s.name, i) for i in range(len(s.files))], front=front)

    def count(self):
        s = self._src()
        return max(1, len(s.files) or len(s.raw))

    def duration(self):
        return self.count() / self.fps

    def frame(self, elapsed, flip=False, speed=1.0, block=False, _main=True):
        """いま表示するコマ(QImage)を返す。用意できていなければ idle 等で代用する。"""
        s = self._src()
        if s.usable:
            n = len(s.files)
            i = max(0, int(elapsed * self.fps))
            i = i % n if self.loop else min(i, n - 1)
            ahead = None
            if _main:                 # 先読みは「いま再生中のアニメ」だけが予約する
                want = int(math.ceil(self.fps * max(0.25, speed) * 0.5))
                ahead = max(MIN_AHEAD, min(self.store.max_ahead, want))
            img = self.store.get(s.name, i, flip, ahead=ahead, loop=self.loop, block=block,
                                 fps=self.fps * max(0.25, speed))
            if img is None and _main and self.idle is not None and s is not self.idle:
                img = self.idle.frame(elapsed, flip, speed, False, _main=False)
            if img is None and _main:
                img = self.store.last_image()
            return img
        # 簡易キャラ(素材なし/読めない場合)
        if s._ph is None:
            s._build_placeholder()
        ph = s._ph
        n = len(ph)
        i = max(0, int(elapsed * self.fps))
        i = i % n if self.loop else min(i, n - 1)
        if flip:
            if s._ph_flip is None:
                s._ph_flip = [self.store.be.mirror(pm) for pm in ph]
            return s._ph_flip[i]
        return ph[i]
