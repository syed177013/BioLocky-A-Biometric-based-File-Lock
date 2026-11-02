import os
import wave
import pyaudio
import speech_recognition as sr
from cryptography.fernet import Fernet
import tkinter as tk
import tkinter.messagebox as msgbox

# Get the directory where the script is located
script_dir = os.path.dirname(__file__)

# Ensure user directory exists in the same location as the script
user_dir = os.path.join(script_dir, "user")
os.makedirs(user_dir, exist_ok=True)

# File paths
audio_file = os.path.join(user_dir, "passphrase.wav")
text_file = os.path.join(user_dir, "passphrase.txt")
key_file = os.path.join(user_dir, "secret.key")

# Generate and save a key if it does not exist
if not os.path.exists(key_file):
    key = Fernet.generate_key()
    with open(key_file, 'wb') as f:
        f.write(key)
else:
    with open(key_file, 'rb') as f:
        key = f.read()

cipher_suite = Fernet(key)

def record_audio(file_path, duration=3):
    chunk = 1024
    format = pyaudio.paInt16
    channels = 1
    rate = 44100
    p = pyaudio.PyAudio()

    # Create a new Tk instance to avoid the empty window
    speak_now_window = tk.Tk()
    speak_now_window.title("Speak Now")
    label = tk.Label(speak_now_window, text="Please speak your passphrase now...")
    label.pack(padx=20, pady=20)

    speak_now_window.update()  # Ensure window is shown immediately

    stream = p.open(format=format, channels=channels,
                    rate=rate, input=True,
                    frames_per_buffer=chunk)

    frames = []
    for _ in range(0, int(rate / chunk * duration)):
        data = stream.read(chunk)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(p.get_sample_size(format))
        wf.setframerate(rate)
        wf.writeframes(b''.join(frames))

    # Close Speak Now dialog
    speak_now_window.destroy()

def recognize_speech(file_path):
    recognizer = sr.Recognizer()

    with sr.AudioFile(file_path) as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="en-IN")
            return text
        except sr.UnknownValueError:
            print("Google Speech Recognition could not understand audio")
        except sr.RequestError as e:
            print(f"Could not request results from Google Speech Recognition service; {e}")

    return None

def encrypt_and_save(text, file_path):
    encrypted_text = cipher_suite.encrypt(text.encode())
    with open(file_path, 'wb') as f:
        f.write(encrypted_text)
    msgbox.showinfo("Success", "Passphrase recorded and encrypted successfully.")

def main():
    # Record passphrase
    record_audio(audio_file)

    # Recognize and encrypt the passphrase
    passphrase_text = recognize_speech(audio_file)
    if passphrase_text:
        encrypt_and_save(passphrase_text, text_file)
    else:
        msgbox.showwarning("Recognition Failed", "Failed to recognize passphrase. Please try again.")

if __name__ == "__main__":
    main()
