"""Compare 5.1 free recognition with command grammar on synthetic application names."""
from pathlib import Path
import json,sys,wave
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from desktop_voice import create_recognizer,parse_command,result_confidence
from desktop_features import validate_settings
from desktop_productivity import extra_commands
old_extra={'seleccionar chrome':'select_app:chrome.exe','seleccionar bloc notas':'select_app:notepad.exe','seleccionar codex':'select_app:codex.exe'}
new_extra=extra_commands(validate_settings({}))
old=create_recognizer(root/'voice-model/vosk-model-small-es-0.42',16000,old_extra,free=True)
new=create_recognizer(root/'voice-model/vosk-model-small-es-0.42',16000,new_extra)
rows=[]
for sample in json.loads((root/'work/app-name-samples.json').read_text(encoding='utf-8')):
    row={'phrase':sample['phrase'],'expected_app':sample['app']}
    for key,recognizer,extra,free in [('before',old,old_extra,True),('after',new,new_extra,False)]:
        recognizer.Reset();parts=[]
        with wave.open(str(root/'work/voice-synthetic'/(sample['file']+'.wav')),'rb') as audio:
            while data:=audio.readframes(2000):
                if recognizer.AcceptWaveform(data):parts.append(json.loads(recognizer.Result()))
        recognizer.AcceptWaveform(bytes(64000));parts.append(json.loads(recognizer.FinalResult()))
        text=' '.join(part.get('text','') for part in parts).strip()
        confidence=min((result_confidence(part) for part in parts if result_confidence(part) is not None),default=0)
        row[key]={'heard':text,'confidence':confidence,'direct_app_selection':parse_command(text,extra,free=free)=='select_app:'+sample['app'] and confidence>=.6}
    rows.append(row)
report={'before_direct':sum(r['before']['direct_app_selection'] for r in rows),'after_direct':sum(r['after']['direct_app_selection'] for r in rows),'total':len(rows),'rows':rows,'physical_microphone':'not opened','desktop_actions_executed':0}
(root/'work/app-voice-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
if not all(r['after']['direct_app_selection'] for r in rows):raise SystemExit(1)
