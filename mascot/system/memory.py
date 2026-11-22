# -*- coding: utf-8 -*-
"""OS依存のメモリ関連処理(使用量の取得・未使用領域の返却)。OSごとの分岐はここに閉じ込める。依存: config のみ。"""

import sys

from mascot.config import MB


def process_memory_mb():
    """このプロセスのメモリ使用量(MB)。デバッグ表示用。取得できなければ -1。"""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC),
                                                   wintypes.DWORD]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return pmc.WorkingSetSize / MB
        else:
            with open("/proc/self/status", encoding="ascii") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024
    except Exception:
        pass
    return -1.0


def release_unused_memory():
    """解放済みなのにOS側に残っているメモリを返す(サイズを小さくした後の見かけの使用量を下げる)。
    失敗しても動作には影響しないので、何があっても無視する。"""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            psapi.EmptyWorkingSet(k32.GetCurrentProcess())
        elif sys.platform.startswith("linux"):
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
