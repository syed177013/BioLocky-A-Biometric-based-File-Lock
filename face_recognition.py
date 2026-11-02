import os
import cv2
import numpy as np
import time
import tkinter as tk
from tkinter import messagebox
import sys

def load_enrolled_faces(faces_dir):
    enrolled_faces = []
    for file_name in os.listdir(faces_dir):
        try:
            face_image = cv2.imread(os.path.join(faces_dir, file_name))
            if face_image is not None and face_image.size != 0:
                enrolled_faces.append(face_image)
            else:
                print(f"Warning: Skipping invalid face image: {file_name}")
        except cv2.error as e:
            print(f"Error loading face image: {file_name} ({e})")
    return enrolled_faces

def recognize_face(enrolled_faces, face_to_recognize):
    if face_to_recognize is None or face_to_recognize.size == 0:
        print("Error: face_to_recognize is empty or not properly loaded.")
        return False

    face_to_recognize_gray = cv2.cvtColor(face_to_recognize, cv2.COLOR_BGR2GRAY)
    for enrolled_face in enrolled_faces:
        if enrolled_face is None or enrolled_face.size == 0:
            print("Error: enrolled_face is empty or not properly loaded.")
            continue
        try:
            enrolled_face_gray = cv2.cvtColor(enrolled_face, cv2.COLOR_BGR2GRAY)
            enrolled_face_resized = cv2.resize(enrolled_face_gray, (face_to_recognize_gray.shape[1], face_to_recognize_gray.shape[0]))
            similarity_score = cv2.matchTemplate(face_to_recognize_gray, enrolled_face_resized, cv2.TM_CCOEFF_NORMED)
            if np.max(similarity_score) >= 0.6:  # Adjusted threshold
                return True
        except cv2.error as e:
            print(f"Error processing enrolled face: {e}")
            continue
    return False

def save_intruder_image(image, intruders_dir):
    if not os.path.exists(intruders_dir):
        os.makedirs(intruders_dir)
    timestamp = int(time.time())
    file_path = os.path.join(intruders_dir, f"intruder_{timestamp}.jpg")
    cv2.imwrite(file_path, image)
    print(f"Intruder image saved at: {file_path}")

def main():
    # Dynamic paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prototxt_path = os.path.join(script_dir, "resources", "deploy.prototxt.txt")
    model_path = os.path.join(script_dir, "resources", "res10_300x300_ssd_iter_140000.caffemodel")
    intruders_dir = os.path.join(script_dir, "intruders")

    enrolled_faces = load_enrolled_faces(os.path.join(script_dir, "faces"))

    # Load pre-trained deep learning model for face detection
    net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)

    cap = cv2.VideoCapture(0)  # Open the video capture device
    if not cap.isOpened():
        print("Error: Could not open video capture device.")
        sys.exit(1)

    # Set camera feed window size
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 600)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 400)

    # Variables for timing
    start_time = None
    face_ok_time = 3  # 3-4 seconds for face to be recognized
    unknown_start_time = None
    unknown_time_limit = 2  # 2 seconds for an unknown face

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture frame.")
            break

        # Detect faces in the frame
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
        net.setInput(blob)
        detections = net.forward()

        face_recognized = False

        # Process each detected face
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.5:  # Filter out weak detections
                box = detections[0, 0, i, 3:7] * np.array([frame.shape[1], frame.shape[0], frame.shape[1], frame.shape[0]])
                (startX, startY, endX, endY) = box.astype("int")

                # Extract the face ROI (region of interest)
                face_roi = frame[startY:endY, startX:endX]

                # Check if the detected face matches any enrolled face
                if recognize_face(enrolled_faces, face_roi):
                    face_recognized = True
                    cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)
                    cv2.putText(frame, "Recognized", (startX, startY - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    # If face is recognized, start counting time
                    if start_time is None:
                        start_time = time.time()
                    else:
                        # Check if 3-4 seconds have passed
                        if time.time() - start_time >= face_ok_time:
                            # Display message
                            root = tk.Tk()
                            root.withdraw()
                            messagebox.showinfo("Alert", "Face recognized, ACCESS GRANTED")
                            # Terminate camera feed
                            cap.release()
                            cv2.destroyAllWindows()
                            sys.exit(0)  # Successful exit
                else:
                    cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 0, 255), 2)
                    cv2.putText(frame, "Unknown", (startX, startY - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    # If unrecognized face is detected, start or reset unknown timer
                    if unknown_start_time is None:
                        unknown_start_time = time.time()
                    else:
                        # Check if 2 seconds have passed
                        if time.time() - unknown_start_time >= unknown_time_limit:
                            save_intruder_image(face_roi, intruders_dir)
                            # Display message
                            root = tk.Tk()
                            root.withdraw()
                            messagebox.showwarning("Warning", "Unknown face detected, ACCESS DENIED")
                            # Terminate camera feed
                            cap.release()
                            cv2.destroyAllWindows()
                            sys.exit(1)  # Exit with error code

        if not face_recognized:
            start_time = None
        else:
            unknown_start_time = None

        # Resize the frame to 600x400
        frame = cv2.resize(frame, (600, 400))

        # Display the frame
        cv2.imshow('Face Detection', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release the video capture device and close all windows
    cap.release()
    cv2.destroyAllWindows()
    sys.exit(1)  # Considered an error if the loop is broken without recognition

if __name__ == "__main__":
    main()
