# -*- coding: utf-8 -*-
"""バイト数上限つきLRU。依存なし(Qtも使わない)。"""

from collections import OrderedDict


class ByteLRU:
    """バイト数の上限つきLRU。古いものから自動で捨てる。排他制御は呼び出し側で行う。"""

    def __init__(self, budget):
        self.budget = int(budget)
        self.total = 0
        self.evicted = 0
        self._od = OrderedDict()

    def __contains__(self, key):          # 使用順は変えない
        return key in self._od

    def __len__(self):
        return len(self._od)

    def get(self, key):
        e = self._od.get(key)
        if e is None:
            return None
        self._od.move_to_end(key)
        return e[0]

    def put(self, key, value, nbytes):
        old = self._od.pop(key, None)
        if old is not None:
            self.total -= old[1]
        self._od[key] = (value, nbytes)
        self.total += nbytes
        while self.total > self.budget and len(self._od) > 1:
            _, (_, n) = self._od.popitem(last=False)
            self.total -= n
            self.evicted += 1

    def clear(self):
        self._od.clear()
        self.total = 0
