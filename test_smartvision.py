"""
Comprehensive Test Suite for SmartVision AI Attendance System
Includes Authentication, RBAC, College Attendance Calculation, and Security Tests.
"""

import os
import unittest
import numpy as np
import datetime

# Import application modules
import config
import database
from face_engine import engine as face_engine
from arduino_bridge import arduino
from attendance_service import attendance_service
from app import app

from security import rate_limiter

class TestSmartVision(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        database.init_db()

    def setUp(self):
        rate_limiter.reset()

    def test_01_database_and_student_lifecycle(self):
        """Test database student registration, query, and cleanup."""
        dummy_feat = np.random.rand(128).astype(np.float32)
        norm = np.linalg.norm(dummy_feat)
        dummy_feat = dummy_feat / norm

        test_id = "TEMP-TEST-001"
        # 1. Add student
        ok, msg = database.add_student(
            student_id=test_id,
            name="Test Researcher",
            department="AI & Robotics",
            role="Researcher",
            email="test@idealab.org",
            phone="9876543210",
            face_feature=dummy_feat,
            photo_path="uploads/students/test.jpg",
            sample_count=5,
            initial_password="TestPassword123!"
        )
        self.assertTrue(ok, f"Failed to add student: {msg}")

        # 2. Duplicate rejection
        dup_ok, _ = database.add_student(test_id, "Duplicate User", "AI", "Member")
        self.assertFalse(dup_ok, "Database must reject duplicate student_id")

        # 3. Retrieve student
        student = database.get_student_by_id(test_id)
        self.assertIsNotNone(student)
        self.assertEqual(student["name"], "Test Researcher")
        self.assertEqual(len(student["face_feature"]), 128)

        # 4. Verify Student User Login Account was created
        stu_user = database.authenticate_user(test_id, "TestPassword123!")
        self.assertIsNotNone(stu_user)
        self.assertEqual(stu_user["role"], "student")

        # 5. Clean up
        database.delete_student(test_id)
        self.assertIsNone(database.get_student_by_id(test_id))
        self.assertIsNone(database.authenticate_user(test_id, "TestPassword123!"))

    def test_02_college_attendance_calculations(self):
        """Test college multi-class attendance percentage and bounds."""
        stats = database.get_dashboard_stats()
        # Verify Turnout is strictly bounded between 0% and 100%
        self.assertGreaterEqual(stats["turnout_pct"], 0.0)
        self.assertLessEqual(stats["turnout_pct"], 100.0)

        # Test individual student calculation on enrolled student (Aditya Jain)
        student = database.get_student_by_id("IL-2026-001")
        if student:
            summary = database.get_student_attendance_summary("IL-2026-001")
            self.assertIsNotNone(summary)
            self.assertGreaterEqual(summary["attendance_pct"], 0.0)
            self.assertLessEqual(summary["attendance_pct"], 100.0)
            self.assertIn("status_category", summary)

    def test_03_face_engine(self):
        """Test deep neural network models and similarity computations."""
        self.assertTrue(face_engine.is_ready(), "FaceEngine models must be loaded and ready")

        v1 = np.random.rand(128).astype(np.float32)
        v1 = v1 / np.linalg.norm(v1)
        sim_self = face_engine.compute_similarity(v1, v1)
        self.assertAlmostEqual(sim_self, 1.0, places=4)

    def test_04_arduino_bridge_simulation(self):
        """Test Arduino hardware controller and virtual fallback mode."""
        arduino.connect("SIMULATION")
        status = arduino.get_status()
        self.assertTrue(status["simulation_mode"])
        self.assertFalse(status["is_connected"])

        ok, msg = arduino.trigger_attendance_success("Test User")
        self.assertTrue(ok)
        self.assertIn("VIRTUAL ARDUINO", msg)

    def test_05_reports_export(self):
        """Test Excel and CSV report generators."""
        csv_text = attendance_service.generate_csv_report()
        self.assertIn("Record ID", csv_text)

        excel_path, filename = attendance_service.generate_excel_report()
        self.assertTrue(os.path.exists(excel_path))
        self.assertGreater(os.path.getsize(excel_path), 1000)

    def test_06_authentication_and_rbac(self):
        """Test role-based access control, admin protection, and student isolation."""
        client = app.test_client()

        # 1. Unauthenticated request to Admin Dashboard should redirect to /login
        r = client.get('/', follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

        # 2. Login as Admin
        admin_pass = config.INITIAL_ADMIN_PASSWORD
        login_res = client.post('/login', data={
            'username': 'admin',
            'password': admin_pass
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)

        # 3. Now Admin can access Dashboard
        r_admin = client.get('/')
        self.assertEqual(r_admin.status_code, 200)
        self.assertIn(b"Command Center", r_admin.data)
        # Verify Alice Robotics does NOT exist anywhere in the dashboard output!
        self.assertNotIn(b"Alice Robotics", r_admin.data)

        # 4. Check Security Headers
        self.assertEqual(r_admin.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(r_admin.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("Content-Security-Policy", r_admin.headers)

        # 5. Test Legal Routes (Publicly accessible)
        self.assertEqual(client.get('/privacy').status_code, 200)
        self.assertEqual(client.get('/terms').status_code, 200)
        self.assertEqual(client.get('/refund').status_code, 200)
        self.assertEqual(client.get('/cookies').status_code, 200)
        self.assertEqual(client.get('/live').status_code, 200)

        # 6. Test Rate Limiting on repeated failed logins
        for _ in range(11):
            client.post('/login', data={'username': 'hacker', 'password': 'wrongpassword'})
        rl_res = client.post('/login', data={'username': 'hacker', 'password': 'wrongpassword'})
        self.assertEqual(rl_res.status_code, 429)

    def test_07_specific_user_credentials_and_portals(self):
        """Test specific 4 student credentials and 1 teacher credential."""
        client = app.test_client()

        # 1. Test 4 Student Logins
        student_creds = [
            ("aditya.26ai3482@jietjodhpur.ac.in", "Aditya69", "26AI3482"),
            ("anushka.26ai4359@jietjodhpur.ac.in", "Anushka69", "26AI4359"),
            ("arvind.26ai5204@jjietjodhpur.ac.in", "Arvind69", "26AI5204"),
            ("akshat.26ai3944@jietjodhpur.ac.in", "Akshat69", "26AI3944"),
        ]

        for email, pwd, sid in student_creds:
            user = database.authenticate_user(email, pwd)
            self.assertIsNotNone(user, f"Authentication failed for student email: {email}")
            self.assertEqual(user["role"], "student")
            self.assertEqual(user["student_id"], sid)

            # Also verify via student_id
            user_by_id = database.authenticate_user(sid, pwd)
            self.assertIsNotNone(user_by_id, f"Authentication failed for student id: {sid}")

        # 2. Test 1 Teacher Login
        teacher_email = "Sureshkumar_69@jietjodhpur.ac.in"
        teacher_pwd = "Suresh69"
        teacher_user = database.authenticate_user(teacher_email, teacher_pwd)
        self.assertIsNotNone(teacher_user, f"Authentication failed for teacher: {teacher_email}")
        self.assertEqual(teacher_user["role"], "admin")

    def test_08_signup_page_and_eye_toggle(self):
        """Verify Sign Up page, eye toggle icons, and mandatory biometric check."""
        client = app.test_client()

        # 1. GET /signup returns 200 and contains Face Biometric Scan UI
        r_signup = client.get('/signup')
        self.assertEqual(r_signup.status_code, 200)
        self.assertIn(b"Mandatory Biometric Face Scan", r_signup.data)
        self.assertIn(b"togglePasswordVisibility", r_signup.data)
        self.assertIn(b"signupEyeIcon", r_signup.data)

        # 2. GET /login contains Eye toggle
        r_login = client.get('/login')
        self.assertEqual(r_login.status_code, 200)
        self.assertIn(b"togglePasswordVisibility", r_login.data)
        self.assertIn(b"loginEyeIcon", r_login.data)

        # 3. GET /student/login contains Eye toggle
        r_stu_login = client.get('/student/login')
        self.assertEqual(r_stu_login.status_code, 200)
        self.assertIn(b"togglePasswordVisibility", r_stu_login.data)
        self.assertIn(b"loginEyeIcon", r_stu_login.data)

        # 4. Mandatory face scan check: POST /api/auth/signup without photo should be rejected (400)
        r_no_photo = client.post('/api/auth/signup', data={
            'name': 'New Student',
            'email': 'newstudent@jietjodhpur.ac.in',
            'student_id': '26AI9999',
            'department': 'AI & Robotics',
            'role': 'student',
            'password': 'Password123',
            'biometric_consent': '1',
            'photo_mode': 'base64_snap',
            'base64_image': ''
        })
        self.assertEqual(r_no_photo.status_code, 400)
        self.assertIn(b"Mandatory face biometric scan is missing", r_no_photo.data)

    def test_09_signup_and_face_enrollment_end_to_end(self):
        """End-to-end test of /api/auth/signup for student and teacher with face scan."""
        import base64
        client = app.test_client()

        # Load real portrait image
        with open("static/uploads/students/IL-2026-001.jpg", "rb") as f:
            b64_img = base64.b64encode(f.read()).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{b64_img}"

        # 1. Test Student Sign Up with Face Scan
        res_stu = client.post('/api/auth/signup', data={
            'name': 'E2E Test Student',
            'email': 'e2e.student@jietjodhpur.ac.in',
            'student_id': '26AI8888',
            'department': 'AI & Robotics',
            'role': 'student',
            'password': 'StudentSecret69',
            'biometric_consent': '1',
            'photo_mode': 'base64_snap',
            'base64_image': data_uri
        })
        self.assertEqual(res_stu.status_code, 200)
        stu_json = res_stu.get_json()
        self.assertTrue(stu_json["success"])
        self.assertIn("dashboard", stu_json["redirect_url"])

        # Verify authentication works for this new student
        auth_stu = database.authenticate_user("e2e.student@jietjodhpur.ac.in", "StudentSecret69")
        self.assertIsNotNone(auth_stu)
        self.assertEqual(auth_stu["role"], "student")

        # 2. Test Teacher Sign Up with Face Scan
        res_fac = client.post('/api/auth/signup', data={
            'name': 'Prof. Test Faculty',
            'email': 'test.faculty@jietjodhpur.ac.in',
            'student_id': 'FAC-8888',
            'department': 'Computer Science',
            'role': 'admin',
            'password': 'FacultySecret69',
            'biometric_consent': '1',
            'photo_mode': 'base64_snap',
            'base64_image': data_uri
        })
        self.assertEqual(res_fac.status_code, 200)
        fac_json = res_fac.get_json()
        self.assertTrue(fac_json["success"])
        self.assertEqual(fac_json["redirect_url"], "/")

        # Verify authentication works for this new teacher with admin role
        auth_fac = database.authenticate_user("test.faculty@jietjodhpur.ac.in", "FacultySecret69")
        self.assertIsNotNone(auth_fac)
        self.assertEqual(auth_fac["role"], "admin")

        # Cleanup test entries
        database.delete_student("26AI8888")
        database.delete_student("FAC-8888")

    def test_10_lab_attendance_slots_and_6pm_lock(self):
        """
        Verify IDEA Lab (Exploratory Project) 2-slot attendance model,
        50% minimum threshold, and the 6:00 PM edit lock rule.
        """
        client = app.test_client()

        # 1. Verify student lab summary for Aditya Jain (26AI3482)
        summary = database.get_student_lab_summary('26AI3482')
        self.assertIsNotNone(summary)
        self.assertEqual(summary['subject_name'], 'Exploratory Project')
        self.assertEqual(summary['min_required_pct'], 50.0, "Lab threshold must be 50.0%")
        self.assertGreaterEqual(summary['total_held'], 8, "Must have at least 8 sessions across 4 scheduled dates")
        self.assertTrue(summary['is_eligible'], "87.5% attendance must be eligible against 50% cutoff")

        # 2. Verify 2 Nov specific case: Slot 1 (01:20 PM) PRESENT, Slot 2 (02:10 PM) ABSENT
        nov2_slots = {s['slot_number']: s['status'] for s in summary['sessions'] if s['date'] == '2026-11-02'}
        self.assertEqual(nov2_slots.get(1), 'PRESENT', "2 Nov Slot 1 must be PRESENT")
        self.assertEqual(nov2_slots.get(2), 'ABSENT', "2 Nov Slot 2 must be ABSENT as requested")

        # 3. Verify 6:00 PM Lock rule on past date (2026-11-02)
        is_locked, lock_msg, _ = database.check_session_lock('2026-11-02')
        self.assertTrue(is_locked, "Past date session must be locked after 6:00 PM on class date")
        self.assertIn("Attendance locked", lock_msg)

        # Attempt toggle without override must be rejected
        ok_no_ov, msg_no_ov = database.toggle_slot_attendance('26AI3482', '2026-11-02', 2, 'PRESENT', allow_override=False)
        self.assertFalse(ok_no_ov)
        self.assertIn("locked", msg_no_ov.lower())

        # Attempt toggle with allow_override must succeed
        ok_ov, msg_ov = database.toggle_slot_attendance('26AI3482', '2026-11-02', 2, 'PRESENT', allow_override=True, admin_notes='Authorized Dean Override')
        self.assertTrue(ok_ov)

        # Restore to ABSENT for test state preservation
        database.toggle_slot_attendance('26AI3482', '2026-11-02', 2, 'ABSENT', allow_override=True, admin_notes='Left early')

        # 4. Verify Admin API endpoint /api/lab/attendance/toggle with lock handling
        # Login as admin
        client.post('/login', data={'username': 'admin', 'password': config.INITIAL_ADMIN_PASSWORD})

        # Past date without override -> 403 locked
        res_lock = client.post('/api/lab/attendance/toggle', data={
            'student_id': '26AI3482',
            'date': '2026-11-02',
            'slot_number': '1',
            'status': 'ABSENT'
        })
        self.assertEqual(res_lock.status_code, 403)
        self.assertTrue(res_lock.get_json()['locked'])

        # Past date with override -> 200 ok
        res_ov = client.post('/api/lab/attendance/toggle', data={
            'student_id': '26AI3482',
            'date': '2026-11-02',
            'slot_number': '1',
            'status': 'PRESENT',
            'allow_override': 'true',
            'admin_notes': 'Authorized by Lab Incharge'
        })
        self.assertEqual(res_ov.status_code, 200)
        self.assertTrue(res_ov.get_json()['success'])

    def test_11_digicampus_reverse_engineering_and_bulk_actions(self):
        """
        Verify reverse-engineered DigiCampus ERP schema, Academics overview (Image 1),
        Exploratory Project drilldown (Image 2), and Faculty Bulk Attendance.
        """
        client = app.test_client()

        # 1. Verify DigiCampus Academics Course Registry (Image 1)
        academics = database.get_digicampus_academics('26AI3482')
        self.assertIsNotNone(academics)
        self.assertEqual(len(academics['courses']), 6, "Must contain all 6 semester courses from Image 1")

        course_names = [c['name'] for c in academics['courses']]
        self.assertIn('Exploratory Project', course_names)
        self.assertIn('Professional Skills', course_names)
        self.assertIn('Soft Skill Development', course_names)
        self.assertIn('Engineering Chemistry', course_names)
        self.assertIn('Sports for Life', course_names)
        self.assertIn('Fundamentals of Programming using C', course_names)

        # Check live Exploratory Project values
        ep_course = next(c for c in academics['courses'] if c['code'] == 'EP101')
        self.assertTrue(ep_course['is_lab'])
        self.assertEqual(ep_course['min_pct'], 50.0)
        self.assertEqual(ep_course['attended'], 7)
        self.assertEqual(ep_course['held'], 8)
        self.assertEqual(ep_course['attendance_pct'], 87.5)

        # 2. Verify DigiCampus Drilldown (Image 2)
        drilldown = database.get_digicampus_drilldown('26AI3482', 'EP101')
        self.assertIsNotNone(drilldown)
        self.assertEqual(drilldown['subject_name'], 'Exploratory Project')
        self.assertEqual(drilldown['total_attended'], 7)
        self.assertEqual(drilldown['total_held'], 8)
        self.assertGreaterEqual(len(drilldown['sessions']), 14)

        # 3. Verify Student Portal HTTP 200 with DigiCampus UI
        # Login as student Aditya
        login_res = client.post('/student/login', data={
            'username': 'aditya.26ai3482@jietjodhpur.ac.in',
            'password': 'Aditya69'
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)

        dash_res = client.get('/student/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        dash_html = dash_res.get_data(as_text=True)
        self.assertIn('Academics', dash_html)
        self.assertIn('Current Term', dash_html)
        self.assertIn('Exploratory Project', dash_html)
        self.assertIn('Component attendance', dash_html)
        self.assertIn('PRESENT (P)', dash_html)

        # 4. Verify Faculty / Admin Bulk Toggle API
        # Login as admin
        client.post('/login', data={'username': 'admin', 'password': config.INITIAL_ADMIN_PASSWORD})

        # Test bulk marking on an upcoming date (e.g. 2026-11-23)
        res_bulk = client.post('/api/lab/attendance/bulk_toggle', data={
            'date': '2026-11-23',
            'slot_number': '1',
            'status': 'PRESENT',
            'admin_notes': 'Faculty 1-Click All Present'
        })
        self.assertEqual(res_bulk.status_code, 200)
        bulk_json = res_bulk.get_json()
        self.assertTrue(bulk_json['success'])
        self.assertGreaterEqual(bulk_json['count'], 4)

        # Reset back for clean state
        client.post('/api/lab/attendance/bulk_toggle', data={
            'date': '2026-11-23',
            'slot_number': '1',
            'status': 'NOT_MARKED'
        })

    def test_12_pwa_and_android_mobile_readiness(self):
        """
        Verify Progressive Web App (PWA) manifest, service worker, mobile icons,
        and Google Play Store privacy compliance endpoints.
        """
        client = app.test_client()

        # 1. PWA Manifest
        res_manifest = client.get('/static/manifest.json')
        self.assertEqual(res_manifest.status_code, 200)
        manifest_data = res_manifest.get_json()
        self.assertIsNotNone(manifest_data)
        self.assertEqual(manifest_data['short_name'], 'SmartVision')
        self.assertEqual(manifest_data['display'], 'standalone')
        self.assertEqual(manifest_data['theme_color'], '#ff4d4f')

        # 2. Service Worker script
        res_sw = client.get('/static/js/service-worker.js')
        self.assertEqual(res_sw.status_code, 200)
        self.assertIn(b'smartvision', res_sw.data)

        # 3. App Icons
        res_icon192 = client.get('/static/img/icons/icon-192.png')
        self.assertEqual(res_icon192.status_code, 200)
        res_icon512 = client.get('/static/img/icons/icon-512.png')
        self.assertEqual(res_icon512.status_code, 200)

        # 4. Play Store Mandatory Privacy Policy URL
        res_priv = client.get('/privacy')
        self.assertEqual(res_priv.status_code, 200)
        self.assertIn(b'Privacy Policy', res_priv.data)

if __name__ == '__main__':
    unittest.main()
