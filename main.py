import customtkinter as ctk
from tkinter import filedialog, Label, Canvas, Scrollbar, Frame
from PIL import Image, ImageFilter, ImageTk
import os
import subprocess
import sys
from file_Configlocky import encrypt_files  # Import encryption function
from file_Configpocky import decrypt_files  # Import decryption function
from face_recognition import main as fdetect_function
from face_record import main as fenroll_function
from record_and_encrypt import main as venroll_function
from validate_passphrase import main as vvalidate_function
import tkinter.messagebox as msgbox
import webbrowser
from cryptography.fernet import Fernet





# Ensure directories exist
files_dir = "files"
thumbnails_dir = "thumbnails"
os.makedirs(files_dir, exist_ok=True)
os.makedirs(thumbnails_dir, exist_ok=True)
mail_process = None

LIGHT_BG = "#F9FAFB"   # soft light gray (Apple-like)
DARK_BG  = "#121212"   # deep dark (security vibe)

PIN_KEY_FILE = "pin.key"
PIN_DATA_FILE = "pin.dat"
DEFAULT_PIN = "131728"

def load_or_create_key():
    if not os.path.exists(PIN_KEY_FILE):
        key = Fernet.generate_key()
        with open(PIN_KEY_FILE, "wb") as f:
            f.write(key)
    else:
        with open(PIN_KEY_FILE, "rb") as f:
            key = f.read()
    return Fernet(key)


fernet = load_or_create_key()

def save_pin(pin: str):
    encrypted = fernet.encrypt(pin.encode())
    with open(PIN_DATA_FILE, "wb") as f:
        f.write(encrypted)



def load_pin():
    if not os.path.exists(PIN_DATA_FILE):
        save_pin(DEFAULT_PIN)
        return DEFAULT_PIN

    with open(PIN_DATA_FILE, "rb") as f:
        encrypted = f.read()
        return fernet.decrypt(encrypted).decode()



def require_pin_and_execute(action_func):
    pin_window = ctk.CTkToplevel(root)
    pin_window.title("Security PIN Required")
    pin_window.geometry("300x180")
    pin_window.resizable(False, False)
    pin_window.transient(root)
    pin_window.grab_set()

    label = ctk.CTkLabel(pin_window, text="Enter Security PIN")
    label.pack(pady=(20, 10))

    pin_entry = ctk.CTkEntry(pin_window, show="*")
    pin_entry.pack(pady=5)

    def verify():
        entered = pin_entry.get()
        if entered == CURRENT_PIN:
            pin_window.destroy()
            action_func()
        else:
            msgbox.showerror("Incorrect PIN", "Invalid Security PIN")

    submit_btn = ctk.CTkButton(
        pin_window,
        text="Verify",
        fg_color="#007AFF",
        hover_color="#5ACCE5",
        command=verify
    )
    submit_btn.pack(pady=15)

def open_update_pin_window():
    global CURRENT_PIN

    win = ctk.CTkToplevel(root)
    win.title("Update Security PIN")
    win.geometry("350x300")
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()

    def labeled_entry(text):
        ctk.CTkLabel(win, text=text).pack(pady=(10, 0))
        e = ctk.CTkEntry(win, show="*")
        e.pack(pady=5)
        return e

    old_pin = labeled_entry("Current PIN")
    new_pin = labeled_entry("New PIN")
    confirm_pin = labeled_entry("Confirm New PIN")

    def update():
        global CURRENT_PIN
        nonlocal old_pin, new_pin, confirm_pin

        if old_pin.get() != CURRENT_PIN:
            msgbox.showerror("Error", "Current PIN is incorrect")
            return

        if new_pin.get() != confirm_pin.get():
            msgbox.showerror("Error", "New PINs do not match")
            return

        if not new_pin.get().isdigit():
            msgbox.showerror("Error", "PIN must be numeric")
            return

        CURRENT_PIN = new_pin.get()
        save_pin(CURRENT_PIN)
        msgbox.showinfo("Success", "Security PIN updated successfully")
        win.destroy()

    ctk.CTkButton(
        win,
        text="Reset PIN",
        fg_color="#007AFF",
        hover_color="#5ACCE5",
        command=update
    ).pack(pady=20)



def open_github():
    webbrowser.open_new_tab("https://github.com/your-username/your-repo")


#subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'mail.py')])
def start_mail_monitor():
    global mail_process
    if mail_process is None or mail_process.poll() is not None:
        mail_process = subprocess.Popen(
            [sys.executable, "mail.py"],
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL
        )

def load_existing_files():
    for filename in os.listdir(files_dir):
        file_path = os.path.join(files_dir, filename)
        if os.path.isfile(file_path):
            display_thumbnail(file_path)  # Reuse the existing display_thumbnail function

CURRENT_PIN = load_pin()


# Initialize the main window
root = ctk.CTk()
root.geometry("950x600")
SIDEBAR_X = 230
TOP_MARGIN = 25
CANVAS_WIDTH = 925
CANVAS_HEIGHT = 525
SCROLLBAR_WIDTH = 20

root.resizable(False,False)
root.title("Welcome to BioLocky")
ctk.set_appearance_mode("light")
root.configure(fg_color=LIGHT_BG)

def toggle_theme():
    current_theme = ctk.get_appearance_mode().lower()
    new_theme = "dark" if current_theme == "light" else "light"

    bg_color = DARK_BG if new_theme == "dark" else LIGHT_BG

    # Root
    root.configure(fg_color=bg_color)

    # Canvas + scroll area
    canvas.configure(bg=bg_color)
    scrollable_frame.configure(bg=bg_color)

    ctk.set_appearance_mode(new_theme)
    print(f"Theme switched to {new_theme}")


# Image buttons
# git_image = ctk.CTkImage(Image.open("github.png"), size=(26, 26))
# git_image_button = ctk.CTkButton(master=root, text="", width=3, fg_color="#007AFF", hover_color="#5ACCE5", image=git_image)
# git_image_button.place(x=200, y=557)

# gear_image = ctk.CTkImage(Image.open("help.png"), size=(26, 26))
# gear_image_button = ctk.CTkButton(master=root, text="", width=3, fg_color="#007AFF", hover_color="#5ACCE5", image=gear_image)
# gear_image_button.place(x=255, y=557)

def open_help_window():
    # Prevent multiple help windows
    if hasattr(root, "help_window") and root.help_window.winfo_exists():
        root.help_window.focus()
        return

    help_window = ctk.CTkToplevel(root)
    root.help_window = help_window  # attach to root

    help_window.title("BioLocky Help")
    help_window.geometry("450x600")
    help_window.resizable(False, False)
    help_window.transient(root)   # stay on top of root
    help_window.grab_set()        # modal behavior

    help_window.configure(fg_color=LIGHT_BG)

    # ---- CONTENT ----
    title = ctk.CTkLabel(
        help_window,
        text="BioLocky Help",
        font=ctk.CTkFont(size=22, weight="bold")
    )
    title.pack(pady=(20, 10))

    help_text=(
        "Yahallo! Thanks for using BioLocky :>\n\n"
        "You can use the \"Toggle Theme\" button to switch between "
        "Light and Dark mode anytime.\n\n"
        "The \"Face Validate\" and \"Voice Validate\" buttons are meant "
        "for testing purposes only — BioLocky is currently in beta.\n\n"
        "To protect your files:\n"
        "• Use \"Capture Face\" to enroll your face for secure access.\n"
        "• Use \"Record Passphrase\" to enroll a voice passphrase instead.\n\n"
        "Once your files are added:\n"
        "• Double-click a file thumbnail to unlock it using face recognition.\n"
        "• Or click the audio wave button to unlock it using your passphrase.\n\n"
        "Thanks for trying BioLocky — your files, secured smarter 🔐"
    )

    body = ctk.CTkLabel(
        help_window,
        text=help_text,
        justify="left",
        wraplength=360
    )
    body.pack(padx=20, pady=10)

    close_btn = ctk.CTkButton(
        help_window,
        text="Close",
        fg_color="#007AFF",
        hover_color="#5ACCE5",
        command=help_window.destroy
    )
    close_btn.pack(side="bottom",pady=20)


git_image = ctk.CTkImage(Image.open("github.png"), size=(26, 26))
git_image_button = ctk.CTkButton(
    master=root,
    text="",
    image=git_image,
    width=32,
    height=32,
    fg_color="transparent",
    hover_color="#E6F0FF",
    command=open_github
)
git_image_button.place(x=200, y=557)


