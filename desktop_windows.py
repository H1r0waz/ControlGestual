"""Small Win32 desktop controller; bounded window, wheel and multimedia actions."""
import ctypes as c
from ctypes import wintypes as w
import os
import time
from pathlib import PureWindowsPath

user32 = c.WinDLL("user32", use_last_error=True)
dwmapi = c.WinDLL("dwmapi")
user32.SetProcessDpiAwarenessContext.argtypes = [c.c_void_p]
user32.SetProcessDpiAwarenessContext(c.c_void_p(-4))

class MONITORINFO(c.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD), ("szDevice", w.WCHAR * 32)]

class WINDOWPLACEMENT(c.Structure):
    _fields_ = [("length", w.UINT), ("flags", w.UINT), ("showCmd", w.UINT), ("ptMinPosition", w.POINT), ("ptMaxPosition", w.POINT), ("rcNormalPosition", w.RECT)]

ENUMWINDOW = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
ENUMMONITOR = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, c.POINTER(w.RECT), w.LPARAM)

def signature(name, args, result):
    fn = getattr(user32, name)
    fn.argtypes, fn.restype = args, result
    return fn

signature("EnumWindows", [ENUMWINDOW, w.LPARAM], w.BOOL)
signature("EnumDisplayMonitors", [w.HDC, c.POINTER(w.RECT), ENUMMONITOR, w.LPARAM], w.BOOL)
signature("GetMonitorInfoW", [w.HANDLE, c.POINTER(MONITORINFO)], w.BOOL)
signature("GetWindowRect", [w.HWND, c.POINTER(w.RECT)], w.BOOL)
signature("GetWindowTextW", [w.HWND, w.LPWSTR, c.c_int], c.c_int)
signature("GetWindowTextLengthW", [w.HWND], c.c_int)
signature("GetClassNameW", [w.HWND, w.LPWSTR, c.c_int], c.c_int)
signature("GetWindowThreadProcessId", [w.HWND, c.POINTER(w.DWORD)], w.DWORD)
signature("GetForegroundWindow", [], w.HWND)
signature("MonitorFromWindow", [w.HWND, w.DWORD], w.HANDLE)
signature("SetWindowPos", [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT], w.BOOL)
signature("ShowWindowAsync", [w.HWND, c.c_int], w.BOOL)
signature("PostMessageW", [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL)
signature("GetWindowPlacement", [w.HWND, c.POINTER(WINDOWPLACEMENT)], w.BOOL)
signature("SetWindowPlacement", [w.HWND, c.POINTER(WINDOWPLACEMENT)], w.BOOL)
signature("GetAsyncKeyState", [c.c_int], w.SHORT)
for name in ("IsWindow", "IsWindowVisible", "IsIconic", "IsZoomed", "IsHungAppWindow"):
    signature(name, [w.HWND], w.BOOL)
get_style = signature("GetWindowLongPtrW" if c.sizeof(c.c_void_p) == 8 else "GetWindowLongW", [w.HWND, c.c_int], c.c_ssize_t)
dwmapi.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, c.c_void_p, w.DWORD]
dwmapi.DwmGetWindowAttribute.restype = c.c_long

PANEL_TITLE = "Control Gestual — Escritorio"

kernel32=c.WinDLL("kernel32",use_last_error=True)
kernel32.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel32.OpenProcess.restype=w.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)];kernel32.QueryFullProcessImageNameW.restype=w.BOOL
kernel32.CloseHandle.argtypes=[w.HANDLE];kernel32.CloseHandle.restype=w.BOOL

def process_name(pid):
    handle=kernel32.OpenProcess(0x1000,False,pid)
    if not handle:return ""
    try:
        text=c.create_unicode_buffer(32768);size=w.DWORD(len(text))
        return PureWindowsPath(text.value).name.lower() if kernel32.QueryFullProcessImageNameW(handle,0,text,c.byref(size)) else ""
    finally:kernel32.CloseHandle(handle)

def rect_dict(rect):
    return dict(left=rect.left, top=rect.top, width=rect.right - rect.left, height=rect.bottom - rect.top)

def monitor_info(handle):
    info = MONITORINFO(); info.cbSize = c.sizeof(info)
    if not user32.GetMonitorInfoW(handle, c.byref(info)):
        raise c.WinError(c.get_last_error())
    return dict(id=int(handle), name=info.szDevice, bounds=rect_dict(info.rcMonitor), workArea=rect_dict(info.rcWork))

