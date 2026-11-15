import time
import threading
import collections
import datetime
from config import DEFAULT_SERIAL_PORT, DEFAULT_BAUD_RATE, SERIAL_TIMEOUT
import database

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

class ArduinoBridge:
    def __init__(self):
        self.serial_conn = None
        self.port = "SIMULATION"
        self.baud_rate = DEFAULT_BAUD_RATE
        self.is_connected = False
        self.simulation_mode = True
        self.lock = threading.Lock()
        self.read_thread = None
        self.stop_event = threading.Event()
        self.recent_events = collections.deque(maxlen=60)
        self.last_event_time = None

    @staticmethod
    def list_available_ports():
        """Scans system for available serial/COM ports and tags potential Arduino boards."""
        if not HAS_SERIAL:
            return []
        
        detected = []
        try:
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                desc = p.description or ""
                hwid = p.hwid or ""
                is_arduino = any(k in (desc + hwid).lower() for k in [
                    "arduino", "ch340", "ch341", "ftdi", "cp210", "usb serial", "usb-serial", "wch"
                ])
                detected.append({
                    "device": p.device,
                    "description": desc,
                    "hwid": hwid,
                    "is_arduino": is_arduino
                })
        except Exception as e:
            print(f"[ArduinoBridge] Error listing ports: {e}")
        return detected

    def connect(self, port_name=None, baud_rate=None):
        """
        Attempts connection to a real serial port.
        If port_name is 'AUTO', scans for the best available port.
        If no port is found or connection fails, falls back gracefully to simulation mode.
        """
        with self.lock:
            self._disconnect_internal()

            baud = baud_rate or int(database.get_setting("baud_rate", DEFAULT_BAUD_RATE))
            target_port = port_name or database.get_setting("serial_port", DEFAULT_SERIAL_PORT)

            if not HAS_SERIAL:
                self.simulation_mode = True
                self.is_connected = False
                self.port = "SIMULATION (pyserial not available)"
                self._record_event("SYS", "SIMULATION_FALLBACK", "PySerial not installed; using virtual mode.")
                return False, "Using Simulation Mode (PySerial missing)"

            if target_port == "AUTO":
                ports = self.list_available_ports()
                arduino_ports = [p["device"] for p in ports if p["is_arduino"]]
                if arduino_ports:
                    target_port = arduino_ports[0]
                elif ports:
                    target_port = ports[0]["device"]
                else:
                    self.simulation_mode = True
                    self.is_connected = False
                    self.port = "SIMULATION"
                    self._record_event("SYS", "NO_PORTS_FOUND", "No physical COM ports detected. Virtual mode active.")
                    return True, "No COM ports detected; running in Virtual Mode."

            if target_port.upper().startswith("SIM"):
                self.simulation_mode = True
                self.is_connected = False
                self.port = "SIMULATION"
                self._record_event("SYS", "SIMULATION_MODE", "Virtual hardware mode explicitly selected.")
                return True, "Virtual Hardware Mode enabled."

            try:
                print(f"[ArduinoBridge] Connecting to {target_port} at {baud} baud...")
                self.serial_conn = serial.Serial(
                    port=target_port,
                    baudrate=baud,
                    timeout=SERIAL_TIMEOUT,
                    write_timeout=SERIAL_TIMEOUT
                )
                # Allow Arduino time to reset after DTR toggle
                time.sleep(2.0)
                self.serial_conn.reset_input_buffer()
                self.serial_conn.reset_output_buffer()

                self.port = target_port
                self.baud_rate = baud
                self.is_connected = True
                self.simulation_mode = False

                self.stop_event.clear()
                self.read_thread = threading.Thread(target=self._serial_read_loop, daemon=True)
                self.read_thread.start()

                # Send initial ping
                self.send_command("PING")

                msg = f"Connected to Arduino on {target_port}"
                self._record_event("SYS", "CONNECTED", msg)
                database.log_hardware_event("CONNECT", "SUCCESS", target_port, msg)
                return True, msg

            except Exception as e:
                err_msg = f"Failed to connect to {target_port}: {str(e)}"
                print(f"[ArduinoBridge] {err_msg}")
                self.simulation_mode = True
                self.is_connected = False
                self.port = "SIMULATION"
                self._record_event("SYS", "CONNECT_FAIL", err_msg)
                database.log_hardware_event("CONNECT", "FAILED", target_port, str(e))
                return False, f"{err_msg}. Falling back to Virtual Mode."

    def disconnect(self):
        """Disconnects serial connection."""
        with self.lock:
            return self._disconnect_internal()

    def _disconnect_internal(self):
        self.stop_event.set()
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

        self.is_connected = False
        self.simulation_mode = True
        self.port = "SIMULATION"
        self._record_event("SYS", "DISCONNECTED", "Hardware disconnected; running in simulation mode.")
        return True

    def _serial_read_loop(self):
        """Background thread monitoring incoming serial responses from Arduino."""
        while not self.stop_event.is_set():
            try:
                if self.serial_conn and self.serial_conn.is_open:
                    if self.serial_conn.in_waiting > 0:
                        line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            self._record_event("RX", "RECV", line)
                    else:
                        time.sleep(0.05)
                else:
                    break
            except Exception as e:
                if not self.stop_event.is_set():
                    self._record_event("ERR", "READ_ERROR", str(e))
                break

    def send_command(self, cmd):
        """Sends command line to Arduino or handles virtual simulation."""
        cmd_clean = cmd.strip()
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if self.is_connected and self.serial_conn and self.serial_conn.is_open:
            try:
                with self.lock:
                    self.serial_conn.write((cmd_clean + "\n").encode('utf-8'))
                    self.serial_conn.flush()
                self._record_event("TX", "SENT", f"Command: {cmd_clean}")
                database.log_hardware_event(cmd_clean, "SENT", self.port, "Delivered to device")
                return True, "Command dispatched"
            except Exception as e:
                err = f"Serial write error: {str(e)}"
                self._record_event("ERR", "WRITE_FAIL", err)
                database.log_hardware_event(cmd_clean, "FAILED", self.port, err)
                # Switch to simulation mode if communication fails
                self.is_connected = False
                self.simulation_mode = True
                return False, err

        # Virtual Simulation Mode handler
        sim_desc = self._get_simulation_description(cmd_clean)
        self._record_event("SIM", "VIRTUAL_ACTION", sim_desc)
        database.log_hardware_event(cmd_clean, "SIMULATED", "VIRTUAL", sim_desc)
        return True, sim_desc

    def _get_simulation_description(self, cmd):
        """Returns human-friendly description of hardware action for simulation."""
        c = cmd.upper()
        if c in ("SUCCESS", "S"):
            return "VIRTUAL ARDUINO: Green LED ON (1.2s) + Buzzer Beep [Attendance Confirmed]"
        elif c in ("ALREADY", "A"):
            return "VIRTUAL ARDUINO: Red LED ON (0.8s) + Double Warning Beep [Already Logged / Cooldown]"
        elif c in ("UNKNOWN", "U"):
            return "VIRTUAL ARDUINO: Red LED Double Blink [Face Not Recognized]"
        elif c == "TEST_GREEN":
            return "VIRTUAL ARDUINO: Green LED Pin 12 Test (1.0s ON)"
        elif c == "TEST_RED":
            return "VIRTUAL ARDUINO: Red LED Pin 11 Test (1.0s ON)"
        elif c == "TEST_BUZZ":
            return "VIRTUAL ARDUINO: Buzzer Pin 8 Tone Test (300ms)"
        elif c == "PING":
            return "VIRTUAL ARDUINO: PONG (Echo OK)"
        return f"VIRTUAL ARDUINO: Received command '{cmd}'"

    def _record_event(self, source, event_type, details):
        """Appends event to recent circular buffer."""
        evt = {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "source": source,
            "type": event_type,
            "details": details
        }
        self.recent_events.append(evt)
        self.last_event_time = evt["time"]

    # High-level trigger actions
    def trigger_attendance_success(self, student_name="Student"):
        return self.send_command("SUCCESS")

    def trigger_already_marked(self, student_name="Student"):
        return self.send_command("ALREADY")

    def trigger_unknown_face(self):
        return self.send_command("UNKNOWN")

    def test_green_led(self):
        return self.send_command("TEST_GREEN")

    def test_red_led(self):
        return self.send_command("TEST_RED")

    def test_buzzer(self):
        return self.send_command("TEST_BUZZ")

    def get_status(self):
        """Returns dictionary of current hardware bridge state."""
        return {
            "is_connected": self.is_connected,
            "simulation_mode": self.simulation_mode,
            "port": self.port,
            "baud_rate": self.baud_rate,
            "last_event_time": self.last_event_time,
            "recent_events": list(self.recent_events)[-15:]
        }

# Global singleton bridge instance
arduino = ArduinoBridge()
