# -*- coding: utf-8 -*-
"""画像の2層キャッシュ(圧縮層/ホット層)・世代管理・読み込みスレッド。依存: config, diagnostics, imaging.lru。"""

import math
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, QThread, Signal

from mascot.config import MB
from mascot.diagnostics import LOG
from mascot.imaging.lru import ByteLRU


BULK_FRAMES = 400        # このコマ数を超えるアニメ(睡眠など)は「長尺」扱いで別枠のキャッシュにする


HOT_MIN_MB = 16          # 展開済みコマ(ホット層)の最低上限(MB)


MIN_AHEAD = 3            # 先読みする最小コマ数


MAX_AHEAD = 36           # 先読みする最大コマ数


NUM_WORKERS = 2          # 読み込みスレッド数


WARM_YIELD_SEC = 0.004   # 背景ウォームアップは1コマごとに少し休んで、他の処理を優先する


class _Src:
    """FrameStore に登録した連番1セットの情報。"""
    __slots__ = ("name", "files", "count", "w0", "h0", "usable", "factor", "pool")


class StoreSignals(QObject):
    """読み込みスレッドからGUIスレッドへ進捗を伝える(Signalはキューされて安全に届く)。"""
    progress = Signal(int, int)       # (完了数, 総数)


class _FrameWorker(QThread):
    def __init__(self, store, index):
        super().__init__()
        self._store = store
        self.setObjectName(f"frame-worker-{index}")

    def run(self):
        st = self._store
        while True:
            job = st._next_job()
            if job is None:
                break
            st._run_job(job)


