import os
import json
from cryptography.fernet import Fernet



# Function to load encryption key
def load_key(key_file):
    with open(key_file, 'rb') as f:
        key = f.read()
    return key

# Function to decrypt a file
def decrypt_file(filename, key):
    fernet = Fernet(key)

    # Check if it's a system file
    if filename.lower().endswith(("thumbs.db",)):
        print(f"Skipped system file: {filename}")
        return

    with open(filename, 'rb') as file:
        encrypted_data = file.read()

    decrypted_data = fernet.decrypt(encrypted_data)

    # Use original filename before encryption
    original_filename = filename[:-4]  # Remove the .enc extension

    with open(original_filename, 'wb') as file:
        file.write(decrypted_data)

    print(f"Decrypting file: {filename}")
    print(f"Decrypted file saved as: {original_filename}")

    # Remove the .enc file after decryption
    os.remove(filename)
    print(f"Encrypted file {filename} removed after decryption.")

# Decrypt all .enc files in the 'files' directory
def decrypt_files():


    key_file = 'encryption_keys.json'
    key = load_key(key_file)

    files_dir = 'files'
    for filename in os.listdir(files_dir):
        # Check if it's a system file
        if filename.lower().endswith(("thumbs.db",)):
            print(f"Skipped system file: {filename}")
            continue
        if filename.endswith(".enc"):
            file_path = os.path.join(files_dir, filename)
            decrypt_file(file_path, key)
    

    print("Vault Decrypted")

if __name__ == "__main__":
    decrypt_files()
