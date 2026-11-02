"""Voice passphrase capture + recognition in a worker thread. Audio is kept in
memory only (the old version wrote an unencrypted .wav to disk)."""
import threading
import time

import numpy as np

RATE, CHUNK = 16000, 1024


class VoiceSession(threading.Thread):
    """Queue messages: ('level', 0..1) | ('state', 'listening'|'processing')
       | ('done', text|None, error|None)"""

    def __init__(self, q, lang="en-IN", max_sec=6.0):
        super().__init__(daemon=True)
        self.q, self.lang, self.max_sec = q, lang, max_sec
        self._stop = threading.Event()

    def cancel(self):
        self._stop.set()

    def run(self):
        try:
            audio = self._record()
            if self._stop.is_set():
                return self.q.put(("done", None, "cancel"))
            if audio is None:
                return self.q.put(("done", None, "No speech detected. Try again."))
            self.q.put(("state", "processing"))
            self.q.put(("done", *self._recognise(audio)))
        except Exception as ex:
            self.q.put(("done", None, f"Microphone error: {ex}"))

    def _record(self):
        import pyaudio
        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                             frames_per_buffer=CHUNK)
            self.q.put(("state", "listening"))
            frames, t0, last_voice, started, noise = [], time.time(), 0.0, False, []
            thr = None
            while not self._stop.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                rms = float(np.sqrt(np.mean(np.frombuffer(data, np.int16).astype(np.float32) ** 2)))
                self.q.put(("level", min(1.0, rms / 5000)))
                now = time.time()
                if len(noise) < 8:
                    noise.append(rms)
                    continue
                if thr is None:
                    thr = max(np.mean(noise), 120) * 2.5 + 200
                if rms > thr:
                    started, last_voice = True, now
                if (started and now - last_voice > 0.9 and now - t0 > 1.2) or now - t0 > self.max_sec:
                    break
            return b"".join(frames) if started else None
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            pa.terminate()

    def _recognise(self, pcm):
        import speech_recognition as sr
        r = sr.Recognizer()
        r.operation_timeout = 10
        try:
            return r.recognize_google(sr.AudioData(pcm, RATE, 2), language=self.lang), None
        except sr.UnknownValueError:
            return None, "Couldn't understand that. Try again."
        except sr.RequestError:
            return None, "Speech service unreachable. Check your internet connection."
