import queue
import tkinter as tk
from collections import deque

import customtkinter as ctk
from PIL import Image, ImageTk

from ..vault import BadSecret, Throttled
from .. import face as facemod
from ..voice import VoiceSession
from .theme import TOK, col
from .widgets import Btn, Field, Sheet

FACE_MSG = {
    "camera": "Couldn’t access the camera. Check that it’s connected and allowed.",
    "timeout": "No face was found in time.",
    "unknown": "Face not recognised.",
}
TONE = {"ok": "accent", "bad": "danger", "info": "muted"}


def err_text(ex):
    return str(ex) if isinstance(ex, (BadSecret, Throttled)) else f"Something went wrong: {ex}"


# ---------------------------------------------------------------- generic
def info(app, title, msg, button="OK"):
    sh = Sheet(app, title, 400, 210)
    sh.label(msg, "muted")
    sh.add_button(button, sh.close, "primary")


def confirm(app, title, msg, ok_label, on_ok, danger=False, cancel_label="Cancel"):
    sh = Sheet(app, title, 400, 210)
    sh.label(msg, "muted")
    sh.add_button(cancel_label, sh.close)

    def go():
        sh.close(cancel=False)
        on_ok()
    sh.add_button(ok_label, go, "danger" if danger else "primary")


def show_recovery(app, code, on_done=None):
    sh = Sheet(app, "Save your recovery code", 440, 300)
    sh.label("This is the only way back in if you forget your passcode. "
             "It is shown once. Write it down and keep it somewhere safe.", "muted")
    ctk.CTkLabel(sh.body, text=code, font=ctk.CTkFont(family="Courier", size=20, weight="bold"),
                 text_color=TOK["text"], fg_color=TOK["field"], corner_radius=8, height=48
                 ).pack(fill="x", pady=10)

    def copy():
        app.clipboard_clear()
        app.clipboard_append(code)
        app.toast("Copied. Paste it somewhere safe.")
    sh.add_button("Copy", copy)
    sh.add_button("I’ve saved it", lambda: (sh.close(cancel=False), on_done and on_done()), "primary")
    sh.on_close = None


def ask_passcode(app, title, on_ok, message="Enter your passcode to continue."):
    sh = Sheet(app, title, 400, 250)
    sh.label(message, "muted")
    e = Field(sh.body, app.fonts, show="•", placeholder="Passcode")
    e.pack(pady=8)
    msg = sh.label("", "danger", app.fonts.small, pady=0)
    e.focus_set()

    def go(_=None):
        pw = e.get()
        if not pw:
            return
        ok_btn.configure(state="disabled")
        msg.configure(text="Checking…", text_color=TOK["muted"])
        app.bg.run(lambda: app.vault.verify(pw), lambda _: (sh.close(cancel=False), on_ok()),
                   lambda ex: (msg.configure(text=err_text(ex), text_color=TOK["danger"]),
                               ok_btn.configure(state="normal"), e.delete(0, "end")))
    e.bind("<Return>", go)
    sh.add_button("Cancel", sh.close)
    ok_btn = sh.add_button("Continue", go, "primary")


def change_passcode(app):
    sh = Sheet(app, "Change passcode", 400, 380)
    fields = []
    for ph in ("Current passcode", "New passcode (6+ characters)", "Confirm new passcode"):
        f = Field(sh.body, app.fonts, show="•", placeholder=ph)
        f.pack(pady=5)
        fields.append(f)
    fields[0].focus_set()
    msg = sh.label("", "danger", app.fonts.small, pady=0)

    def go(_=None):
        old, new, conf = (f.get() for f in fields)
        if len(new) < 6:
            return msg.configure(text="New passcode must be at least 6 characters.")
        if new != conf:
            return msg.configure(text="New passcodes don’t match.")
        btn.configure(state="disabled")
        msg.configure(text="Updating…", text_color=TOK["muted"])
        app.bg.run(lambda: app.vault.change_passcode(old, new),
                   lambda _: (sh.close(cancel=False), app.toast("Passcode updated")),
                   lambda ex: (msg.configure(text=err_text(ex), text_color=TOK["danger"]),
                               btn.configure(state="normal")))
    fields[2].bind("<Return>", go)
    sh.add_button("Cancel", sh.close)
    btn = sh.add_button("Update", go, "primary")


