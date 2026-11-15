# SmartVision: AI-Based Face Detection Attendance System for Idea Lab
### (SmartAttend AI)

An enterprise-grade, edge AI-powered biometric attendance system designed specifically for the **Idea Lab**. It combines high-speed deep neural network computer vision with an IoT Arduino hardware controller (Green LED, Red LED, and Buzzer signals) and an interactive web dashboard.

---

## 🌟 Key Features

1. **Edge AI Biometric Vision Engine**:
   - Uses OpenCV's **YuNet** face detector (ultra-fast deep neural network on ONNX).
   - Uses **SFace** ResNet deep face recognizer to generate 128-dimensional biometric embeddings.
   - Real-time cosine similarity vector matching with customizable confidence thresholds.
   - Multi-sample enrollment: Captures multiple frames to build an averaged, angle-invariant composite face embedding.

2. **IoT Hardware Integration (Arduino)**:
   - USB Serial communication (9600 baud) directly connected to an Arduino Uno / Nano / Mega.
   - **Green LED (Pin 12)**: Lights up for 1.2s on attendance confirmation.
   - **Red LED (Pin 11)**: Alerts on duplicate/cooldown scans or unrecognized faces.
   - **Buzzer (Pin 8)**: Emits a pleasant verification tone on attendance, or a double-beep on warnings.
   - **Virtual Simulation Mode**: If no Arduino is connected, the system automatically falls back to virtual mode without crashing or hanging, synthesizing audio chimes in the browser!

3. **Anti-Duplicate & Anti-Proxy Attendance Rules**:
   - Configurable cooldown window (e.g. 60 minutes) or strict once-a-day mode.
   - Prevents duplicate attendance logging if a student lingers in front of the camera.

4. **Idea Lab Command Center & Web Dashboard**:
   - **Live Kiosk View**: Dedicated full-screen kiosk interface with live face tracking bounding boxes, confidence %, and verified admission spotlight.
   - **Member Directory**: Enrolled members with photo avatars, ID badges, department classification, and personal attendance history.
   - **Student Enrollment Portal**: Register via live webcam (single photo or smart 5-sample burst) or file upload.
   - **Attendance Analytics**: Daily attendance rate %, hourly entrance flow chart, department distribution chart.
   - **One-Click Reports Export**: Generates professionally styled **Excel (.xlsx)** workbooks and **CSV** files.
   - **Hardware Diagnostics Test Bench**: Interactive buttons to test the Green LED, Red LED, and Buzzer on demand, with a live serial transaction terminal.
   - **Manual Attendance Override**: Allows teachers/admins to manually log attendance with an audit note.

---

## 🔌 Hardware Circuit & Wiring Guide

### Components Required
| Component | Purpose | Pins / Connections |
| :--- | :--- | :--- |
| **USB Webcam** | Face capture at entrance | Laptop USB port |
| **Arduino Uno / Nano** | Microcontroller | Laptop USB (COM Port) |
| **Green LED** | Attendance Marked confirmation | Pin 12 (+) through 220Ω resistor -> GND (-) |
| **Red LED** | Warning / Duplicate alert | Pin 11 (+) through 220Ω resistor -> GND (-) |
| **Buzzer (Active/Passive)** | Audio feedback | Pin 8 (+) -> GND (-) |
| **2x 220Ω - 330Ω Resistors** | Current limiting for LEDs | In series with LED anodes |
| **Breadboard & Wires** | Prototyping | Standard jumper connections |

### Schematic Diagram
```
        +-----------------------------------------+
        |               ARDUINO UNO               |
        |                                         |
        |  [PIN 12] ──[ 220Ω ]──>|── (Green LED) ┐|
        |  [PIN 11] ──[ 220Ω ]──>|── (Red LED)   ┤|
        |  [PIN 8 ] ────────────(+)─ [ Buzzer ] ─┤|
        |                                        ||
        |  [ GND  ] <────────────────────────────┘|
        +-----------------------------------------+
```

### Arduino Code Upload
1. Open the file `arduino/smartvision_arduino.ino` in the **Arduino IDE**.
2. Select your board (e.g., *Arduino Uno*) and port (e.g., *COM3*).
3. Click **Upload**.
4. Both LEDs and buzzer will perform a 150ms startup self-test.

---

## 💻 Software Stack
- **Backend**: Python 3.10+ / 3.14, Flask, SQLite3, PySerial, XlsxWriter
- **Computer Vision & AI**: OpenCV DNN (`FaceDetectorYN`, `FaceRecognizerSF`), ONNX Models (YuNet & SFace)
- **Frontend**: HTML5, CSS3, JavaScript (ES6), Bootstrap 5, FontAwesome 6, Chart.js, Web Audio API

---

## 🚀 Quickstart & Setup

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Launch SmartVision
Run the launcher:
```powershell
python run.py
```
Or directly:
```powershell
python app.py
```

### 3. Open in Browser
- **Dashboard**: `http://localhost:5000`
- **Live Kiosk Entrance**: `http://localhost:5000/live`
- **Enroll Member**: `http://localhost:5000/register`
- **Hardware Controller**: `http://localhost:5000/hardware`

---

## 📖 How to Use

### 1. Enrolling Students
1. Navigate to **Enroll Face** (`/register`).
2. Fill in the student's **Name**, **Student ID**, and **Department**.
3. Choose either:
   - **Live Webcam**: Look at the camera and click **Snap Photo** or **Smart 5-Sample Capture**.
   - **Upload Photo File**: Select a clear front-facing portrait.
4. Click **Complete Registration**. The deep face embedding will be computed and stored in the database.

### 2. Marking Attendance
1. Open the **Live Kiosk** (`/live`) on a laptop or monitor at the entrance.
2. Click **Fullscreen**.
3. When an enrolled member steps in front of the camera:
   - A **Green Bounding Box** appears with their name, ID, and confidence score.
   - The **Arduino Green LED** illuminates and the **Buzzer** beeps.
   - The web app plays an audio chime and displays a verified confirmation card.
   - The attendance record is logged in the database.
4. If the student stands in front of the camera again during the cooldown period, the system displays **Already Recorded** with an amber indicator and prevents duplicate logging.

### 3. Exporting Reports
1. Navigate to **Attendance** (`/attendance`).
2. Filter by date, department, or search by name.
3. Click **Export Excel (.xlsx)** for a formatted spreadsheet report, or **Export CSV**.

### 4. Hardware Management
1. Navigate to **Hardware & IoT** (`/hardware`).
2. The system auto-detects connected COM ports. Select your Arduino's port and click **Connect**.
3. Use the diagnostic buttons (**Test Green LED**, **Test Red LED**, **Test Buzzer**) to verify physical signals.
4. View real-time TX/RX commands in the terminal window.
