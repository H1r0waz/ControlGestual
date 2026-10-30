"""Decode synthetic free speech without microphone or desktop actions."""
from pathlib import Path
import json,sys,wave
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from desktop_voice import create_recognizer,parse_command,result_confidence,recognition_score
recognizer=create_recognizer(root/'voice-model/vosk-model-small-es-0.42',16000,free=True)
rows=[]
for sample,expected in [('free-question',True),('free-maximize',True),('free-long',True),('assistant-help',False)]:
    recognizer.Reset();parts=[];scores=[]
    with wave.open(str(root/'work/voice-synthetic'/(sample+'.wav')),'rb') as audio:
        while data:=audio.readframes(2000):
            if recognizer.AcceptWaveform(data):parts.append(json.loads(recognizer.Result()))
    recognizer.AcceptWaveform(bytes(64000));parts.append(json.loads(recognizer.FinalResult()))
    text=' '.join(p.get('text','') for p in parts).strip()
    complete={'text':text,'result':[word for p in parts for word in p.get('result',[])]}
    confidence,mode=recognition_score(complete,free=True)
    passed=bool(parse_command(text,free=True)) and confidence is not None and confidence>=(.8 if mode=='phrase' else .6)
    rows.append({'sample':sample,'heard':text,'confidence':confidence,'mode':mode,'eligible_for_request':passed,'expected_eligible':expected,'passed':passed==expected})
(root/'work/free-voice-check.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False))
if not all(row['passed'] for row in rows):raise SystemExit(1)
