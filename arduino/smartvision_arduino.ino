/*
 * ==============================================================================
 * SmartVision / SmartAttend AI - Arduino Hardware Controller
 * Idea Lab Face Recognition Attendance System
 * ==============================================================================
 * 
 * Hardware Connections:
 *  - PIN 12 : Green LED Anode (+) through 220-330 ohm resistor to GND (-)
 *  - PIN 11 : Red LED Anode (+) through 220-330 ohm resistor to GND (-)
 *  - PIN 8  : Buzzer Positive (+) [Active or Passive] to GND (-)
 * 
 * Serial Protocol:
 *  - Baud Rate: 9600 bps
 *  - Commands:
 *      SUCCESS   -> Green LED ON (1.2s) + Single pleasant buzzer beep
 *      ALREADY   -> Red LED ON (0.8s) + Double warning beep
 *      UNKNOWN   -> Red LED rapid double flash
 *      TEST_GREEN-> Turn Green LED ON for 1 second
 *      TEST_RED  -> Turn Red LED ON for 1 second
 *      TEST_BUZZ -> Sound buzzer for 300 ms
 *      PING      -> Responds with "PONG"
 * ==============================================================================
 */

// Pin Definitions
const int PIN_GREEN_LED = 12;
const int PIN_RED_LED   = 11;
const int PIN_BUZZER    = 8;

// Non-blocking timing variables
unsigned long greenLedTimer = 0;
unsigned long redLedTimer   = 0;
unsigned long buzzerTimer   = 0;

bool greenLedActive = false;
bool redLedActive   = false;
bool buzzerActive   = false;

// Double beep helper variables
int doubleBeepStep = 0;
unsigned long doubleBeepTimer = 0;

void setup() {
  // Initialize digital output pins
  pinMode(PIN_GREEN_LED, OUTPUT);
  pinMode(PIN_RED_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  digitalWrite(PIN_GREEN_LED, LOW);
  digitalWrite(PIN_RED_LED, LOW);
  digitalWrite(PIN_BUZZER, LOW);

  // Initialize Serial interface
  Serial.begin(9600);
  while (!Serial && millis() < 3000) {
    ; // Wait up to 3 seconds for native USB serial
  }

  // Startup self-test sequence
  digitalWrite(PIN_GREEN_LED, HIGH);
  digitalWrite(PIN_RED_LED, HIGH);
  tone(PIN_BUZZER, 1800, 100);
  delay(150);
  digitalWrite(PIN_GREEN_LED, LOW);
  digitalWrite(PIN_RED_LED, LOW);

  Serial.println(F("[SMARTVISION_ARDUINO_READY]"));
}

void loop() {
  unsigned long currentMillis = millis();

  // Read incoming Serial commands
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "SUCCESS" || cmd == "S") {
      triggerSuccessSignal();
    } else if (cmd == "ALREADY" || cmd == "A") {
      triggerAlreadySignal();
    } else if (cmd == "UNKNOWN" || cmd == "U") {
      triggerUnknownSignal();
    } else if (cmd == "TEST_GREEN") {
      digitalWrite(PIN_GREEN_LED, HIGH);
      greenLedActive = true;
      greenLedTimer = currentMillis;
      Serial.println(F("[ARDUINO] Green LED test triggered."));
    } else if (cmd == "TEST_RED") {
      digitalWrite(PIN_RED_LED, HIGH);
      redLedActive = true;
      redLedTimer = currentMillis;
      Serial.println(F("[ARDUINO] Red LED test triggered."));
    } else if (cmd == "TEST_BUZZ") {
      tone(PIN_BUZZER, 2000, 300);
      Serial.println(F("[ARDUINO] Buzzer test triggered."));
    } else if (cmd == "PING") {
      Serial.println(F("PONG"));
    } else if (cmd.length() > 0) {
      Serial.print(F("[ARDUINO_UNKNOWN_CMD]: "));
      Serial.println(cmd);
    }
  }

  // Handle Green LED timeout (Non-blocking)
  if (greenLedActive && (currentMillis - greenLedTimer >= 1200)) {
    digitalWrite(PIN_GREEN_LED, LOW);
    greenLedActive = false;
  }

  // Handle Red LED timeout (Non-blocking)
  if (redLedActive && (currentMillis - redLedTimer >= 800)) {
    digitalWrite(PIN_RED_LED, LOW);
    redLedActive = false;
  }

  // Handle Double Beep state machine for "ALREADY" warning
  if (doubleBeepStep == 1 && (currentMillis - doubleBeepTimer >= 80)) {
    noTone(PIN_BUZZER);
    doubleBeepStep = 2;
    doubleBeepTimer = currentMillis;
  } else if (doubleBeepStep == 2 && (currentMillis - doubleBeepTimer >= 60)) {
    tone(PIN_BUZZER, 1000);
    doubleBeepStep = 3;
    doubleBeepTimer = currentMillis;
  } else if (doubleBeepStep == 3 && (currentMillis - doubleBeepTimer >= 80)) {
    noTone(PIN_BUZZER);
    doubleBeepStep = 0;
  }
}

// Trigger Green LED and short pleasant tone for successful attendance
void triggerSuccessSignal() {
  digitalWrite(PIN_GREEN_LED, HIGH);
  greenLedActive = true;
  greenLedTimer = millis();

  // 1760 Hz (Note A6) for 150ms
  tone(PIN_BUZZER, 1760, 160);

  Serial.println(F("[ARDUINO] ACK: Attendance Marked -> Green LED ON, Buzzer beeped."));
}

// Trigger Red LED and two warning beeps for duplicate/already marked
void triggerAlreadySignal() {
  digitalWrite(PIN_RED_LED, HIGH);
  redLedActive = true;
  redLedTimer = millis();

  // Start double-beep sequence
  tone(PIN_BUZZER, 1000);
  doubleBeepStep = 1;
  doubleBeepTimer = millis();

  Serial.println(F("[ARDUINO] ACK: Already Marked / Cooldown -> Red LED ON, Double beep."));
}

// Trigger rapid red flash for unknown face
void triggerUnknownSignal() {
  digitalWrite(PIN_RED_LED, HIGH);
  redLedActive = true;
  redLedTimer = millis();

  tone(PIN_BUZZER, 600, 100);

  Serial.println(F("[ARDUINO] ACK: Unknown Face Detected."));
}
