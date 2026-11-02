"""Intruder e-mail alerts, sent from a short-lived thread (no polling subprocess)."""
import smtplib
import threading
from email.message import EmailMessage


def configured(cfg: dict) -> bool:
    return bool(cfg.get("enabled") and all(cfg.get(k) for k in ("server", "user", "password", "to")))


def send_async(cfg, jpg, done):
    """done(ok: bool, message: str) is called from the worker thread."""
    def work():
        try:
            m = EmailMessage()
            m["From"], m["To"], m["Subject"] = cfg["user"], cfg["to"], "BioLocky intruder alert"
            m.set_content("An unsuccessful face-unlock attempt was detected. The captured face is attached.")
            if jpg:
                m.add_attachment(jpg, maintype="image", subtype="jpeg", filename="intruder.jpg")
            with smtplib.SMTP(cfg["server"], int(cfg.get("port") or 587), timeout=20) as s:
                s.starttls()
                s.login(cfg["user"], cfg["password"])
                s.send_message(m)
            done(True, "Alert e-mail sent")
        except Exception as ex:
            done(False, f"Alert e-mail failed: {ex}")
    threading.Thread(target=work, daemon=True).start()
