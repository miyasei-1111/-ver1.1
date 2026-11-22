# -*- coding: utf-8 -*-
"""音声(語録)の再生。依存: config, diagnostics。アニメーションや画像には依存しない。"""

import random
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from mascot.config import AUDIO_EXTS, VOICE_DIR
from mascot.diagnostics import LOG


class VoicePlayer:
    def __init__(self, volume, voice_dir=None):
        self.voice_dir = Path(voice_dir) if voice_dir else VOICE_DIR
        self.audio = None
        self.player = None
        self._last = {}
        self._bag = {}      # イベントごとの「まだ再生していないファイル」
        self._prev = {}     # イベントごとの直前に再生したファイル
        try:
            self.audio = QAudioOutput()
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.audio)
            self.player.errorOccurred.connect(self._on_error)
        except Exception:
            # 音声デバイスが無い等。音声なしで動作を続ける
            LOG.exception("音声の初期化に失敗しました(音声なしで続行します)")
            self.player = None
        self.set_volume(volume)

    def _on_error(self, error, message=""):
        LOG.warning("音声の再生エラー: %s", message)

    def set_volume(self, v):
        if self.audio is not None:
            self.audio.setVolume(max(0, min(100, v)) / 100.0)

    def _files(self, event):
        try:
            d = self.voice_dir / event
            if not d.is_dir():
                return []
            return sorted(p for p in d.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        except OSError:
            return []

    def _pick(self, event, files):
        """フォルダ内の全ファイルを1回ずつランダムな順で再生し、一巡したらシャッフルし直す。
        同じ音声が2回連続で鳴らないようにする(ファイルが2つ以上ある場合)。"""
        bag = [f for f in self._bag.get(event, []) if f in files]
        if not bag:
            bag = list(files)
            random.shuffle(bag)
            if len(bag) > 1 and bag[-1] == self._prev.get(event):
                bag[0], bag[-1] = bag[-1], bag[0]
        pick = bag.pop()
        self._bag[event] = bag
        self._prev[event] = pick
        return pick

    def play(self, event, cooldown=0.4):
        """そのイベントのフォルダからランダムに1つ再生。再生したらTrue。"""
        if self.player is None:
            return False
        now = time.monotonic()
        if now - self._last.get(event, 0) < cooldown:
            return False
        files = self._files(event)
        if not files:
            return False
        self._last[event] = now
        try:
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(self._pick(event, files))))
            self.player.play()
        except Exception:
            LOG.exception("音声の再生に失敗しました: %s", event)
            return False
        return True

    def is_playing(self):
        try:
            return (self.player is not None and
                    self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        except Exception:
            return False

    def stop(self):
        try:
            if self.player is not None:
                self.player.stop()
        except Exception:
            pass