def monitors():
    result, errors = [], []
    @ENUMMONITOR
    def collect(handle, _dc, _rect, _data):
        try: result.append(monitor_info(handle))
        except OSError as error: errors.append(error)
        return True
    if not user32.EnumDisplayMonitors(None, None, collect, 0):
        raise c.WinError(c.get_last_error())
    if errors: raise errors[0]
    return sorted(result, key=lambda item: item["bounds"]["left"])

def window_info(hwnd):
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd): return None
    pid = w.DWORD(); user32.GetWindowThreadProcessId(hwnd, c.byref(pid))
    if pid.value == os.getpid(): return None
    title = c.create_unicode_buffer(min(user32.GetWindowTextLengthW(hwnd) + 1, 4096))
    user32.GetWindowTextW(hwnd, title, len(title))
    if not title.value.strip() or PANEL_TITLE in title.value: return None
    klass = c.create_unicode_buffer(256); user32.GetClassNameW(hwnd, klass, 256)
    if klass.value in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}: return None
    if get_style(hwnd, -20) & 0x80 or get_style(hwnd, -16) & 0x40000000: return None
    cloaked = w.DWORD()
    if dwmapi.DwmGetWindowAttribute(hwnd, 14, c.byref(cloaked), c.sizeof(cloaked)) == 0 and cloaked.value: return None
    rect = w.RECT()
    if not user32.GetWindowRect(hwnd, c.byref(rect)): return None
    return dict(hwnd=int(hwnd), pid=pid.value, title=title.value, app=process_name(pid.value), bounds=rect_dict(rect), minimized=bool(user32.IsIconic(hwnd)), maximized=bool(user32.IsZoomed(hwnd)))

def windows():
    result = []
    @ENUMWINDOW
    def collect(hwnd, _data):
        info = window_info(hwnd)
        if info: result.append(info)
        return True
    if not user32.EnumWindows(collect, 0): raise c.WinError(c.get_last_error())
    return result

def destination(current, displays, direction):
    if direction not in {"left", "right"}: raise ValueError("Dirección inválida.")
    center = current["bounds"]["left"] + current["bounds"]["width"] / 2
    candidates = [d for d in displays if d["id"] != current["id"] and
        ((d["bounds"]["left"] + d["bounds"]["width"] / 2 > center) if direction == "right" else
         (d["bounds"]["left"] + d["bounds"]["width"] / 2 < center))]
    if not candidates: raise ValueError("No hay otra pantalla en esa dirección.")
    return min(candidates, key=lambda d: abs(d["bounds"]["left"] + d["bounds"]["width"] / 2 - center))

def capture_placement(snapshot):
    hwnd, pid = snapshot.get("hwnd"), snapshot.get("pid")
    if type(hwnd) is not int or type(pid) is not int or not 0 < hwnd < 2 ** (8 * c.sizeof(c.c_void_p)) or not 0 < pid < 2 ** 32:
        raise ValueError("Ventana inválida.")
    info = window_info(snapshot.get("hwnd"))
    if not info or info["pid"] != snapshot.get("pid"): raise ValueError("La ventana ya no está disponible.")
    placement = WINDOWPLACEMENT(); placement.length = c.sizeof(placement)
    if not user32.GetWindowPlacement(info["hwnd"], c.byref(placement)): raise c.WinError(c.get_last_error())
    return {"hwnd": info["hwnd"], "pid": info["pid"], "placement": bytes(placement),
            "bounds": info["bounds"], "maximized": info["maximized"], "monitor": int(user32.MonitorFromWindow(info["hwnd"], 2))}

def restore_placement(saved):
    info = window_info(saved["hwnd"])
    if not info or info["pid"] != saved["pid"]: raise ValueError("La ventana original se cerró; no se puede deshacer.")
    if user32.IsHungAppWindow(saved["hwnd"]): raise ValueError("La aplicación no responde.")
    if saved["monitor"] not in {d["id"] for d in monitors()}: raise ValueError("La pantalla original ya no está conectada.")
    placement = WINDOWPLACEMENT.from_buffer_copy(saved["placement"])
    placement.flags |= 4  # WPF_ASYNCWINDOWPLACEMENT; coordinates remain in workspace units.
    if not user32.SetWindowPlacement(saved["hwnd"], c.byref(placement)): raise c.WinError(c.get_last_error())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        restored = window_info(saved["hwnd"])
        correct_monitor = int(user32.MonitorFromWindow(saved["hwnd"], 2)) == saved["monitor"]
        correct_bounds = restored and all(abs(restored["bounds"][k] - saved["bounds"][k]) <= 3 for k in saved["bounds"])
        if correct_monitor and restored and restored["maximized"] == saved["maximized"] and (saved["maximized"] or correct_bounds):
            return {"message": "Movimiento deshecho. Ventana en su posición original."}
        time.sleep(.02)
    raise ValueError("La aplicación no confirmó la posición original. Podés volver a intentar deshacer.")

