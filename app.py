import os
import time
import base64
import datetime
import cv2
import numpy as np
from pathlib import Path
from flask import (
    Flask, render_template, Response, request, jsonify,
    send_file, redirect, url_for, flash, session, abort
)

from config import (
    SECRET_KEY, HOST, PORT, DEBUG,
    STUDENT_PHOTOS_DIR, DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_COOLDOWN_MINUTES, DEFAULT_CAMERA_INDEX,
    SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE, PERMANENT_SESSION_LIFETIME,
    DEFAULT_CLASSES_PER_DAY, MINIMUM_REQUIRED_ATTENDANCE_PCT
)
import database
from security import (
    rate_limit, login_required, admin_required, student_required,
    apply_security_headers, sanitize_text, validate_student_id, validate_email
)
from face_engine import engine as face_engine
from arduino_bridge import arduino
from attendance_service import attendance_service
from camera_manager import camera_manager

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Configure Flask Session Security
app.config["SESSION_COOKIE_HTTPONLY"] = SESSION_COOKIE_HTTPONLY
app.config["SESSION_COOKIE_SAMESITE"] = SESSION_COOKIE_SAMESITE
app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
app.config["PERMANENT_SESSION_LIFETIME"] = PERMANENT_SESSION_LIFETIME

# Initialize database schema and default admin account
database.init_db()

# Auto-connect hardware bridge (simulation fallback if no physical board connected)
arduino.connect("AUTO")

# Start camera grabber thread
camera_manager.start()

# Security Middleware: Security Headers
@app.after_request
def security_header_middleware(response):
    return apply_security_headers(response)

# Inject current user into all Jinja templates
@app.context_processor
def inject_user_context():
    return {
        "current_user": session.get("username"),
        "current_role": session.get("role"),
        "current_name": session.get("full_name"),
        "student_id": session.get("student_id"),
        "year": datetime.datetime.now().year
    }

# ----------------- Video Stream Generator ----------------- #

def gen_frames():
    """Generator function yielding MJPEG video stream."""
    while True:
        frame_bytes = camera_manager.get_latest_jpeg()
        if frame_bytes is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            time.sleep(0.04)

@app.route('/video_feed')
def video_feed():
    """Video streaming route for <img> tag."""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ----------------- Authentication Routes ----------------- #

@app.route('/login', methods=['GET', 'POST'])
@rate_limit(max_requests=10, window_seconds=60)
def login_page():
    """Administrator Login Portal."""
    if session.get("user_id") and session.get("role") == "admin":
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = sanitize_text(request.form.get('username', ''))
        password = request.form.get('password', '')

        user = database.authenticate_user(username, password)
        if user and user["role"] == "admin":
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            next_url = request.args.get('next')
            return redirect(next_url if next_url and next_url.startswith('/') else url_for('index'))
        elif user and user["role"] == "student":
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            session["student_id"] = user["student_id"]
            flash(f"Welcome, {user['full_name']}! Redirecting to Student Portal.", "success")
            return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid administrator credentials. Access restricted.", "danger")

    return render_template('login.html', portal_type="admin")