def mail_config(app):
    cfg = app.vault.mail_cfg()
    sh = Sheet(app, "Intruder alerts", 440, 470)
    sh.label("E-mail yourself a photo when someone fails face unlock. "
             "For Gmail use an App Password, not your normal one.", "muted", app.fonts.small)
    rows = {}
    for key, ph, show in (("server", "SMTP server (smtp.gmail.com)", None), ("port", "Port (587)", None),
                          ("user", "Sender e-mail", None), ("password", "App password", "•"),
                          ("to", "Send alerts to", None)):
        f = Field(sh.body, app.fonts, show=show, placeholder=ph, width=300)
        f.pack(pady=4)
        if cfg.get(key):
            f.insert(0, str(cfg[key]))
        rows[key] = f
    en = ctk.CTkSwitch(sh.body, text="Enable alerts", font=app.fonts.body, text_color=TOK["text"],
                       progress_color=TOK["accent"], fg_color=TOK["line"])
    en.pack(pady=10)
    if cfg.get("enabled"):
        en.select()

    def save():
        new = {k: f.get().strip() for k, f in rows.items()} | {"enabled": bool(en.get())}
        app.bg.run(lambda: app.vault.set_mail_cfg(new), lambda _: app.toast("Alert settings saved"))
        sh.close(cancel=False)
    sh.add_button("Cancel", sh.close)
    sh.add_button("Save", save, "primary")


def help_sheet(app):
    sh = Sheet(app, "BioLocky Help", 480, 470)
    txt = ("Files you add are encrypted with AES-256 and moved into the vault. Originals are removed "
           "after the encrypted copy has been verified.\n\n"
           "Double-click a file to unlock it with your face, or right-click for voice passphrase "
           "or passcode. The file is decrypted to a private temporary folder and wiped again after "
           "the re-lock time, when the vault locks, and when you quit.\n\n"
           "Set up Face Unlock and a Voice Passphrase in Settings. Both need your passcode.\n\n"
           "Voice recognition uses Google’s speech service, so audio is sent online for transcription. "
           "It is never stored on disk.\n\n"
           "Keep your recovery code safe. Without the passcode or recovery code, data cannot be recovered.")
    l = ctk.CTkLabel(sh.body, text=txt, font=app.fonts.body, text_color=TOK["muted"], justify="left",
                     wraplength=int(410 * app.scale))
    l.pack(anchor="w")
    sh.add_button("Close", sh.close, "primary")


# ---------------------------------------------------------------- biometrics
class FaceSheet(Sheet):
    def __init__(self, app, mode, on_ok):
        super().__init__(app, "Set up Face Unlock" if mode == "enroll" else "Face Unlock", 400, 420)
        self.mode, self.on_ok = mode, on_ok
        self.preview = tk.Label(self.body, bd=0, bg=col("field"), width=320, height=240)
        self.preview.pack(pady=(0, 8))
        self.photo = None
        self.status = self.label("Starting camera…", "muted", pady=0)
        self.cancel_btn = self.add_button("Cancel", self.close)
        self.retry_btn = None
        self.on_close = self._stop
        self.session = None
        self.after(260, self.start)  # let the slide finish before heavy work begins

    def _stop(self):
        if self.session:
            self.session.cancel()

    def start(self):
        if not self.winfo_exists():
            return
        v, a = self.app.vault, self.app
        matcher = None
        if self.mode == "verify":
            matcher = facemod.Matcher(v.faces())
        self.q = queue.Queue()
        det = facemod.Detector(a.res / "deploy.prototxt.txt", a.res / "res10_300x300_ssd_iter_140000.caffemodel")
        self.session = facemod.FaceSession(det, self.q, self.mode, matcher, a.settings.get("face_threshold"))
        self.session.start()
        if self.retry_btn:
            self.retry_btn.destroy()
            self.retry_btn = None
        self._poll()

    def _poll(self):
        if not self.winfo_exists():
            return
        frame = done = None
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "frame":
                    frame = m
                else:
                    done = m[1]
                    break
        except queue.Empty:
            pass
        if frame:
            img = Image.fromarray(frame[1])
            if self.photo is None:
                self.photo = ImageTk.PhotoImage(img)
                self.preview.configure(image=self.photo, width=0, height=0)
            else:
                self.photo.paste(img)
            self.status.configure(text=frame[2], text_color=TOK[TONE[frame[3]]])
        if done:
            return self._finish(done)
        self.after(33, self._poll)

    def _finish(self, r):
        a = self.app
        if r["ok"]:
            if self.mode == "enroll":
                a.bg.run(lambda: a.vault.save_faces(r["faces"]),
                         lambda _: (self.close(cancel=False), a.toast("Face Unlock is ready"), a.refresh_settings()),
                         lambda ex: self._fail(err_text(ex)))
            else:
                a.log_event("granted", "File unlocked with face")
                self.close(cancel=False)
                self.on_ok()
            return
        if r["reason"] == "cancel":
            return
        if r["reason"] == "unknown":
            a.intruder(r.get("crop"))
        self._fail(FACE_MSG.get(r["reason"], r.get("detail", "Face unlock failed.")))

    def _fail(self, text):
        self.status.configure(text=text, text_color=TOK["danger"])
        self.session = None
        if self.retry_btn is None:
            self.retry_btn = self.add_button("Try Again", self.start, "primary")


