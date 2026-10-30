"""Package the portable release without local settings or Android pairing keys."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'releases/ControlGestual-V5.3'
OUTPUT=Path(r'C:\Users\titiv\Documents\Codex\2026-10-29\se-x20\outputs')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

for name in ['THIRD_PARTY_LICENSES','Python-LICENSE.txt','PyInstaller-COPYING.txt','Vosk-LICENSE.txt']:
    source=ROOT/'releases/ControlGestual-V4.0'/name
    if source.is_dir():shutil.copytree(source,RELEASE/name,dirs_exist_ok=True)
    else:shutil.copy2(source,RELEASE/name)
for source,target in [('README.md','LEEME.md'),('VERIFICATION.md','VERIFICACION.md'),('ASSETS.json','ASSETS.json'),('VOICE_ASSETS.json','VOICE_ASSETS.json'),('PHONE_ASSETS.json','PHONE_ASSETS.json')]:
    shutil.copy2(ROOT/source,RELEASE/target)
notice=(ROOT/'releases/ControlGestual-V4.0/THIRD_PARTY.txt').read_text(encoding='utf-8').replace('4.0.0','5.3.0')
notice+='\nTeléfono: distribución oficial portable scrcpy 5.0.1 de Genymobile, con ADB 37.0.1, SDL y FFmpeg. Procedencia y hashes en PHONE_ASSETS.json. Se conserva el archivo LICENSE.txt y todos los componentes de la distribución original en _internal/phone-tools/scrcpy-win64-v5.0.1.\n'
notice+='\nRespuestas habladas: System.Speech y Windows PowerShell instalados en Windows; no se redistribuyen esos componentes ni voces del sistema. No hay un servicio TTS remoto.\n'
(RELEASE/'THIRD_PARTY.txt').write_text(notice,encoding='utf-8')
for source in (ROOT/'desktop').iterdir():
    assert digest(source)==digest(RELEASE/'_internal/desktop'/source.name),source.name
for asset in json.loads((ROOT/'PHONE_ASSETS.json').read_text())['files']:
    assert digest(RELEASE/'_internal/phone-tools'/asset['file'])==asset['sha256'],asset['file']
for asset in json.loads((ROOT/'VOICE_ASSETS.json').read_text())['files']:
    relative=Path(asset['file'])
    assert digest(RELEASE/'_internal/voice-model'/relative)==asset['sha256'],relative
files=[p for p in RELEASE.rglob('*') if p.is_file() and 'phone-private' not in p.relative_to(RELEASE).parts and p.name not in {'settings.json','RELEASE_MANIFEST.json'}]
manifest={'version':'5.3.0','date':'2026-10-30','platform':'Windows x64','voice_assets':'VOICE_ASSETS.json','phone_assets':'PHONE_ASSETS.json','files':[{'path':p.relative_to(RELEASE).as_posix(),'sha256':digest(p)} for p in sorted(files)]}
(RELEASE/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
files.append(RELEASE/'RELEASE_MANIFEST.json')
OUTPUT.mkdir(parents=True,exist_ok=True)
archive=OUTPUT/'ControlGestual-5.3.0-Windows-x64.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
    for p in files:bundle.write(p,Path(RELEASE.name)/p.relative_to(RELEASE))
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    assert all('phone-private' not in Path(name).parts and Path(name).name!='settings.json' for name in bundle.namelist())
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'files':len(files),'sha256':digest(archive),'phone_tools':'16 verified hashes','private_data':'excluded'}))