help_image = ctk.CTkImage(Image.open("help.png"), size=(26, 26))
help_image_button = ctk.CTkButton(
    master=root,
    text="",
    image=help_image,
    width=32,
    height=32,
    fg_color="transparent",
    hover_color="#E6F0FF",
    command=open_help_window
)
help_image_button.place(x=255, y=557)


# Create a canvas with a vertical scrollbar
canvas = Canvas(
    root,
    bg=LIGHT_BG,
    highlightthickness=0,
    bd=0)

scrollbar = Scrollbar(root, orient="vertical", command=canvas.yview)
scrollable_frame = Frame(
    canvas,
    bg=LIGHT_BG
    )

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

#canvas.place(x=200, y=25, width=725, height=525)
canvas.place(
    x=SIDEBAR_X,
    y=TOP_MARGIN,
    width=CANVAS_WIDTH,
    height=CANVAS_HEIGHT
)
#scrollbar.place(x=925, y=25, height=525)  # Adjust the scrollbar placement
scrollbar.place(
    x=SIDEBAR_X + CANVAS_WIDTH,
    y=TOP_MARGIN,
    width=SCROLLBAR_WIDTH,
    height=CANVAS_HEIGHT
)

def pixelate_image(image, pixel_size):
    small_image = image.resize((image.width // pixel_size, image.height // pixel_size), Image.NEAREST)
    pixelated_image = small_image.resize(image.size, Image.NEAREST)
    return pixelated_image

def normalize_pixelate_and_blur_image(image_path):
    fixed_size = (64, 64)  # Smaller size
    image = Image.open(image_path)
    image.thumbnail(fixed_size, Image.LANCZOS)

    new_image = Image.new("RGB", fixed_size, (255, 255, 255))
    new_image.paste(image, ((fixed_size[0] - image.size[0]) // 2, (fixed_size[1] - image.size[1]) // 2))

    pixelated_image = pixelate_image(new_image, pixel_size=1)
    blurred_image = pixelated_image.filter(ImageFilter.GaussianBlur(radius=1))

    return blurred_image

def select_files():
    file_paths = filedialog.askopenfilenames(filetypes=[("All Files", "*.*")])
    for file_path in file_paths:
        save_file(file_path)
        display_thumbnail(file_path)

def save_file(file_path):
    base_name = os.path.basename(file_path)
    destination_path = os.path.join(files_dir, base_name)
    with open(file_path, 'rb') as src_file:
        with open(destination_path, 'wb') as dst_file:
            dst_file.write(src_file.read())

def open_file(file_name, use_face_recognition=True):
    start_mail_monitor()
    file_path = os.path.join("files", file_name)
    
    try:
        if use_face_recognition:
            # Step 1: Face Recognition
            face_result = subprocess.run([sys.executable, "face_recognition.py"], capture_output=True, text=True)
            if face_result.returncode != 0:
                print("Face recognition failed. File cannot be opened.")
                return
        
        # If face recognition is successful or not required, proceed to open the file
        if sys.platform.startswith('win'):
            os.startfile(file_path)
        elif sys.platform.startswith('linux') or sys.platform == 'darwin':
            subprocess.call(('xdg-open' if sys.platform.startswith('linux') else 'open', file_path))
    
    except Exception as e:
        print(f"Error opening file: {e}")






def execute_file_if_validated(file_name):
    # Call the validate_passphrase function
    if vvalidate_function():
        # If validation is successful, proceed to open the file without face recognition
        open_file(file_name, use_face_recognition=False)
    else:
        # Show GUI warning instead of print
        msgbox.showwarning("Access Denied", "Passphrase Unrecognized.")



# Function to display a thumbnail in the scrollable_frame
def display_thumbnail(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()

    # Skip thumbs.db files
    if os.path.basename(file_path).lower() == "thumbs.db":
        return

    # Handle image files
    if file_extension in ['.png', '.jpg', '.jpeg']:
        normalized_image = normalize_pixelate_and_blur_image(file_path)
        thumbnail_tk = ImageTk.PhotoImage(normalized_image)

        if normalized_image.size != (0, 0):
            current_row = len(scrollable_frame.grid_slaves()) // 4
            current_column = len(scrollable_frame.grid_slaves()) % 4

            label_frame = ctk.CTkFrame(scrollable_frame)
            label_frame.grid(row=current_row, column=current_column, padx=5, pady=5)

            thumbnail_label = Label(label_frame, image=thumbnail_tk)
            thumbnail_label.image = thumbnail_tk
            thumbnail_label.pack()

            filename_label = Label(label_frame, text=os.path.basename(file_path), wraplength=100)
            filename_label.pack()

            delete_button = ctk.CTkButton(
                label_frame, 
                text="Delete", 
                fg_color="#007AFF", 
                hover_color="#5ACCE5", 
                command=lambda: delete_thumbnail(label_frame, file_path),
                width=120  # Adjust width for delete button
            )
            delete_button.pack(side="left", fill="x", expand=True)

            # New radio button using an image
            radio_image = ctk.CTkImage(Image.open("radio.png"), size=(26, 26))
            radio_button = ctk.CTkButton(
                label_frame,
                text="",  # No text
                fg_color="#007AFF",
                hover_color="#5ACCE5",
                image=radio_image,
                width=40,
                command=lambda: execute_file_if_validated(os.path.basename(file_path))  # Use voice validation
            )
            radio_button.pack(side="right", padx=5)  # Position to the right

            # Bind double-click event to open the file using face recognition
            thumbnail_label.bind("<Double-1>", lambda e: open_file(os.path.basename(file_path)))

            # Save the normalized thumbnail
            thumbnail_image_path = os.path.join(thumbnails_dir, os.path.basename(file_path) + '_thumbnail.png')
            normalized_image.save(thumbnail_image_path)

    # Handle non-image files with icons
    else:
        # Get the file extension
        file_extension = file_extension[1:]  # Remove the dot
        icon_path = f"icons/{file_extension}.png"  # Placeholder path

        # Check if the placeholder icon exists
        if os.path.exists(icon_path):
            icon_image = Image.open(icon_path)
            icon_image = icon_image.resize((64, 64), Image.LANCZOS)  # Resize the icon
            icon_tk = ImageTk.PhotoImage(icon_image)

            # Calculate grid position
            current_row = len(scrollable_frame.grid_slaves()) // 4  # 4 thumbnails per row
            current_column = len(scrollable_frame.grid_slaves()) % 4

            label_frame = ctk.CTkFrame(scrollable_frame)
            label_frame.grid(row=current_row, column=current_column, padx=5, pady=5)

            icon_label = Label(label_frame, image=icon_tk)
            icon_label.image = icon_tk  # Keep a reference to avoid garbage collection
            icon_label.pack()

            filename_label = Label(label_frame, text=os.path.basename(file_path), wraplength=100)
            filename_label.pack()

            delete_button = ctk.CTkButton(
                label_frame, 
                text="Delete", 
                fg_color="#007AFF", 
                hover_color="#5ACCE5", 
                command=lambda: delete_thumbnail(label_frame, file_path),
                width=120  # Adjust width for delete button
            )
            delete_button.pack(side="left", fill="x", expand=True)

            # New radio button using an image
            radio_image = ctk.CTkImage(Image.open("radio.png"), size=(15, 15))
            radio_button = ctk.CTkButton(
                label_frame,
                text="",  # No text
                fg_color="#007AFF",
                hover_color="#5ACCE5",
                image=radio_image,
                width=40,
                command=lambda: execute_file_if_validated(os.path.basename(file_path))  # Use voice validation
            )
            radio_button.pack(side="right", padx=5)  # Position to the right

            # Bind double-click event to open the file using face recognition
            icon_label.bind("<Double-1>", lambda e: open_file(os.path.basename(file_path)))

            # Save the icon as a thumbnail if necessary
            icon_thumbnail_path = os.path.join(thumbnails_dir, os.path.basename(file_path) + '_thumbnail.png')
            icon_image.save(icon_thumbnail_path)
        else:
            # Use a default icon if no specific placeholder is found
            default_icon_path = "icons/default.png"
            icon_image = Image.open(default_icon_path)
            icon_image = icon_image.resize((64, 64), Image.LANCZOS)
            icon_tk = ImageTk.PhotoImage(icon_image)

            # Repeat the same steps as above for displaying the default icon
            current_row = len(scrollable_frame.grid_slaves()) // 4  # 4 thumbnails per row
            current_column = len(scrollable_frame.grid_slaves()) % 4

            label_frame = ctk.CTkFrame(scrollable_frame)
            label_frame.grid(row=current_row, column=current_column, padx=5, pady=5)

            icon_label = Label(label_frame, image=icon_tk)
            icon_label.image = icon_tk  # Keep a reference to avoid garbage collection
            icon_label.pack()

            filename_label = Label(label_frame, text=os.path.basename(file_path), wraplength=100)
            filename_label.pack()

            delete_button = ctk.CTkButton(
                label_frame, 
                text="Delete", 
                fg_color="#007AFF", 
                hover_color="#5ACCE5", 
                command=lambda: delete_thumbnail(label_frame, file_path),
                width=120  # Adjust width for delete button
            )
            delete_button.pack(side="left", fill="x", expand=True)

            # New radio button using an image
            radio_image = ctk.CTkImage(Image.open("radio.png"), size=(15, 15))
            radio_button = ctk.CTkButton(
                label_frame,
                text="",  # No text
                fg_color="#007AFF",
                hover_color="#5ACCE5",
                image=radio_image,
                width=40  # Smaller width for the radio button
            )
            radio_button.pack(side="right", padx=5)  # Position to the right

            # Save the default icon as a thumbnail
            icon_thumbnail_path = os.path.join(thumbnails_dir, os.path.basename(file_path) + '_thumbnail.png')
            icon_image.save(icon_thumbnail_path)




def refresh_canvas():
    # Clear the current display and reload existing files
    for widget in scrollable_frame.winfo_children():
        widget.destroy()
    load_existing_files()

def delete_thumbnail(label_frame, file_path):
    # Construct the path for the original file
    base_name = os.path.basename(file_path)
    original_file_path = os.path.join(files_dir, base_name)  # Full path to the original file
    thumbnail_file_path = os.path.join(thumbnails_dir, base_name + '_thumbnail.png')

    # Delete the original file and thumbnail
    if os.path.exists(original_file_path):
        os.remove(original_file_path)
        print(f"Deleted original file: {original_file_path}")

    if os.path.exists(thumbnail_file_path):
        os.remove(thumbnail_file_path)
        print(f"Deleted thumbnail: {thumbnail_file_path}")

    # Remove the label frame from the grid layout
    label_frame.grid_forget()  # Use grid_forget to remove it from the grid

    # Refresh the canvas
    refresh_canvas()

def on_exit():
    # Encrypt all files before closing
    encrypt_files()

    global mail_process
    try:
        if mail_process and mail_process.poll() is None:
            mail_process.terminate()
            mail_process.wait(timeout=3)
    except Exception as e:
        print(f"Mail Process Termination Failed: {e}")

    if mail_process and mail_process.poll() is None:
        mail_process.kill()

    root.destroy()
    sys.exit()


decrypt_files()
load_existing_files()

facedetect_btn = ctk.CTkButton(root, text="Face Validate", fg_color="#007AFF", hover_color="#5ACCE5", command=lambda: subprocess.run([sys.executable, "face_recognition.py"], check=True))
facedetect_btn.place(x=15, y=450)

voicedetect_btn = ctk.CTkButton(root, text="Voice Validate", fg_color="#007AFF", hover_color="#5ACCE5", command=vvalidate_function)
voicedetect_btn.place(x=15, y=400)

fenroll_btn = ctk.CTkButton(root, command=lambda: require_pin_and_execute(fenroll_function), text="Capture Face", fg_color="#007AFF", hover_color="#5ACCE5")
fenroll_btn.place(x=15, y=500)

venroll_btn = ctk.CTkButton(root, text="Record Passphrase", fg_color="#007AFF", hover_color="#5ACCE5", command=lambda: require_pin_and_execute(venroll_function))
venroll_btn.place(x=15, y=550)

fileadd_btn = ctk.CTkButton(root, text="+ Add File", command=select_files, fg_color="#007AFF", hover_color="#5ACCE5")
fileadd_btn.place(x=800, y=566)

exit_button = ctk.CTkButton(root, text="Exit", command=on_exit, fg_color="#FF5C5C", hover_color="#FF8B8B")
exit_button.place(x=650, y=566)

# Button to toggle between light and dark mode
toggle_theme_button = ctk.CTkButton(root, text="Toggle Theme", command=toggle_theme, fg_color="#007AFF", hover_color="#5ACCE5")
toggle_theme_button.place(x=15, y=25)

update_pin_btn = ctk.CTkButton(
    root,
    text="Update PIN",
    fg_color="#FF9500",
    hover_color="#FFB347",
    command=lambda: require_pin_and_execute(open_update_pin_window)
)
update_pin_btn.place(x=15, y=60)


root.mainloop()
