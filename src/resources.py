"""Small host-resource probe shared by runtime paths without evaluation imports."""

import ctypes
import os


def free_memory_mib() -> float:
    if os.name != "nt":
        sysconf = getattr(os, "sysconf")
        return sysconf("SC_AVPHYS_PAGES") * sysconf("SC_PAGE_SIZE") / 1048576

    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in ("physical", "available", "page", "available_page", "virtual", "available_virtual", "extended")]]
    state = Memory()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError("host memory inspection failed")
    return state.available / 1048576
