"""Cryptographic primitives: AES-256-GCM streaming, scrypt KDF, key wrapping.

File format (BLK1): magic | 8-byte nonce prefix | chunks.
Each chunk is AES-GCM sealed with nonce = prefix||counter and AAD = file-id||final-flag,
so reordering, truncation and cross-file swaps are all detected.
"""
import hashlib
import hmac
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"BLK1"
CHUNK = 1 << 20
TAG = 16
SCRYPT_N = 2 ** 15


def derive(secret: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=8, p=1).derive(secret)


def subkey(master: bytes, label: str) -> bytes:
    return hmac.new(master, b"blk-sub:" + label.encode(), hashlib.sha256).digest()


def seal(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def unseal(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def encrypt_stream(key, src, dst, aad=b"", progress=None) -> str:
    """Encrypt src->dst. Returns SHA-256 of the plaintext."""
    aead, prefix, h, i, done = AESGCM(key), os.urandom(8), hashlib.sha256(), 0, 0
    dst.write(MAGIC + prefix)
    buf = src.read(CHUNK)
    while True:
        nxt = src.read(CHUNK)
        final = not nxt
        dst.write(aead.encrypt(prefix + struct.pack(">I", i), buf,
                               aad + (b"\x01" if final else b"\x00")))
        h.update(buf)
        done += len(buf)
        i += 1
        if progress:
            progress(done)
        if final:
            return h.hexdigest()
        buf = nxt


def decrypt_stream(key, src, dst=None, aad=b"") -> str:
    """Decrypt src->dst (dst may be None to just verify). Returns plaintext SHA-256."""
    head = src.read(12)
    if len(head) != 12 or head[:4] != MAGIC:
        raise ValueError("Not a BioLocky file")
    aead, prefix, h, i = AESGCM(key), head[4:], hashlib.sha256(), 0
    buf = src.read(CHUNK + TAG)
    while True:
        nxt = src.read(CHUNK + TAG)
        final = not nxt
        plain = aead.decrypt(prefix + struct.pack(">I", i), buf,
                             aad + (b"\x01" if final else b"\x00"))
        h.update(plain)
        if dst is not None:
            dst.write(plain)
        i += 1
        if final:
            return h.hexdigest()
        buf = nxt
