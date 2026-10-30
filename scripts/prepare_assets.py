"""Download pinned MediaPipe assets into this project, without installing packages."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.2.0"
PACKAGE = f"https://registry.npmjs.org/@mediapipe/tasks-vision/{VERSION}"
MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def main():
    metadata = json.loads(fetch(PACKAGE))
    archive = fetch(metadata["dist"]["tarball"])
    digest = base64.b64encode(hashlib.sha512(archive).digest()).decode()
    if metadata["dist"]["integrity"] != "sha512-" + digest:
        raise RuntimeError("Package integrity check failed")
    destination = ROOT / "extension" / "vendor"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        for member in package.getmembers():
            name = member.name.removeprefix("package/")
            if not (name == "vision_bundle.mjs" or name.startswith("wasm/") and name.endswith((".js", ".wasm"))):
                continue
            target = (destination / name).resolve()
            if not target.is_relative_to(destination.resolve()) or not member.isfile():
                raise RuntimeError("Unsafe package member")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = package.extractfile(member).read()
            target.write_bytes(data)
            records.append({"file": target.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(data).hexdigest()})
    model = fetch(MODEL)
    (destination / "hand_landmarker.task").write_bytes(model)
    records.append({"file": "extension/vendor/hand_landmarker.task", "sha256": hashlib.sha256(model).hexdigest()})
    license_url = "https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE"
    (destination / "LICENSE.mediapipe").write_bytes(fetch(license_url))
    (ROOT / "ASSETS.json").write_text(json.dumps({"package": PACKAGE, "integrity": metadata["dist"]["integrity"],
        "model": MODEL, "license_source": license_url, "files": records}, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(records)} local runtime assets; package SHA-512 verified.")


if __name__ == "__main__":
    main()