def animate_window(hwnd, start, end, duration=.24, steps=12):
    for frame in range(1, steps + 1):
        progress = frame / steps
        eased = progress * progress * (3 - 2 * progress)
        rect = {key: round(start[key] + (end[key] - start[key]) * eased) for key in ("left", "top", "width", "height")}
        if not user32.SetWindowPos(hwnd, None, rect["left"], rect["top"], rect["width"], rect["height"], 0x4014):
            raise c.WinError(c.get_last_error())
        if frame < steps: time.sleep(duration / steps)

def minimize_window(snapshot):
    saved=capture_placement(snapshot);hwnd=saved["hwnd"]
    if user32.IsIconic(hwnd):raise ValueError("La ventana ya está minimizada.")
    if user32.IsHungAppWindow(hwnd):raise ValueError("La aplicación no responde.")
    try:
        if not user32.ShowWindowAsync(hwnd,6):raise c.WinError(c.get_last_error())
        deadline=time.monotonic()+2
        while not user32.IsIconic(hwnd) and time.monotonic()<deadline:time.sleep(.02)
        if not user32.IsIconic(hwnd):raise ValueError("La aplicación no aceptó minimizarse.")
        return {"message":"Ventana minimizada. Podés recuperarla con Deshacer."}
    except Exception:
        placement=WINDOWPLACEMENT.from_buffer_copy(saved["placement"])
        user32.SetWindowPlacement(hwnd,c.byref(placement));raise

def set_window_state(snapshot,state):
    if state not in ('maximized','normal'):raise ValueError('Estado de ventana inválido.')
    info=window_info(snapshot.get('hwnd'))
    if not info or info['pid']!=snapshot.get('pid'):raise ValueError('La ventana cambió.')
    wanted=state=='maximized'
    if not info['minimized'] and bool(info['maximized'])==wanted:return {"message":"La ventana ya está maximizada." if wanted else "La ventana ya está restaurada."}
    saved=capture_placement(snapshot)
    hwnd=saved['hwnd']
    if user32.IsHungAppWindow(hwnd):raise ValueError('La aplicación no responde.')
    if wanted and not get_style(hwnd,-16)&0x00010000:raise ValueError('Esta ventana no permite maximizarse.')
    try:
        if not user32.ShowWindowAsync(hwnd,3 if wanted else 1):raise c.WinError(c.get_last_error())
        deadline=time.monotonic()+2
        while (bool(user32.IsZoomed(hwnd))!=wanted or user32.IsIconic(hwnd)) and time.monotonic()<deadline:time.sleep(.02)
        if bool(user32.IsZoomed(hwnd))!=wanted or user32.IsIconic(hwnd):raise ValueError('La aplicación no aceptó el cambio de tamaño.')
        return {"message":"Ventana maximizada." if wanted else "Ventana restaurada a su tamaño normal."}
    except Exception:
        restore_placement(saved);raise

def toggle_maximize_window(snapshot):
    saved=capture_placement(snapshot);hwnd=saved["hwnd"]
    minimized=bool(user32.IsIconic(hwnd))
    if user32.IsHungAppWindow(hwnd):raise ValueError("La aplicación no responde.")
    if (minimized or not saved["maximized"]) and not get_style(hwnd,-16)&0x00010000:
        raise ValueError("Esta ventana no permite maximizarse.")
    maximized=minimized or not saved["maximized"]
    try:
        if not user32.ShowWindowAsync(hwnd,3 if maximized else 9):raise c.WinError(c.get_last_error())
        deadline=time.monotonic()+2
        while (bool(user32.IsZoomed(hwnd))!=maximized or user32.IsIconic(hwnd)) and time.monotonic()<deadline:time.sleep(.02)
        if bool(user32.IsZoomed(hwnd))!=maximized or user32.IsIconic(hwnd):raise ValueError("La aplicación no aceptó el cambio de tamaño.")
        return {"message":"Ventana maximizada." if maximized else "Ventana restaurada a su tamaño normal."}
    except Exception:
        placement=WINDOWPLACEMENT.from_buffer_copy(saved["placement"])
        user32.SetWindowPlacement(hwnd,c.byref(placement));raise

