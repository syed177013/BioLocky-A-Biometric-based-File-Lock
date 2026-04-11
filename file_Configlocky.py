import os
import json
from cryptography.fernet import Fernet



# Function to generate or load encryption key
def load_key(key_file):
    if os.path.exists(key_file):
        # Load key from file
        with open(key_file, 'rb') as f:
            key = f.read()
    else:
        # Generate a new key and save it
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
    
    return key

# Function to encrypt a file
def encrypt_file(filename, key):
    fernet = Fernet(key)

    # Check if the encrypted file already exists
    if os.path.exists(filename + ".enc"):
        print(f"{filename} already encrypted. Skipping...")
        return
    
    with open(filename, 'rb') as file:
        file_data = file.read()

    encrypted_data = fernet.encrypt(file_data)

    with open(filename + ".enc", 'wb') as file:
        file.write(encrypted_data)

    print(f"Encrypting file: {filename}")
    print(f"Key saved for {filename}: {key.decode()}")

    # Delete the original file after encryption
    os.remove(filename)
    print(f"Original file {filename} deleted after encryption.")

# Encrypt all files in the 'files' directory
def encrypt_files():


    key_file = 'encryption_keys.json'
    key = load_key(key_file)

    files_dir = 'files'
    for filename in os.listdir(files_dir):
        file_path = os.path.join(files_dir, filename)
        if os.path.isfile(file_path):
            # Skip system files like Thumbs.db
            if filename.lower().endswith(("thumbs.db",)):
                print(f"Skipped system file: {filename}")
                continue
            # Skip already encrypted files
            if filename.endswith(".enc"):
                print(f"{filename} already encrypted. Skipping...")
                continue
            encrypt_file(file_path, key)


    # Update encryption details in JSON file
    encryption_details = {
        "encryption_key": key.decode(),
        "encrypted_files": [filename for filename in os.listdir('files') if filename.endswith(".enc")]
    }
    with open('encryption_details.json', 'w') as json_file:
        json.dump(encryption_details, json_file, indent=4)
    

    print("Vault Encrypted")



if __name__ == "__main__":
    encrypt_files()
