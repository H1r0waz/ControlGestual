"""Decode generated Spanish speech, never open a microphone or execute desktop actions."""
import json
from pathlib import Path
import sys
import wave
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from desktop_voice import create_recognizer,parse_command,result_confidence
extra_path=root/'work/voice-extra.json'
extra=json.loads(extra_path.read_text(encoding='utf-8')) if extra_path.is_file() else {}
from desktop_features import validate_settings
from desktop_productivity import extra_commands
extra={**extra_commands(validate_settings({})),**extra}
recognizer=create_recognizer(root/'voice-model/vosk-model-small-es-0.42',16000,extra)
results=[]
for item in json.loads((root/'work/voice-phrases.json').read_text(encoding='utf-8')):
    recognizer.Reset();texts=[];scores=[]
    with wave.open(str(root/'work/voice-synthetic'/(item.get('sample',item['command'])+'.wav')),'rb') as audio:
        assert audio.getframerate()==16000 and audio.getnchannels()==1 and audio.getsampwidth()==2
        while data:=audio.readframes(2000):
            if recognizer.AcceptWaveform(data):
                result=json.loads(recognizer.Result());texts.append(result.get('text',''));scores.append(result_confidence(result))
    if recognizer.AcceptWaveform(bytes(64000)):
        result=json.loads(recognizer.Result());texts.append(result.get('text',''));scores.append(result_confidence(result))
    result=json.loads(recognizer.FinalResult());texts.append(result.get('text',''));scores.append(result_confidence(result))
    text=' '.join(t for t in texts if t)
    confidence=min((score for score in scores if score is not None),default=0)
    results.append({'expected':item['command'],'heard':text,'confidence':confidence,'passed':parse_command(text,extra)==item['command'] and confidence>=.6})
(root/'work/voice-model-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':sum(r['passed'] for r in results),'total':len(results),'failures':[r for r in results if not r['passed']],'physical_microphone':'not opened'},ensure_ascii=False))
if not all(r['passed'] for r in results):sys.exit(1)