def panel_window(action):
    found=[]
    @ENUMWINDOW
    def collect(hwnd,_):
        title=c.create_unicode_buffer(512);user32.GetWindowTextW(hwnd,title,len(title))
        if title.value==PANEL_TITLE or title.value.startswith(PANEL_TITLE+" - Google Chrome"):found.append(hwnd)
        return True
    user32.EnumWindows(collect,0)
    if not found:raise ValueError("No se encontró el panel. Si lo cerraste, reiniciá la aplicación.")
    user32.ShowWindowAsync(found[0],6 if action=="hide" else 9)
    if action!="hide":signature("SetForegroundWindow",[w.HWND],w.BOOL)(found[0])

def move_window(snapshot, direction, monitor_id=None):
    hwnd, pid = snapshot.get("hwnd"), snapshot.get("pid")
    if type(hwnd) is not int or type(pid) is not int or not 0 < hwnd < 2 ** (8 * c.sizeof(c.c_void_p)) or not 0 < pid < 2 ** 32:
        raise ValueError("Ventana inválida.")
    info = window_info(hwnd)
    if not info or info["pid"] != pid: raise ValueError("La ventana se cerró o cambió. Elegila de nuevo.")
    if info["minimized"]: raise ValueError("Restaurá la ventana minimizada antes de moverla.")
    if user32.IsHungAppWindow(hwnd): raise ValueError("La aplicación no responde; no se movió.")
    displays = monitors()
    current = monitor_info(user32.MonitorFromWindow(hwnd, 2))
    target = destination(current, displays, direction) if monitor_id is None else next((d for d in displays if d["id"]==monitor_id),None)
    if target is None:raise ValueError("La pantalla elegida ya no está conectada.")
    if target["id"]==current["id"]:raise ValueError("La ventana ya está en la pantalla elegida.")
    b, screen = info["bounds"], current["bounds"]
    if not get_style(hwnd, -16) & 0x00C00000 and b["width"] >= screen["width"] and b["height"] >= screen["height"]:
        raise ValueError("Salí de pantalla completa antes de mover esa aplicación.")
    original = WINDOWPLACEMENT(); original.length = c.sizeof(original)
    if not user32.GetWindowPlacement(hwnd, c.byref(original)): raise c.WinError(c.get_last_error())
    maximized = info["maximized"]
    try:
        if maximized:
            user32.ShowWindowAsync(hwnd, 9)
            deadline = time.monotonic() + 1
            while user32.IsZoomed(hwnd) and time.monotonic() < deadline: time.sleep(.02)
            rect = w.RECT()
            if not user32.GetWindowRect(hwnd, c.byref(rect)): raise c.WinError(c.get_last_error())
            b = rect_dict(rect)
        area = target["workArea"]
        width, height = min(b["width"], area["width"]), min(b["height"], area["height"])
        left, top = area["left"] + (area["width"] - width) // 2, area["top"] + (area["height"] - height) // 2
        animate_window(hwnd, b, dict(left=left, top=top, width=width, height=height))
        deadline = time.monotonic() + 2
        while int(user32.MonitorFromWindow(hwnd, 2)) != target["id"] and time.monotonic() < deadline: time.sleep(.02)
        if int(user32.MonitorFromWindow(hwnd, 2)) != target["id"]:
            raise ValueError("La aplicación no aceptó el movimiento. Puede tener restricciones de permisos o tamaño.")
        if maximized:
            user32.ShowWindowAsync(hwnd, 3)
            deadline = time.monotonic() + 1
            while not user32.IsZoomed(hwnd) and time.monotonic() < deadline: time.sleep(.02)
            if not user32.IsZoomed(hwnd): raise ValueError("La aplicación no aceptó restaurar la maximización.")
        return {"hwnd": hwnd, "pid": pid, "message": "Ventana movida a la otra pantalla."}
    except Exception:
        user32.SetWindowPlacement(hwnd, c.byref(original))
        raise

def layout_bounds(area,layout):
    if layout not in {"left","right","top","bottom","top_left","top_right","bottom_left","bottom_right"}:raise ValueError("Distribución inválida.")
    left,top,width,height=area["left"],area["top"],area["width"],area["height"]
    if "left" in layout:width=width//2
    elif "right" in layout:left+=width//2;width-=width//2
    if "top" in layout:height=height//2
    elif "bottom" in layout:top+=height//2;height-=height//2
    return dict(left=left,top=top,width=width,height=height)

