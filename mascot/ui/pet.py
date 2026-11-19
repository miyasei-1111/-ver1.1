# -*- coding: utf-8 -*-
"""キャラクター本体(ウィンドウ・物理・入力・描画)。Sprites と VoicePlayer は外から渡される(依存性注入)ので、animation / audio / imaging には依存しない。"""

import math
import random
import time
from collections import deque

from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QWidget

from mascot.config import DEBUG, FLIP_INVERTED, MOTION_DURATION, save_config
from mascot.diagnostics import LOG
from mascot.system.memory import process_memory_mb, release_unused_memory
from mascot.ui.settings import SettingsDialog


class Pet(QWidget):
    IDLE, WALK, DRAG, FALL, SLEEP = range(5)

    GRAVITY = 2600.0     # px/s^2
    WALL_SPEED = 450.0   # この速度以上で壁に当たると音声
    LAND_SPEED = 350.0   # この速度以上で着地すると音声+モーション
    MAX_THROW = 3500.0
    DRAG_THRESHOLD = 6   # px。これ未満の移動はクリック扱い
    LAND_SPRITE_SEC = 0.6

    def __init__(self, cfg, sprites, voice):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if cfg.get("always_on_top"):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.cfg = cfg
        self.voice = voice                           # 音声(VoicePlayer)と
        self.sprites = sprites                       # 画像(Sprites)は、組み立て役(startup)から渡される
        self.pad_x = self.pad_top = 0
        self.fit_size()

        now = time.monotonic()
        self.state = self.IDLE
        self.state_until = now + 1.0
        self.facing = 1
        self.vx = self.vy = 0.0
        self.landed = True
        self.anim_t = 0.0
        self.last_tick = now
        self.last_activity = now
        self.react_until = 0.0
        self.land_until = 0.0
        self.start_until = 0.0        # 起動アニメの終了時刻
        self.exit_until = 0.0         # 終了アニメの終了時刻
        self._exit_voice = False
        self.getup_until = 0.0        # 起き上がりアニメの終了時刻
        self.did_land = False         # 着地アニメを再生したか(起き上がり判定用)
        self.motion = None            # (名前, 開始時刻, 継続秒)
        self.cur_anim = None          # 再生中の連番名
        self.anim_start = now
        self.pressed = False
        self.dragging = False
        self.press_global = QPointF()
        self.grab_off = QPointF()
        self.history = deque(maxlen=16)
        self._quitting = False
        self._sync_paint = False      # True の間の1回目の描画は、足りないコマをその場で作る(サイズ変更直後用)

        b = self._bounds_at(QPoint(0, 0))
        xmin, xmax = self._x_range(b)
        self.px = float(random.randint(xmin, max(xmin, xmax)))
        self.py = float(b.y() + b.height() - self.height())
        self.move(round(self.px), round(self.py))

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

        if DEBUG:                                    # メモリ使用量とキャッシュ状況を定期的にログへ
            self._stats_timer = QTimer(self)
            self._stats_timer.timeout.connect(self._log_stats)
            self._stats_timer.start(5000)

    # ---- サイズ(モーション用の透明余白つき) ---------------------------
    def fit_size(self):
        m = max(self.sprites.W, self.sprites.H)
        self.pad_x = round(m * 0.3)       # 左右の余白(回転・震え用)
        self.pad_top = round(m * 0.6)     # 上の余白(ジャンプ・回転用)
        self.setFixedSize(self.sprites.W + 2 * self.pad_x,
                          self.sprites.H + self.pad_top)

    def _x_range(self, b):
        # 透明な余白は画面外にはみ出してよい(キャラ本体が壁に接する)
        return b.x() - self.pad_x, b.x() + b.width() - self.width() + self.pad_x

    # ---- 画面範囲 -------------------------------------------------------
    @staticmethod
    def _bounds_at(pt):
        scr = QGuiApplication.screenAt(pt) or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def bounds(self):
        c = QPoint(int(self.px + self.width() / 2), int(self.py + self.height() / 2))
        return self._bounds_at(c)

    # ---- モーション -----------------------------------------------------
    def start_motion(self, name):
        if name == "random":
            name = random.choice(list(MOTION_DURATION))
        if name not in MOTION_DURATION:
            return
        self.motion = (name, time.monotonic(), MOTION_DURATION[name])

    def motion_params(self, now):
        """(dx, dy, 回転角, 横倍率, 縦倍率) を返す。"""
        dx = dy = ang = 0.0
        sx = sy = 1.0
        if self.motion:
            name, start, dur = self.motion
            t = (now - start) / dur
            if 0 <= t < 1:
                k = math.sin(math.pi * t)
                W, H = self.sprites.W, self.sprites.H
                if name == "squash":
                    sy, sx = 1 - 0.3 * k, 1 + 0.2 * k
                elif name == "hop":
                    dy = -H * 0.25 * k
                elif name == "spin":
                    ang = 360 * (t * t * (3 - 2 * t))
                    dy = -H * 0.35 * k
                elif name == "shake":
                    dx = math.sin(t * 40) * W * 0.06 * (1 - t)
                elif name == "wobble":
                    ang = 12 * math.sin(t * 20) * (1 - t)
        return dx, dy, ang, sx, sy

    # ---- ユーザー操作 ---------------------------------------------------
    def _log_stats(self):
        LOG.info("メモリ %.0f MB / %s", process_memory_mb(), self.sprites.store.stats())

    def speed(self):
        return max(1, self.cfg["anim_speed"]) / 100.0

    def touch(self):
        self.last_activity = time.monotonic()

    def wake(self):
        if self.state == self.SLEEP:
            self.state = self.IDLE
            self.state_until = time.monotonic() + 1.0

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._quitting:
            return
        self.touch()
        self.wake()
        self.pressed = True
        self.dragging = False
        g = e.globalPosition()
        self.press_global = g
        self.grab_off = g - QPointF(self.px, self.py)
        self.history.clear()
        self.history.append((time.monotonic(), g))

    def mouseMoveEvent(self, e):
        if not self.pressed:
            return
        g = e.globalPosition()
        if not self.dragging and (g - self.press_global).manhattanLength() > self.DRAG_THRESHOLD:
            self.dragging = True
            self.state = self.DRAG
            self.voice.play("grab")                  # 掴まれた瞬間の音声
            self.vx = self.vy = 0.0
            self.motion = None
            self.react_until = self.land_until = self.start_until = 0.0
            self.getup_until = 0.0
            self.did_land = False
        if self.dragging:
            self.touch()
            self.px = g.x() - self.grab_off.x()
            self.py = g.y() - self.grab_off.y()
            self.move(round(self.px), round(self.py))
            self.history.append((time.monotonic(), g))

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.pressed:
            return
        self.pressed = False
        self.touch()
        if self.dragging:
            self.dragging = False
            now = time.monotonic()
            self.history.append((now, e.globalPosition()))
            recent = [h for h in self.history if h[0] >= now - 0.1]
            vx = vy = 0.0
            if len(recent) >= 2:
                (t0, p0), (t1, p1) = recent[0], recent[-1]
                dt = t1 - t0
                if dt > 0.01:
                    vx = (p1.x() - p0.x()) / dt
                    vy = (p1.y() - p0.y()) / dt
            speed = math.hypot(vx, vy)
            if speed > self.MAX_THROW:
                vx *= self.MAX_THROW / speed
                vy *= self.MAX_THROW / speed
            self.vx, self.vy = vx, vy
            if abs(vx) > 50:
                self.facing = 1 if vx > 0 else -1
            self.landed = False
            self.state = self.FALL
        else:
            self.on_click()

    def on_click(self):
        """左クリックの反応: 専用画像 + モーション + 音声。"""
        now = time.monotonic()
        hold = max(self.cfg["react_sec"], self.sprites.anims["react"].duration() / self.speed())
        self.react_until = now + hold
        self.cur_anim = None                         # 連番を頭から再生し直す
        self.start_motion(self.cfg["click_motion"])
        self.voice.play("click", cooldown=0)

    def contextMenuEvent(self, e):
        if self._quitting:
            return
        self.touch()
        self.wake()
        m = QMenu(self)
        m.addAction("設定...", self.open_settings)
        m.addSeparator()
        m.addAction("終了", self.quit_app)
        m.exec(e.globalPos())
        self.touch()

    # ---- 設定 -----------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self.cfg)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.apply_settings(dlg.values())
        self.touch()

    def apply_settings(self, new):
        old = self.cfg
        self.cfg = {**old, **new}
        self.voice.set_volume(self.cfg["volume"])
        if bool(self.cfg.get("always_on_top")) != bool(old.get("always_on_top")):
            self.apply_topmost()
        if self.cfg["scale"] != old["scale"]:
            cx = self.px + self.width() / 2
            bottom = self.py + self.height()
            # 古いサイズのキャッシュを捨てて新しいサイズに切り替える(読み込みは待たない)。
            # 必要なコマは再生しながら背景で作る。連続して変更されても、古い要求は無効になる。
            self.sprites.set_scale(self.cfg["scale"])
            self.fit_size()
            self.px = cx - self.width() / 2        # 足元中央を基準に拡縮
            self.py = bottom - self.height()
            self.move(round(self.px), round(self.py))
            self._sync_paint = True                  # 次の描画だけは、いまのコマをその場で用意する
            QTimer.singleShot(3000, release_unused_memory)   # 古いサイズの画像が消えた頃に、未使用領域をOSへ返す
            self.voice.play("resize", cooldown=0)
        save_config(self.cfg)

    def apply_topmost(self):
        """最前面表示の切り替え(フラグ変更でウィンドウが隠れるので表示し直す)。"""
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,
                           bool(self.cfg.get("always_on_top")))
        self.show()
        self.move(round(self.px), round(self.py))

    # ---- 起動 / 終了 ----------------------------------------------------
    def play_start(self):
        """起動時: 専用アニメーション(assets/start)+ 起動音声。"""
        a = self.sprites.anims["start"]
        if not a.fallback:                           # 素材が無ければ何もしない
            self.start_until = time.monotonic() + a.duration() / self.speed()
            self.cur_anim = None
        QTimer.singleShot(300, lambda: self.voice.play("start", cooldown=0))

    def quit_app(self):
        """終了時: 専用アニメーション(assets/exit)+ 終了音声が終わってから閉じる。"""
        if self._quitting:
            return
        self._quitting = True
        now = time.monotonic()
        a = self.sprites.anims["exit"]
        if not a.fallback:
            a.prefetch_all()                         # 終了アニメの全コマを最優先で先読み(待たない)
        anim_len = 0.0 if a.fallback else a.duration() / self.speed()
        self.exit_until = now + anim_len
        self.cur_anim = None                         # 終了アニメを頭から再生
        self.motion = None
        self._exit_voice = self.voice.play("exit", cooldown=0)
        if self._exit_voice or anim_len > 0:
            self._q_start = now
            self._q_limit = max(8.0, anim_len + 3.0)
            self._q_timer = QTimer(self)
            self._q_timer.timeout.connect(self._check_quit)
            self._q_timer.start(100)
        else:
            QApplication.quit()

    def _check_quit(self):
        now = time.monotonic()
        el = now - self._q_start
        voice_done = (not self._exit_voice) or (el > 0.6 and not self.voice.is_playing())
        if el > self._q_limit or (now >= self.exit_until and voice_done):
            QApplication.quit()

    # ---- メインループ ---------------------------------------------------
    def choose_action(self, now):
        if random.random() < 0.65:
            self.state = self.WALK
            self.facing = random.choice((-1, 1))
            self.state_until = now + random.uniform(2, 6)
        else:
            self.state = self.IDLE
            self.state_until = now + random.uniform(1, 3)

    def wall_hit(self):
        if abs(self.vx) > self.WALL_SPEED:
            self.voice.play("wall")
        self.vx = -self.vx * 0.6
        if abs(self.vx) > 50:
            self.facing = 1 if self.vx > 0 else -1

    def on_land(self, now):
        """着地: 音声 + 着地画像 + 着地モーション。"""
        self.voice.play("land")
        self.did_land = True
        self.land_until = now + max(self.LAND_SPRITE_SEC,
                                    self.sprites.anims["land"].duration() / self.speed())
        self.cur_anim = None                         # 連番を頭から再生し直す
        self.start_motion(self.cfg["land_motion"])

    def tick(self):
        now = time.monotonic()
        dt = min(now - self.last_tick, 0.05)
        self.last_tick = now
        self.anim_t += dt

        if self.pressed:
            self.touch()
            self.update()
            return

        b = self.bounds()
        xmin, xmax = self._x_range(b)
        ymin = b.y() - self.pad_top
        ground = b.y() + b.height() - self.height()

        if self.state in (self.IDLE, self.WALK, self.SLEEP):
            if self.py < ground - 2:                 # 空中にいたら落下
                self.vx = self.vy = 0.0
                self.landed = False
                self.state = self.FALL
            else:
                self.py = ground
                busy = (now < self.start_until or now < self.getup_until
                        or self._quitting)   # 起動・起き上がり・終了アニメ中
                if busy:
                    pass
                elif self.state != self.SLEEP and now - self.last_activity >= self.cfg["sleep_sec"]:
                    self.state = self.SLEEP
                    self.voice.play("sleep", cooldown=0)
                elif self.state != self.SLEEP and now >= self.state_until:
                    self.choose_action(now)

                # クリック反応中・起動/終了アニメ中はその場で立ち止まる
                if self.state == self.WALK and now >= self.react_until and not busy:
                    self.px += self.facing * self.cfg["walk_speed"] * dt
                    if self.px <= xmin:
                        self.px, self.facing = xmin, 1
                    elif self.px >= xmax:
                        self.px, self.facing = xmax, -1
                self.px = max(xmin, min(xmax, self.px))

        elif self.state == self.FALL:
            self.vy += self.GRAVITY * dt
            self.px += self.vx * dt
            self.py += self.vy * dt
            if self.px < xmin:
                self.px = xmin
                self.wall_hit()
            elif self.px > xmax:
                self.px = xmax
                self.wall_hit()
            if self.py < ymin:
                self.py = ymin
                self.vy = abs(self.vy) * 0.5
            if self.py >= ground:
                self.py = ground
                if not self.landed and self.vy > self.LAND_SPEED:
                    self.on_land(now)
                self.landed = True
                self.vy = -self.vy * 0.35 if self.vy > 200 else 0.0
                self.vx *= 0.02 ** dt                # 地面の摩擦
                if self.vy == 0.0 and abs(self.vx) < 25:
                    self.vx = 0.0
                    self.state = self.IDLE
                    self.state_until = now + 1.0
                    g = self.sprites.anims["getup"]
                    if self.did_land and not g.fallback:
                        # 着地アニメが終わってから起き上がりを再生する
                        begin = max(now, self.land_until)
                        self.getup_until = begin + g.duration() / self.speed()
                        self.state_until = self.getup_until + 0.5
                    self.did_land = False

        self.move(round(self.px), round(self.py))
        self.update()

    # ---- 描画 -----------------------------------------------------------
    def current_anim_name(self, now):
        if self._quitting and not self.sprites.anims["exit"].fallback:
            return "exit"                            # 終了アニメ(最後のコマで保持)
        if self.state == self.SLEEP:
            return "sleep"
        if self.state == self.DRAG:
            return "grabbed"
        if now < self.start_until:
            return "start"
        if now < self.react_until:
            return "react"
        if now < self.land_until:
            return "land"
        if now < self.getup_until:
            return "getup"
        if self.state == self.FALL:
            return "grabbed"
        if self.state == self.WALK:
            return "walk"
        return "idle"

    def paintEvent(self, _):
        now = time.monotonic()
        p = QPainter(self)
        W, H = self.sprites.W, self.sprites.H

        name = self.current_anim_name(now)
        if name != self.cur_anim:                    # 状態が変わったら頭から再生
            self.cur_anim = name
            self.anim_start = now
        anim = self.sprites.anims[name]
        flip = (self.facing < 0) != (name in FLIP_INVERTED)   # 素材の向きが逆の状態は反転を逆に
        sync, self._sync_paint = self._sync_paint, False
        pm = anim.frame((now - self.anim_start) * self.speed(), flip, self.speed(), block=sync)
        if pm is None:                               # まだ何も用意できていない(ごく短時間)
            p.end()
            return

        # walk 素材が無く idle で代用している間だけ、上下に小さく弾ませる
        walking = self.state == self.WALK and now >= self.react_until
        bob = -abs(math.sin(self.anim_t * 9)) * H * 0.03 if (walking and anim.fallback) else 0.0
        dx, dy, ang, sx, sy = self.motion_params(now)

        # 原点 = 足元中央
        ox = self.pad_x + W / 2 + dx
        oy = self.pad_top + H + bob + dy
        if ang or sx != 1.0 or sy != 1.0:
            # モーション中だけ変形描画(足元基準)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.translate(ox, oy)
            if ang:
                p.translate(0, -H / 2)               # キャラ中心で回転
                p.rotate(ang)
                p.translate(0, H / 2)
            p.scale(sx, sy)
            p.drawImage(-pm.width() // 2, -pm.height(), pm)
            p.resetTransform()
        else:
            # 通常時は変形なしでそのまま描く(速くて画質も落ちない)
            p.drawImage(round(ox - pm.width() / 2), round(oy - pm.height()), pm)
