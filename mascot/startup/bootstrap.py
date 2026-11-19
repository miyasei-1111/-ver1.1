# -*- coding: utf-8 -*-
"""起動の進行役。読み込み画面 → 素材の優先読み込み → 音声初期化 → キャラクター表示。依存: 下位の全モジュール(ここが組み立て役)。"""

import time

from PySide6.QtCore import Qt, QObject, QTimer
from PySide6.QtWidgets import QApplication

from mascot.animation.sprites import Sprites
from mascot.audio.voice import VoicePlayer
from mascot.diagnostics import LOG
from mascot.imaging.store import StoreSignals
from mascot.startup.loading_window import LoadingWindow
from mascot.system.memory import process_memory_mb
from mascot.ui.pet import Pet


STARTUP_TIMEOUT_SEC = 20.0   # 起動読み込みの最大待ち時間(超えたら素材が揃わなくても表示する)


LOADING_MIN_SEC = 0.5        # 「読み込み中」画面を最低これだけ表示する(一瞬で消えないように)


class Bootstrap(QObject):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.t0 = time.monotonic()
        self.signals = StoreSignals()
        self.loading = LoadingWindow()
        self.sprites = None
        self.voice = None
        self.pet = None
        self._finished = False
        self._aborted = False
        self._down = False
        self._finish_timer = None
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._check_ready)

    def start(self):
        self.loading.abort_requested.connect(self.abort)
        self.signals.progress.connect(self._on_progress, type=Qt.ConnectionType.QueuedConnection)
        self.loading.show()
        self.loading.raise_()
        # 画面が描画されてから重い処理に入る(イベントループに一度戻す)
        QTimer.singleShot(30, self._step_sprites)

    def _step_sprites(self):
        if self._aborted:
            return
        try:
            self.sprites = Sprites(self.cfg["scale"], self.cfg, signals=self.signals)
        except Exception:
            LOG.exception("素材の準備に失敗しました。簡易キャラで続行します")
            self.sprites = Sprites(self.cfg["scale"], self.cfg, use_assets=False,
                                   signals=self.signals)
        self.sprites.begin_startup()           # 読み込みスレッドが動き出す
        d, t = self.sprites.store.startup_state()
        self.loading.set_progress(d, t)
        QTimer.singleShot(0, self._step_voice)

    def _step_voice(self):
        if self._aborted:
            return
        self.voice = VoicePlayer(self.cfg["volume"])   # 読み込みスレッドと並行して初期化
        self._poll.start()
        self._check_ready()

    def _on_progress(self, done, total):
        if not self._finished and not self._aborted:
            self.loading.set_progress(done, total)
            self._check_ready()

    def _ready(self):
        if self.sprites is None or self.voice is None:
            return False
        done, total = self.sprites.store.startup_state()
        return done >= total

    def _check_ready(self):
        if self._finished or self._aborted or self.sprites is None or self.voice is None:
            return
        elapsed = time.monotonic() - self.t0
        timed_out = elapsed > STARTUP_TIMEOUT_SEC
        if not (self._ready() or timed_out):
            return
        if timed_out and not self._ready():
            LOG.warning("起動の読み込みが %.0f 秒を超えたため、揃っていない分は後から読み込みます",
                        STARTUP_TIMEOUT_SEC)
        remain = LOADING_MIN_SEC - elapsed      # 読み込み画面が一瞬で消えないように
        if remain > 0:
            if self._finish_timer is None:
                self._finish_timer = QTimer(self)
                self._finish_timer.setSingleShot(True)
                self._finish_timer.timeout.connect(self._finish)
                self._finish_timer.start(int(remain * 1000) + 10)
            return
        self._finish()

    def _finish(self):
        if self._finished or self._aborted:
            return
        self._finished = True
        self._poll.stop()
        try:
            self.pet = Pet(self.cfg, self.sprites, self.voice)
            self.pet.show()
            self.pet.play_start()
        except Exception:
            LOG.exception("キャラクターの表示に失敗しました")
            QApplication.quit()
            return
        LOG.info("起動完了: %.2f 秒 / メモリ %.0f MB / %s", time.monotonic() - self.t0,
                 process_memory_mb(), self.sprites.store.stats())
        # キャラクターが表示された「後」で読み込み画面を閉じる(空白の時間を作らない)
        self.loading.raise_()
        QTimer.singleShot(250, self.loading.close)

    def abort(self):
        """読み込み中の終了(読み込み画面の右クリック / Esc)。"""
        if self._aborted or self._finished:
            return
        self._aborted = True
        self._poll.stop()
        self.shutdown()
        self.loading.close()
        QTimer.singleShot(0, QApplication.quit)

    def shutdown(self):
        """読み込みスレッドと音声を止める(何度呼んでも安全)。"""
        if self._down:
            return
        self._down = True
        self._poll.stop()
        try:
            if self.sprites is not None:
                self.sprites.shutdown()
            if self.voice is not None:
                self.voice.stop()
        except Exception:
            LOG.exception("終了処理でエラー")
