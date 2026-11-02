"""Encrypted vault: key management, index, import/export, temp-file lifecycle.

Design
  * A random 256-bit data key (DEK) encrypts everything. The DEK is stored only
    wrapped: once by a scrypt(passcode) key and once by a scrypt(recovery code) key.
  * Files live in blobs/<id>.blk (always encrypted). Names, thumbnails, voice hash,
    mail settings and the activity log live in one sealed index.
  * Opening a file decrypts it to a private temp folder which is wiped on a timer,
    on lock and on exit. Nothing is ever left decrypted inside the vault folder.
"""
import base64
import getpass
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from . import crypto

b64 = lambda b: base64.b64encode(b).decode()
unb64 = lambda s: base64.b64decode(s)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
SKIP_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}


class VaultError(Exception):
    pass


class BadSecret(VaultError):
    pass


class Throttled(VaultError):
    def __init__(self, wait):
        super().__init__(f"Too many attempts. Try again in {int(wait) + 1}s.")
        self.wait = wait


def shred(path) -> bool:
    """Best-effort overwrite + delete (SSD wear-levelling can't be fully defeated)."""
    p = Path(path)
    try:
        if p.is_file():
            os.chmod(p, 0o600)
            size = p.stat().st_size
            with open(p, "r+b") as f:
                left, z = size, b"\0" * (1 << 20)
                while left > 0:
                    f.write(z[:min(left, len(z))])
                    left -= len(z)
                f.flush()
                os.fsync(f.fileno())
        p.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", os.path.basename(name)).strip(" .")
    return name or "file"


