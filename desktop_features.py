"""Version 2 settings and action vocabulary, shared by the local controller."""
import re
from desktop_productivity import validate_productivity

VERSION="5.3.0"
ACTIONS={
    "move_left":"Mover al monitor izquierdo","move_right":"Mover al monitor derecho",
    "minimize":"Minimizar","maximize":"Maximizar / Restaurar",
    "close":"Cerrar ventana (sin deshacer)",
    "snap_left":"Mitad izquierda","snap_right":"Mitad derecha","snap_top":"Mitad superior","snap_bottom":"Mitad inferior",
    "snap_top_left":"Cuarto superior izquierdo","snap_top_right":"Cuarto superior derecho",
    "snap_bottom_left":"Cuarto inferior izquierdo","snap_bottom_right":"Cuarto inferior derecho",
    "next_app":"Aplicación siguiente","previous_app":"Aplicación anterior","none":"Desactivado",
    "scroll_up":"Scroll hacia arriba","scroll_down":"Scroll hacia abajo",
    "volume_up":"Subir volumen","volume_down":"Bajar volumen","volume_mute":"Silenciar / Activar sonido",
    "media_toggle":"Reproducir / Pausar música","media_next":"Pista siguiente","media_previous":"Pista anterior",
}
PROFILES={
    "windows":{"left":"move_left","right":"move_right","up":"maximize","down":"minimize"},
    "organize":{"left":"snap_left","right":"snap_right","up":"snap_top","down":"snap_bottom"},
    "navigate":{"left":"previous_app","right":"next_app","up":"maximize","down":"minimize"},
}
FINGER_GESTURES={
    "index":{"label":"Pulgar + índice", "bindings":{"left":"snap_left","right":"snap_right","up":"snap_top","down":"snap_bottom"}},
    "victory":{"label":"Pulgar + medio", "bindings":{"left":"previous_app","right":"next_app","up":"maximize","down":"minimize"}},
    "three":{"label":"Pulgar + anular", "bindings":{"top_left":"snap_top_left","top_right":"snap_top_right","bottom_left":"snap_bottom_left","bottom_right":"snap_bottom_right"}},
    "pinky":{"label":"Pulgar + meñique", "bindings":{"left":"previous_app","right":"next_app","up":"none","down":"none"}},
}

def validate_settings(data):
    if not isinstance(data,dict):raise ValueError("Ajustes inválidos.")
    sensitivity=data.get("sensitivity",18);calibration=data.get("calibration");invert=data.get("invert",False)
    if type(sensitivity) is not int or not 8<=sensitivity<=35 or type(invert) is not bool:raise ValueError("Sensibilidad inválida.")
    if calibration is not None:
        if not isinstance(calibration,dict) or any(type(calibration.get(k)) not in (int,float) for k in ("closed","open")):
            raise ValueError("Calibración inválida.")
        if not .05<=calibration["closed"]<calibration["open"]<=4 or calibration["open"]-calibration["closed"]<.1:
            raise ValueError("Calibración inválida.")
        calibration={k:calibration[k] for k in ("closed","open")}
    profile=data.get("profile","windows")
    if profile not in (*PROFILES,"custom"):raise ValueError("Perfil inválido.")
    bindings=data.get("bindings",PROFILES.get(profile,PROFILES["windows"]))
    if not isinstance(bindings,dict) or set(bindings)!={"left","right","up","down"} or any(type(a) is not str or a not in ACTIONS for a in bindings.values()):
        raise ValueError("Asignación de gestos inválida.")
    finger_bindings=data.get("finger_bindings",{k:v["bindings"] for k,v in FINGER_GESTURES.items()})
    if isinstance(finger_bindings,dict) and set(finger_bindings)==set(FINGER_GESTURES)-{"pinky"}:
        finger_bindings={**finger_bindings,"pinky":dict(FINGER_GESTURES["pinky"]["bindings"])}
    if not isinstance(finger_bindings,dict) or set(finger_bindings)!=set(FINGER_GESTURES):raise ValueError("Gestos de dedos inválidos.")
    for pose,values in finger_bindings.items():
        if not isinstance(values,dict) or set(values)!=set(FINGER_GESTURES[pose]["bindings"]) or any(type(a) is not str or a not in ACTIONS for a in values.values()):
            raise ValueError("Asignación de dedos inválida.")
    excluded=data.get("excluded_apps",[])
    if not isinstance(excluded,list) or len(excluded)>50:raise ValueError("Lista de aplicaciones inválida.")
    normalized=[]
    for name in excluded:
        if not isinstance(name,str) or not 5<=len(name)<=128 or not name.lower().endswith('.exe') or re.search(r'[\\/:*?"<>|\x00-\x1f]',name):
            raise ValueError("Escribí solo nombres de aplicaciones, por ejemplo notepad.exe.")
        normalized.append(name.strip().lower())
    return {"sensitivity":sensitivity,"calibration":calibration,"invert":invert,"profile":profile,
            "bindings":dict(bindings),"finger_bindings":{k:dict(v) for k,v in finger_bindings.items()},"excluded_apps":sorted(set(normalized)),**validate_productivity(data,ACTIONS)}
