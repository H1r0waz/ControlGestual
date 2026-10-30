"""Download the Spanish Vosk model once; runtime always uses an explicit local path."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

root=Path(__file__).resolve().parents[1]
url="https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
archive=root/"work/vosk-model-small-es-0.42.zip"
archive.parent.mkdir(exist_ok=True)
if not archive.is_file():urllib.request.urlretrieve(url,archive)
target=root/"voice-model";target.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as package:
    for member in package.infolist():
        if not (target/member.filename).resolve().is_relative_to(target.resolve()):raise ValueError("Ruta del modelo inválida.")
    package.extractall(target)
manifest={"source":url,"license":"Apache-2.0","license_source":"https://alphacephei.com/vosk/models","archive_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
    "files":[{"file":str(p.relative_to(target)).replace('\\','/'),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(target.rglob('*')) if p.is_file()]}
(root/"VOICE_ASSETS.json").write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({"voice_model":"vosk-model-small-es-0.42","bytes":archive.stat().st_size,"files":len(manifest['files'])}))
