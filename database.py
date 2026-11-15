import sqlite3
import datetime
import math
import numpy as np
from pathlib import Path
from config import (
    DB_PATH, DEFAULT_CONFIDENCE_THRESHOLD, DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_CAMERA_INDEX, DEFAULT_SERIAL_PORT, DEFAULT_BAUD_RATE,
    INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_PASSWORD, INITIAL_ADMIN_NAME, INITIAL_ADMIN_EMAIL,
    DEFAULT_CLASSES_PER_DAY, MINIMUM_REQUIRED_ATTENDANCE_PCT,
    LAB_CLASSES_PER_DAY, LAB_MINIMUM_REQUIRED_ATTENDANCE_PCT, LAB_CUTOFF_HOUR,
    LAB_SLOT_1_TIME, LAB_SLOT_2_TIME
)
from security import hash_password, verify_password

def get_db_connection():
    """Returns a thread-safe connection with dictionary-like row factory and WAL mode."""
    conn = sqlite3.connect(str(DB_PATH), timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    """Initializes schema, security tables, and default admin account."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users table (Authentication & RBAC: admin vs student)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student', -- 'admin' or 'student'
            student_id TEXT,
            full_name TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );
    """)

    # 2. Students table (Enrolled biometric profiles)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            role TEXT DEFAULT 'Member',
            email TEXT,
            phone TEXT,
            face_feature BLOB,
            photo_path TEXT,
            sample_count INTEGER DEFAULT 1,
            biometric_consent INTEGER DEFAULT 1,
            age_consent INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );
    """)

    # 3. Attendance table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            department TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            classes_attended INTEGER DEFAULT 10, -- Number of classes credited for this day
            status TEXT DEFAULT 'Present',
            confidence REAL DEFAULT 1.0,
            snapshot_path TEXT,
            marked_via TEXT DEFAULT 'AI_CAMERA',
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );
    """)

    # 4. Academic Working Sessions / Days table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS academic_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            session_name TEXT DEFAULT 'Regular Lab Session',
            total_classes INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 5. GDPR / DPDP Data Deletion Requests table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deletion_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'PENDING',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        );
    """)

    # 6. Settings table (Key-Value)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # 7. Hardware Logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hardware_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            command TEXT NOT NULL,
            status TEXT NOT NULL,
            port TEXT,
            details TEXT
        );
    """)

    # 8. IDEA Lab Class Sessions table (2 Slots per Lab Day: 01:20 PM & 02:10 PM)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lab_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            slot_number INTEGER NOT NULL, -- 1 or 2
            slot_time TEXT NOT NULL, -- '01:20 PM' or '02:10 PM'
            subject_name TEXT DEFAULT 'Exploratory Project',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, slot_number)
        );
    """)

    # 9. IDEA Lab Student Session Attendance Ledger
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lab_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date TEXT NOT NULL,
            slot_number INTEGER NOT NULL, -- 1 or 2
            slot_time TEXT NOT NULL, -- '01:20 PM' or '02:10 PM'
            status TEXT NOT NULL DEFAULT 'PRESENT', -- 'PRESENT', 'ABSENT', 'NOT_MARKED'
            marked_via TEXT DEFAULT 'AI_CAMERA', -- 'AI_CAMERA', 'ADMIN_MANUAL', 'PENDING'
            admin_notes TEXT,
            is_override INTEGER DEFAULT 0,
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            UNIQUE(student_id, date, slot_number)
        );
    """)

    # 10. DigiCampus Academic Courses (Reverse Engineered ERP Course Registry)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS digicampus_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'Practical / Lab',
            faculty_name TEXT DEFAULT 'Faculty',
            credits INTEGER DEFAULT 2,
            min_pct REAL DEFAULT 50.0,
            mock_attended INTEGER DEFAULT 0,
            mock_held INTEGER DEFAULT 0,
            bar_color TEXT DEFAULT '#ff4d4f',
            display_order INTEGER DEFAULT 1
        );
    """)

    # Migrations for existing tables
    def ensure_column(table_name, col_name, col_def):
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};")
        except sqlite3.OperationalError:
            pass # Column already exists

    ensure_column("attendance", "classes_attended", "INTEGER DEFAULT 10")
    ensure_column("attendance", "total_classes_for_day", "INTEGER DEFAULT 10")
    ensure_column("students", "biometric_consent", "INTEGER DEFAULT 1")
    ensure_column("students", "age_consent", "INTEGER DEFAULT 1")
    defaults = {
        "confidence_threshold": str(DEFAULT_CONFIDENCE_THRESHOLD),
        "cooldown_minutes": str(DEFAULT_COOLDOWN_MINUTES),
        "camera_index": str(DEFAULT_CAMERA_INDEX),
        "serial_port": str(DEFAULT_SERIAL_PORT),
        "baud_rate": str(DEFAULT_BAUD_RATE),
        "classes_per_day": str(DEFAULT_CLASSES_PER_DAY),
        "min_required_pct": str(MINIMUM_REQUIRED_ATTENDANCE_PCT),
        "lab_min_required_pct": str(LAB_MINIMUM_REQUIRED_ATTENDANCE_PCT),
        "duplicate_rule": "COOLDOWN"
    }
    for key, val in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (key, val))

    # Provision Initial Super Admin Account if none exists
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin';")
    if cursor.fetchone()["cnt"] == 0:
        admin_hash = hash_password(INITIAL_ADMIN_PASSWORD)
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, full_name, email)
            VALUES (?, ?, 'admin', ?, ?);
        """, (INITIAL_ADMIN_USERNAME, admin_hash, INITIAL_ADMIN_NAME, INITIAL_ADMIN_EMAIL))
        print(f"[Database] Super Admin provisioned: {INITIAL_ADMIN_USERNAME}")

    # Ensure today's academic session entry exists
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute("INSERT OR IGNORE INTO academic_sessions (date, total_classes) VALUES (?, ?);",
                   (today_str, DEFAULT_CLASSES_PER_DAY))

    conn.commit()
    conn.close()

    # Seed initial lab schedule & historical records
    seed_default_lab_schedule()
    # Seed DigiCampus curriculum course catalog matching ERP Image 1
    seed_digicampus_courses()