def norm_phrase(t: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", "", t.lower()).split())


def make_thumb(src) -> "bytes | None":
    """Deliberately blurred 96px preview so contents aren't exposed in the grid."""
    try:
        from PIL import Image, ImageFilter
        im = Image.open(src)
        im.draft("RGB", (256, 256))
        im = im.convert("RGB")
        im.thumbnail((96, 96))
        tiny = im.resize((max(1, im.width // 6), max(1, im.height // 6)), Image.BILINEAR)
        im = tiny.resize(im.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return None


class Vault:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.blobs = self.home / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self._kr_path = self.home / "keyring.json"
        self._idx_path = self.home / "index.blob"
        self._faces_path = self.home / "faces.blob"
        self._lock = threading.RLock()
        self._dek = None
        self._idx = None
        self._faces = None
        try:
            user = getpass.getuser()
        except Exception:
            user = "user"
        self.tmp_root = Path(tempfile.gettempdir()) / f"biolocky-{user}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.tmp_root, 0o700)
        except OSError:
            pass
        self._temps = {}
        self.purge_stale_temps()

    # ---------------------------------------------------------------- keyring
    @property
    def exists(self):
        return self._kr_path.exists()

    @property
    def unlocked(self):
        return self._dek is not None

    def _kr(self):
        return json.loads(self._kr_path.read_text("utf-8"))

    def _save_kr(self, kr):
        tmp = self._kr_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(kr), "utf-8")
        os.replace(tmp, self._kr_path)

    @staticmethod
    def _wrap(secret: str, dek: bytes, label: str) -> dict:
        salt = os.urandom(16)
        return {"salt": b64(salt),
                "blob": b64(crypto.seal(crypto.derive(secret.encode(), salt), dek, label.encode()))}

    @staticmethod
    def _unwrap(w: dict, secret: str, label: str):
        try:
            kek = crypto.derive(secret.encode(), unb64(w["salt"]))
            return crypto.unseal(kek, unb64(w["blob"]), label.encode())
        except Exception:
            return None

    def _try(self, kind: str, secret: str):
        """Throttled unwrap. Returns DEK or raises Throttled/BadSecret."""
        with self._lock:
            kr = self._kr()
            wait = kr.get("locked_until", 0) - time.time()
            if wait > 0:
                raise Throttled(wait)
            dek = self._unwrap(kr["wraps"][kind], secret, kind)
            if dek is None:
                kr["fails"] = kr.get("fails", 0) + 1
                if kr["fails"] >= 5:
                    kr["locked_until"] = time.time() + min(900, 15 * 2 ** (kr["fails"] - 5))
                self._save_kr(kr)
                raise BadSecret("Incorrect " + ("passcode" if kind == "pass" else "recovery code"))
            kr["fails"], kr["locked_until"] = 0, 0
            self._save_kr(kr)
            return dek

    def create(self, passcode: str) -> str:
        """Initialise a new vault. Returns the one-time recovery code."""
        if self.exists:
            raise VaultError("Vault already exists")
        dek = os.urandom(32)
        raw = secrets.token_hex(10).upper()
        recovery = "-".join(raw[i:i + 5] for i in range(0, 20, 5))
        kr = {"v": 1, "fails": 0, "locked_until": 0,
              "wraps": {"pass": self._wrap(passcode, dek, "pass"),
                        "recovery": self._wrap(recovery.replace("-", ""), dek, "recovery")}}
        self._save_kr(kr)
        self._dek = dek
        self._idx = {"files": [], "events": [], "voice": None, "mail": {}}
        self._save_index()
        return recovery

    def unlock(self, passcode: str):
        dek = self._try("pass", passcode)
        with self._lock:
            self._dek = dek
            self._load_index()

    def verify(self, passcode: str) -> bool:
        self._try("pass", passcode)
        return True

    def change_passcode(self, old: str, new: str):
        with self._lock:
            dek = self._try("pass", old)
            kr = self._kr()
            kr["wraps"]["pass"] = self._wrap(new, dek, "pass")
            self._save_kr(kr)

    def reset_with_recovery(self, code: str, new_passcode: str):
        dek = self._try("recovery", code.replace("-", "").replace(" ", "").upper())
        with self._lock:
            kr = self._kr()
            kr["wraps"]["pass"] = self._wrap(new_passcode, dek, "pass")
            self._save_kr(kr)
            self._dek = dek
            self._load_index()

    def lock(self):
        with self._lock:
            self._dek = self._idx = self._faces = None
        self.wipe_temps(force=True)

    # ---------------------------------------------------------------- index
    def _need(self):
        if self._dek is None:
            raise VaultError("Vault is locked")
        return self._dek

    def _load_index(self):
        if self._idx_path.exists():
            raw = crypto.unseal(crypto.subkey(self._dek, "index"), self._idx_path.read_bytes())
            self._idx = json.loads(raw)
        else:
            self._idx = {"files": [], "events": [], "voice": None, "mail": {}}

    def _save_index(self):
        data = crypto.seal(crypto.subkey(self._need(), "index"), json.dumps(self._idx).encode())
        tmp = self._idx_path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, self._idx_path)

    def files(self):
        with self._lock:
            self._need()
            return list(self._idx["files"])

    def entry(self, fid):
        for e in self.files():
            if e["id"] == fid:
                return e
        raise VaultError("File not found")

    # ---------------------------------------------------------------- files
    def _fkey(self, fid):
        return crypto.subkey(self._need(), "file:" + fid)

    def ingest(self, name, reader, thumb_src=None, progress=None, times=None):
        key_dek = self._need()
        fid = uuid.uuid4().hex
        key = crypto.subkey(key_dek, "file:" + fid)
        part, final = self.blobs / (fid + ".part"), self.blobs / (fid + ".blk")
        try:
            with open(part, "wb") as out:
                digest = crypto.encrypt_stream(key, reader, out, fid.encode(), progress)
                out.flush()
                os.fsync(out.fileno())
            with open(part, "rb") as chk:   # read-back verification before we trust it
                if crypto.decrypt_stream(key, chk, None, fid.encode()) != digest:
                    raise VaultError("Verification failed")
            size = part.stat().st_size
            os.replace(part, final)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        ext = os.path.splitext(name)[1].lower()
        thumb = make_thumb(thumb_src) if (thumb_src is not None and ext in IMAGE_EXT) else None
        entry = {"id": fid, "name": _safe_name(name), "size": max(0, size - 12 - 16),
                 "added": int(time.time()), "thumb": b64(thumb) if thumb else None}
        if times:
            entry.update(times)
        with self._lock:
            self._idx["files"].append(entry)
            self._save_index()
        return entry

    def import_path(self, path, move=True, progress=None):
        path = Path(path)
        st = path.stat()
        total = st.st_size or 1
        created = getattr(st, "st_birthtime", None) or (st.st_ctime if os.name == "nt" else st.st_mtime)
        times = {"created": int(created), "modified": int(st.st_mtime)}
        with open(path, "rb") as f:
            e = self.ingest(path.name, f, str(path), (lambda d: progress(d / total)) if progress else None, times)
        if move and not shred(path):
            raise VaultError(f"Imported, but couldn't remove the original: {path.name}")
        return e

    def _decrypt_to(self, fid, dest):
        with open(self.blobs / (fid + ".blk"), "rb") as src, open(dest, "wb") as dst:
            crypto.decrypt_stream(self._fkey(fid), src, dst, fid.encode())

    def export(self, fid, dest):
        self.entry(fid)
        self._decrypt_to(fid, dest)

    def open_temp(self, fid, relock_sec) -> Path:
        e = self.entry(fid)
        d = Path(tempfile.mkdtemp(dir=self.tmp_root))
        path = d / _safe_name(e["name"])
        try:
            self._decrypt_to(fid, path)
        except BaseException:
            shred(path)
            d.rmdir()
            raise
        self._temps[str(d)] = time.time() + relock_sec
        return path

    def wipe_temps(self, force=False) -> int:
        now = time.time()
        for d, exp in list(self._temps.items()):
            if force or exp <= now:
                if self._clear_dir(Path(d)):
                    self._temps.pop(d, None)
        return len(self._temps)

    @staticmethod
    def _clear_dir(d: Path) -> bool:
        ok = True
        if d.exists():
            for f in d.iterdir():
                ok = shred(f) and ok
            try:
                d.rmdir()
            except OSError:
                ok = False
        return ok

    def purge_stale_temps(self):
        for d in self.tmp_root.iterdir():
            if d.is_dir() and str(d) not in self._temps:
                self._clear_dir(d)

    def delete(self, fid):
        with self._lock:
            self._need()
            self._idx["files"] = [e for e in self._idx["files"] if e["id"] != fid]
            self._save_index()
        (self.blobs / (fid + ".blk")).unlink(missing_ok=True)

    def delete_many(self, ids):
        ids = set(ids)
        with self._lock:
            self._need()
            self._idx["files"] = [e for e in self._idx["files"] if e["id"] not in ids]
            self._save_index()
        for i in ids:
            (self.blobs / (i + ".blk")).unlink(missing_ok=True)

    # ---------------------------------------------------------------- faces
    @property
    def has_faces(self):
        return self._faces_path.exists()

    def save_faces(self, arr: np.ndarray):
        buf = io.BytesIO()
        np.save(buf, arr.astype(np.uint8), allow_pickle=False)
        data = crypto.seal(crypto.subkey(self._need(), "faces"), buf.getvalue())
        tmp = self._faces_path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, self._faces_path)
        self._faces = arr

    def faces(self):
        if self._faces is None and self.has_faces:
            raw = crypto.unseal(crypto.subkey(self._need(), "faces"), self._faces_path.read_bytes())
            self._faces = np.load(io.BytesIO(raw), allow_pickle=False)
        return self._faces

    # ---------------------------------------------------------------- voice
    @property
    def has_voice(self):
        return bool(self._idx and self._idx.get("voice"))

    def set_voice(self, phrase):
        salt = os.urandom(16)
        h = hmac.new(salt, norm_phrase(phrase).encode(), hashlib.sha256).digest()
        with self._lock:
            self._need()
            self._idx["voice"] = {"salt": b64(salt), "hash": b64(h)}
            self._save_index()

    def check_voice(self, text) -> bool:
        v = self._idx and self._idx.get("voice")
        if not v:
            return False
        h = hmac.new(unb64(v["salt"]), norm_phrase(text).encode(), hashlib.sha256).digest()
        return hmac.compare_digest(h, unb64(v["hash"]))

    # ---------------------------------------------------------------- events / mail
    def add_event(self, kind, message, thumb=None):
        ev = {"t": int(time.time()), "kind": kind, "msg": message, "thumb": b64(thumb) if thumb else None}
        with self._lock:
            self._need()
            self._idx["events"] = ([ev] + self._idx["events"])[:100]
            self._save_index()

    def events(self):
        with self._lock:
            self._need()
            return list(self._idx["events"])

    def clear_events(self):
        with self._lock:
            self._need()
            self._idx["events"] = []
            self._save_index()

    def mail_cfg(self):
        return dict(self._idx.get("mail", {})) if self._idx else {}

    def set_mail_cfg(self, cfg):
        with self._lock:
            self._need()
            self._idx["mail"] = cfg
            self._save_index()
