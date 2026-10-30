"""Restore redirected pipes for PyInstaller windowed helper processes."""
import os
import sys

def redirected_stdio():
    if sys.stdin is not None and sys.stdout is not None:return
    import ctypes
    import msvcrt
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.GetStdHandle.argtypes=[ctypes.c_ulong];kernel.GetStdHandle.restype=ctypes.c_void_p
    for name,number,flags,mode in (("stdin",-10,os.O_RDONLY,"r"),("stdout",-11,os.O_WRONLY,"w")):
        if getattr(sys,name) is not None:continue
        handle=kernel.GetStdHandle(number)
        if not handle or handle==ctypes.c_void_p(-1).value:raise SystemExit("El proceso auxiliar requiere una tubería local.")
        fd=msvcrt.open_osfhandle(handle,flags)
        setattr(sys,name,os.fdopen(fd,mode,encoding="utf-8",buffering=1))
