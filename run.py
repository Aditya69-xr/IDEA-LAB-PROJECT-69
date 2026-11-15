"""
SmartVision: AI Face Recognition Attendance System for Idea Lab
Enterprise Launcher & Pre-flight Diagnostics
"""

import sys
import os
import subprocess

def check_environment():
    print("=" * 68)
    print("  SmartVision: AI-Based Face Detection Attendance System")
    print("  Idea Lab Enterprise Architecture • Security & IoT Integrated")
    print("=" * 68)
    print(f"[1/4] Python Runtime: {sys.version.split()[0]} (Verified)")

    # Verify key dependencies
    required = ["cv2", "flask", "numpy", "serial", "xlsxwriter", "dotenv"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[!] Installing missing packages: {', '.join(missing)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("[2/4] Core Dependencies Verified (Verified)")

    # Check model files
    from config import YUNET_MODEL_PATH, SFACE_MODEL_PATH
    if not os.path.exists(YUNET_MODEL_PATH) or not os.path.exists(SFACE_MODEL_PATH):
        print("[!] Deep learning neural models missing. Downloading...")
        import urllib.request
        os.makedirs(os.path.dirname(YUNET_MODEL_PATH), exist_ok=True)
        if not os.path.exists(YUNET_MODEL_PATH):
            urllib.request.urlretrieve("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", YUNET_MODEL_PATH)
        if not os.path.exists(SFACE_MODEL_PATH):
            urllib.request.urlretrieve("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx", SFACE_MODEL_PATH)
    print("[3/4] Deep Neural Network Vision Models Verified (Verified)")

    # Initialize Database & Schema
    import database
    database.init_db()
    print("[4/4] SQLite Database & Schema Verified (Verified)")

def main():
    check_environment()
    from config import PORT, HOST, INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_PASSWORD, DEBUG

    print("\n" + "=" * 68)
    print(f"  >>> Admin Command Center: http://localhost:{PORT}")
    print(f"  >>> Admin Login:          http://localhost:{PORT}/login")
    print(f"  >>> Student Portal:       http://localhost:{PORT}/student/login")
    print(f"  >>> Sign Up & Face Scan:  http://localhost:{PORT}/signup")
    print(f"  >>> Entrance Kiosk View:  http://localhost:{PORT}/live")
    print(f"  >>> Hardware Controller:  http://localhost:{PORT}/hardware")
    print(f"  >>> Privacy Policy:       http://localhost:{PORT}/privacy")
    print("-" * 68)
    print(f"  Initial Admin Username:   {INITIAL_ADMIN_USERNAME}")
    print(f"  Initial Admin Password:   {INITIAL_ADMIN_PASSWORD}")
    print("=" * 68 + "\n")

    from app import app
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)

if __name__ == '__main__':
    main()
