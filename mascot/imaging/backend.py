# -*- coding: utf-8 -*-
"""Qt の画像処理(読み込み・縮小・反転・ロスレス圧縮)。QImage のみ使用(スレッドから安全)。依存: diagnostics。"""

import zlib

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QTransform

from mascot.diagnostics import LOG


class QtImageBackend:
    """
    画像まわりの処理をまとめたクラス(FrameStore から呼ばれる)。
    QImage はスレッドから安全に使える。QPixmap はGUIスレッド専用なので使わない。
    """

    def __init__(self):
        self.fmt = QImage.Format.Format_ARGB32_Premultiplied
        self._pack_ok = self._probe_pack()
        self._mirror_fn = self._probe_mirror()
        if not self._pack_ok:
            LOG.warning("画像の圧縮保存が使えないため、無圧縮で保持します(メモリ使用量が増えます)")

    # ---- 起動時の自己診断(PySide6のバージョン差で壊れないように) ------
    def _probe_pack(self):
        try:
            im = QImage(5, 3, self.fmt)
            im.fill(QColor(10, 20, 30, 200))
            im.setPixelColor(1, 1, QColor(255, 0, 0, 255))
            out = self._unpack_z(self._pack_z(im)[0])
            return (out.size() == im.size() and out.pixel(1, 1) == im.pixel(1, 1)
                    and out.pixel(0, 0) == im.pixel(0, 0))
        except Exception:
            LOG.exception("圧縮保存の自己診断に失敗")
            return False

    def _probe_mirror(self):
        cands = []
        if hasattr(QImage, "flipped"):
            cands.append(lambda i: i.flipped(Qt.Orientation.Horizontal))
        cands.append(lambda i: i.mirrored(True, False))
        cands.append(lambda i: i.transformed(QTransform().scale(-1, 1)))
        im = QImage(2, 1, self.fmt)
        im.setPixelColor(0, 0, QColor(255, 0, 0))
        im.setPixelColor(1, 0, QColor(0, 0, 255))
        for fn in cands:
            try:
                o = fn(im)
                if o.pixel(0, 0) == im.pixel(1, 0) and o.pixel(1, 0) == im.pixel(0, 0):
                    return fn
            except Exception:
                continue
        return cands[-1]

    # ---- FrameStore から使う操作 --------------------------------------
    def image_size(self, path):
        """画像本体は読まず、(幅, 高さ)だけ調べる。読めなければ None。"""
        try:
            sz = QImageReader(str(path)).size()
            if sz.isValid() and sz.width() > 0 and sz.height() > 0:
                return sz.width(), sz.height()
        except Exception:
            pass
        return None

    def decode(self, path):
        img = QImage(str(path))
        if img.isNull():
            return None
        if img.format() != self.fmt:
            img = img.convertToFormat(self.fmt)
        return img

    def size_of(self, img):
        return img.width(), img.height()

    def scale(self, img, w, h):
        if img.width() == w and img.height() == h:
            return img
        return img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)

    def mirror(self, img):
        return self._mirror_fn(img)

    def nbytes(self, img):
        try:
            return int(img.sizeInBytes())
        except Exception:
            return img.bytesPerLine() * img.height()

    # ---- ロスレス圧縮(画質は変わらない) ----------------------------------
    @staticmethod
    def _pack_z(img):
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        raw = img.constBits()
        if len(raw) != bpl * h:
            raise ValueError("画像バッファのサイズが想定と違います")
        data = zlib.compress(raw, 1)
        return ("z", w, h, bpl, data), len(data) + 64

    def _unpack_z(self, payload):
        _, w, h, bpl, data = payload
        raw = zlib.decompress(data)
        # QImage(bytes, ...) は元のバッファを参照するだけなので、すぐ copy() して独立させる
        return QImage(raw, w, h, bpl, self.fmt).copy()

    def pack(self, img):
        """表示サイズの画像を圧縮して (保存用データ, バイト数) を返す。"""
        if self._pack_ok:
            try:
                return self._pack_z(img)
            except Exception:
                LOG.exception("画像の圧縮に失敗(この画像は無圧縮で保持します)")
        return ("i", img), self.nbytes(img)

    def unpack(self, payload):
        if payload[0] == "i":
            return payload[1]
        return self._unpack_z(payload)
