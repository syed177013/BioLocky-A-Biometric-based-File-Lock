import os
import wave
import pyaudio
import speech_recognition as sr
from cryptography.fernet import Fernet
import tkinter as tk
import tkinter.messagebox as msgbox

# Base directory path
base_dir = os.path.dirname(os.path.abspath(__file__))

# Ensure user directory exists in the same location as the script
user_dir = os.path.join(base_dir, "user")
os.makedirs(user_dir, exist_ok=True)

# File paths
audio_file = os.path.join(user_dir, "auth_sample.wav")
text_file = os.path.join(user_dir, "passphrase.txt")
key_file = os.path.join(user_dir, "secret.key")

# Load the key
with open(key_file, 'rb') as f:
    key = f.read()

cipher_suite = Fernet(key)

def record_audio(file_path, duration=3):
    chunk = 1024
    format = pyaudio.paInt16
    channels = 1
    rate = 44100
    p = pyaudio.PyAudio()

    print("Recording for {} seconds...".format(duration))

    stream = p.open(format=format, channels=channels, rate=rate, input=True, frames_per_buffer=chunk)

    frames = []
    for _ in range(0, int(rate / chunk * duration)):
        data = stream.read(chunk)
        frames.append(data)

    print("Recording finished.")
    
    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open(file_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(p.get_sample_size(format))
        wf.setframerate(rate)
        wf.writeframes(b''.join(frames))

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

def show_speak_now_window():
    speak_now_window = tk.Toplevel()
    speak_now_window.title("Speak Now")
    tk.Label(speak_now_window, text="Please speak now...", padx=20, pady=20).pack()
    speak_now_window.update()  # Ensure window is shown
    return speak_now_window

def main():
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    # Show "Speak Now" window
    speak_now_window = show_speak_now_window()
    
    # Record authentication sample
    record_audio(audio_file)
    
    # Close "Speak Now" window
    speak_now_window.destroy()

    # Recognize the spoken passphrase
    auth_text = recognize_speech(audio_file)
    if auth_text:
        # Decrypt the stored passphrase
        with open(text_file, 'rb') as f:
            encrypted_text = f.read()
        stored_passphrase = cipher_suite.decrypt(encrypted_text).decode()
        
        # Compare passphrases directly
        if auth_text.strip().lower() == stored_passphrase.strip().lower():
            msgbox.showinfo("Access Granted", "Voice passphrase recognized. Access granted!")
            return True
        else:
            msgbox.showwarning("Access Denied", "Voice passphrase did not match. Access denied!")
    else:
        msgbox.showerror("Recognition Failed", "Failed to recognize the passphrase. Please try again.")
    return False

if __name__ == "__main__":
    main()
