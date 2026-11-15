import os
import cv2
import numpy as np
from pathlib import Path
from config import (
    YUNET_MODEL_PATH, SFACE_MODEL_PATH,
    DEFAULT_CONFIDENCE_THRESHOLD, DETECTOR_SCORE_THRESHOLD, DETECTOR_NMS_THRESHOLD
)

class FaceEngine:
    def __init__(self, yunet_path=YUNET_MODEL_PATH, sface_path=SFACE_MODEL_PATH):
        self.yunet_path = str(yunet_path)
        self.sface_path = str(sface_path)
        self.detector = None
        self.recognizer = None
        self.haar_cascade = None
        self.current_input_size = (320, 320)
        self._init_models()

    def _init_models(self):
        """Initializes OpenCV YuNet and SFace neural networks."""
        try:
            if os.path.exists(self.yunet_path) and os.path.getsize(self.yunet_path) > 1000:
                self.detector = cv2.FaceDetectorYN.create(
                    self.yunet_path,
                    "",
                    self.current_input_size,
                    DETECTOR_SCORE_THRESHOLD,
                    DETECTOR_NMS_THRESHOLD,
                    5000
                )
            else:
                print(f"[FaceEngine] YuNet model file missing or invalid: {self.yunet_path}")
        except Exception as e:
            print(f"[FaceEngine] Error loading YuNet: {e}")

        try:
            if os.path.exists(self.sface_path) and os.path.getsize(self.sface_path) > 1000000:
                self.recognizer = cv2.FaceRecognizerSF.create(self.sface_path, "")
            else:
                print(f"[FaceEngine] SFace model file missing or invalid: {self.sface_path}")
        except Exception as e:
            print(f"[FaceEngine] Error loading SFace: {e}")

        # Initialize Haar Cascade fallback detector
        try:
            haar_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            if os.path.exists(haar_path):
                self.haar_cascade = cv2.CascadeClassifier(haar_path)
        except Exception as e:
            print(f"[FaceEngine] Haar cascade fallback not loaded: {e}")

    def is_ready(self):
        """Returns True if deep learning detector & recognizer are active."""
        return (self.detector is not None and self.recognizer is not None)

    def detect_faces(self, frame):
        """
        Detects faces in a BGR frame.
        Returns list of face dicts:
        [{'box': (x, y, w, h), 'score': float, 'landmarks': [(x,y), ...], 'raw': face_array}, ...]
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]

        # Use YuNet deep learning detector if available
        if self.detector is not None:
            if (w, h) != self.current_input_size:
                self.detector.setInputSize((w, h))
                self.current_input_size = (w, h)

            _, faces = self.detector.detect(frame)
            results = []
            if faces is not None:
                for f in faces:
                    box = [int(f[0]), int(f[1]), int(f[2]), int(f[3])]
                    # Clip box to frame boundaries
                    box[0] = max(0, box[0])
                    box[1] = max(0, box[1])
                    box[2] = min(w - box[0], box[2])
                    box[3] = min(h - box[1], box[3])

                    score = float(f[14])
                    # Landmarks: right_eye, left_eye, nose, right_mouth, left_mouth
                    landmarks = [(int(f[4 + 2*i]), int(f[5 + 2*i])) for i in range(5)]
                    results.append({
                        "box": tuple(box),
                        "score": score,
                        "landmarks": landmarks,
                        "raw": f
                    })
            return results

        # Fallback to Haar Cascade
        if self.haar_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detected = self.haar_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            results = []
            for (x, y, bw, bh) in detected:
                results.append({
                    "box": (int(x), int(y), int(bw), int(bh)),
                    "score": 0.85,
                    "landmarks": [],
                    "raw": None
                })
            return results

        return []

    def extract_feature(self, frame, face_data):
        """
        Extracts 128D feature embedding for a detected face.
        Returns (feature_vector_128, aligned_face_crop).
        """
        if self.recognizer is None or frame is None:
            return None, None

        raw = face_data.get("raw")
        if raw is not None:
            try:
                aligned = self.recognizer.alignCrop(frame, raw)
                feature = self.recognizer.feature(aligned)
                # Ensure 1D flattened float32 array
                feature_flat = feature.flatten().astype(np.float32)
                # Normalize vector to unit length
                norm = np.linalg.norm(feature_flat)
                if norm > 1e-6:
                    feature_flat = feature_flat / norm
                return feature_flat, aligned
            except Exception as e:
                print(f"[FaceEngine] Alignment/feature error: {e}")

        # Fallback: simple crop if raw landmarks not available
        x, y, w, h = face_data["box"]
        crop = frame[y:y+h, x:x+w]
        if crop.size > 0:
            resized = cv2.resize(crop, (112, 112))
            try:
                feature = self.recognizer.feature(resized)
                feat = feature.flatten().astype(np.float32)
                norm = np.linalg.norm(feat)
                if norm > 1e-6:
                    feat = feat / norm
                return feat, resized
            except Exception:
                pass

        return None, None

    @staticmethod
    def compute_similarity(feat1, feat2):
        """
        Calculates cosine similarity between two 128D embeddings.
        Values range from 0.0 to 1.0 (higher = closer match).
        """
        if feat1 is None or feat2 is None:
            return 0.0

        f1 = feat1.flatten().astype(np.float32)
        f2 = feat2.flatten().astype(np.float32)

        norm1 = np.linalg.norm(f1)
        norm2 = np.linalg.norm(f2)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return 0.0

        dot = np.dot(f1, f2)
        cosine = float(dot / (norm1 * norm2))
        return max(0.0, min(1.0, cosine))

    def match_face(self, query_feature, enrolled_students, threshold=DEFAULT_CONFIDENCE_THRESHOLD):
        """
        Matches query feature against all enrolled students.
        enrolled_students: list of dicts with 'student_id', 'name', 'department', 'face_feature'.
        Returns (is_match, matched_student_dict, best_score).
        """
        if query_feature is None or not enrolled_students:
            return False, None, 0.0

        best_student = None
        best_score = -1.0

        for student in enrolled_students:
            enrolled_feat = student.get("face_feature")
            if enrolled_feat is None:
                continue

            score = self.compute_similarity(query_feature, enrolled_feat)
            if score > best_score:
                best_score = score
                best_student = student

        if best_student and best_score >= threshold:
            return True, best_student, best_score

        return False, best_student, max(0.0, best_score)

    def process_registration_image(self, bgr_image):
        """
        Analyzes an uploaded or captured image for student registration.
        Returns (success, message, embedding, aligned_crop).
        """
        if bgr_image is None or bgr_image.size == 0:
            return False, "Invalid image data received.", None, None

        faces = self.detect_faces(bgr_image)
        if not faces:
            return False, "No face detected. Please ensure face is centered with clear lighting.", None, None

        # Choose the largest / most confident face
        faces.sort(key=lambda f: f["box"][2] * f["box"][3], reverse=True)
        primary_face = faces[0]

        feature, aligned = self.extract_feature(bgr_image, primary_face)
        if feature is None or aligned is None:
            return False, "Failed to extract face features. Please try another photo.", None, None

        return True, "Face captured successfully.", feature, aligned

    def process_multi_sample_registration(self, frame_list):
        """
        Processes multiple captured frames for high-accuracy composite registration.
        Averages features across all valid frames.
        Returns (success, message, composite_embedding, representative_crop).
        """
        valid_features = []
        best_crop = None

        for frame in frame_list:
            faces = self.detect_faces(frame)
            if faces:
                faces.sort(key=lambda f: f["box"][2] * f["box"][3], reverse=True)
                feat, crop = self.extract_feature(frame, faces[0])
                if feat is not None:
                    valid_features.append(feat)
                    if best_crop is None and crop is not None:
                        best_crop = crop

        if not valid_features:
            return False, "Could not detect clear face across captured frames.", None, None

        # Composite feature: mean vector + L2 normalize
        mean_feat = np.mean(valid_features, axis=0).astype(np.float32)
        norm = np.linalg.norm(mean_feat)
        if norm > 1e-6:
            mean_feat = mean_feat / norm

        return True, f"Enrolled with {len(valid_features)} face samples.", mean_feat, best_crop

# Global singleton engine instance
engine = FaceEngine()