# ----------------- User Authentication & Management ----------------- #

def authenticate_user(identifier, password):
    """Verifies credentials by checking username, email, or student_id (case-insensitive)."""
    if not identifier or not password:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    clean_id = identifier.strip().lower()
    cursor.execute("""
        SELECT * FROM users
        WHERE (LOWER(username) = ? OR LOWER(COALESCE(email, '')) = ? OR LOWER(COALESCE(student_id, '')) = ?)
          AND is_active = 1;
    """, (clean_id, clean_id, clean_id))
    user = cursor.fetchone()
    conn.close()

    if user and verify_password(user["password_hash"], password):
        return dict(user)
    return None

def create_user(username, password, role="student", full_name="", email=None, student_id=None):
    """Creates a new user account with hashed password."""
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(password)
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, full_name, email, student_id)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (username.strip(), pwd_hash, role, full_name.strip(), email, student_id))
        conn.commit()
        return True, "User account created successfully."
    except sqlite3.IntegrityError:
        return False, f"Username '{username}' already exists."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, full_name, email, student_id, is_active FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_admins():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, email, created_at FROM users WHERE role = 'admin' ORDER BY id ASC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_user_password(user_id, new_password):
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?;", (pwd_hash, user_id))
    conn.commit()
    conn.close()
    return True

# ----------------- Student Management ----------------- #

def serialize_feature(feature_np):
    if feature_np is None:
        return None
    return feature_np.astype(np.float32).tobytes()

def deserialize_feature(blob):
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)

