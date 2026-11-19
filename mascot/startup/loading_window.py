# -*- coding: utf-8 -*-
"""起動時の「読み込み中」画面。依存: Qt のみ。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QLabel, QMenu, QProgressBar, QVBoxLayout, QWidget


class LoadingWindow(QWidget):
    """起動時の「読み込み中」表示。キャラクターが出るまで最前面に出し続ける。"""
    abort_requested = Signal()

    def __init__(self):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.Tool)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(340, 130)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(8)
        self.title = QLabel("読み込み中...")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        self.title.setFont(f)
        self.title.setStyleSheet("color: rgb(60, 40, 30); background: transparent;")
        self.detail = QLabel("リソースを確認しています")
        self.detail.setStyleSheet("color: rgb(120, 80, 50); background: transparent;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)                     # 総数が分かるまでは「処理中」表示
        self.bar.setTextVisible(False)
        lay.addWidget(self.title)
        lay.addWidget(self.detail)
        lay.addWidget(self.bar)
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.center() - self.rect().center())

    def set_detail(self, text):
        self.detail.setText(text)

    def set_progress(self, done, total):
        """総数が確定しているときだけ、完了数/総数の進捗を出す。"""
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(min(done, total))
            self.detail.setText(f"キャラクターを準備しています  ({min(done, total)} / {total})")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(255, 248, 236))
        p.setPen(QPen(QColor(120, 80, 50), 2))
        p.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 16, 16)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("読み込みを中止して終了", lambda: self.abort_requested.emit())
        m.exec(e.globalPos())

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.abort_requested.emit()
