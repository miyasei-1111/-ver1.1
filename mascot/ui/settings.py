# -*- coding: utf-8 -*-
"""設定ダイアログ。依存: config のみ(画像・音声・アニメには依存しない)。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QSlider,
)

from mascot.config import MOTIONS


class SettingsDialog(QDialog):
    SLIDERS = [
        ("scale", "サイズ", 30, 400, "%"),
        ("walk_speed", "歩く速さ", 10, 400, " px/s"),
        ("volume", "音量", 0, 100, "%"),
        ("sleep_sec", "眠るまでの時間", 5, 600, " 秒"),
        ("anim_speed", "アニメーション速度", 25, 300, "%"),
        ("react_sec", "クリック反応の表示時間", 1, 10, " 秒"),
    ]
    COMBOS = [
        ("click_motion", "クリック時のモーション"),
        ("land_motion", "着地時のモーション"),
    ]

    def __init__(self, cfg):
        super().__init__(None)
        self.setWindowTitle("設定")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(400)
        form = QFormLayout(self)

        self.sliders = {}
        for key, label, lo, hi, unit in self.SLIDERS:
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(int(cfg[key]))
            v = QLabel(f"{s.value()}{unit}")
            v.setMinimumWidth(70)
            s.valueChanged.connect(lambda val, v=v, unit=unit: v.setText(f"{val}{unit}"))
            row = QHBoxLayout()
            row.addWidget(s)
            row.addWidget(v)
            form.addRow(label, row)
            self.sliders[key] = s

        self.combos = {}
        for key, label in self.COMBOS:
            c = QComboBox()
            for mk, ml in MOTIONS.items():
                c.addItem(ml, mk)
            c.setCurrentIndex(max(0, c.findData(cfg.get(key))))
            form.addRow(label, c)
            self.combos[key] = c

        self.topmost = QCheckBox("常に最前面に表示する")
        self.topmost.setChecked(bool(cfg.get("always_on_top", False)))
        form.addRow(self.topmost)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        v = {k: s.value() for k, s in self.sliders.items()}
        v.update({k: c.currentData() for k, c in self.combos.items()})
        v["always_on_top"] = self.topmost.isChecked()
        return v