def arrange_window(snapshot,layout,monitor_id=None):
    saved=capture_placement(snapshot);hwnd=saved["hwnd"]
    info=window_info(hwnd)
    if info["minimized"]:raise ValueError("Recuperá la ventana minimizada antes de acomodarla.")
    if user32.IsHungAppWindow(hwnd):raise ValueError("La aplicación no responde.")
    if not get_style(hwnd,-16)&0x00040000:raise ValueError("Esta ventana no permite cambiar su tamaño.")
    display=monitor_info(saved["monitor"]) if monitor_id is None else next((d for d in monitors() if d["id"]==monitor_id),None)
    if display is None:raise ValueError("La pantalla elegida ya no está conectada.")
    bounds=layout_bounds(display["workArea"],layout)
    try:
        if info["maximized"]:
            user32.ShowWindowAsync(hwnd,9)
            deadline=time.monotonic()+1
            while user32.IsZoomed(hwnd) and time.monotonic()<deadline:time.sleep(.02)
        rect=w.RECT()
        if not user32.GetWindowRect(hwnd,c.byref(rect)):raise c.WinError(c.get_last_error())
        animate_window(hwnd,rect_dict(rect),bounds)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            actual=window_info(hwnd)
            if actual and all(abs(actual["bounds"][k]-bounds[k])<=4 for k in bounds):return {"message":"Ventana acomodada en la pantalla elegida."}
            time.sleep(.02)
        raise ValueError("La aplicación impone un tamaño mínimo o rechazó la distribución.")
    except Exception:
        original=WINDOWPLACEMENT.from_buffer_copy(saved["placement"]);user32.SetWindowPlacement(hwnd,c.byref(original));raise

def close_window(snapshot):
    hwnd,pid=snapshot.get('hwnd'),snapshot.get('pid')
    if type(hwnd) is not int or type(pid) is not int or not 0<hwnd<2**(8*c.sizeof(c.c_void_p)) or not 0<pid<2**32:
        raise ValueError('Ventana inválida.')
    info=window_info(hwnd)
    if not info or info['pid']!=pid:raise ValueError('La ventana ya no está disponible.')
    if user32.IsHungAppWindow(hwnd):raise ValueError('La aplicación no responde; no se forzará su cierre.')
    # WM_CLOSE lets the application ask to save or cancel; never terminate its process.
    if not user32.PostMessageW(hwnd,0x0010,0,0):raise c.WinError(c.get_last_error())
    return {'message':'Cierre solicitado: '+info['title']+'. Si aparece un diálogo para guardar, resolvelo en esa aplicación. El cierre no se puede deshacer.'}


def activate_window(snapshot):
    hwnd=snapshot.get("hwnd");info=window_info(hwnd)
    if not info or info["pid"]!=snapshot.get("pid"):raise ValueError("La aplicación ya no está disponible.")
    if user32.IsHungAppWindow(hwnd):raise ValueError("La aplicación no responde.")
    if info["minimized"]:user32.ShowWindowAsync(hwnd,9)
    foreground=signature("SetForegroundWindow",[w.HWND],w.BOOL)
    if not foreground(hwnd):
        kernel32.GetCurrentThreadId.restype=w.DWORD
        current=kernel32.GetCurrentThreadId();active=user32.GetForegroundWindow()
        other=user32.GetWindowThreadProcessId(active,None) if active else 0
        owner=user32.GetWindowThreadProcessId(hwnd,None)
        attach=signature("AttachThreadInput",[w.DWORD,w.DWORD,w.BOOL],w.BOOL)
        attached=[]
        # Join both queues only for the requested focus transition, then always detach.
        for thread in set((other,owner)):
            if thread and thread!=current and attach(current,thread,True):attached.append(thread)
        try:
            signature("BringWindowToTop",[w.HWND],w.BOOL)(hwnd)
            foreground(hwnd)
            deadline=time.monotonic()+.25
            while user32.GetForegroundWindow()!=hwnd and time.monotonic()<deadline:time.sleep(.01)
        finally:
            for thread in attached:attach(current,thread,False)
    deadline=time.monotonic()+1
    while user32.GetForegroundWindow()!=hwnd and time.monotonic()<deadline:time.sleep(.02)
    if user32.GetForegroundWindow()!=hwnd:raise ValueError("Windows no permitió cambiar el foco. Activá la aplicación desde la barra de tareas.")
    return {"message":"Aplicación activada."}