@app.route('/student/login', methods=['GET', 'POST'])
@rate_limit(max_requests=10, window_seconds=60)
def student_login_page():
    """Student / Member Self-Service Portal Login."""
    if session.get("user_id") and session.get("role") == "student":
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        student_id = sanitize_text(request.form.get('student_id', '') or request.form.get('username', ''))
        password = request.form.get('password', '')

        user = database.authenticate_user(student_id, password)
        if user and user["role"] == "student":
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            session["student_id"] = user["student_id"]
            flash(f"Welcome, {user['full_name']}!", "success")
            return redirect(url_for('student_dashboard'))
        elif user and user["role"] == "admin":
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            flash(f"Welcome back, {user['full_name']}! Redirecting to Admin Dashboard.", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid Student ID or password. Use your enrolled Student ID to login.", "danger")

    return render_template('login.html', portal_type="student")

@app.route('/signup')
def signup_page():
    """Dual Sign Up Portal (Student & Teacher) with Mandatory Biometric Face Scan."""
    if session.get("user_id"):
        if session.get("role") == "admin":
            return redirect(url_for('index'))
        return redirect(url_for('student_dashboard'))
    return render_template('signup.html')

@app.route('/api/auth/signup', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60)
def api_auth_signup():
    """
    Public Sign Up & Face Biometric Registration Endpoint.
    Enrolls the face embedding into the entrance AI camera and provisions credentials.
    """
    try:
        name = sanitize_text(request.form.get('name', ''))
        email = sanitize_text(request.form.get('email', '')).lower()
        student_id = sanitize_text(request.form.get('student_id', '')).upper()
        department = sanitize_text(request.form.get('department', ''))
        role_type = sanitize_text(request.form.get('role', 'student')).lower()  # 'student' or 'admin'
        password = request.form.get('password', '')
        photo_mode = request.form.get('photo_mode', 'base64_snap')

        # 1. Validation
        if not name or not email or not student_id or not password:
            return jsonify({"success": False, "message": "All fields (Full Name, College Email, ID, Password) are required."}), 400

        if len(password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters long."}), 400

        if not validate_email(email):
            return jsonify({"success": False, "message": "Please enter a valid official college email address."}), 400

        if not validate_student_id(student_id):
            return jsonify({"success": False, "message": "ID contains invalid characters. Use alphanumeric characters or hyphens."}), 400

        biometric_consent = 1 if request.form.get('biometric_consent') == '1' else 0
        if not biometric_consent:
            return jsonify({"success": False, "message": "Biometric face processing consent is mandatory for registration."}), 400

        # Check existing user
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?) OR LOWER(student_id) = LOWER(?);",
                       (student_id, email, student_id))
        existing_user = cursor.fetchone()
        conn.close()

        if existing_user:
            return jsonify({"success": False, "message": f"An account with ID '{student_id}' or Email '{email}' already exists. Please sign in instead."}), 400

        # Check existing student
        existing_student = database.get_student_by_id(student_id)
        if existing_student:
            return jsonify({"success": False, "message": f"Student / Faculty ID '{student_id}' is already registered in the biometric database."}), 400

        # 2. Extract Face Image / Samples (MANDATORY)
        bgr_image = None
        multi_frames = []

        if photo_mode == 'camera_snap':
            snap = camera_manager.get_snapshot()
            if snap is None:
                return jsonify({"success": False, "message": "Could not access main lab camera. Please use live webcam snap or upload a portrait photo."}), 400
            bgr_image = snap

        elif photo_mode == 'base64_snap':
            base64_data = request.form.get('base64_image', '')
            if not base64_data:
                return jsonify({"success": False, "message": "Mandatory face biometric scan is missing. Please click 'Snap Face' before submitting."}), 400
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            try:
                img_bytes = base64.b64decode(base64_data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception as e:
                return jsonify({"success": False, "message": f"Invalid webcam image data: {str(e)}"}), 400

        elif photo_mode == 'multi_sample':
            raw_samples = request.form.getlist('samples[]')
            if not raw_samples:
                return jsonify({"success": False, "message": "No burst scan samples received. Please position face and retry burst scan."}), 400
            for s in raw_samples:
                if ',' in s:
                    s = s.split(',')[1]
                dec = base64.b64decode(s)
                nparr = np.frombuffer(dec, np.uint8)
                fr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if fr is not None:
                    multi_frames.append(fr)

        else:  # upload
            if 'photo' not in request.files or request.files['photo'].filename == '':
                return jsonify({"success": False, "message": "Please select a portrait image file to upload."}), 400
            file = request.files['photo']
            file_bytes = file.read()
            nparr = np.frombuffer(file_bytes, np.uint8)
            bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 3. AI Face Extraction & Alignment
        feature_embedding = None
        aligned_crop = None

        if multi_frames and len(multi_frames) > 1:
            ok, msg, feature_embedding, aligned_crop = face_engine.process_multi_sample_registration(multi_frames)
            if not ok:
                return jsonify({"success": False, "message": f"Face scan validation failed: {msg}. Please ensure your face is well-lit and directly facing the camera."}), 400
            sample_count = len(multi_frames)
        else:
            if bgr_image is None or bgr_image.size == 0:
                return jsonify({"success": False, "message": "No valid face image captured. Face scan is mandatory to register."}), 400
            ok, msg, feature_embedding, aligned_crop = face_engine.process_registration_image(bgr_image)
            if not ok:
                return jsonify({"success": False, "message": f"Face scan validation failed: {msg}. Please ensure your face is clearly visible inside the guide frame."}), 400
            sample_count = 1

        # 4. Save Biometric Portrait File
        photo_filename = f"{student_id}.jpg"
        save_path = STUDENT_PHOTOS_DIR / photo_filename
        if aligned_crop is not None and aligned_crop.size > 0:
            cv2.imwrite(str(save_path), aligned_crop)
        else:
            cv2.imwrite(str(save_path), bgr_image)
        rel_photo_path = f"uploads/students/{photo_filename}"

        # 5. Database Insertion
        assigned_role = "Teacher" if role_type == "admin" else "Student"
        user_role = "admin" if role_type == "admin" else "student"

        # Register in biometric directory so entrance camera recognizes them
        db_ok, db_msg = database.add_student(
            student_id=student_id,
            name=name,
            department=department or ("Faculty" if role_type == "admin" else "Engineering"),
            role=assigned_role,
            email=email,
            face_feature=feature_embedding,
            photo_path=rel_photo_path,
            sample_count=sample_count,
            biometric_consent=1,
            age_consent=1,
            initial_password=password
        )
        if not db_ok:
            return jsonify({"success": False, "message": db_msg}), 400

        # If admin role, set user account role to 'admin'
        if user_role == "admin":
            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET role = 'admin' WHERE LOWER(student_id) = LOWER(?) OR LOWER(username) = LOWER(?);",
                           (student_id, student_id))
            conn.commit()
            conn.close()

        # Reload camera recognition memory
        camera_manager.reload_students()

        # 6. Auto-login session for user
        user = database.authenticate_user(email, password) or database.authenticate_user(student_id, password)
        if user:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            session["student_id"] = user.get("student_id")

            redirect_url = url_for('index') if user["role"] == "admin" else url_for('student_dashboard')
            return jsonify({
                "success": True,
                "message": f"Account successfully created and face enrolled! Welcome to Idea Lab, {name}!",
                "redirect_url": redirect_url
            })

        return jsonify({
            "success": True,
            "message": "Registration successful! You may now sign in.",
            "redirect_url": url_for('login_page') if user_role == 'admin' else url_for('student_login_page')
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Registration server error: {str(e)}"}), 500

@app.route('/logout')
def logout():
    """Logs out current user session."""
    session.clear()
    flash("You have been signed out securely.", "info")
    return redirect(url_for('login_page'))

# ----------------- Student Personal Portal (Zero IDOR) ----------------- #

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    """Student Personal Attendance Portal (DigiCampus Reverse Engineered UI)."""
    student_id = session.get("student_id")
    if not student_id:
        return redirect(url_for('student_login_page'))

    summary = database.get_student_attendance_summary(student_id)
    if not summary:
        flash("Student profile not found.", "warning")
        return redirect(url_for('student_login_page'))

    academics = database.get_digicampus_academics(student_id)
    drilldown = database.get_digicampus_drilldown(student_id, 'EP101')
    active_tab = request.args.get('tab', 'academics') # 'academics', 'drilldown', or 'profile'

    return render_template(
        'student_dashboard.html',
        summary=summary,
        academics=academics,
        drilldown=drilldown,
        active_tab=active_tab
    )

@app.route('/student/request_deletion', methods=['POST'])
@student_required
def student_request_deletion():
    """GDPR / DPDP Right to be Forgotten deletion request by student."""
    student_id = session.get("student_id")
    reason = sanitize_text(request.form.get('reason', 'Student requested data removal'))
    student = database.get_student_by_id(student_id)
    name = student["name"] if student else session.get("full_name", "Student")

    database.create_deletion_request(student_id, name, reason)
    flash("Your data deletion request has been submitted to the Idea Lab Data Protection Officer.", "success")
    return redirect(url_for('student_dashboard'))

# ----------------- Admin Protected Routes ----------------- #

@app.route('/')
@admin_required
def index():
    """Main Admin Command Center Dashboard."""
    stats = database.get_dashboard_stats()
    hw_status = arduino.get_status()
    departments = [d["department"] for d in stats["dept_stats"] if d.get("department")]
    return render_template(
        'index.html',
        stats=stats,
        hw_status=hw_status,
        departments=departments,
        camera_available=camera_manager.is_camera_available
    )

@app.route('/students')
@admin_required
def students():
    """Registered Members Directory with Individual Attendance Rates."""
    all_students_summary = database.get_all_students_attendance_summary()
    departments = sorted(list(set(s["department"] for s in all_students_summary if s.get("department"))))
    return render_template('students.html', students=all_students_summary, departments=departments)

@app.route('/register')
@admin_required
def register_page():
    """Member Enrollment Page."""
    return render_template('register.html')

@app.route('/attendance')
@admin_required
def attendance_page():
    """Attendance History and Audit Trail."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    date_filter = request.args.get('date', today_str)
    dept_filter = request.args.get('department', 'All')
    status_filter = request.args.get('status', 'All')
    search_q = sanitize_text(request.args.get('q', '').strip())
    lab_date = sanitize_text(request.args.get('lab_date', today_str))

    lab_matrix = database.get_lab_date_matrix(lab_date)

    records = database.get_attendance_records(
        start_date=date_filter if date_filter != 'All' else None,
        end_date=date_filter if date_filter != 'All' else None,
        student_id=search_q if search_q else None,
        department=dept_filter if dept_filter != 'All' else None,
        status=status_filter if status_filter != 'All' else None,
        limit=1000
    )

    all_students = database.get_all_students(active_only=True)
    departments = sorted(list(set(s["department"] for s in all_students if s.get("department"))))

    return render_template(
        'attendance.html',
        records=records,
        date_filter=date_filter,
        dept_filter=dept_filter,
        status_filter=status_filter,
        search_q=search_q,
        departments=departments,
        students=all_students,
        lab_matrix=lab_matrix
    )

@app.route('/hardware')
@admin_required
def hardware_page():
    """Hardware Diagnostics & Arduino IoT Controller."""
    hw_status = arduino.get_status()
    ports = arduino.list_available_ports()
    recent_logs = database.get_recent_hardware_logs(30)
    return render_template(
        'hardware.html',
        hw_status=hw_status,
        available_ports=ports,
        recent_logs=recent_logs
    )

@app.route('/settings')
@admin_required
def settings_page():
    """System Preferences and Thresholds."""
    current_settings = {
        "confidence_threshold": database.get_setting("confidence_threshold", str(DEFAULT_CONFIDENCE_THRESHOLD)),
        "cooldown_minutes": database.get_setting("cooldown_minutes", str(DEFAULT_COOLDOWN_MINUTES)),
        "camera_index": database.get_setting("camera_index", str(DEFAULT_CAMERA_INDEX)),
        "serial_port": database.get_setting("serial_port", "AUTO"),
        "baud_rate": database.get_setting("baud_rate", "9600"),
        "duplicate_rule": database.get_setting("duplicate_rule", "COOLDOWN"),
        "classes_per_day": database.get_setting("classes_per_day", str(DEFAULT_CLASSES_PER_DAY)),
        "min_required_pct": database.get_setting("min_required_pct", str(MINIMUM_REQUIRED_ATTENDANCE_PCT))
    }
    admins = database.get_all_admins()
    deletion_requests = database.get_deletion_requests()
    return render_template('settings.html', settings=current_settings, admins=admins, deletion_requests=deletion_requests)

# ----------------- Public / Kiosk / Legal Routes ----------------- #

@app.route('/live')
def live_kiosk():
    """Entrance Attendance Kiosk View (View-only for lab entrance display)."""
    hw_status = arduino.get_status()
    return render_template('live.html', hw_status=hw_status)

@app.route('/privacy')
def privacy_page():
    """GDPR & DPDP Act 2023 Biometric Privacy Policy."""
    return render_template('legal/privacy.html')

@app.route('/terms')
def terms_page():
    """Terms of Service."""
    return render_template('legal/terms.html')

@app.route('/refund')
def refund_page():
    """Refund & Fee Policy."""
    return render_template('legal/refund.html')

@app.route('/cookies')
def cookies_page():
    """Cookie Policy."""
    return render_template('legal/cookies.html')

# ----------------- Secure API Endpoints ----------------- #

@app.route('/api/students/register', methods=['POST'])
@admin_required
@rate_limit(max_requests=20, window_seconds=60)
def api_register_student():
    """Registers student with face embedding & consent checks."""
    try:
        student_id = sanitize_text(request.form.get('student_id', '')).upper()
        name = sanitize_text(request.form.get('name', ''))
        department = sanitize_text(request.form.get('department', ''))
        role = sanitize_text(request.form.get('role', 'Member'))
        email = sanitize_text(request.form.get('email', ''))
        phone = sanitize_text(request.form.get('phone', ''))
        initial_pwd = request.form.get('password', '')
        photo_mode = request.form.get('photo_mode', 'upload')

        # Form consent validations
        biometric_consent = 1 if request.form.get('biometric_consent') == '1' else 0
        age_consent = 1 if request.form.get('age_consent') == '1' else 0

        if not biometric_consent:
            return jsonify({"success": False, "message": "Biometric data processing consent is required to enroll."}), 400

        if not student_id or not name or not department:
            return jsonify({"success": False, "message": "Student ID, Name, and Department are required."}), 400

        if not validate_student_id(student_id):
            return jsonify({"success": False, "message": "Student ID contains invalid characters. Use alphanumeric, hyphens, or dots."}), 400

        if email and not validate_email(email):
            return jsonify({"success": False, "message": "Invalid email address format."}), 400

        existing = database.get_student_by_id(student_id)
        if existing:
            return jsonify({"success": False, "message": f"Student ID '{student_id}' is already registered."}), 400

        bgr_image = None
        multi_frames = []

        if photo_mode == 'camera_snap':
            snap = camera_manager.get_snapshot()
            if snap is None:
                return jsonify({"success": False, "message": "Failed to capture snapshot from webcam."}), 500
            bgr_image = snap

        elif photo_mode == 'base64_snap':
            base64_data = request.form.get('base64_image', '')
            if not base64_data:
                return jsonify({"success": False, "message": "No webcam image data received."}), 400
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            img_bytes = base64.b64decode(base64_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        elif photo_mode == 'multi_sample':
            raw_samples = request.form.getlist('samples[]')
            for s in raw_samples:
                if ',' in s:
                    s = s.split(',')[1]
                dec = base64.b64decode(s)
                nparr = np.frombuffer(dec, np.uint8)
                fr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if fr is not None:
                    multi_frames.append(fr)

        else: # Upload
            if 'photo' not in request.files or request.files['photo'].filename == '':
                return jsonify({"success": False, "message": "Please select a photo file to upload."}), 400
            file = request.files['photo']
            file_bytes = file.read()
            nparr = np.frombuffer(file_bytes, np.uint8)
            bgr_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        feature_embedding = None
        aligned_crop = None

        if multi_frames and len(multi_frames) > 1:
            ok, msg, feature_embedding, aligned_crop = face_engine.process_multi_sample_registration(multi_frames)
            if not ok:
                return jsonify({"success": False, "message": msg}), 400
            sample_count = len(multi_frames)
        else:
            if bgr_image is None or bgr_image.size == 0:
                return jsonify({"success": False, "message": "Invalid image received."}), 400
            ok, msg, feature_embedding, aligned_crop = face_engine.process_registration_image(bgr_image)
            if not ok:
                return jsonify({"success": False, "message": msg}), 400
            sample_count = 1

        photo_filename = f"{student_id}.jpg"
        save_path = STUDENT_PHOTOS_DIR / photo_filename
        if aligned_crop is not None and aligned_crop.size > 0:
            cv2.imwrite(str(save_path), aligned_crop)
        else:
            cv2.imwrite(str(save_path), bgr_image)

        rel_photo_path = f"uploads/students/{photo_filename}"

        db_ok, db_msg = database.add_student(
            student_id=student_id,
            name=name,
            department=department,
            role=role,
            email=email if email else None,
            phone=phone if phone else None,
            face_feature=feature_embedding,
            photo_path=rel_photo_path,
            sample_count=sample_count,
            biometric_consent=biometric_consent,
            age_consent=age_consent,
            initial_password=initial_pwd if initial_pwd else None
        )

        if not db_ok:
            return jsonify({"success": False, "message": db_msg}), 400

        camera_manager.reload_students()

        return jsonify({
            "success": True,
            "message": f"Member '{name}' enrolled successfully! Login account provisioned with ID '{student_id}'.",
            "photo_path": rel_photo_path
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Enrollment error: {str(e)}"}), 500

@app.route('/api/students/delete', methods=['POST'])
@admin_required
def api_delete_student():
    """Purges student and all associated data."""
    student_id = sanitize_text(request.form.get('student_id', '')).upper()
    if not student_id:
        return jsonify({"success": False, "message": "Student ID required."}), 400

    ok, msg = database.execute_purge_student_data(student_id)
    camera_manager.reload_students()
    return jsonify({"success": ok, "message": msg})

@app.route('/api/students/get/<student_id>')
@admin_required
def api_get_student(student_id):
    """Retrieves student details and individual attendance calculations."""
    student_id = sanitize_text(student_id).upper()
    summary = database.get_student_attendance_summary(student_id)
    if not summary:
        return jsonify({"success": False, "message": "Student not found."}), 404
    return jsonify({"success": True, "student": summary})

@app.route('/api/attendance/manual', methods=['POST'])
@admin_required
def api_manual_attendance():
    """Manually marks attendance with audit reason."""
    student_id = sanitize_text(request.form.get('student_id', '')).upper()
    note = sanitize_text(request.form.get('note', 'Manual verification by admin'))

    if not student_id:
        return jsonify({"success": False, "message": "Student ID required."}), 400

    ok, msg = attendance_service.manual_mark_attendance(student_id, note)
    return jsonify({"success": ok, "message": msg})

@app.route('/api/attendance/update_classes', methods=['POST'])
@admin_required
def api_update_attendance_classes():
    """Credits or updates classes attended for a student on a specific date (e.g. 7 out of 10)."""
    student_id = sanitize_text(request.form.get('student_id', '')).upper()
    date_str = sanitize_text(request.form.get('date', datetime.date.today().strftime('%Y-%m-%d')))
    classes_att = request.form.get('classes_attended', '10')
    total_classes = request.form.get('total_classes', '10')

    if not student_id:
        return jsonify({"success": False, "message": "Student ID required."}), 400

    try:
        ok, msg = database.update_attendance_classes(
            student_id=student_id,
            date_str=date_str,
            classes_attended=int(classes_att),
            total_classes_for_day=int(total_classes)
        )
        return jsonify({"success": ok, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# ----------------- IDEA Lab Session-Wise API Endpoints ----------------- #

@app.route('/api/lab/matrix', methods=['GET'])
@admin_required
def api_lab_matrix():
    """Returns matrix of students and their slot attendance for a specific date."""
    target_date = sanitize_text(request.args.get('date', datetime.date.today().strftime('%Y-%m-%d')))
    matrix = database.get_lab_date_matrix(target_date)
    return jsonify({"success": True, "data": matrix})

@app.route('/api/lab/attendance/toggle', methods=['POST'])
@admin_required
def api_lab_attendance_toggle():
    """
    Toggles or sets attendance for a student for a specific slot on a date.
    Enforces the 6:00 PM lock rule.
    """
    student_id = sanitize_text(request.form.get('student_id', '')).upper()
    date_str = sanitize_text(request.form.get('date', ''))
    slot_num = request.form.get('slot_number', '1')
    new_status = sanitize_text(request.form.get('status', 'PRESENT')).upper()
    allow_override = request.form.get('allow_override', 'false').lower() in ('true', '1')
    admin_notes = sanitize_text(request.form.get('admin_notes', ''))

    if not student_id or not date_str:
        return jsonify({"success": False, "message": "Student ID and Date are required."}), 400

    # Check 6:00 PM lock
    is_locked, lock_msg, time_info = database.check_session_lock(date_str, allow_override=allow_override)
    if is_locked:
        return jsonify({
            "success": False,
            "locked": True,
            "message": lock_msg,
            "time_info": time_info
        }), 403

    ok, msg = database.toggle_slot_attendance(
        student_id=student_id,
        date_str=date_str,
        slot_number=int(slot_num),
        new_status=new_status,
        allow_override=allow_override,
        admin_notes=admin_notes
    )

    if ok:
        return jsonify({
            "success": True,
            "message": msg,
            "student_id": student_id,
            "date": date_str,
            "slot_number": int(slot_num),
            "new_status": new_status,
            "is_locked": is_locked
        })
    else:
        return jsonify({"success": False, "message": msg}), 400

@app.route('/api/lab/attendance/bulk_toggle', methods=['POST'])
@admin_required
def api_lab_attendance_bulk_toggle():
    """
    Bulk marks all active students as PRESENT, ABSENT, or NOT_MARKED for a specific slot on a date.
    Enforces the 6:00 PM lock rule unless allow_override=True.
    """
    date_str = sanitize_text(request.form.get('date', ''))
    slot_num = request.form.get('slot_number', '1')
    new_status = sanitize_text(request.form.get('status', 'PRESENT')).upper()
    allow_override = request.form.get('allow_override', 'false').lower() in ('true', '1')
    admin_notes = sanitize_text(request.form.get('admin_notes', ''))

    if not date_str:
        return jsonify({"success": False, "message": "Date is required."}), 400

    is_locked, lock_msg, time_info = database.check_session_lock(date_str, allow_override=allow_override)
    if is_locked:
        return jsonify({
            "success": False,
            "locked": True,
            "message": lock_msg,
            "time_info": time_info
        }), 403

    ok, msg, count = database.bulk_toggle_lab_attendance(
        date_str=date_str,
        slot_number=int(slot_num),
        status=new_status,
        allow_override=allow_override,
        admin_notes=admin_notes
    )

    if ok:
        return jsonify({
            "success": True,
            "message": msg,
            "count": count,
            "date": date_str,
            "slot_number": int(slot_num),
            "new_status": new_status
        })
    else:
        return jsonify({"success": False, "message": msg}), 400

@app.route('/api/student/digicampus/academics')
@student_required
def api_student_digicampus_academics():
    """Returns JSON of DigiCampus current term academics for the logged-in student."""
    student_id = session.get("student_id")
    academics = database.get_digicampus_academics(student_id)
    return jsonify({"success": True, "data": academics})

@app.route('/api/admin/create_admin', methods=['POST'])
@admin_required
def api_create_admin():
    """Adds a new authorized administrator account."""
    username = sanitize_text(request.form.get('username', '')).lower()
    full_name = sanitize_text(request.form.get('full_name', ''))
    email = sanitize_text(request.form.get('email', ''))
    password = request.form.get('password', '')

    if not username or not full_name or not password:
        flash("Username, Full Name, and Password are required.", "danger")
        return redirect(url_for('settings_page'))

    if len(password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for('settings_page'))

    ok, msg = database.create_user(username, password, role="admin", full_name=full_name, email=email)
    if ok:
        flash(f"Authorized Administrator '{full_name}' added successfully.", "success")
    else:
        flash(f"Error adding admin: {msg}", "danger")
    return redirect(url_for('settings_page'))

@app.route('/api/admin/purge_request', methods=['POST'])
@admin_required
def api_admin_purge_request():
    """Processes a GDPR/DPDP student data purge request."""
    student_id = sanitize_text(request.form.get('student_id', '')).upper()
    ok, msg = database.execute_purge_student_data(student_id)
    camera_manager.reload_students()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for('settings_page'))

@app.route('/api/live_events')
def api_live_events():
    """Returns recent recognition events for UI polling."""
    events = attendance_service.get_live_events()
    hw_status = arduino.get_status()
    stats = database.get_dashboard_stats()
    return jsonify({
        "events": events[-10:],
        "hw_status": hw_status,
        "today_present": stats["today_present"],
        "turnout_pct": stats["turnout_pct"],
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
    })

# ----------------- Hardware APIs (Admin Protected) ----------------- #

@app.route('/api/hardware/scan')
@admin_required
def api_hardware_scan():
    ports = arduino.list_available_ports()
    return jsonify({"ports": ports})

@app.route('/api/hardware/connect', methods=['POST'])
@admin_required
def api_hardware_connect():
    port_name = sanitize_text(request.form.get('port', 'AUTO'))
    baud_rate = int(request.form.get('baud', 9600))
    database.set_setting("serial_port", port_name)
    database.set_setting("baud_rate", str(baud_rate))

    ok, msg = arduino.connect(port_name, baud_rate)
    return jsonify({"success": ok, "message": msg, "status": arduino.get_status()})

@app.route('/api/hardware/disconnect', methods=['POST'])
@admin_required
def api_hardware_disconnect():
    arduino.disconnect()
    return jsonify({"success": True, "message": "Hardware disconnected. Running in Virtual Mode.", "status": arduino.get_status()})

@app.route('/api/hardware/test', methods=['POST'])
@admin_required
def api_hardware_test():
    action = request.form.get('action', 'test_green')
    if action == 'test_green':
        ok, msg = arduino.test_green_led()
    elif action == 'test_red':
        ok, msg = arduino.test_red_led()
    elif action == 'test_buzzer':
        ok, msg = arduino.test_buzzer()
    elif action == 'ping':
        ok, msg = arduino.send_command("PING")
    else:
        return jsonify({"success": False, "message": "Unknown action."}), 400
    return jsonify({"success": ok, "message": msg, "status": arduino.get_status()})

@app.route('/api/hardware/status')
@admin_required
def api_hardware_status():
    logs = database.get_recent_hardware_logs(20)
    return jsonify({"status": arduino.get_status(), "recent_logs": logs})

# ----------------- Settings & Export APIs ----------------- #

@app.route('/api/settings/save', methods=['POST'])
@admin_required
def api_save_settings():
    conf = request.form.get('confidence_threshold')
    cooldown = request.form.get('cooldown_minutes')
    cam_idx = request.form.get('camera_index')
    dup_rule = request.form.get('duplicate_rule')
    classes_per_day = request.form.get('classes_per_day')
    min_pct = request.form.get('min_required_pct')

    if conf is not None:
        database.set_setting("confidence_threshold", str(float(conf)))
    if cooldown is not None:
        database.set_setting("cooldown_minutes", str(int(cooldown)))
    if dup_rule is not None:
        database.set_setting("duplicate_rule", dup_rule)
    if classes_per_day is not None:
        database.set_setting("classes_per_day", str(int(classes_per_day)))
    if min_pct is not None:
        database.set_setting("min_required_pct", str(float(min_pct)))
    if cam_idx is not None and int(cam_idx) != camera_manager.camera_index:
        camera_manager.change_camera(int(cam_idx))

    flash("System settings & academic parameters updated successfully!", "success")
    return redirect(url_for('settings_page'))

@app.route('/export/csv')
@admin_required
def export_csv():
    date_filter = request.args.get('date', None)
    dept_filter = request.args.get('department', None)
    status_filter = request.args.get('status', None)

    csv_content = attendance_service.generate_csv_report(
        start_date=date_filter if date_filter and date_filter != 'All' else None,
        end_date=date_filter if date_filter and date_filter != 'All' else None,
        department=dept_filter if dept_filter and dept_filter != 'All' else None,
        status=status_filter if status_filter and status_filter != 'All' else None
    )

    filename = f"SmartVision_Attendance_{date_filter or 'All'}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/export/excel')
@admin_required
def export_excel():
    date_filter = request.args.get('date', None)
    dept_filter = request.args.get('department', None)
    status_filter = request.args.get('status', None)

    excel_path, filename = attendance_service.generate_excel_report(
        start_date=date_filter if date_filter and date_filter != 'All' else None,
        end_date=date_filter if date_filter and date_filter != 'All' else None,
        department=dept_filter if dept_filter and dept_filter != 'All' else None,
        status=status_filter if status_filter and status_filter != 'All' else None
    )

    return send_file(
        excel_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == '__main__':
    print("=" * 65)
    print("  SmartVision: Enterprise AI Attendance & IoT Controller")
    print(f"  Idea Lab Server running at: http://{HOST}:{PORT}")
    print(f"  Admin Login Portal:        http://localhost:{PORT}/login")
    print(f"  Student Portal:            http://localhost:{PORT}/student/login")
    print(f"  Live Kiosk Entrance:       http://localhost:{PORT}/live")
    print("=" * 65)
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
