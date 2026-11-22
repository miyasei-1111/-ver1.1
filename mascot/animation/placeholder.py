# -*- coding: utf-8 -*-
"""素材が無いときの簡易キャラ(プログラム描画)。依存: なし(Qtのみ)。"""

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QImage, QPainter, QPen


def make_placeholder(name):
    S = 200
    pm = QImage(S, S, QImage.Format.Format_ARGB32_Premultiplied)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(60, 40, 30), 4))

    feet = {"walk1": [(52, 158), (112, 172)],
            "walk2": [(52, 172), (112, 158)],
            "grabbed": [(60, 176), (110, 176)]}.get(name, [(60, 168), (110, 168)])
    p.setBrush(QColor(120, 80, 50))
    for fx, fy in feet:
        p.drawEllipse(QRect(fx, fy, 34, 18))
    p.setBrush(QColor(240, 170, 90))
    p.drawRoundedRect(QRect(52, 95, 96, 85), 30, 30)
    p.setBrush(QColor(250, 200, 140))
    p.drawEllipse(QRect(48, 18, 104, 96))

    if name == "sleep":                       # 閉じた目
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRect(70, 58, 22, 14), 0, -180 * 16)
        p.drawArc(QRect(108, 58, 22, 14), 0, -180 * 16)
        p.drawArc(QRect(88, 80, 24, 14), 0, -180 * 16)
    elif name == "grabbed":                   # 驚き目
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRect(68, 50, 26, 26))
        p.drawEllipse(QRect(106, 50, 26, 26))
        p.setBrush(QColor(30, 30, 30))
        p.drawEllipse(QRect(76, 58, 10, 10))
        p.drawEllipse(QRect(114, 58, 10, 10))
        p.drawEllipse(QRect(92, 84, 16, 16))
    elif name == "react":                     # にっこり + ほっぺ
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRect(70, 56, 22, 16), 0, 180 * 16)
        p.drawArc(QRect(108, 56, 22, 16), 0, 180 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 120, 120, 170))
        p.drawEllipse(QRect(58, 76, 20, 12))
        p.drawEllipse(QRect(122, 76, 20, 12))
        p.setPen(QPen(QColor(60, 40, 30), 4))
        p.setBrush(QColor(200, 70, 70))
        p.drawChord(QRect(86, 80, 28, 22), 0, -180 * 16)
    elif name == "land":                      # > < の目
        for ex in (72, 112):
            p.drawLine(ex, 54, ex + 16, 62)
            p.drawLine(ex, 70, ex + 16, 62)
        p.drawLine(90, 90, 110, 90)
    else:                                     # idle / walk
        p.setBrush(QColor(30, 30, 30))
        p.drawEllipse(QRect(76, 56, 12, 16))
        p.drawEllipse(QRect(112, 56, 12, 16))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRect(88, 80, 24, 14), 0, -180 * 16)
    p.end()
    return pm


def placeholder_frames(state):
    if state == "walk":
        return [make_placeholder("walk1"), make_placeholder("walk2")]
    return [make_placeholder(state)]