class MOUSEINPUT(c.Structure):
    _fields_=[('dx',w.LONG),('dy',w.LONG),('mouseData',w.DWORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',c.c_size_t)]
class KEYBDINPUT(c.Structure):
    _fields_=[('wVk',w.WORD),('wScan',w.WORD),('dwFlags',w.DWORD),('time',w.DWORD),('dwExtraInfo',c.c_size_t)]
class INPUTUNION(c.Union):
    _fields_=[('mi',MOUSEINPUT),('ki',KEYBDINPUT)]
class INPUT(c.Structure):
    _fields_=[('type',w.DWORD),('data',INPUTUNION)]

def send_inputs(inputs):
    values=(INPUT*len(inputs))(*inputs)
    send=signature('SendInput',[w.UINT,c.POINTER(INPUT),c.c_int],w.UINT)
    if send(len(values),values,c.sizeof(INPUT))!=len(values):raise ValueError('Windows rechazó la entrada. Revisá si la aplicación tiene permisos elevados.')

MEDIA_KEYS={'volume_up':0xAF,'volume_down':0xAE,'volume_mute':0xAD,'media_toggle':0xB3,'media_next':0xB0,'media_previous':0xB1}

def multimedia_action(action):
    if action not in MEDIA_KEYS:raise ValueError('Control multimedia inválido.')
    key=MEDIA_KEYS[action]
    release=INPUT(type=1,data=INPUTUNION(ki=KEYBDINPUT(wVk=key,dwFlags=2)))
    try:send_inputs([INPUT(type=1,data=INPUTUNION(ki=KEYBDINPUT(wVk=key))),release])
    except ValueError:
        try:send_inputs([release])
        except ValueError:pass
        raise
    return {'message':'Orden multimedia enviada a Windows. El reproductor activo decide cómo responder.'}

def scroll_window(snapshot,direction):
    if direction not in ('up','down'):raise ValueError('Dirección de scroll inválida.')
    activate_window(snapshot)
    info=window_info(snapshot['hwnd'])
    if not info or info['pid']!=snapshot['pid']:raise ValueError('La ventana cambió.')
    rect=info['bounds'];center=(rect['left']+rect['width']//2,rect['top']+rect['height']//2)
    point=w.POINT()
    if not signature('GetCursorPos',[c.POINTER(w.POINT)],w.BOOL)(c.byref(point)):raise ValueError('No se pudo leer la posición del puntero.')
    cursor=signature('SetCursorPos',[c.c_int,c.c_int],w.BOOL)
    try:
        if not cursor(*center):raise ValueError('No se pudo dirigir la rueda a la ventana elegida.')
        under=signature('WindowFromPoint',[w.POINT],w.HWND)(w.POINT(*center))
        root=signature('GetAncestor',[w.HWND,w.UINT],w.HWND)(under,2)
        if root!=snapshot['hwnd'] or user32.GetForegroundWindow()!=snapshot['hwnd']:raise ValueError('Otra ventana tapa el destino del scroll. Seleccionala y repetí.')
        send_inputs([INPUT(type=0,data=INPUTUNION(mi=MOUSEINPUT(mouseData=(360 if direction=='up' else -360)&0xffffffff,dwFlags=0x800)))])
    finally:
        current=w.POINT();user32.GetCursorPos(c.byref(current))
        if (current.x,current.y)==center:cursor(point.x,point.y)
    return {'message':'Scroll enviado a la ventana elegida.'}

def place_bounds(snapshot,bounds,maximized=False):
    info=window_info(snapshot.get('hwnd'))
    if not info or info['pid']!=snapshot.get('pid'):raise ValueError('Una ventana de la distribución cambió.')
    if user32.IsHungAppWindow(snapshot['hwnd']):raise ValueError('Una ventana no responde.')
    if not get_style(snapshot['hwnd'],-16)&0x00040000:raise ValueError('Una ventana no permite cambiar de tamaño.')
    set_window_state(snapshot,'normal')
    actual=window_info(snapshot['hwnd']);animate_window(snapshot['hwnd'],actual['bounds'],bounds)
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        actual=window_info(snapshot['hwnd'])
        if actual and all(abs(actual['bounds'][k]-bounds[k])<=4 for k in bounds):break
        time.sleep(.02)
    else:raise ValueError('La aplicación rechazó el tamaño guardado.')
    if maximized:set_window_state(snapshot,'maximized')
    return {'message':'Distribución aplicada.'}
