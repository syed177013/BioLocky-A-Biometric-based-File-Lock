"""One-time import from the pre-2.0 layout (files/*.enc + Fernet keys, faces/, user/, intruders/)."""
import io
import json
from pathlib import Path

import cv2
import numpy as np
from cryptography.fernet import Fernet

from . import face
from .vault import SKIP_NAMES, shred


def _items(root: Path):
    d = root / "files"
    if not d.is_dir():
        return []
    return [p for p in d.iterdir() if p.is_file() and p.name.lower() not in SKIP_NAMES]


def count(root: Path) -> int:
    n = len(_items(root))
    fd = root / "faces"
    n += len([p for p in fd.glob("*.jpg")]) if fd.is_dir() else 0
    return n


def migrate(vault, root: Path, progress=None) -> dict:
    """Move legacy data into the vault. A legacy file is shredded only after verified import."""
    out = {"files": 0, "faces": 0, "failed": []}
    fernet = None
    kf = root / "encryption_keys.json"
    if kf.exists():
        fernet = Fernet(kf.read_bytes().strip())
    items = _items(root)
    for i, p in enumerate(items):
        try:
            if p.suffix == ".enc":
                if fernet is None:
                    raise ValueError("legacy key missing")
                data = fernet.decrypt(p.read_bytes())
                name = p.name[:-4]
            else:
                data, name = p.read_bytes(), p.name
            vault.ingest(name, io.BytesIO(data), io.BytesIO(data))
            shred(p)
            out["files"] += 1
        except Exception as ex:
            out["failed"].append(f"{p.name}: {ex}")
        if progress:
            progress((i + 1) / max(1, len(items)))
    fd = root / "faces"
    if fd.is_dir() and not vault.has_faces:
        crops = [cv2.imread(str(p)) for p in sorted(fd.glob("*.jpg"))]
        crops = [face.prep(c) for c in crops if c is not None and c.size]
        if crops:
            vault.save_faces(np.stack(crops))
            out["faces"] = len(crops)
            for p in fd.glob("*.jpg"):
                shred(p)
    # legacy passphrase (Fernet key sat next to the ciphertext)
    u = root / "user"
    try:
        if (u / "passphrase.txt").exists() and (u / "secret.key").exists() and not vault.has_voice:
            phrase = Fernet((u / "secret.key").read_bytes().strip()).decrypt((u / "passphrase.txt").read_bytes()).decode()
            vault.set_voice(phrase)
        for n in ("passphrase.txt", "passphrase.wav", "auth_sample.wav", "secret.key"):
            shred(u / n)
    except Exception as ex:
        out["failed"].append(f"voice passphrase: {ex}")
    if not out["failed"]:  # old key/PIN material is only removed when everything imported
        for n in ("encryption_keys.json", "encryption_details.json", "pin.key", "pin.dat"):
            shred(root / n)
    return out
