import time
import threading
import cv2
import numpy as np
from pathlib import Path

from config import DEFAULT_CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, DEFAULT_CONFIDENCE_THRESHOLD
from face_engine import engine as face_engine
from attendance_service import attendance_service
import database

class CameraManager:
    def __init__(self):
        self.camera_index = int(database.get_setting("camera_index", str(DEFAULT_CAMERA_INDEX)))
        self.cap = None
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        
        self.active_students = []
        self.reload_students()
        
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.recent_detections = []
        
        # Detection throttle (detect every N frames to keep 30 FPS smooth)
        self.detect_interval = 2
        self.frame_index = 0
        self.is_camera_available = False

        # Pre-initialize fallback frames
        fallback = self._generate_fallback_frame()
        self.latest_raw_frame = fallback
        self.latest_annotated_frame = fallback
        ret, buf = cv2.imencode('.jpg', fallback, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        self.latest_jpeg = buf.tobytes() if ret else None

    def reload_students(self):
        """Reloads active enrolled students and their embeddings from DB."""
        try:
            self.active_students = database.get_all_students(active_only=True)
            print(f"[CameraManager] Loaded {len(self.active_students)} enrolled students.")
        except Exception as e:
            print(f"[CameraManager] Error loading students: {e}")
            self.active_students = []

    def start(self):
        """Starts background camera capture thread."""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops background capture and releases hardware."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self._release_camera()

    def change_camera(self, new_index):
        """Switches to another camera index."""
        with self.lock:
            self.camera_index = int(new_index)
            database.set_setting("camera_index", str(self.camera_index))
            self._release_camera()
            self._init_camera()

    def _init_camera(self):
        """Attempts to open OpenCV VideoCapture."""
        try:
            # On Windows, cv2.CAP_DSHOW provides fast startup for USB webcams
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_index)
            
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
                self.is_camera_available = True
                print(f"[CameraManager] Camera {self.camera_index} initialized successfully.")
            else:
                self.is_camera_available = False
                print(f"[CameraManager] Camera {self.camera_index} could not be opened.")
        except Exception as e:
            self.is_camera_available = False
            print(f"[CameraManager] Camera open exception: {e}")

    def _release_camera(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.is_camera_available = False

    def _capture_worker(self):
        """Continuous background grabber and AI recognition pipeline."""
        self._init_camera()
        
        while self.is_running:
            raw_frame = None
            
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    raw_frame = frame
                    self.is_camera_available = True
                else:
                    self.is_camera_available = False
            
            # If physical camera fails or is unavailable, render synthetic animated placeholder
            if raw_frame is None:
                raw_frame = self._generate_fallback_frame()
                self.is_camera_available = False
                time.sleep(0.04) # ~25 FPS

            self.frame_index += 1
            annotated_frame = raw_frame.copy()

            # Run AI Face Detection & Recognition on interval
            threshold = float(database.get_setting("confidence_threshold", str(DEFAULT_CONFIDENCE_THRESHOLD)))
            
            if (self.frame_index % self.detect_interval == 0):
                self.recent_detections = []
                faces = face_engine.detect_faces(raw_frame)
                
                for f in faces:
                    box = f["box"]
                    feat, crop = face_engine.extract_feature(raw_frame, f)
                    
                    if feat is not None:
                        is_match, student, score = face_engine.match_face(feat, self.active_students, threshold)
                        
                        if is_match and student:
                            # Trigger attendance logic
                            res = attendance_service.process_face_match(student, score, raw_frame, box)
                            status_code = res.get("status", "SUCCESS")
                            self.recent_detections.append({
                                "box": box,
                                "matched": True,
                                "name": student["name"],
                                "id": student["student_id"],
                                "dept": student.get("department", ""),
                                "score": score,
                                "status": status_code
                            })
                        else:
                            self.recent_detections.append({
                                "box": box,
                                "matched": False,
                                "name": "Unknown Person",
                                "id": "Not Registered",
                                "dept": "",
                                "score": score,
                                "status": "UNKNOWN"
                            })

            # Draw visual HUD overlays on annotated frame
            self._draw_hud(annotated_frame, self.recent_detections)

            # Update FPS calculation
            self.frame_count += 1
            now = time.time()
            elapsed = now - self.last_fps_time
            if elapsed >= 1.0:
                self.fps = round(self.frame_count / elapsed, 1)
                self.frame_count = 0
                self.last_fps_time = now

            # Draw FPS & Status banner
            self._draw_status_banner(annotated_frame)

            # Encode display frame as JPEG for streaming
            ret, buffer = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            jpeg_bytes = buffer.tobytes() if ret else None

            with self.lock:
                self.latest_raw_frame = raw_frame
                self.latest_annotated_frame = annotated_frame
                self.latest_jpeg = jpeg_bytes

        self._release_camera()

    def _draw_hud(self, frame, detections):
        """Draws modern, sleek cyber-hud bounding boxes and identity badges."""
        for det in detections:
            x, y, w, h = det["box"]
            matched = det["matched"]
            name = det["name"]
            sid = det["id"]
            score = det["score"]
            status = det.get("status", "UNKNOWN")

            # Color scheme:
            # Green (SUCCESS / Present), Blue (ALREADY_MARKED), Red (UNKNOWN)
            if matched:
                if status == "SUCCESS":
                    box_color = (46, 204, 113)    # Emerald Green
                    badge_title = "ATTENDANCE MARKED"
                else:
                    box_color = (243, 156, 18)    # Amber / Orange (Already Logged)
                    badge_title = "ALREADY RECORDED"
            else:
                box_color = (60, 60, 235)         # Crimson Red
                badge_title = "UNRECOGNIZED"

            # 1. Sleek corner bracket bounding box
            corner_len = min(20, int(w * 0.25), int(h * 0.25))
            thick = 2
            # Top-Left
            cv2.line(frame, (x, y), (x + corner_len, y), box_color, thick)
            cv2.line(frame, (x, y), (x, y + corner_len), box_color, thick)
            # Top-Right
            cv2.line(frame, (x + w, y), (x + w - corner_len, y), box_color, thick)
            cv2.line(frame, (x + w, y), (x + w, y + corner_len), box_color, thick)
            # Bottom-Left
            cv2.line(frame, (x, y + h), (x + corner_len, y + h), box_color, thick)
            cv2.line(frame, (x, y + h), (x, y + h - corner_len), box_color, thick)
            # Bottom-Right
            cv2.line(frame, (x + w, y + h), (x + w - corner_len, y + h), box_color, thick)
            cv2.line(frame, (x + w, y + h), (x + w, y + h - corner_len), box_color, thick)

            # Semi-transparent bounding box outline
            cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 1)

            # 2. Sleek Name & Details Badge
            badge_h = 44
            badge_y1 = max(0, y - badge_h - 4)
            badge_y2 = badge_y1 + badge_h
            badge_w = max(180, w + 20)
            badge_x2 = min(frame.shape[1] - 4, x + badge_w)
            badge_x1 = max(4, badge_x2 - badge_w)

            # Draw badge background
            sub_img = frame[badge_y1:badge_y2, badge_x1:badge_x2]
            if sub_img.shape[0] > 0 and sub_img.shape[1] > 0:
                dark_rect = np.full(sub_img.shape, (15, 23, 42), dtype=np.uint8) # Dark slate
                blended = cv2.addWeighted(sub_img, 0.25, dark_rect, 0.75, 0)
                frame[badge_y1:badge_y2, badge_x1:badge_x2] = blended
                cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), box_color, 1)

                # Badge text
                conf_pct = int(score * 100) if score > 0 else 0
                title_line = f"{name} ({conf_pct}%)" if matched else "Unknown Member"
                sub_line = f"{sid} • {badge_title}" if matched else "Scan face again or register"

                cv2.putText(frame, title_line, (badge_x1 + 8, badge_y1 + 18),
                            cv2.FONT_HERSHEY_DUPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.putText(frame, sub_line, (badge_x1 + 8, badge_y1 + 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, box_color, 1, cv2.LINE_AA)

    def _draw_status_banner(self, frame):
        """Top banner showing Idea Lab SmartVision status, FPS, and live timestamp."""
        h, w = frame.shape[:2]
        
        # Subtle top bar
        cv2.rectangle(frame, (0, 0), (w, 30), (15, 23, 42), -1)
        cv2.line(frame, (0, 30), (w, 30), (37, 99, 235), 1)

        # Brand text
        cv2.putText(frame, "SmartVision AI | Idea Lab", (12, 20),
                    cv2.FONT_HERSHEY_DUPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)

        # Live time & FPS
        time_str = time.strftime("%H:%M:%S")
        info_str = f"FPS: {self.fps} | {time_str}"
        (tw, _), _ = cv2.getTextSize(info_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        cv2.putText(frame, info_str, (w - tw - 12, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (148, 163, 184), 1, cv2.LINE_AA)

    def _generate_fallback_frame(self):
        """Generates a stylish digital test card if camera device is missing or occupied."""
        frame = np.full((CAMERA_HEIGHT, CAMERA_WIDTH, 3), (20, 24, 33), dtype=np.uint8)
        
        # Grid lines
        for y in range(0, CAMERA_HEIGHT, 40):
            cv2.line(frame, (0, y), (CAMERA_WIDTH, y), (30, 36, 48), 1)
        for x in range(0, CAMERA_WIDTH, 40):
            cv2.line(frame, (x, 0), (x, CAMERA_HEIGHT), (30, 36, 48), 1)

        # Center target
        cx, cy = CAMERA_WIDTH // 2, CAMERA_HEIGHT // 2
        cv2.circle(frame, (cx, cy), 90, (37, 99, 235), 2)
        cv2.circle(frame, (cx, cy), 6, (46, 204, 113), -1)

        cv2.putText(frame, "CAMERA INITIALIZING / SIMULATION", (cx - 180, cy - 20),
                    cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Connecting to Camera Index {self.camera_index}...", (cx - 140, cy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (148, 163, 184), 1, cv2.LINE_AA)
        return frame

    def get_latest_jpeg(self):
        """Returns latest JPEG frame bytes for MJPEG streaming."""
        with self.lock:
            return self.latest_jpeg

    def get_snapshot(self):
        """Captures a snapshot frame for registration or snapshot archives."""
        with self.lock:
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
            return None

# Global camera manager instance
camera_manager = CameraManager()