def add_student(student_id, name, department, role="Member", email=None, phone=None,
                face_feature=None, photo_path=None, sample_count=1,
                biometric_consent=1, age_consent=1, initial_password=None):
    """Adds new student and automatically creates their personal student login account."""
    conn = get_db_connection()
    cursor = conn.cursor()
    feature_blob = serialize_feature(face_feature)

    sid = student_id.strip()
    s_name = name.strip()
    dept = department.strip()

    try:
        cursor.execute("""
            INSERT INTO students (student_id, name, department, role, email, phone,
                                  face_feature, photo_path, sample_count, biometric_consent, age_consent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (sid, s_name, dept, role.strip(), email, phone, feature_blob, photo_path, sample_count, biometric_consent, age_consent))

        # Create student login account (Default password is sid or custom)
        student_pwd = initial_password or f"Student@{sid}"
        pwd_hash = hash_password(student_pwd)
        cursor.execute("""
            INSERT OR REPLACE INTO users (username, password_hash, role, full_name, email, student_id)
            VALUES (?, ?, 'student', ?, ?, ?);
        """, (sid, pwd_hash, s_name, email, sid))

        conn.commit()
        return True, "Student enrolled and account provisioned successfully."
    except sqlite3.IntegrityError:
        return False, f"A student with ID '{sid}' already exists."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_student(student_id):
    """Deletes student record, cascade removes attendance, and removes user account."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM attendance WHERE student_id = ?;", (student_id,))
        cursor.execute("DELETE FROM users WHERE student_id = ?;", (student_id,))
        cursor.execute("DELETE FROM students WHERE student_id = ?;", (student_id,))
        conn.commit()
        return True, "Student and associated records purged."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_student_by_id(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE student_id = ?;", (student_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["face_feature"] = deserialize_feature(d["face_feature"])
    return d

def get_all_students(active_only=True):
    conn = get_db_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM students WHERE is_active = 1 ORDER BY name ASC;")
    else:
        cursor.execute("SELECT * FROM students ORDER BY name ASC;")
    rows = cursor.fetchall()
    conn.close()

    students = []
    for r in rows:
        item = dict(r)
        item["face_feature"] = deserialize_feature(item["face_feature"])
        students.append(item)
    return students

# ----------------- College Attendance Calculation Engine ----------------- #

def ensure_session_exists(date_str=None, total_classes=DEFAULT_CLASSES_PER_DAY):
    """Ensures an academic session record exists for the given date."""
    d = date_str or datetime.date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO academic_sessions (date, total_classes)
        VALUES (?, ?);
    """, (d, total_classes))
    conn.commit()
    conn.close()

def record_attendance(student_id, student_name, department, confidence=1.0,
                      status='Present', snapshot_path=None, marked_via='AI_CAMERA',
                      classes_attended=None):
    """Records attendance for student for today's session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # Get configured classes per day
    classes_per_day = classes_attended or int(get_setting("classes_per_day", str(DEFAULT_CLASSES_PER_DAY)))

    # Ensure academic session exists
    cursor.execute("INSERT OR IGNORE INTO academic_sessions (date, total_classes) VALUES (?, ?);", (date_str, classes_per_day))

    cursor.execute("""
        INSERT INTO attendance (student_id, student_name, department, date, time, timestamp,
                               classes_attended, status, confidence, snapshot_path, marked_via)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (student_id, student_name, department, date_str, time_str, now.isoformat(),
          classes_per_day, status, round(float(confidence), 4), snapshot_path, marked_via))

    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()
    return inserted_id

def get_last_attendance(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM attendance
        WHERE student_id = ?
        ORDER BY timestamp DESC
        LIMIT 1;
    """, (student_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def has_attended_today(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM attendance
        WHERE student_id = ? AND date = ?;
    """, (student_id, today_str))
    row = cursor.fetchone()
    conn.close()
    return (row["cnt"] > 0) if row else False

def get_attendance_records(start_date=None, end_date=None, student_id=None, department=None, status=None, limit=1000):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM attendance WHERE 1=1"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if student_id:
        query += " AND (student_id LIKE ? OR student_name LIKE ?)"
        params.extend([f"%{student_id}%", f"%{student_id}%"])
    if department and department != "All":
        query += " AND department = ?"
        params.append(department)
    if status and status != "All":
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY timestamp DESC LIMIT ?;"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_attendance_classes(student_id, date_str, classes_attended, total_classes_for_day=None):
    """Updates or logs classes credited for a student on a specific date (e.g. 7 out of 10)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    student = get_student_by_id(student_id)
    if not student:
        conn.close()
        return False, "Student ID not found."

    total_classes = total_classes_for_day or int(get_setting("classes_per_day", str(DEFAULT_CLASSES_PER_DAY)))
    classes_att = max(0, min(total_classes, int(classes_attended)))

    # Ensure academic session exists
    cursor.execute("INSERT OR IGNORE INTO academic_sessions (date, total_classes) VALUES (?, ?);", (date_str, total_classes))

    # Check if record exists for this date
    cursor.execute("SELECT id FROM attendance WHERE student_id = ? AND date = ?;", (student_id, date_str))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE attendance
            SET classes_attended = ?, total_classes_for_day = ?, status = 'Present'
            WHERE id = ?;
        """, (classes_att, total_classes, existing["id"]))
    else:
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        now_iso = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO attendance (student_id, student_name, department, date, time, timestamp,
                                   classes_attended, total_classes_for_day, status, confidence, marked_via)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Present', 1.0, 'MANUAL_OVERRIDE');
        """, (student_id, student["name"], student["department"], date_str, now_time, now_iso, classes_att, total_classes))

    conn.commit()
    conn.close()
    return True, f"Recorded {classes_att}/{total_classes} classes for {student['name']} on {date_str}."

# ----------------- College Standard Per-Student Calculations ----------------- #

def get_student_attendance_summary(student_id):
    """
    Computes rigorous academic college attendance stats for an individual student:
    - Total academic days held
    - Total classes/periods held across all sessions
    - Days attended
    - Classes/periods attended
    - Overall Attendance Rate % = min(100.0, (classes_attended / classes_held) * 100)
    - Eligibility status: GOOD (>= 75%), WARNING (60% - 74.9%), CRITICAL (< 60%)
    - Consecutively required classes to achieve 75%
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    student = get_student_by_id(student_id)
    if not student:
        conn.close()
        return None

    # Total academic days and classes held
    cursor.execute("SELECT COUNT(*) as total_days, COALESCE(SUM(total_classes), 0) as total_classes FROM academic_sessions;")
    sess_row = cursor.fetchone()
    total_days_held = max(1, sess_row["total_days"]) # At least 1 session
    total_classes_held = max(1, sess_row["total_classes"])

    # Student attended sessions and classes
    cursor.execute("""
        SELECT COUNT(DISTINCT date) as days_attended,
               COALESCE(SUM(classes_attended), 0) as classes_attended
        FROM attendance
        WHERE student_id = ?;
    """, (student_id,))
    att_row = cursor.fetchone()

    days_attended = att_row["days_attended"] or 0
    classes_attended = min(total_classes_held, att_row["classes_attended"] or 0)

    # Calculate exact percentage (capped at 100.0%)
    if total_classes_held > 0:
        attendance_pct = round(min(100.0, (classes_attended / total_classes_held) * 100.0), 1)
    else:
        attendance_pct = 100.0

    # Minimum threshold (default 75%)
    min_pct = float(get_setting("min_required_pct", str(MINIMUM_REQUIRED_ATTENDANCE_PCT)))

    if attendance_pct >= min_pct:
        status_category = "GOOD"
        status_label = "Eligible for Exams / Lab Pass"
        status_badge = "badge-status-present"
    elif attendance_pct >= 60.0:
        status_category = "WARNING"
        status_label = "Attendance Shortage (Condonation Range)"
        status_badge = "badge-status-sim"
    else:
        status_category = "CRITICAL"
        status_label = "Critical Shortage (Debarred)"
        status_badge = "badge-status-danger"

    # Classes needed to reach 75%
    # Equation: (classes_attended + x) / (total_classes_held + x) >= 0.75
    # => x >= 3 * total_classes_held - 4 * classes_attended
    needed_classes = 0
    if attendance_pct < min_pct:
        diff = (3 * total_classes_held) - (4 * classes_attended)
        needed_classes = max(0, diff)

    # Today's individual classes status
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute("SELECT classes_attended, total_classes_for_day FROM attendance WHERE student_id = ? AND date = ?;", (student_id, today_str))
    today_att_row = cursor.fetchone()
    default_classes_day = int(get_setting("classes_per_day", str(DEFAULT_CLASSES_PER_DAY)))
    if today_att_row:
        today_classes_att = today_att_row["classes_attended"] if today_att_row["classes_attended"] is not None else default_classes_day
        today_classes_held = today_att_row["total_classes_for_day"] if today_att_row["total_classes_for_day"] is not None else default_classes_day
    else:
        today_classes_att = 0
        today_classes_held = default_classes_day

    today_pct = round((today_classes_att / today_classes_held * 100.0), 1) if today_classes_held > 0 else 0.0

    # Recent student records
    cursor.execute("""
        SELECT * FROM attendance
        WHERE student_id = ?
        ORDER BY timestamp DESC
        LIMIT 25;
    """, (student_id,))
    recent_records = [dict(r) for r in cursor.fetchall()]

    conn.close()

    # Attach detailed IDEA Lab summary
    lab_summary = get_student_lab_summary(student_id)

    return {
        "student_id": student["student_id"],
        "name": student["name"],
        "department": student["department"],
        "role": student.get("role", "Member"),
        "email": student.get("email"),
        "phone": student.get("phone"),
        "photo_path": student.get("photo_path"),
        "total_days_held": total_days_held,
        "total_classes_held": total_classes_held,
        "days_attended": days_attended,
        "classes_attended": classes_attended,
        "today_classes_attended": today_classes_att,
        "today_classes_held": today_classes_held,
        "today_pct": today_pct,
        "missed_classes": max(0, total_classes_held - classes_attended),
        "attendance_pct": lab_summary["attendance_pct"] if lab_summary else attendance_pct,
        "status_category": status_category,
        "status_label": lab_summary["status_label"] if lab_summary else status_label,
        "status_badge": lab_summary["status_badge"] if lab_summary else status_badge,
        "needed_classes": needed_classes,
        "recent_records": recent_records,
        "lab_summary": lab_summary
    }

# ----------------- IDEA Lab Class Sessions & Attendance (Date & Slot-Wise) ----------------- #

def check_session_lock(date_str, allow_override=False):
    """
    Checks if a lab session on date_str is editable by Admin.
    Rule:
    - On class date: Edits permitted ONLY until 6:00 PM (18:00).
    - After 6:00 PM on that date (or past dates): Strictly locked.
    - Unless allow_override is True (authorized administrative override).
    """
    if allow_override:
        return False, "Authorized Super-Admin override active.", {"status": "OVERRIDE"}

    try:
        class_date = datetime.date.fromisoformat(date_str)
    except Exception:
        return True, "Invalid date format.", {"status": "ERROR"}

    today = datetime.date.today()
    now_dt = datetime.datetime.now()
    cutoff_time = datetime.time(LAB_CUTOFF_HOUR, 0, 0) # 18:00 (6:00 PM)

    if class_date < today:
        return True, f"Attendance locked: Modifications closed at 6:00 PM on class date ({date_str}).", {"status": "LOCKED_PAST"}
    elif class_date == today:
        if now_dt.time() >= cutoff_time:
            return True, "Attendance locked: Daily edit window closed at 6:00 PM today. Requires administrative override.", {"status": "LOCKED_6PM"}
        else:
            diff_sec = (datetime.datetime.combine(today, cutoff_time) - now_dt).total_seconds()
            hrs = max(0, int(diff_sec // 3600))
            mins = max(0, int((diff_sec % 3600) // 60))
            return False, f"Open for editing: Window closes at 6:00 PM today ({hrs}h {mins}m remaining).", {"status": "OPEN", "hrs": hrs, "mins": mins}
    else:
        # Future date
        return False, "Upcoming scheduled session.", {"status": "UPCOMING"}

def seed_default_lab_schedule():
    """
    Seeds standard IDEA Lab schedule and historical records matching Image 2:
    - Schedule dates: 12 Oct, 26 Oct, 02 Nov, 09 Nov, 16 Nov (Today), 23 Nov, 30 Nov
    - Two class slots per lab day: 01:20 PM (Slot 1) & 02:10 PM (Slot 2)
    - Pre-seeds 02 Nov: Slot 1 is PRESENT (P), Slot 2 is ABSENT (A)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    schedule_dates = [
        "2026-10-12",
        "2026-10-26",
        "2026-11-02",
        "2026-11-09",
        "2026-11-16",
        "2026-11-23",
        "2026-11-30"
    ]

    for d in schedule_dates:
        cursor.execute("""
            INSERT OR IGNORE INTO lab_classes (date, slot_number, slot_time, subject_name)
            VALUES (?, 1, '01:20 PM', 'Exploratory Project');
        """, (d,))
        cursor.execute("""
            INSERT OR IGNORE INTO lab_classes (date, slot_number, slot_time, subject_name)
            VALUES (?, 2, '02:10 PM', 'Exploratory Project');
        """, (d,))

    cursor.execute("SELECT COUNT(*) as cnt FROM lab_attendance;")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("SELECT student_id, name FROM students WHERE is_active = 1;")
        all_students = cursor.fetchall()

        for s in all_students:
            sid = s["student_id"]
            # 12 Oct: Both slots Present
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-10-12', 1, '01:20 PM', 'PRESENT', 'AI_CAMERA');", (sid,))
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-10-12', 2, '02:10 PM', 'PRESENT', 'AI_CAMERA');", (sid,))

            # 26 Oct: Both slots Present
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-10-26', 1, '01:20 PM', 'PRESENT', 'AI_CAMERA');", (sid,))
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-10-26', 2, '02:10 PM', 'PRESENT', 'AI_CAMERA');", (sid,))

            # 02 Nov: Slot 1 Present, Slot 2 ABSENT (User explicit case!)
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-11-02', 1, '01:20 PM', 'PRESENT', 'AI_CAMERA');", (sid,))
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via, admin_notes) VALUES (?, '2026-11-02', 2, '02:10 PM', 'ABSENT', 'ADMIN_MANUAL', 'Left early from second period');", (sid,))

            # 09 Nov: Both slots Present
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-11-09', 1, '01:20 PM', 'PRESENT', 'AI_CAMERA');", (sid,))
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-11-09', 2, '02:10 PM', 'PRESENT', 'AI_CAMERA');", (sid,))

            # 16 Nov (Today): Both slots NOT_MARKED
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-11-16', 1, '01:20 PM', 'NOT_MARKED', 'PENDING');", (sid,))
            cursor.execute("INSERT OR IGNORE INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via) VALUES (?, '2026-11-16', 2, '02:10 PM', 'NOT_MARKED', 'PENDING');", (sid,))

    conn.commit()
    conn.close()

def seed_digicampus_courses():
    """
    Seeds the standard DigiCampus semester course catalog strictly matching Image 1:
    1. Professional Skills (77.78%, 14/18)
    2. Soft Skill Development (50%, 8/16)
    3. Engineering Chemistry (82.35%, 14/17)
    4. Sports for Life (12.5%, 1/8)
    5. Exploratory Project / IDEA Lab (Live linked to lab_attendance, 50% min requirement)
    6. Fundamentals of Programming using C (73.68%, 14/19)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    courses = [
        ('PS102', 'Professional Skills', 'Theory / Lab', 'Prof. R. Sharma', 2, 75.0, 14, 18, '#ff4d4f', 1),
        ('SS103', 'Soft Skill Development', 'Practical / Soft Skills', 'Prof. M. Gupta', 1, 75.0, 8, 16, '#ff4d4f', 2),
        ('EC104', 'Engineering Chemistry', 'Theory & Lab', 'Dr. S. K. Verma', 4, 75.0, 14, 17, '#ff4d4f', 3),
        ('SL105', 'Sports for Life', 'Activity / Physical Ed', 'Coach V. Rathore', 1, 50.0, 1, 8, '#ff4d4f', 4),
        ('EP101', 'Exploratory Project', 'IDEA Lab Practicals', 'Prof. Suresh Kumar', 2, 50.0, 12, 12, '#ff4d4f', 5),
        ('CS106', 'Fundamentals of Programming using C', 'Theory & Lab', 'Er. P. Choudhary', 4, 75.0, 14, 19, '#78716c', 6)
    ]

    for c in courses:
        cursor.execute("""
            INSERT OR REPLACE INTO digicampus_courses
            (code, name, category, faculty_name, credits, min_pct, mock_attended, mock_held, bar_color, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, c)

    conn.commit()
    conn.close()

def record_slot_attendance(student_id, date_str, slot_number, slot_time=None, status='PRESENT', marked_via='AI_CAMERA', admin_notes=None, allow_override=False):
    """
    Records attendance for a specific class slot on a date.
    Enforces 6:00 PM lock check unless allow_override=True.
    """
    is_locked, lock_msg, _ = check_session_lock(date_str, allow_override=allow_override)
    if is_locked:
        return False, lock_msg

    slot_t = slot_time or ("01:20 PM" if int(slot_number) == 1 else "02:10 PM")
    stat = status.upper().strip()
    now_iso = datetime.datetime.now().isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ensure class slot exists
        cursor.execute("INSERT OR IGNORE INTO lab_classes (date, slot_number, slot_time, subject_name) VALUES (?, ?, ?, 'Exploratory Project');",
                       (date_str, int(slot_number), slot_t))

        cursor.execute("""
            INSERT INTO lab_attendance (student_id, date, slot_number, slot_time, status, marked_via, admin_notes, is_override, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_id, date, slot_number) DO UPDATE SET
                status = excluded.status,
                marked_via = excluded.marked_via,
                admin_notes = COALESCE(excluded.admin_notes, lab_attendance.admin_notes),
                is_override = excluded.is_override,
                updated_at = excluded.updated_at;
        """, (student_id, date_str, int(slot_number), slot_t, stat, marked_via, admin_notes, 1 if allow_override else 0, now_iso))

        # Also sync daily classes attended in main attendance table
        cursor.execute("SELECT COUNT(*) as pres_count FROM lab_attendance WHERE student_id = ? AND date = ? AND status = 'PRESENT';", (student_id, date_str))
        pres_count = cursor.fetchone()["pres_count"]

        student = get_student_by_id(student_id)
        s_name = student["name"] if student else "Student"
        s_dept = student["department"] if student else "Engineering"

        cursor.execute("SELECT id FROM attendance WHERE student_id = ? AND date = ?;", (student_id, date_str))
        att_ex = cursor.fetchone()
        if att_ex:
            cursor.execute("""
                UPDATE attendance
                SET classes_attended = ?, total_classes_for_day = 2,
                    status = CASE WHEN ? > 0 THEN 'Present' ELSE 'Absent' END
                WHERE id = ?;
            """, (pres_count, pres_count, att_ex["id"]))
        else:
            cursor.execute("""
                INSERT INTO attendance (student_id, student_name, department, date, time, timestamp, classes_attended, total_classes_for_day, status, marked_via)
                VALUES (?, ?, ?, ?, ?, ?, ?, 2, ?, ?);
            """, (student_id, s_name, s_dept, date_str, datetime.datetime.now().strftime("%H:%M:%S"), now_iso, pres_count, 'Present' if pres_count > 0 else 'Absent', marked_via))

        conn.commit()
        return True, f"Slot {slot_number} marked {stat} for {student_id}."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def toggle_slot_attendance(student_id, date_str, slot_number, new_status, allow_override=False, admin_notes=None):
    """
    Toggles or sets attendance for student in a specific slot.
    Enforces the 6:00 PM lock check.
    """
    return record_slot_attendance(
        student_id=student_id,
        date_str=date_str,
        slot_number=slot_number,
        status=new_status,
        marked_via='ADMIN_MANUAL',
        admin_notes=admin_notes,
        allow_override=allow_override
    )

def get_student_lab_summary(student_id):
    """
    Returns the comprehensive IDEA Lab (Exploratory Project) attendance summary matching Images 1 & 2:
    - Component Attendance %
    - Number of attended sessions vs total held sessions
    - 50.0% Minimum Lab Attendance Eligibility
    - Full chronological list of session cards with PRESENT (P), ABSENT (A), Not marked
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    student = get_student_by_id(student_id)
    if not student:
        conn.close()
        return None

    # Fetch all scheduled sessions ordered by date DESC, slot_number DESC
    cursor.execute("""
        SELECT lc.date, lc.slot_number, lc.slot_time, lc.subject_name,
               COALESCE(la.status, 'NOT_MARKED') as status,
               la.marked_via, la.marked_at, la.admin_notes, la.is_override
        FROM lab_classes lc
        LEFT JOIN lab_attendance la 
               ON lc.date = la.date 
              AND lc.slot_number = la.slot_number 
              AND la.student_id = ?
        ORDER BY lc.date DESC, lc.slot_number DESC;
    """, (student_id,))
    rows = cursor.fetchall()
    conn.close()

    today = datetime.date.today()
    sessions = []
    total_held = 0
    total_attended = 0
    total_absent = 0
    total_unmarked = 0

    for r in rows:
        d_str = r["date"]
        try:
            d_obj = datetime.date.fromisoformat(d_str)
            formatted_date = d_obj.strftime("%d %b")
        except Exception:
            formatted_date = d_str

        display_time = f"{formatted_date}, {r['slot_time']}"
        status = r["status"].upper()

        is_locked, lock_msg, _ = check_session_lock(d_str)

        # Counting held vs attended
        is_held = (d_obj < today) or (d_obj == today and status in ('PRESENT', 'ABSENT'))
        if is_held:
            total_held += 1
            if status == 'PRESENT':
                total_attended += 1
            elif status == 'ABSENT':
                total_absent += 1
            else:
                total_absent += 1 # Past unrecorded session
        else:
            if status == 'PRESENT':
                total_held += 1
                total_attended += 1
            elif status == 'ABSENT':
                total_held += 1
                total_absent += 1
            else:
                total_unmarked += 1

        sessions.append({
            "date": d_str,
            "formatted_date": formatted_date,
            "slot_number": r["slot_number"],
            "slot_time": r["slot_time"],
            "display_datetime": display_time,
            "subject_name": r["subject_name"] or "Exploratory Project",
            "status": status,
            "marked_via": r["marked_via"] or "AI_CAMERA",
            "admin_notes": r["admin_notes"],
            "is_locked": is_locked,
            "lock_msg": lock_msg,
            "is_override": bool(r["is_override"])
        })

    effective_held = max(1, total_held) if total_held > 0 else 0
    if effective_held > 0:
        attendance_pct = round(min(100.0, (total_attended / effective_held) * 100.0), 1)
    else:
        attendance_pct = 100.0

    min_required_pct = float(LAB_MINIMUM_REQUIRED_ATTENDANCE_PCT) # 50.0%
    is_eligible = attendance_pct >= min_required_pct

    needed_sessions = max(0, total_held - 2 * total_attended) if not is_eligible else 0

    return {
        "subject_name": "Exploratory Project",
        "student_id": student["student_id"],
        "student_name": student["name"],
        "total_held": total_held,
        "total_attended": total_attended,
        "total_absent": total_absent,
        "total_unmarked": total_unmarked,
        "attendance_pct": attendance_pct,
        "min_required_pct": min_required_pct,
        "is_eligible": is_eligible,
        "status_label": "Eligible (Safe)" if is_eligible else "Shortage Warning (< 50%)",
        "status_badge": "badge-status-present" if is_eligible else "badge-status-danger",
        "needed_sessions": needed_sessions,
        "sessions": sessions
    }

def get_digicampus_academics(student_id):
    """
    Returns full semester courses overview strictly matching DigiCampus Image 1:
    - Current Term tab
    - For Exploratory Project (EP101): Dynamically derived from real lab_attendance
    - For other registered courses: Displays official term curriculum with attendance progress bars
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM digicampus_courses ORDER BY display_order ASC;")
    raw_courses = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Get student's live Exploratory Project lab summary
    lab_sum = get_student_lab_summary(student_id)

    formatted_courses = []
    total_attended_all = 0
    total_held_all = 0

    for c in raw_courses:
        code = c["code"]
        name = c["name"]
        min_pct = float(c["min_pct"])
        bar_color = c.get("bar_color", "#ff4d4f")

        if code == "EP101" and lab_sum:
            # LIVE DATA from IDEA Lab attendance engine!
            attended = lab_sum["total_attended"]
            held = max(1, lab_sum["total_held"]) if lab_sum["total_held"] > 0 else 0
            pct = lab_sum["attendance_pct"]
            is_lab = True
            is_eligible = lab_sum["is_eligible"]
        else:
            attended = int(c["mock_attended"])
            held = max(1, int(c["mock_held"]))
            pct = round(min(100.0, (attended / held) * 100.0), 2)
            if pct == int(pct):
                pct = int(pct)
            is_lab = False
            is_eligible = pct >= min_pct

        total_attended_all += attended
        total_held_all += held

        sessions_label = f"{attended} of {held} sessions"

        formatted_courses.append({
            "code": code,
            "name": name,
            "category": c.get("category", "Course"),
            "faculty_name": c.get("faculty_name", "Faculty"),
            "credits": c.get("credits", 2),
            "min_pct": min_pct,
            "attended": attended,
            "held": held,
            "attendance_pct": pct,
            "sessions_label": sessions_label,
            "is_lab": is_lab,
            "is_eligible": is_eligible,
            "bar_color": bar_color,
            "is_active_drilldown": (code == "EP101")
        })

    overall_pct = round((total_attended_all / max(1, total_held_all)) * 100.0, 1)

    return {
        "term_title": "Current Term",
        "academic_year": "2026-2027",
        "semester": "Semester 1",
        "total_courses": len(formatted_courses),
        "overall_attendance_pct": overall_pct,
        "courses": formatted_courses,
        "lab_summary": lab_sum
    }

def get_digicampus_drilldown(student_id, course_code='EP101'):
    """
    Returns granular drilldown for a single subject strictly matching Image 2:
    - Component attendance card (percentage, attended of held, circular gauge)
    - Filter pills (ALL, PRESENT, ABSENT, Not marked)
    - Chronological session cards with slot timing, left stripe, and pill badges
    """
    if course_code == 'EP101':
        return get_student_lab_summary(student_id)
    return None

def bulk_toggle_lab_attendance(date_str, slot_number, status, allow_override=False, admin_notes=None):
    """
    Allows faculty/admin to bulk mark all students Present or Absent for a slot in 1 click.
    Respects the 6:00 PM lock check unless allow_override=True.
    """
    is_locked, lock_msg, _ = check_session_lock(date_str, allow_override=allow_override)
    if is_locked:
        return False, lock_msg, 0

    students = get_all_students(active_only=True)
    count = 0
    for s in students:
        ok, _ = record_slot_attendance(
            student_id=s["student_id"],
            date_str=date_str,
            slot_number=int(slot_number),
            status=status,
            marked_via='ADMIN_BULK',
            admin_notes=admin_notes or f"Bulk marked {status} by faculty",
            allow_override=allow_override
        )
        if ok:
            count += 1

    return True, f"Successfully marked {count} students as {status} for Slot {slot_number}.", count

def get_lab_date_matrix(date_str=None):
    """
    Returns full lab matrix for Admin:
    - List of available dates
    - Selected date
    - 6:00 PM lock status for selected date
    - All students with their Slot 1 and Slot 2 attendance
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT date FROM lab_classes ORDER BY date DESC;")
    dates = [r["date"] for r in cursor.fetchall()]

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    selected_date = date_str if (date_str and date_str in dates) else (today_str if today_str in dates else (dates[0] if dates else today_str))

    is_locked, lock_msg, time_info = check_session_lock(selected_date)

    cursor.execute("SELECT student_id, name, department, role, photo_path FROM students WHERE is_active = 1 ORDER BY student_id ASC;")
    students = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT student_id, slot_number, slot_time, status, marked_via, admin_notes, is_override
        FROM lab_attendance
        WHERE date = ?;
    """, (selected_date,))
    att_rows = cursor.fetchall()

    att_map = {}
    for r in att_rows:
        key = (r["student_id"], r["slot_number"])
        att_map[key] = dict(r)

    matrix_students = []
    for s in students:
        sid = s["student_id"]
        slot1 = att_map.get((sid, 1), {"status": "NOT_MARKED", "slot_time": "01:20 PM", "marked_via": "NONE"})
        slot2 = att_map.get((sid, 2), {"status": "NOT_MARKED", "slot_time": "02:10 PM", "marked_via": "NONE"})

        lab_sum = get_student_lab_summary(sid)

        matrix_students.append({
            "student_id": sid,
            "name": s["name"],
            "department": s["department"],
            "photo_path": s.get("photo_path"),
            "slot1": slot1,
            "slot2": slot2,
            "overall_pct": lab_sum["attendance_pct"] if lab_sum else 100.0,
            "is_eligible": lab_sum["is_eligible"] if lab_sum else True
        })

    conn.close()

    try:
        d_obj = datetime.date.fromisoformat(selected_date)
        formatted_selected = d_obj.strftime("%d %b %Y")
    except Exception:
        formatted_selected = selected_date

    return {
        "dates": dates,
        "selected_date": selected_date,
        "formatted_selected": formatted_selected,
        "is_locked": is_locked,
        "lock_msg": lock_msg,
        "time_info": time_info,
        "students": matrix_students
    }

def get_all_students_attendance_summary():
    """Returns attendance statistics for every single enrolled student individually."""
    students = get_all_students(active_only=True)
    summaries = []
    for s in students:
        summary = get_student_attendance_summary(s["student_id"])
        if summary:
            summaries.append(summary)
    return summaries

def get_dashboard_stats():
    """
    Calculates summary KPIs strictly bounded between 0% and 100%:
    - total_students: count of registered active students
    - today_present: count of unique registered students present today (via INNER JOIN)
    - today_turnout_pct: strictly between 0% and 100%
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    # 1. Total registered active students
    cursor.execute("SELECT COUNT(*) as total FROM students WHERE is_active = 1;")
    total_students = cursor.fetchone()["total"]

    # 2. Today's unique attendees (strictly joined to active students table to eliminate orphan/test records!)
    cursor.execute("""
        SELECT COUNT(DISTINCT s.student_id) as present
        FROM students s
        INNER JOIN attendance a ON s.student_id = a.student_id
        WHERE a.date = ? AND s.is_active = 1;
    """, (today_str,))
    today_present = cursor.fetchone()["present"]

    # Strictly bounded between 0.0% and 100.0%
    if total_students > 0:
        turnout_pct = round(min(100.0, (today_present / total_students) * 100.0), 1)
    else:
        turnout_pct = 0.0

    # 3. Overall average attendance rate across all students
    all_summaries = get_all_students_attendance_summary()
    if all_summaries:
        avg_student_rate = round(sum(s["attendance_pct"] for s in all_summaries) / len(all_summaries), 1)
    else:
        avg_student_rate = 0.0

    # 4. Recent logs for today (strictly legitimate students)
    cursor.execute("""
        SELECT a.*
        FROM attendance a
        INNER JOIN students s ON a.student_id = s.student_id
        WHERE a.date = ? AND s.is_active = 1
        ORDER BY a.timestamp DESC
        LIMIT 10;
    """, (today_str,))
    recent_logs = [dict(r) for r in cursor.fetchall()]

    # 5. Hourly distribution for today (08:00 to 19:00)
    cursor.execute("""
        SELECT substr(time, 1, 2) as hour, COUNT(*) as count
        FROM attendance a
        INNER JOIN students s ON a.student_id = s.student_id
        WHERE a.date = ? AND s.is_active = 1
        GROUP BY hour
        ORDER BY hour ASC;
    """, (today_str,))
    hourly_raw = {r["hour"]: r["count"] for r in cursor.fetchall()}
    hourly_labels = [f"{h:02d}:00" for h in range(8, 20)]
    hourly_data = [hourly_raw.get(f"{h:02d}", 0) for h in range(8, 20)]

    # 6. Department breakdown
    cursor.execute("""
        SELECT s.department, COUNT(DISTINCT s.student_id) as total_enrolled,
               COUNT(DISTINCT a.student_id) as present_today
        FROM students s
        LEFT JOIN attendance a ON s.student_id = a.student_id AND a.date = ?
        WHERE s.is_active = 1
        GROUP BY s.department;
    """, (today_str,))
    dept_stats = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "today_str": today_str,
        "total_students": total_students,
        "today_present": today_present,
        "turnout_pct": turnout_pct,
        "avg_student_rate": avg_student_rate,
        "recent_logs": recent_logs,
        "hourly_labels": hourly_labels,
        "hourly_data": hourly_data,
        "dept_stats": dept_stats,
        "all_summaries": all_summaries
    }

# ----------------- Settings & GDPR Data Deletion ----------------- #

def get_setting(key, default=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?);", (key, str(value)))
    conn.commit()
    conn.close()

def log_hardware_event(command, status, port="N/A", details=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hardware_logs (command, status, port, details)
        VALUES (?, ?, ?, ?);
    """, (command, status, port, details))
    cursor.execute("""
        DELETE FROM hardware_logs
        WHERE id NOT IN (SELECT id FROM hardware_logs ORDER BY id DESC LIMIT 200);
    """)
    conn.commit()
    conn.close()

