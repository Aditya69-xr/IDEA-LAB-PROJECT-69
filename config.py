import os
import secrets
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent

# Check if running in Vercel Serverless environment
IS_VERCEL = bool(os.getenv("VERCEL"))
if IS_VERCEL:
    DATA_DIR = Path("/tmp/data")
    EXPORTS_DIR = Path("/tmp/exports")
    UPLOADS_DIR = Path("/tmp/uploads")
    STUDENT_PHOTOS_DIR = UPLOADS_DIR / "students"
    SNAPSHOTS_DIR = UPLOADS_DIR / "snapshots"
else:
    DATA_DIR = BASE_DIR / "data"
    EXPORTS_DIR = BASE_DIR / "exports"
    UPLOADS_DIR = BASE_DIR / "static" / "uploads"
    STUDENT_PHOTOS_DIR = UPLOADS_DIR / "students"
    SNAPSHOTS_DIR = UPLOADS_DIR / "snapshots"

MODELS_DIR = BASE_DIR / "models"
STATIC_DIR = BASE_DIR / "static"

# Ensure essential directories exist
for folder in [DATA_DIR, MODELS_DIR, STATIC_DIR, UPLOADS_DIR, STUDENT_PHOTOS_DIR, SNAPSHOTS_DIR, EXPORTS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Load environment variables from .env
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Security: Secret Key (Load from env or generate robust random token)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)

# Production security controls
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
FLASK_ENV = os.getenv("FLASK_ENV", "production")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))

# Session Security (OWASP Recommended)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")
PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("PERMANENT_SESSION_LIFETIME_HOURS", "12")))

# Initial Admin Credentials (Provisioned securely on first initialization)
INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "Admin@IdeaLab2026!")
INITIAL_ADMIN_NAME = os.getenv("INITIAL_ADMIN_NAME", "Idea Lab Administrator")
INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", "idealab@college.edu")

# Academic & College Attendance Parameters
DEFAULT_CLASSES_PER_DAY = int(os.getenv("DEFAULT_CLASSES_PER_DAY", "10"))
MINIMUM_REQUIRED_ATTENDANCE_PCT = float(os.getenv("MINIMUM_REQUIRED_ATTENDANCE_PCT", "75.0"))

# IDEA Lab Specific Attendance Rules (2 Sessions per Lab Day, 50% Threshold, 6:00 PM Edit Lock)
LAB_CLASSES_PER_DAY = 2
LAB_MINIMUM_REQUIRED_ATTENDANCE_PCT = 50.0  # Minimum 50% attendance required for IDEA Lab
LAB_CUTOFF_HOUR = 18  # 6:00 PM (18:00) lock cutoff
LAB_SLOT_1_TIME = "01:20 PM"
LAB_SLOT_2_TIME = "02:10 PM"

# Database
DB_PATH = DATA_DIR / "smartvision.db"

# Deep Learning Vision Models (YuNet Face Detector & SFace Recognizer)
YUNET_MODEL_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# Default AI Recognition Parameters
DEFAULT_CONFIDENCE_THRESHOLD = 0.40  # SFace cosine similarity benchmark
DETECTOR_SCORE_THRESHOLD = 0.70      # YuNet detection score
DETECTOR_NMS_THRESHOLD = 0.30        # YuNet NMS suppression
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
DEFAULT_CAMERA_INDEX = 0

# Anti-Duplicate Rules
DEFAULT_COOLDOWN_MINUTES = 60
DUPLICATE_MODE = "COOLDOWN"

# Hardware / Arduino Settings
DEFAULT_SERIAL_PORT = "AUTO"
DEFAULT_BAUD_RATE = 9600
SERIAL_TIMEOUT = 1.0
