#include <Arduino.h>

// Definisi Pin GPIO
const int LED1_PIN = 25;
const int LED2_PIN = 26;
const int SW1_PIN = 32;
const int SW2_PIN = 33;

// Class untuk menampung state dan logika dari sebuah switch yang di-debounce
class DebouncedSwitch {
private:
    uint8_t pin;
    const char* id;
    int lastSteadyState;
    int lastFlickerableState;
    unsigned long lastDebounceTime;
    static const unsigned long DEBOUNCE_DELAY = 50;

public:
    // Constructor
    DebouncedSwitch(uint8_t pin, const char* id) : pin(pin), id(id) {
        lastSteadyState = HIGH;
        lastFlickerableState = HIGH;
        lastDebounceTime = 0;
    }

    void begin() {
        pinMode(pin, INPUT_PULLUP);
    }

    // Method untuk memproses switch dan mengirim status jika berubah
    void process() {
        int currentState = digitalRead(pin);

        if (currentState != lastFlickerableState) {
            lastDebounceTime = millis();
            lastFlickerableState = currentState;
        }

        if ((millis() - lastDebounceTime) > DEBOUNCE_DELAY) {
            if (currentState != lastSteadyState) {
                lastSteadyState = currentState;
                Serial.printf("%s:%d\n", id, (lastSteadyState == LOW) ? 1 : 0);
            }
        }
    }
};

// Inisialisasi dua switch
DebouncedSwitch sw1(SW1_PIN, "SW1");
DebouncedSwitch sw2(SW2_PIN, "SW2");

void setup() {
    // Inisialisasi Serial (UART0) dengan baudrate 115200
    Serial.begin(115200);

    // Konfigurasi Pin
    pinMode(LED1_PIN, OUTPUT);
    pinMode(LED2_PIN, OUTPUT);
    sw1.begin(); // Menggunakan internal pull-up resistor
    sw2.begin();

    // Matikan LED saat awal
    digitalWrite(LED1_PIN, LOW);
    digitalWrite(LED2_PIN, LOW);

    Serial.println("SYSTEM_READY");
}

void loop() {
    // --- 1. Menerima Data dari Python (Kontrol LED) ---
    if (Serial.available() > 0) {
        String command = Serial.readStringUntil('\n');
        command.trim(); // Menghapus karakter whitespace/newline
        
        // Refactoring: Parse perintah KEY:VALUE untuk skalabilitas
        int separatorIndex = command.indexOf(':');
        if (separatorIndex != -1) {
            String key = command.substring(0, separatorIndex);
            String value = command.substring(separatorIndex + 1);

            if (key == "LED1") {
                digitalWrite(LED1_PIN, (value == "ON") ? HIGH : LOW);
            } else if (key == "LED2") {
                digitalWrite(LED2_PIN, (value == "ON") ? HIGH : LOW);
            }
            // Anda bisa dengan mudah menambahkan 'else if' untuk key lain di sini
        }
    }

    // --- 2. Membaca Switch dan Mengirim ke Python (Monitoring) ---
    sw1.process();
    sw2.process();
}