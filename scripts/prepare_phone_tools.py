"""Fetch the official portable Windows tools, verify and keep them inside the project."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile
root=Path(__file__).resolve().parents[1]
url='https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy-win64-v5.0.1.zip'
expected='b12a2c4ee8be317422451fc7dcf8ee20a71b5ea7ef9ad73ddd825a25316227a5'
archive=root/'work/scrcpy-win64-v5.0.1.zip';archive.parent.mkdir(exist_ok=True)
if not archive.is_file():urllib.request.urlretrieve(url,archive)
if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:raise ValueError('El archivo descargado no coincide con el SHA-256 oficial.')
target=root/'phone-tools';target.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as package:
    for member in package.infolist():
        if not (target/member.filename).resolve().is_relative_to(target.resolve()):raise ValueError('Ruta de archivo inválida.')
    package.extractall(target)
manifest={'source':url,'sha256':expected,'hash_source':'https://github.com/Genymobile/scrcpy/blob/master/doc/windows.md',
    'files':[{'file':str(p.relative_to(target)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(target.rglob('*')) if p.is_file()]}
(root/'PHONE_ASSETS.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'phone_tools':'scrcpy 5.0.1 portable','archive_bytes':archive.stat().st_size,'hash':'verified','files':len(manifest['files'])}))
