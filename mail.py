import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import time
import traceback
import atexit
import signal
import sys

# ================= CONFIG =================

SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

EMAIL_ADDRESS = '' 
EMAIL_PASSWORD = ''   

RECIPIENT_EMAIL = '' 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INTRUDERS_FOLDER = os.path.join(BASE_DIR, 'intruders')
LOG_FILE = os.path.join(BASE_DIR, 'mail_debug.log')

# ==========================================


def log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")

def handle_termination(sugnum,frame):
    log(f"mail.py received Termination signal : {signum}")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_termination)
signal.signal(signal.SIGINT, handle_termination)

def log_exit():
    log("mail.py is exiting normally")

atexit.register(log_exit)

def send_intruder_alert(image_path):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = '🚨 BioLocky Intruder Alert'

        body = (
            "An unsuccessful biometric authorization attempt has been detected.\n\n"
            "Please find the intruder image attached for verification."
        )
        msg.attach(MIMEText(body, 'plain'))

        with open(image_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())

        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="{os.path.basename(image_path)}"'
        )
        msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
        server.quit()

        log(f"Email sent successfully for: {os.path.basename(image_path)}")

    except Exception as e:
        log("EMAIL SEND FAILED")
        log(str(e))
        log(traceback.format_exc())


def monitor_intruders_folder():
    os.makedirs(INTRUDERS_FOLDER, exist_ok=True)
    log("mail.py started — monitoring intruders folder")

    seen_files = set(os.listdir(INTRUDERS_FOLDER))

    while True:
        try:
            current_files = set(os.listdir(INTRUDERS_FOLDER))
            new_files = current_files - seen_files

            for filename in new_files:
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    full_path = os.path.join(INTRUDERS_FOLDER, filename)
                    log(f"New intruder image detected: {filename}")
                    send_intruder_alert(full_path)

            seen_files = current_files

        except Exception as e:
            log("FOLDER MONITOR ERROR")
            log(str(e))
            log(traceback.format_exc())

        time.sleep(10)


if __name__ == "__main__":
    try:
        monitor_intruders_folder()
    except KeyboardInterrupt:
        log("mail.py stopped manually")
