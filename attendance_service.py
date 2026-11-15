import os
import time
import datetime
import csv
import io
import collections
import cv2
from pathlib import Path
import xlsxwriter

from config import SNAPSHOTS_DIR, EXPORTS_DIR, DEFAULT_COOLDOWN_MINUTES
import database
from arduino_bridge import arduino

class AttendanceService:
    def __init__(self):
        # In-memory debounce cache: {student_id: float_epoch_timestamp}
        self.last_attendance_cache = {}
        # Audio / signal debounce: {student_id: float_epoch_timestamp} (avoids buzzer buzzing on every video frame)
        self.signal_debounce = {}
        # Live recognition events queue for real-time frontend streaming
        self.live_events = collections.deque(maxlen=40)
        self._load_today_cache()

    def _load_today_cache(self):
        """Preloads today's recorded attendances into memory cache."""
        today_records = database.get_attendance_records(
            start_date=datetime.date.today().strftime("%Y-%m-%d"),
            limit=500
        )
        now_epoch = time.time()
        for r in today_records:
            sid = r["student_id"]
            if sid not in self.last_attendance_cache:
                self.last_attendance_cache[sid] = now_epoch

    def check_eligibility(self, student_id):
        """
        Determines if student can be marked present right now.
        Returns (is_eligible, reason_code, message).
        """
        rule = database.get_setting("duplicate_rule", "COOLDOWN")
        cooldown_mins = float(database.get_setting("cooldown_minutes", str(DEFAULT_COOLDOWN_MINUTES)))

        # Rule 1: ONCE_A_DAY
        if rule == "ONCE_A_DAY":
            if database.has_attended_today(student_id):
                return False, "ALREADY_TODAY", "Attendance already marked for today."

        # Rule 2: COOLDOWN in minutes
        if student_id in self.last_attendance_cache:
            elapsed_seconds = time.time() - self.last_attendance_cache[student_id]
            if elapsed_seconds < (cooldown_mins * 60):
                remaining_mins = int((cooldown_mins * 60 - elapsed_seconds) / 60) + 1
                return False, "COOLDOWN_ACTIVE", f"Already marked. Cooldown active ({remaining_mins} min remaining)."

        # Fallback to DB check for safety
        last_rec = database.get_last_attendance(student_id)
        if last_rec:
            try:
                rec_dt = datetime.datetime.fromisoformat(last_rec["timestamp"])
                elapsed_seconds = (datetime.datetime.now() - rec_dt).total_seconds()
                if rule == "ONCE_A_DAY" and rec_dt.date() == datetime.date.today():
                    self.last_attendance_cache[student_id] = time.time()
                    return False, "ALREADY_TODAY", "Attendance already marked for today."
                elif rule == "COOLDOWN" and elapsed_seconds < (cooldown_mins * 60):
                    self.last_attendance_cache[student_id] = time.time()
                    remaining_mins = int((cooldown_mins * 60 - elapsed_seconds) / 60) + 1
                    return False, "COOLDOWN_ACTIVE", f"Already marked. Cooldown active ({remaining_mins} min remaining)."
            except Exception:
                pass

        return True, "ELIGIBLE", "Ready for attendance."

    def process_face_match(self, student, confidence, frame=None, face_box=None):
        """
        Processes a successful AI face match.
        Handles debounced hardware signaling, database logging, snapshot saving, and UI push.
        """
        student_id = student["student_id"]
        student_name = student["name"]
        department = student["department"]
        now = time.time()

        is_eligible, reason, message = self.check_eligibility(student_id)

        if not is_eligible:
            # Student is already marked; check audio signal debounce (do not buzz more than once every 10 seconds)
            last_sig = self.signal_debounce.get(student_id, 0)
            if (now - last_sig) > 10.0:
                self.signal_debounce[student_id] = now
                arduino.trigger_already_marked(student_name)
                self._push_live_event({
                    "type": "ALREADY_MARKED",
                    "student_id": student_id,
                    "student_name": student_name,
                    "department": department,
                    "confidence": round(float(confidence) * 100, 1),
                    "message": message,
                    "time": datetime.datetime.now().strftime("%H:%M:%S")
                })
            return {
                "status": "ALREADY_MARKED",
                "message": message,
                "student": student,
                "confidence": confidence
            }

        # Save snapshot if frame is provided
        snapshot_filename = None
        if frame is not None:
            try:
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"snap_{student_id}_{stamp}.jpg"
                save_path = SNAPSHOTS_DIR / filename

                # If face box provided, save cropped face with small margin, else resize frame
                if face_box:
                    x, y, w, h = face_box
                    h_img, w_img = frame.shape[:2]
                    pad_x = int(w * 0.2)
                    pad_y = int(h * 0.2)
                    x1 = max(0, x - pad_x)
                    y1 = max(0, y - pad_y)
                    x2 = min(w_img, x + w + pad_x)
                    y2 = min(h_img, y + h + pad_y)
                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        cv2.imwrite(str(save_path), crop)
                    else:
                        cv2.imwrite(str(save_path), frame)
                else:
                    cv2.imwrite(str(save_path), frame)
                snapshot_filename = f"uploads/snapshots/{filename}"
            except Exception as e:
                print(f"[AttendanceService] Snapshot save error: {e}")

        # Record in IDEA Lab Slot Ledger (Slot 1 at 01:20 PM, Slot 2 at 02:10 PM)
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        now_time = datetime.datetime.now().time()
        if now_time < datetime.time(14, 10):
            target_slot = 1
            target_time = "01:20 PM"
        else:
            target_slot = 2
            target_time = "02:10 PM"

        # If Slot 1 is already marked present for today, advance to Slot 2
        try:
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT status FROM lab_attendance WHERE student_id = ? AND date = ? AND slot_number = 1;", (student_id, today_str))
            slot1_row = cur.fetchone()
            conn.close()
            if slot1_row and slot1_row["status"] == "PRESENT":
                target_slot = 2
                target_time = "02:10 PM"
        except Exception:
            pass

        database.record_slot_attendance(
            student_id=student_id,
            date_str=today_str,
            slot_number=target_slot,
            slot_time=target_time,
            status="PRESENT",
            marked_via="AI_CAMERA"
        )

        # Record in General Attendance Database
        record_id = database.record_attendance(
            student_id=student_id,
            student_name=student_name,
            department=department,
            confidence=confidence,
            status="Present",
            snapshot_path=snapshot_filename,
            marked_via="AI_CAMERA"
        )

        # Update in-memory caches
        self.last_attendance_cache[student_id] = now
        self.signal_debounce[student_id] = now

        # Trigger Arduino Green LED + Buzzer!
        arduino.trigger_attendance_success(student_name)

        # Push to UI event feed
        event_payload = {
            "type": "MARKED_PRESENT",
            "record_id": record_id,
            "student_id": student_id,
            "student_name": student_name,
            "department": department,
            "confidence": round(float(confidence) * 100, 1),
            "snapshot_path": snapshot_filename,
            "message": f"Attendance marked for {student_name}!",
            "time": datetime.datetime.now().strftime("%H:%M:%S")
        }
        self._push_live_event(event_payload)

        return {
            "status": "SUCCESS",
            "message": f"Attendance logged for {student_name}.",
            "record_id": record_id,
            "student": student,
            "confidence": confidence
        }

    def manual_mark_attendance(self, student_id, note="Manual entry by admin"):
        """Allows teachers or admins to manually mark attendance for a student."""
        student = database.get_student_by_id(student_id)
        if not student:
            return False, "Student ID not found."

        record_id = database.record_attendance(
            student_id=student["student_id"],
            student_name=student["name"],
            department=student["department"],
            confidence=1.0,
            status="Present",
            snapshot_path=student.get("photo_path"),
            marked_via="MANUAL_OVERRIDE"
        )

        self.last_attendance_cache[student_id] = time.time()
        arduino.trigger_attendance_success(student["name"])

        event_payload = {
            "type": "MANUAL_ENTRY",
            "record_id": record_id,
            "student_id": student["student_id"],
            "student_name": student["name"],
            "department": student["department"],
            "confidence": 100.0,
            "message": f"Manual attendance logged for {student['name']} ({note}).",
            "time": datetime.datetime.now().strftime("%H:%M:%S")
        }
        self._push_live_event(event_payload)
        return True, f"Attendance recorded for {student['name']}."

    def _push_live_event(self, event):
        self.live_events.append(event)

    def get_live_events(self):
        return list(self.live_events)

    # ----------------- Reports Export ----------------- #

    def generate_csv_report(self, start_date=None, end_date=None, department=None, status=None):
        """Generates CSV report string for attendance logs."""
        records = database.get_attendance_records(
            start_date=start_date,
            end_date=end_date,
            department=department,
            status=status,
            limit=5000
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Record ID", "Student ID", "Student Name", "Department", "Date", "Time", "Status", "Confidence", "Marked Via"])

        for r in records:
            writer.writerow([
                r["id"],
                r["student_id"],
                r["student_name"],
                r["department"],
                r["date"],
                r["time"],
                r["status"],
                f"{round(r['confidence'] * 100, 1)}%",
                r["marked_via"]
            ])

        output.seek(0)
        return output.getvalue()

    def generate_excel_report(self, start_date=None, end_date=None, department=None, status=None):
        """
        Creates a beautifully styled Excel (.xlsx) workbook report using xlsxwriter.
        Includes title banner, KPI summary cards, structured data table, and formulas.
        """
        records = database.get_attendance_records(
            start_date=start_date,
            end_date=end_date,
            department=department,
            status=status,
            limit=10000
        )

        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        date_label = start_date if start_date else "All_Dates"
        excel_filename = f"SmartVision_Attendance_{date_label}_{timestamp_str}.xlsx"
        excel_filepath = EXPORTS_DIR / excel_filename

        workbook = xlsxwriter.Workbook(str(excel_filepath))
        worksheet = workbook.add_worksheet("Attendance Log")
        worksheet.hide_gridlines(0)  # Show gridlines

        # Styles
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 16, 'font_color': '#ffffff',
            'bg_color': '#0f172a', 'align': 'left', 'valign': 'vcenter'
        })
        subtitle_fmt = workbook.add_format({
            'font_size': 10, 'font_color': '#94a3b8',
            'bg_color': '#0f172a', 'align': 'left', 'valign': 'vcenter'
        })
        header_fmt = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#ffffff',
            'bg_color': '#2563eb', 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'border_color': '#cbd5e1'
        })
        cell_fmt = workbook.add_format({
            'font_size': 10, 'font_color': '#1e293b',
            'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0'
        })
        cell_center_fmt = workbook.add_format({
            'font_size': 10, 'font_color': '#1e293b',
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0'
        })
        cell_alt_fmt = workbook.add_format({
            'font_size': 10, 'font_color': '#1e293b', 'bg_color': '#f8fafc',
            'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0'
        })
        cell_alt_center_fmt = workbook.add_format({
            'font_size': 10, 'font_color': '#1e293b', 'bg_color': '#f8fafc',
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0'
        })
        status_present_fmt = workbook.add_format({
            'bold': True, 'font_size': 10, 'font_color': '#166534', 'bg_color': '#dcfce7',
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#bbf7d0'
        })
        summary_title_fmt = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#0f172a',
            'bg_color': '#f1f5f9', 'border': 1, 'border_color': '#cbd5e1'
        })
        summary_val_fmt = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#2563eb',
            'align': 'center', 'bg_color': '#f1f5f9', 'border': 1, 'border_color': '#cbd5e1'
        })

        # Title Rows
        worksheet.set_row(0, 32)
        worksheet.set_row(1, 20)
        worksheet.merge_range("A1:H1", "  SmartVision: AI Face Recognition Attendance System", title_fmt)
        export_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.merge_range("A2:H2", f"  Idea Lab Attendance Report | Exported: {export_time} | Filter: {department or 'All Departments'}", subtitle_fmt)

        # Space row
        worksheet.set_row(2, 10)

        # Headers
        headers = ["#", "Student ID", "Full Name", "Department", "Date", "Time", "Status", "Confidence", "Source"]
        worksheet.set_row(3, 24)
        for col_idx, h in enumerate(headers):
            worksheet.write(3, col_idx, h, header_fmt)

        # Data Rows
        row_idx = 4
        for idx, r in enumerate(records, start=1):
            worksheet.set_row(row_idx, 20)
            is_alt = (idx % 2 == 0)
            c_fmt = cell_alt_fmt if is_alt else cell_fmt
            c_center = cell_alt_center_fmt if is_alt else cell_center_fmt

            worksheet.write(row_idx, 0, idx, c_center)
            worksheet.write(row_idx, 1, r["student_id"], c_center)
            worksheet.write(row_idx, 2, r["student_name"], c_fmt)
            worksheet.write(row_idx, 3, r["department"] or "General", c_fmt)
            worksheet.write(row_idx, 4, r["date"], c_center)
            worksheet.write(row_idx, 5, r["time"], c_center)
            worksheet.write(row_idx, 6, r["status"], status_present_fmt)
            conf_str = f"{round(r['confidence'] * 100, 1)}%"
            worksheet.write(row_idx, 7, conf_str, c_center)
            worksheet.write(row_idx, 8, r["marked_via"], c_center)
            row_idx += 1

        # Summary footer
        row_idx += 1
        worksheet.set_row(row_idx, 22)
        worksheet.merge_range(row_idx, 0, row_idx, 3, "Total Records Exported:", summary_title_fmt)
        worksheet.write(row_idx, 4, len(records), summary_val_fmt)

        # Column widths
        col_widths = [6, 16, 24, 20, 14, 12, 14, 14, 16]
        for c_idx, w in enumerate(col_widths):
            worksheet.set_column(c_idx, c_idx, w)

        workbook.close()
        return str(excel_filepath), excel_filename

# Global service instance
attendance_service = AttendanceService()
