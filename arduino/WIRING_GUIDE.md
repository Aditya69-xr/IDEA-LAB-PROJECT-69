# SmartVision Hardware & Arduino Wiring Guide

This guide describes how to connect the electronic components (Arduino, Green LED, Red LED, Buzzer, and Resistors) to build the hardware feedback unit for the Idea Lab Smart Attendance System.

---

## 1. Components Checklist
- **1x Arduino Board**: Arduino Uno, Nano, or Mega (or compatible clone with CH340 / FTDI chip)
- **1x Green LED**: Indicates successful attendance recognition
- **1x Red LED**: Indicates unrecognized person or duplicate/cooldown warning
- **1x Buzzer**: 5V Active or Passive piezo buzzer
- **2x 220Ω - 330Ω Resistors**: Current-limiting resistors for the LEDs
- **1x Breadboard & Jumper Wires** (Male-to-Male / Male-to-Female)
- **1x USB Type-B or Mini/Micro/Type-C cable** (to connect Arduino to laptop)

---

## 2. Pin Connections Table

| Component | Component Lead / Pin | Connects To | Notes |
| :--- | :--- | :--- | :--- |
| **Green LED** | Longer Lead (Anode `+`) | Arduino **Digital PIN 12** | In series with 220Ω / 330Ω resistor |
| **Green LED** | Shorter Lead (Cathode `-`) | Arduino **GND** | Ground rail |
| **Red LED** | Longer Lead (Anode `+`) | Arduino **Digital PIN 11** | In series with 220Ω / 330Ω resistor |
| **Red LED** | Shorter Lead (Cathode `-`) | Arduino **GND** | Ground rail |
| **Buzzer** | Positive (`+` or red wire) | Arduino **Digital PIN 8** | Digital PWM / Tone pin |
| **Buzzer** | Negative (`-` or black wire) | Arduino **GND** | Ground rail |

---

## 3. Circuit Schematic (ASCII)

```
        +-----------------------------------------+
        |               ARDUINO UNO               |
        |                                         |
        |  [D12] ──[ 220Ω ]──>|── (Green LED) ──┐ |
        |  [D11] ──[ 220Ω ]──>|── (Red LED)   ──┤ |
        |  [D8 ] ────────────(+)─ [ Buzzer ] ───┤ |
        |                                       | |
        |  [GND] <──────────────────────────────┘ |
        +-----------------------------------------+
```

---

## 4. How to Upload the Arduino Code

1. Download and open the **Arduino IDE** (or use Arduino Web Editor).
2. Connect your Arduino board to your computer via USB.
3. In Arduino IDE:
   - Go to **Tools > Board** and select your board (e.g. *Arduino Uno* or *Arduino Nano*).
   - Go to **Tools > Port** and select the port that appears (e.g. `COM3`, `COM4`, or `/dev/ttyUSB0`).
   - If using Arduino Nano with CH340 chip, select processor: *ATmega328P (Old Bootloader)* if standard upload fails.
4. Open the file `arduino/smartvision_arduino.ino`.
5. Click the **Upload** button (Right arrow icon).
6. Once uploaded, both LEDs and the buzzer will do a quick 150ms startup self-test beep.
7. Close the Arduino IDE Serial Monitor so that the SmartVision Python web application can access the COM port without port conflict.

---

## 5. Testing the Hardware via Web Dashboard

1. Launch the SmartVision web application.
2. Navigate to the **Hardware & IoT** page in the top menu.
3. Select your Arduino's COM port from the dropdown (or leave as **AUTO**).
4. Click **Connect to Hardware**.
5. Use the interactive buttons:
   - **Test Green LED**: Verifies Pin 12 lighting.
   - **Test Red LED**: Verifies Pin 11 lighting.
   - **Test Buzzer**: Verifies sound generation on Pin 8.
6. If the Arduino is disconnected or unplugged, the SmartVision system automatically runs in **Virtual Simulation Mode**, displaying simulated hardware signals in the UI with sound effects so testing is never blocked!
