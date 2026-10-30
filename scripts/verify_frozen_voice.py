"""Verify the packaged speech runtime without microphone access or desktop actions."""
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
arguments=[str(root/'releases/ControlGestual-V5.3/ControlGestual-V5.3.exe'),'--verify-voice']
fixture=root/'work/voice-spanish-test.wav'
if fixture.is_file():arguments+=['--audio-fixture',str(fixture)]
result=subprocess.run(arguments,capture_output=True,text=True,encoding='utf-8',timeout=30)
if result.returncode:raise RuntimeError(result.stderr or 'Falló la verificación del motor de voz.')
state=json.loads(result.stdout)
assert state['voice_model']=='ready' and state['portaudio']=='loaded'
if fixture.is_file():assert state['recognized_action']=='minimize'
print(json.dumps(state))
for sample,expected in [('name-chrome','select_app:chrome.exe'),('name-discord','select_app:discord.exe')]:
    fixture=root/'work/voice-synthetic'/(sample+'.wav')
    result=subprocess.run([arguments[0],'--verify-voice','--audio-fixture',str(fixture)],capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr
    parsed=json.loads(result.stdout);assert parsed['recognized_action']==expected,parsed
    print(json.dumps({'fixture':sample,'recognized_action':parsed['recognized_action'],'physical_microphone':'not opened'}))
