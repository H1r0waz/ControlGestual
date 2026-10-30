"""Bounded local preferences and layout matching for the desktop tools."""
import re
import math
from desktop_voice import normalize,COMMANDS,LEGACY_COMMANDS

DEFAULT_APP_NAMES={'chrome':'chrome.exe','bloc notas':'notepad.exe','codex':'codex.exe'}
ADDITIONAL_APP_NAMES={'discord':'discord.exe','spotify':'spotify.exe','steam':'steam.exe','whatsapp':'whatsapp.exe','explorador':'explorer.exe','edge':'msedge.exe'}

def phrase(value,max_words=5):
    if not isinstance(value,str):raise ValueError('Nombre de voz inválido.')
    value=normalize(value)
    if not re.fullmatch(r'[a-z]+(?: [a-z]+)*',value) or len(value)>48 or len(value.split())>max_words or 'control' in value.split():
        raise ValueError('Usá de una a cinco palabras, sin números, símbolos ni la palabra Control.')
    return value

def executable(value):
    if not isinstance(value,str) or not re.fullmatch(r'[^\\/:*?"<>|\x00-\x1f]{1,124}\.exe',value,re.I):raise ValueError('Aplicación inválida. Usá el nombre del ejecutable.')
    return value.lower()

def validate_productivity(data,actions):
    aliases=data.get('voice_aliases',{});names=data.get('app_names',DEFAULT_APP_NAMES);layouts=data.get('layouts',{})
    if not isinstance(aliases,dict) or len(aliases)>30 or not isinstance(names,dict) or len(names)>20 or not isinstance(layouts,dict) or len(layouts)>10:raise ValueError('Demasiados comandos, nombres o distribuciones.')
    catalog=data.get('app_catalog_version',0)
    if type(catalog) is not int or catalog not in (0,1):raise ValueError('Catálogo de aplicaciones inválido.')
    if catalog==0:
        names=dict(names)
        for name,app in ADDITIONAL_APP_NAMES.items():
            if name not in names and len(names)<20:names[name]=app
    clean_aliases={};allowed=set(actions)|set(COMMANDS.values())
    for name,action in aliases.items():
        name=phrase(name)
        if name in COMMANDS or name in LEGACY_COMMANDS or name.startswith(('seleccionar ','modo ')) or name in clean_aliases:raise ValueError('Esa frase está reservada o repetida.')
        if type(action) is not str or action not in allowed:raise ValueError('Acción personalizada inválida.')
        clean_aliases[name]=action
    clean_names={}
    for name,app in names.items():
        name=phrase(name,3)
        if name in clean_names:raise ValueError('Nombre de aplicación repetido.')
        clean_names[name]=executable(app)
    clean_layouts={}
    for name,slots in layouts.items():
        name=phrase(name,3)
        if name in clean_layouts or not isinstance(slots,list) or not 1<=len(slots)<=8:raise ValueError('Distribución inválida; elegí de una a ocho ventanas.')
        entries=[]
        for slot in slots:
            if not isinstance(slot,dict):raise ValueError('Ventana guardada inválida.')
            app=executable(slot.get('app'));title=slot.get('title');display=slot.get('display');index=slot.get('monitor_index');maximized=slot.get('maximized')
            if not isinstance(title,str) or len(title)>200 or not isinstance(display,str) or len(display)>128 or type(index) is not int or not 0<=index<16 or type(maximized) is not bool:raise ValueError('Datos de distribución inválidos.')
            rect={k:slot.get(k) for k in ('left','top','width','height')}
            if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in rect.values()) or rect['width']<.05 or rect['height']<.05:raise ValueError('Tamaño de distribución inválido.')
            entries.append(dict(app=app,title=title,display=display,monitor_index=index,maximized=maximized,**rect))
        clean_layouts[name]=entries
    sound=data.get('audio_feedback',False)
    if type(sound) is not bool:raise ValueError('Ajuste de sonido inválido.')
    spoken=data.get('spoken_replies',False)
    if type(spoken) is not bool:raise ValueError('Ajuste de respuestas habladas inválido.')
    return dict(voice_aliases=clean_aliases,app_names=clean_names,layouts=clean_layouts,audio_feedback=sound,spoken_replies=spoken,app_catalog_version=1)

def extra_commands(settings):
    bare={name:'select_app:'+app for name,app in settings['app_names'].items() if name not in COMMANDS and name not in LEGACY_COMMANDS and name not in settings['voice_aliases']}
    return {**bare,**settings['voice_aliases'],**{'seleccionar '+name:'select_app:'+app for name,app in settings['app_names'].items()},**{'modo '+name:'layout:'+name for name in settings['layouts']}}

def match_layout(slots,windows,displays,excluded):
    result=[];used=set()
    for slot in slots:
        candidates=[w for w in windows if w.get('app','').lower()==slot['app'] and w['hwnd'] not in used]
        exact=[w for w in candidates if w['title']==slot['title']]
        if slot['app'] in excluded:raise ValueError('La distribución incluye una aplicación excluida: '+slot['app'])
        target=exact[0] if len(exact)==1 else candidates[0] if len(candidates)==1 else None
        if target is None:raise ValueError('Abrí la ventana guardada o resolvé las ventanas repetidas: '+slot['title'])
        display=next((d for d in displays if d.get('name')==slot['display']),None)
        if display is None:raise ValueError('La pantalla guardada no está conectada. Volvé a guardar la distribución.')
        area=display['workArea'];width=max(1,round(area['width']*slot['width']));height=max(1,round(area['height']*slot['height']))
        bounds=dict(left=area['left']+min(round(area['width']*slot['left']),area['width']-width),top=area['top']+min(round(area['height']*slot['top']),area['height']-height),width=width,height=height)
        result.append((target,bounds,slot['maximized']));used.add(target['hwnd'])
    return result
