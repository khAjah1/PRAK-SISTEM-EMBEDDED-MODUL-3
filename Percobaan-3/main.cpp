#include <Arduino.h>
#include <string.h>

// USART2: PA3=RX, PA2=TX (default STM32F103 USART2)
HardwareSerial Serial2(PA3, PA2);

/*
 * Full Duplex: STM32 <---> ESP32 <---> PC
 *
 * USART1 (Serial)  : PA9  (TX) -- PA10 (RX)  --> PC (GUI Serial)
 * USART2 (Serial2) : PA2  (TX) -- PA3  (RX)  --> ESP32
 *
 * LED (dikontrol via GUI perintah serial dari PC):
 *   LED1 (PA0)  : Kontrol GUI   cmd: LED1_ON / LED1_OFF
 *   LED2 (PA1)  : Kontrol GUI   cmd: LED2_ON / LED2_OFF
 *   LED3 (PB12) : Kontrol GUI   cmd: LED3_ON / LED3_OFF
 *   LED4 (PB13) : Kontrol GUI   cmd: LED4_ON / LED4_OFF
 *
 * Switch (monitor status dikirim ke PC):
 *   SW1 (PB0) : internal pull-up, perubahan state dilaporkan ke PC
 *   SW2 (PB1) : internal pull-up, perubahan state dilaporkan ke PC
 *
 * Format GUI perintah (kirim dari Serial Monitor / aplikasi PC):
 *   LED1_ON   -> LED1 nyala
 *   LED1_OFF  -> LED1 mati
 *   STATUS    -> kirim status semua LED & switch
 */

#define PC_BAUD   115200
#define ESP_BAUD  115200

// --- Pin LED (active HIGH) ---
#define LED1  PA0
#define LED2  PA1
#define LED3  PB12
#define LED4  PB13

// --- Pin Switch (active LOW, internal pull-up) ---
#define SW1  PB0
#define SW2  PB1

// Status LED (untuk GUI)
bool ledState[4] = {false, false, false, false};
const uint8_t ledPin[4] = {LED1, LED2, LED3, LED4};

// Status switch sebelumnya (debounce sederhana)
bool swLast[2] = {true, true};
uint32_t swDebounce[2] = {0, 0};
#define DEBOUNCE_MS  50

// Buffer PC → ESP32
volatile char pcBuf[128];
volatile uint8_t pcIdx = 0;
volatile bool pcReady = false;

// Buffer ESP32 → PC
volatile char espBuf[128];
volatile uint8_t espIdx = 0;
volatile bool espReady = false;

// ---- Fungsi pembantu ----

void setLed(uint8_t idx, bool on) {
    ledState[idx] = on;
    digitalWrite(ledPin[idx], on ? HIGH : LOW);
}

void sendStatus() {
    Serial2.println("--- STATUS ---");
    for (uint8_t i = 0; i < 4; i++) {
        Serial2.printf("LED%d : %s\n", i + 1, ledState[i] ? "ON" : "OFF");
    }
    bool sw[2];
    sw[0] = !digitalRead(SW1);
    sw[1] = !digitalRead(SW2);
    for (uint8_t i = 0; i < 2; i++) {
        Serial2.printf("SW%d  : %s\n", i + 1, sw[i] ? "PRESSED" : "RELEASED");
    }
    Serial2.println("--------------");
}

// Parse dan jalankan perintah GUI dari PC
void handleCommand(const char* cmd) {
    // Bandingkan case-insensitive dengan strupr-safe cara manual
    char buf[32];
    strncpy(buf, cmd, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    // Uppercase manual
    for (uint8_t i = 0; buf[i]; i++) {
        if (buf[i] >= 'a' && buf[i] <= 'z') buf[i] -= 32;
    }
    // Trim \r jika ada
    uint8_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\r') buf[--len] = '\0';

    if      (strcmp(buf, "LED1_ON")  == 0) { setLed(0, true);  Serial2.println("LED1 ON"); }
    else if (strcmp(buf, "LED1_OFF") == 0) { setLed(0, false); Serial2.println("LED1 OFF"); }
    else if (strcmp(buf, "LED2_ON")  == 0) { setLed(1, true);  Serial2.println("LED2 ON"); }
    else if (strcmp(buf, "LED2_OFF") == 0) { setLed(1, false); Serial2.println("LED2 OFF"); }
    else if (strcmp(buf, "LED3_ON")  == 0) { setLed(2, true);  Serial2.println("LED3 ON"); }
    else if (strcmp(buf, "LED3_OFF") == 0) { setLed(2, false); Serial2.println("LED3 OFF"); }
    else if (strcmp(buf, "LED4_ON")  == 0) { setLed(3, true);  Serial2.println("LED4 ON"); }
    else if (strcmp(buf, "LED4_OFF") == 0) { setLed(3, false); Serial2.println("LED4 OFF"); }
    else if (strcmp(buf, "STATUS")   == 0) { sendStatus(); }
    else {
        Serial2.printf("Unknown: %s\n", cmd);
    }
}

// Interrupt callback: data masuk dari PC (USART1)
void serialEvent() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n') {
            pcBuf[pcIdx] = '\0';
            pcReady = true;
            pcIdx = 0;
        } else if (pcIdx < 127) {
            pcBuf[pcIdx++] = c;
        }
    }
}

// Interrupt callback: data masuk dari ESP32 (USART2)
void serialEvent2() {
    while (Serial2.available()) {
        char c = (char)Serial2.read();
        if (c == '\n') {
            espBuf[espIdx] = '\0';
            espReady = true;
            espIdx = 0;
        } else if (espIdx < 127) {
            espBuf[espIdx++] = c;
        }
    }
}

// ---- Setup ----
void setup() {
    // LED
    for (uint8_t i = 0; i < 4; i++) {
        pinMode(ledPin[i], OUTPUT);
        digitalWrite(ledPin[i], LOW);
    }

    // Switch (internal pull-up)
    pinMode(SW1, INPUT_PULLUP);
    pinMode(SW2, INPUT_PULLUP);

    // USART1 → PC
    Serial.begin(PC_BAUD);
    // USART2 → ESP32
    Serial2.begin(ESP_BAUD);

    delay(2000);
    Serial2.println("=== STM32 Ready ===");
    Serial2.println("Perintah: LED1_ON/OFF..LED4_ON/OFF, STATUS");
    Serial2.println("Ready");
}

// ---- Loop ----
void loop() {
    uint32_t now = millis();
    const uint8_t swPin[2] = {SW1, SW2};

    // --- Monitor switch: laporkan perubahan state ke PC ---
    for (uint8_t i = 0; i < 2; i++) {
        bool cur = !digitalRead(swPin[i]);  // true = ditekan
        if (cur != swLast[i]) {
            if (now - swDebounce[i] > DEBOUNCE_MS) {
                swDebounce[i] = now;
                swLast[i] = cur;
                Serial2.printf("[SW%d] %s\n", i + 1, cur ? "PRESSED" : "RELEASED");
            }
        }
    }

    // Polling serialEvent
    serialEvent();
    serialEvent2();

    // Data dari PC → proses perintah GUI atau teruskan ke ESP32
    if (pcReady) {
        pcReady = false;
        handleCommand((const char*)pcBuf);
    }

    // Data dari ESP32 (PC via bridge) → proses perintah
    if (espReady) {
        espReady = false;
        handleCommand((const char*)espBuf);
    }
}
