"""Small non-activating Windows indicator, controlled through a private stdin pipe."""
import json
import queue
import sys
import threading
import time
import tkinter as tk
import desktop_windows as native
from desktop_runtime import redirected_stdio

class NOTIFYICONDATA(native.c.Structure):
    _fields_=[("cbSize",native.w.DWORD),("hWnd",native.w.HWND),("uID",native.w.UINT),("uFlags",native.w.UINT),
      ("uCallbackMessage",native.w.UINT),("hIcon",native.w.HANDLE),("szTip",native.w.WCHAR*128),
      ("dwState",native.w.DWORD),("dwStateMask",native.w.DWORD),("szInfo",native.w.WCHAR*256),
      ("uTimeout",native.w.UINT),("szInfoTitle",native.w.WCHAR*64),("dwInfoFlags",native.w.DWORD),
      ("guidItem",native.c.c_ubyte*16),("hBalloonIcon",native.w.HANDLE)]

def install_tray(hwnd,set_style):
    c,w=native.c,native.w
    shell=c.WinDLL("shell32");shell.Shell_NotifyIconW.argtypes=[w.DWORD,c.POINTER(NOTIFYICONDATA)];shell.Shell_NotifyIconW.restype=w.BOOL
    icon=NOTIFYICONDATA();icon.cbSize=c.sizeof(icon);icon.hWnd=hwnd;icon.uID=1;icon.uFlags=7;icon.uCallbackMessage=0x8001
    icon.hIcon=native.signature("LoadIconW",[w.HANDLE,c.c_void_p],w.HANDLE)(None,c.c_void_p(32512))
    icon.szTip="Control Gestual · F8 pausa · Ctrl+Alt+Z deshace"
    available=bool(shell.Shell_NotifyIconW(0,c.byref(icon)))
    register=native.signature("RegisterHotKey",[w.HWND,c.c_int,w.UINT,w.UINT],w.BOOL)
    shortcut=bool(register(hwnd,1,0x4003,ord("Z")))
    call=native.signature("CallWindowProcW",[c.c_void_p,w.HWND,w.UINT,w.WPARAM,w.LPARAM],c.c_ssize_t)
    old=native.get_style(hwnd,-4)
    created=native.signature("RegisterWindowMessageW",[w.LPCWSTR],w.UINT)("TaskbarCreated")
    def emit(action):print(json.dumps({"action":action}),flush=True)
    callback_type=c.WINFUNCTYPE(c.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
    @callback_type
    def callback(window,message,wp,lp):
        if message==created:
            shell.Shell_NotifyIconW(0,c.byref(icon));return 0
        if message==0x0312 and wp==1:emit("undo");return 0
        if message==0x8001:
            if lp==0x0203:emit("show")
            elif lp==0x0205:
                menu=native.signature("CreatePopupMenu",[],w.HANDLE)()
                append=native.signature("AppendMenuW",[w.HANDLE,w.UINT,c.c_size_t,w.LPCWSTR],w.BOOL)
                actions=[("Mostrar panel","show"),("Ocultar panel","hide"),("Pausar cámara","pause"),("Deshacer · Ctrl+Alt+Z","undo"),("Salir","quit")]
                try:
                    for i,(title,_) in enumerate(actions,1):append(menu,0,i,title)
                    point=w.POINT();native.signature("GetCursorPos",[c.POINTER(w.POINT)],w.BOOL)(c.byref(point))
                    native.signature("SetForegroundWindow",[w.HWND],w.BOOL)(hwnd)
                    choice=native.signature("TrackPopupMenu",[w.HANDLE,w.UINT,c.c_int,c.c_int,c.c_int,w.HWND,c.POINTER(w.RECT)],w.UINT)(menu,0x0182,point.x,point.y,0,hwnd,None)
                    if 1<=choice<=len(actions):emit(actions[choice-1][1])
                finally:native.signature("DestroyMenu",[w.HANDLE],w.BOOL)(menu)
            return 0
        return call(c.c_void_p(old),window,message,wp,lp)
    set_style(hwnd,-4,c.cast(callback,c.c_void_p).value)
    print(json.dumps({"event":"capabilities","tray":available,"shortcut":shortcut}),flush=True)
    def cleanup():
        set_style(hwnd,-4,old)
        native.signature("UnregisterHotKey",[w.HWND,c.c_int],w.BOOL)(hwnd,1)
        shell.Shell_NotifyIconW(2,c.byref(icon))
    return callback,cleanup

def main():
    redirected_stdio()
    sys.stdin.reconfigure(encoding="utf-8");sys.stdout.reconfigure(encoding="utf-8")
    messages = queue.SimpleQueue()
    def read():
        for line in sys.stdin:
            try: messages.put(json.loads(line))
            except ValueError: pass
        messages.put(None)
    threading.Thread(target=read, daemon=True).start()
    root = tk.Tk(); root.withdraw(); root.title(native.PANEL_TITLE + " — Indicador")
    root.overrideredirect(True); root.attributes("-topmost", True); root.attributes("-alpha", .94)
    label = tk.Label(root, text="", bg="#172842", fg="#edf4ff", font=("Segoe UI", 13), padx=18, pady=14, wraplength=390, justify="left")
    label.pack(); root.update_idletasks()
    ancestor = native.signature("GetAncestor", [native.w.HWND, native.w.UINT], native.w.HWND)
    hwnd = ancestor(root.winfo_id(), 2)
    set_style = native.signature("SetWindowLongPtrW" if native.c.sizeof(native.c.c_void_p) == 8 else "SetWindowLongW", [native.w.HWND, native.c.c_int, native.c.c_ssize_t], native.c.c_ssize_t)
    set_style(hwnd, -20, native.get_style(hwnd, -20) | 0x080800A0)
    callback,cleanup=install_tray(hwnd,set_style)
    deadline = 0
    def tick():
        nonlocal deadline
        while not messages.empty():
            message = messages.get()
            if message is None: cleanup(); root.destroy(); return
            if not message.get("text"):
                root.withdraw(); deadline = 0; continue
            label.config(text=message["text"][:200]); root.update_idletasks()
            x, y = message.get("x", 20), message.get("y", 20)
            root.geometry(f"+{max(0,x)}+{max(0,y)}")
            # SetWindowPos uses signed screen coordinates, including monitors left of primary.
            native.user32.ShowWindowAsync(hwnd, 4)  # SW_SHOWNOACTIVATE
            native.user32.SetWindowPos(hwnd, -1, x, y, root.winfo_reqwidth(), root.winfo_reqheight(), 0x0050)
            deadline = time.monotonic() + 5
        if deadline and time.monotonic() > deadline: root.withdraw(); deadline = 0
        root.after(60, tick)
    root.after(60, tick)
    try:root.mainloop()
    finally:
        if native.user32.IsWindow(hwnd):cleanup()

if __name__ == "__main__": main()