class VoiceSheet(Sheet):
    BARS = 28

    def __init__(self, app, mode, on_ok):
        super().__init__(app, "Record Passphrase" if mode == "enroll" else "Voice Unlock", 400, 330)
        self.mode, self.on_ok, self.heard = mode, on_ok, None
        self.hist = deque([0.0] * self.BARS, maxlen=self.BARS)
        w, h = int(300 * self.s), int(70 * self.s)
        self.meter = tk.Canvas(self.body, width=w, height=h, bd=0, highlightthickness=0, bg=col("card"))
        self.meter.pack(pady=(4, 6))
        self.status = self.label("Preparing microphone…", "muted", pady=2)
        self.text = self.label("", "text", app.fonts.bold, pady=2)
        self.cancel_btn = self.add_button("Cancel", self.close)
        self.extra = []
        self.on_close = lambda: self.session and self.session.cancel()
        self.session = None
        self.after(200, self.start)

    def start(self):
        if not self.winfo_exists():
            return
        for b in self.extra:
            b.destroy()
        self.extra = []
        self.text.configure(text="")
        self.q = queue.Queue()
        self.session = VoiceSession(self.q, self.app.settings.get("voice_lang"))
        self.session.start()
        self._poll()

    def _paint(self):
        c, s = self.meter, self.s
        c.delete("all")
        w, h = int(300 * s), int(70 * s)
        bw = w / self.BARS
        for i, v in enumerate(self.hist):
            bh = max(3 * s, v * h)
            c.create_rectangle(i * bw + 2, (h - bh) / 2, (i + 1) * bw - 2, (h + bh) / 2,
                               fill=col("accent") if v > 0.05 else col("line"), outline="")

    def _poll(self):
        if not self.winfo_exists():
            return
        done = None
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "level":
                    self.hist.append(m[1])
                elif m[0] == "state":
                    self.status.configure(text="Speak now…" if m[1] == "listening" else "Recognising…")
                else:
                    done = m
                    break
        except queue.Empty:
            pass
        self._paint()
        if done:
            return self._finish(done[1], done[2])
        self.after(40, self._poll)

    def _retry(self):
        self.extra.append(self.add_button("Try Again", self.start, "primary"))

    def _finish(self, text, error):
        a = self.app
        self.session = None
        if error == "cancel":
            return
        if error:
            self.status.configure(text=error, text_color=TOK["danger"])
            return self._retry()
        if self.mode == "enroll":
            self.status.configure(text="Is this your passphrase?", text_color=TOK["muted"])
            self.text.configure(text=f"“{text}”")
            self.extra.append(self.add_button("Retry", self.start))

            def save():
                a.bg.run(lambda: a.vault.set_voice(text),
                         lambda _: (self.close(cancel=False), a.toast("Voice passphrase saved"), a.refresh_settings()))
            self.extra.append(self.add_button("Use This", save, "primary"))
        elif a.vault.check_voice(text):
            a.log_event("granted", "File unlocked with voice")
            self.close(cancel=False)
            self.on_ok()
        else:
            a.log_event("denied", "Voice passphrase did not match")
            self.status.configure(text="Passphrase didn’t match.", text_color=TOK["danger"])
            self._retry()
