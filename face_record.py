import os
import cv2
import numpy as np
import time  # Import the time module

MAX_IMAGES = 10  # Maximum number of images for enrollment

def main():
    # Get the directory of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create a directory to store enrolled faces if it doesn't exist
    faces_dir = os.path.join(script_dir, "faces")
    if not os.path.exists(faces_dir):
        os.makedirs(faces_dir)

    # Load pre-trained deep learning model for face detection
    prototxt_path = os.path.join(script_dir, "resources", "deploy.prototxt.txt")
    model_path = os.path.join(script_dir, "resources", "res10_300x300_ssd_iter_140000.caffemodel")
    
    # Print paths for debugging
    print(f"Prototxt Path: {prototxt_path}")
    print(f"Model Path: {model_path}")

    # Check if the files exist
    if not os.path.exists(prototxt_path):
        print(f"Error: {prototxt_path} does not exist.")
        return
    if not os.path.exists(model_path):
        print(f"Error: {model_path} does not exist.")
        return

    net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)

    # Open a video capture device (webcam)
    cap = cv2.VideoCapture(0)
    
    # Set the camera feed window size
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 600)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 400)

    enrolled_faces = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Resize the frame to 300x300
        frame = cv2.resize(frame, (300, 300))

        # Detect faces in the frame
        blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0))
        net.setInput(blob)
        detections = net.forward()

        # Process each detected face
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.5:  # Filter out weak detections
                box = detections[0, 0, i, 3:7] * np.array([frame.shape[1], frame.shape[0], frame.shape[1], frame.shape[0]])
                (startX, startY, endX, endY) = box.astype("int")

                # Extract the face ROI (region of interest)
                face_roi = frame[startY:endY, startX:endX]

                # Limit the number of enrolled faces
                if len(enrolled_faces) < MAX_IMAGES:
                    # Add a 1.5 second delay
                    time.sleep(1.5)

                    # Save the detected face
                    face_file_path = os.path.join(faces_dir, f"face_{len(enrolled_faces)}.jpg")
                    cv2.imwrite(face_file_path, face_roi)
                    enrolled_faces.append(face_roi)
                    print(f"Face {len(enrolled_faces)} enrolled")

                # Draw a rectangle around the face
                cv2.rectangle(frame, (startX, startY), (endX, endY), (255, 0, 0), 2)

        # Display the frame
        cv2.imshow('Face Enrollment', frame)
        if cv2.waitKey(1) & 0xFF == ord('q') or len(enrolled_faces) >= MAX_IMAGES:
            break

    # Release the video capture device and close all windows
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