def get_recent_hardware_logs(limit=25):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hardware_logs ORDER BY id DESC LIMIT ?;", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# GDPR / DPDP "Right to be Forgotten"
def create_deletion_request(student_id, student_name, reason="Student requested complete data removal"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO deletion_requests (student_id, student_name, reason)
        VALUES (?, ?, ?);
    """, (student_id, student_name, reason))
    conn.commit()
    conn.close()
    return True

def get_deletion_requests():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deletion_requests ORDER BY requested_at DESC LIMIT 50;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def execute_purge_student_data(student_id):
    """Completely and irreversibly removes all biometric and personal data for a student."""
    student = get_student_by_id(student_id)
    if not student:
        return False, "Student not found."

    # Delete photo file
    if student.get("photo_path"):
        from config import BASE_DIR
        photo_file = BASE_DIR / "static" / student["photo_path"]
        if photo_file.exists():
            try:
                photo_file.unlink()
            except Exception:
                pass

    # Delete snapshots
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT snapshot_path FROM attendance WHERE student_id = ?;", (student_id,))
    snapshots = cursor.fetchall()
    for s in snapshots:
        if s["snapshot_path"]:
            from config import BASE_DIR
            snap_file = BASE_DIR / "static" / s["snapshot_path"]
            if snap_file.exists():
                try:
                    snap_file.unlink()
                except Exception:
                    pass

    # Delete all DB records
    cursor.execute("DELETE FROM attendance WHERE student_id = ?;", (student_id,))
    cursor.execute("DELETE FROM users WHERE student_id = ?;", (student_id,))
    cursor.execute("DELETE FROM students WHERE student_id = ?;", (student_id,))
    cursor.execute("UPDATE deletion_requests SET status = 'PROCESSED', processed_at = CURRENT_TIMESTAMP WHERE student_id = ?;", (student_id,))
    conn.commit()
    conn.close()
    return True, f"All biometric templates, photos, and attendance records for student '{student_id}' have been completely wiped."