class FrameStore:
    """
    連番画像の2層キャッシュと、読み込みスレッドの管理。

      圧縮層 … 表示サイズに縮小した画像をロスレス圧縮して持つ(約1/10のメモリ)。
               上限(バイト)を超えたら古いものから捨てる。
      ホット層 … 再生位置の少し先までの展開済み画像(QImage)。左右反転もここで作る。
               こちらも上限つきLRU。

    ・GUIスレッドは get() で「今すぐ使える画像」だけを受け取る(読み込みで止まらない)
    ・足りない分は読み込みスレッドが先読みする
    ・サイズ変更のたびに「世代」を進め、古い世代の結果は捨てる(キャンセル相当)
    ・失敗したコマは記録して再試行しない(次のサイズ変更まで)
    """

    def __init__(self, backend, core_mb=160, bulk_mb=96, workers=NUM_WORKERS, signals=None):
        self.be = backend
        self.signals = signals
        self.cv = threading.Condition(threading.RLock())
        self.sources = {}
        self.gen = 0
        self.W = self.H = 0
        self.max_ahead = MAX_AHEAD
        self._core_budget = int(core_mb * MB)
        self._bulk_budget = int(bulk_mb * MB)
        self._comp = {"core": ByteLRU(self._core_budget), "bulk": ByteLRU(self._bulk_budget)}
        self.hot = ByteLRU(HOT_MIN_MB * MB)
        self._hot_pending = {}            # {(名前, コマ, 反転): 優先度}  小さいほど先
        self._startup_q = deque()
        self._warm_q = deque()
        self._inflight = set()
        self._building = set()
        self._failed = set()
        self._logged = set()
        self._last_any = None
        self._build_s = 0.0               # 1コマを元画像から作るのにかかる時間(移動平均, 秒)
        self._startup_total = 0
        self._startup_done = 0
        self._stop = False
        self._nworkers = max(1, workers)
        self._workers = []

    # ---- 登録・設定 ------------------------------------------------------
    def register(self, name, files):
        """連番を登録する。画像本体は読まず、先頭の寸法だけ調べる。"""
        s = _Src()
        s.name, s.files, s.count = name, list(files), len(files)
        s.w0 = s.h0 = 0
        s.usable = False
        s.factor = 1.0
        s.pool = "bulk" if s.count > BULK_FRAMES else "core"
        for p in s.files[:3]:
            sz = self.be.image_size(p)
            if sz:
                s.w0, s.h0 = sz
                s.usable = True
                break
        if not s.usable and s.files:
            LOG.warning("連番を読めません(代わりに簡易キャラを使います): %s", name)
        self.sources[name] = s
        return s

    def set_target(self, W, H):
        """表示サイズを変更する。古いサイズのキャッシュと読み込み要求はすべて無効にする。"""
        with self.cv:
            self.gen += 1
            self.W, self.H = W, H
            for s in self.sources.values():
                # 連番全体で同じ倍率を使う(コマごとに大きさがブレないように)
                s.factor = min(W / s.w0, H / s.h0) if s.usable else 1.0
            self._comp = {"core": ByteLRU(self._core_budget), "bulk": ByteLRU(self._bulk_budget)}
            fb = max(1, W * H * 4)
            hot_budget = max(HOT_MIN_MB * MB, 20 * fb)       # 1コマ=fb バイト。大きい表示ほど枚数は絞る
            self.hot = ByteLRU(hot_budget)
            # 先読みの窓は上限の半分まで(残り半分は、左右反転した向きに切り替わる分の余裕)
            self.max_ahead = max(MIN_AHEAD, min(MAX_AHEAD, int(hot_budget / fb) // 2 - 2))
            self._hot_pending = {}
            self._startup_q.clear()
            self._warm_q.clear()
            self._failed.clear()
            self._last_any = None
            self._build_s = 0.0           # サイズが変わると作成時間も変わるので学び直す
            self.cv.notify_all()
        return self.gen

    # ---- スレッド管理 ----------------------------------------------------
    def start(self):
        if self._workers or self._stop:
            return
        for i in range(self._nworkers):
            w = _FrameWorker(self, i)
            self._workers.append(w)
            w.start(QThread.Priority.LowPriority)

    def shutdown(self):
        """読み込みスレッドを止める(何度呼んでも安全)。"""
        with self.cv:
            if self._stop:
                return
            self._stop = True
            self._hot_pending = {}
            self._startup_q.clear()
            self._warm_q.clear()
            self.cv.notify_all()
        for w in self._workers:
            try:
                if not w.wait(5000):
                    LOG.warning("読み込みスレッドが終了しないため強制終了します")
                    w.terminate()
                    w.wait(500)
            except Exception:
                pass
        self._workers = []

    # ---- 先読みの予約 ----------------------------------------------------
    def begin_startup(self, items):
        """起動に必須のコマ [(名前, コマ番号), ...] を最優先で読む。"""
        with self.cv:
            self._startup_q = deque(items)
            self._startup_total = len(items)
            self._startup_done = 0
            self.cv.notify_all()

    def startup_state(self):
        with self.cv:
            return self._startup_done, self._startup_total

    def warm(self, items, front=False):
        """表示中でなくても、先に圧縮層へ入れておきたいコマ(背景で、他より後回しに読む)。"""
        with self.cv:
            if front:
                self._warm_q.extendleft(reversed(list(items)))
            else:
                self._warm_q.extend(items)
            self.cv.notify_all()

    def _schedule_ahead_locked(self, src, idx, flip, loop, ahead, gen, fps=None):
        n = src.count
        pend = {}
        # 元画像から作ると「作っている間に再生位置が通り過ぎる」コマ(近すぎるコマ)は後回しにし、
        # 間に合う位置のコマから作る。作成が再生速度に追いつかない間も、遅れが溜まり続けない。
        lead = 0
        if fps and self._build_s > 0:
            lead = min(ahead, int(math.ceil(self._build_s * fps)) + 1)
        pool = self._comp[src.pool]
        for d in range(ahead + 1):
            j = idx + d
            if j >= n:
                if not loop:
                    break
                j %= n
            k = (src.name, j, flip)
            if k in self.hot or (src.name, j) in self._failed:
                continue
            if (gen, "H", src.name, j, flip) in self._inflight:
                continue
            late = d < lead and (src.name, j) not in pool    # 圧縮層にあれば展開だけなので急がなくてよい
            pend.setdefault(k, d + 1000 if late else d)
        self._hot_pending = pend          # 再生位置を過ぎた予約はここで自然に消える
        if pend:
            self.cv.notify()

    # ---- GUIスレッドからの取得 -------------------------------------------
    def last_image(self):
        with self.cv:
            return self._last_any

    def get(self, name, idx, flip=False, ahead=None, loop=True, block=False, fps=None):
        """
        そのコマの画像(QImage)を返す。まだ無ければ None(= 呼び出し側で代用する)。
        ahead を渡すと、その先のコマの読み込みも予約する。
        圧縮層にあれば、その場で展開して返す(GUIスレッドでも数ms以内)。
        block=True のときだけ、無ければ元画像から作る(サイズ変更直後の1コマ用)。
        """
        with self.cv:
            src = self.sources.get(name)
            if src is None or not src.usable or src.count == 0:
                return None
            gen = self.gen
            f = src.factor
            key = (name, idx, flip)
            exact = self.hot.get(key)
            near = None
            payload = None
            failed = False
            if exact is not None:
                self._last_any = exact
            elif (name, idx) in self._failed:
                failed = True
                near = self._nearest_locked(src, idx, flip, loop)
            else:
                payload = self._comp[src.pool].get((name, idx))
                if payload is None:       # まだ作れていない: 同じアニメの直前のコマで代用(止めない)
                    near = self._nearest_locked(src, idx, flip, loop)
            if ahead is not None:
                self._schedule_ahead_locked(src, idx, flip, loop, ahead, gen, fps)
        if exact is not None:
            return exact
        if failed:
            return near
        try:
            if payload is not None:
                img = self.be.unpack(payload)
            elif block:
                img = self._build_and_store(src, idx, gen, f)
            else:
                return near
            if img is None:
                return None
            if flip:
                img = self.be.mirror(img)
        except Exception as e:
            self._mark_failed(name, idx, gen, e)
            return None
        nb = self.be.nbytes(img)
        with self.cv:
            if gen == self.gen:
                self.hot.put(key, img, nb)
                self._last_any = img
        return img

    def _nearest_locked(self, src, idx, flip, loop):
        """壊れたコマの代わりに、直前の読み込み済みのコマを探す。"""
        for d in range(1, 25):
            j = idx - d
            if j < 0:
                if not loop:
                    break
                j %= src.count
            img = self.hot.get((src.name, j, flip))
            if img is not None:
                return img
        return None

    # ---- 読み込みスレッド側 ----------------------------------------------
    def _need_comp_locked(self, name, idx):
        src = self.sources[name]
        return (name, idx) not in self._failed and (name, idx) not in self._comp[src.pool]

    def _next_job(self):
        with self.cv:
            while True:
                if self._stop:
                    return None
                job = self._pick_locked()
                if job is not None:
                    return job
                self.cv.wait(0.3)

    def _pick_locked(self):
        gen = self.gen
        # 1) いま見ているアニメの先読み(再生位置に近い順)
        while self._hot_pending:
            key = min(self._hot_pending, key=self._hot_pending.__getitem__)
            del self._hot_pending[key]
            name, idx, flip = key
            src = self.sources[name]
            if key in self.hot or (name, idx) in self._failed:
                continue
            fk = (gen, "H", name, idx, flip)
            if fk in self._inflight:
                continue
            has_comp = (name, idx) in self._comp[src.pool]
            bkey = (gen, name, idx)
            if not has_comp:
                if bkey in self._building:    # 他のスレッドが作成中。次のコマ更新時に再予約される
                    continue
                self._building.add(bkey)
            self._inflight.add(fk)
            return ("H", name, idx, flip, gen, src.factor, False, not has_comp)
        # 2) 起動に必須のコマ → 3) 背景ウォームアップ
        for q, startup in ((self._startup_q, True), (self._warm_q, False)):
            while q:
                name, idx = q.popleft()
                if name not in self.sources:
                    continue
                bkey = (gen, name, idx)
                fk = (gen, "W", name, idx, False)
                if (not self._need_comp_locked(name, idx) or bkey in self._building
                        or fk in self._inflight):
                    if startup:
                        self._startup_done += 1       # すでに用意済み(または他で作成中)
                    continue
                self._building.add(bkey)
                self._inflight.add(fk)
                return ("W", name, idx, False, gen, self.sources[name].factor, startup, True)
        return None

    def _run_job(self, job):
        kind, name, idx, flip, gen, f, startup, builds = job
        try:
            src = self.sources[name]
            if kind == "H":
                self._make_hot(src, idx, flip, gen, f)
            else:
                self._build_and_store(src, idx, gen, f)
        except Exception as e:            # MemoryError もここに来る(スレッドは止めない)
            self._mark_failed(name, idx, gen, e)
        finally:
            with self.cv:
                self._inflight.discard((gen, kind, name, idx, flip))
                if builds:
                    self._building.discard((gen, name, idx))
                counted = startup and gen == self.gen
                if counted:
                    self._startup_done += 1
                state = (self._startup_done, self._startup_total)
            if counted:
                self._emit_progress(*state)
            if kind == "W" and not startup:
                time.sleep(WARM_YIELD_SEC)

    def _emit_progress(self, done, total):
        if self.signals is not None:
            try:
                self.signals.progress.emit(done, total)
            except Exception:
                pass                       # 終了処理中などで受け取り側が無い場合

    def _build_and_store(self, src, idx, gen, f):
        """元画像を読んで表示サイズに縮小し、圧縮層に入れる。縮小済み画像を返す(世代が古ければ None)。"""
        path = src.files[idx]
        t_start = time.perf_counter()
        img0 = self.be.decode(path)
        if img0 is None:
            raise ValueError(f"画像を読めません: {path}")
        if gen != self.gen:
            return None
        w0, h0 = self.be.size_of(img0)
        scaled = self.be.scale(img0, max(1, round(w0 * f)), max(1, round(h0 * f)))
        del img0                           # 大きい元画像はここで破棄
        if gen != self.gen:
            return None
        payload, nb = self.be.pack(scaled)
        dt = time.perf_counter() - t_start
        with self.cv:
            if gen == self.gen:
                self._comp[src.pool].put((src.name, idx), payload, nb)
                self._build_s = dt if self._build_s <= 0 else 0.8 * self._build_s + 0.2 * dt
        return scaled

    def _make_hot(self, src, idx, flip, gen, f):
        with self.cv:
            if gen != self.gen:
                return
            payload = self._comp[src.pool].get((src.name, idx))
        if payload is not None:
            img = self.be.unpack(payload)
        else:
            img = self._build_and_store(src, idx, gen, f)
            if img is None:
                return
        if flip:
            img = self.be.mirror(img)
        nb = self.be.nbytes(img)
        with self.cv:
            if gen == self.gen:
                self.hot.put((src.name, idx, flip), img, nb)

    def _mark_failed(self, name, idx, gen, err):
        """失敗したコマを記録する(再試行しない)。ログは同じコマにつき1回だけ。"""
        with self.cv:
            if gen == self.gen:
                self._failed.add((name, idx))
            first = (name, idx) not in self._logged
            self._logged.add((name, idx))
            if isinstance(err, MemoryError):
                self.hot.clear()          # メモリ不足のときは展開済みの分を手放す
        if first:
            LOG.warning("コマの読み込みに失敗しました: %s #%d (%s: %s)",
                        name, idx, type(err).__name__, err)

    # ---- 状況確認 --------------------------------------------------------
    def stats(self):
        with self.cv:
            comp_b = sum(c.total for c in self._comp.values())
            comp_n = sum(len(c) for c in self._comp.values())
            return {"gen": self.gen, "comp_MB": round(comp_b / MB, 1), "comp_n": comp_n,
                    "hot_MB": round(self.hot.total / MB, 1), "hot_n": len(self.hot),
                    "evicted": sum(c.evicted for c in self._comp.values()) + self.hot.evicted,
                    "failed": len(self._failed), "pending": len(self._hot_pending)}
