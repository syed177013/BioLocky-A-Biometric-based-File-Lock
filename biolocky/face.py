"""Face detection/matching. All camera + DNN work happens in a worker thread;
the UI only receives small preview frames through a queue."""
import sys
import threading
import time
import queue

import cv2
import numpy as np

FACE = 96
cv2.setNumThreads(2)


def prep(face_bgr) -> np.ndarray:
    g = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (FACE, FACE), interpolation=cv2.INTER_AREA)
    g = cv2.createCLAHE(2.0, (8, 8)).apply(g)
    return cv2.GaussianBlur(g, (3, 3), 0)


def _norm(a):
    a = a.reshape(a.shape[0], -1).astype(np.float32)
    a -= a.mean(axis=1, keepdims=True)
    return a / (a.std(axis=1, keepdims=True) + 1e-6)


class Matcher:
    def __init__(self, templates: np.ndarray):
        self.T = _norm(templates)

    def score(self, face96: np.ndarray) -> float:
        f = _norm(face96[None])[0]
        return float((self.T @ f).max() / f.size)


class Detector:
    _lock = threading.Lock()
    _net = None

    def __init__(self, proto, model):
        self.proto, self.model = str(proto), str(model)

    def _get(self):
        if Detector._net is None:
            Detector._net = cv2.dnn.readNetFromCaffe(self.proto, self.model)
        return Detector._net

    def largest(self, frame, min_conf=0.6):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104, 177, 123))
        with Detector._lock:
            net = self._get()
            net.setInput(blob)
            det = net.forward()[0, 0]
        best = None
        for d in det:
            if d[2] < min_conf:
                continue
            x1, y1, x2, y2 = (d[3:7] * (w, h, w, h)).astype(int)
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
            if x2 - x1 < 40 or y2 - y1 < 40:
                continue
            if best is None or (x2 - x1) * (y2 - y1) > (best[2] - best[0]) * (best[3] - best[1]):
                best = (x1, y1, x2, y2, float(d[2]))
        return best


def crop_square(frame, box, margin=0.08):
    x1, y1, x2, y2 = box[:4]
    h, w = frame.shape[:2]
    cx, cy, s = (x1 + x2) / 2, (y1 + y2) / 2, max(x2 - x1, y2 - y1) * (1 + margin) / 2
    return frame[max(0, int(cy - s)):min(h, int(cy + s)), max(0, int(cx - s)):min(w, int(cx + s))]


def _jpg(img, size=160) -> bytes:
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()


class FaceSession(threading.Thread):
    """mode='enroll' -> done payload {'ok','reason','faces': ndarray}
       mode='verify' -> done payload {'ok','reason','crop': jpg|None}
    Queue messages: ('frame', rgb ndarray 320x240, status, tone) | ('done', payload)"""
    PW, PH = 320, 240

    def __init__(self, detector, q, mode, matcher=None, threshold=0.72, samples=10):
        super().__init__(daemon=True)
        self.det, self.q, self.mode = detector, q, mode
        self.matcher, self.thr, self.samples = matcher, threshold, samples
        self._stop = threading.Event()

    def cancel(self):
        self._stop.set()

    def _put(self, msg):
        if msg[0] == "frame":
            try:
                while self.q.qsize() > 1:
                    self.q.get_nowait()
            except queue.Empty:
                pass
        self.q.put(msg)

    def _open(self):
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if sys.platform.startswith("win") else cv2.VideoCapture(0)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def run(self):
        cap = None
        try:
            self._put(("frame", np.zeros((self.PH, self.PW, 3), np.uint8), "Starting camera…", "info"))
            cap = self._open()
            if not cap.isOpened():
                return self._put(("done", {"ok": False, "reason": "camera"}))
            payload = self._loop(cap)
        except Exception as ex:  # never let the thread die silently
            payload = {"ok": False, "reason": "error", "detail": str(ex)}
        finally:
            if cap is not None:
                cap.release()
        self._put(("done", payload))

    def _loop(self, cap):
        verify = self.mode == "verify"
        t0, n, det, status, tone = time.time(), 0, None, "Looking for your face…", "info"
        timeout = 20 if verify else 60
        match_since = unk_since = last_cap = None
        samples = []
        while not self._stop.is_set():
            now = time.time()
            if now - t0 > timeout:
                return {"ok": False, "reason": "timeout"}
            ok, frame = cap.read()
            if not ok:
                return {"ok": False, "reason": "camera"}
            n += 1
            if n % 3 == 0:
                det = self.det.largest(frame, 0.6 if verify else 0.75)
                if det is None:
                    match_since = unk_since = None
                    status, tone = ("Looking for your face…" if verify else "Face the camera"), "info"
                elif verify:
                    face = crop_square(frame, det)
                    if face.size == 0:
                        continue
                    if self.matcher.score(prep(face)) >= self.thr:
                        unk_since, match_since = None, match_since or now
                        status, tone = "Recognised", "ok"
                        if now - match_since >= 1.2:
                            return {"ok": True, "reason": "match"}
                    else:
                        match_since, unk_since = None, unk_since or now
                        status, tone = "Not recognised", "bad"
                        if now - unk_since >= 2.0:
                            return {"ok": False, "reason": "unknown", "crop": _jpg(face)}
                else:
                    if det[2] - det[0] < 110:
                        status, tone = "Move closer", "info"
                    elif last_cap is None or now - last_cap >= 0.5:
                        face = crop_square(frame, det)
                        if face.size:
                            samples.append(prep(face))
                            last_cap = now
                            status, tone = f"Hold still… {len(samples)}/{self.samples}", "ok"
                            if len(samples) >= self.samples:
                                return {"ok": True, "reason": "enrolled", "faces": np.stack(samples)}
            small = cv2.flip(cv2.resize(frame, (self.PW, self.PH)), 1)
            if det is not None:
                sx, sy = self.PW / frame.shape[1], self.PH / frame.shape[0]
                x1, y1, x2, y2 = int(det[0] * sx), int(det[1] * sy), int(det[2] * sx), int(det[3] * sy)
                color = {"ok": (80, 200, 120), "bad": (220, 80, 70)}.get(tone, (240, 240, 240))
                cv2.rectangle(small, (self.PW - x2, y1), (self.PW - x1, y2), color[::-1], 2)
            self._put(("frame", cv2.cvtColor(small, cv2.COLOR_BGR2RGB), status, tone))
        return {"ok": False, "reason": "cancel"}
