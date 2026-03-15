#include <Arduino.h>
#include <ctype.h>
#include <string.h>

namespace {

constexpr uint8_t LED1_PIN = PB13;
constexpr uint8_t LED2_PIN = PB12;
constexpr uint8_t SWITCH1_PIN = PA0;
constexpr uint8_t SWITCH2_PIN = PA1;

constexpr uint8_t LED1_ACTIVE_LEVEL = HIGH;
constexpr uint8_t LED2_ACTIVE_LEVEL = HIGH;
constexpr uint8_t SWITCH_ACTIVE_LEVEL = LOW;

constexpr size_t COMMAND_BUFFER_SIZE = 32;
constexpr unsigned long STATUS_INTERVAL_MS = 1000;
constexpr unsigned long DEBOUNCE_MS = 50;

char commandBuffer[COMMAND_BUFFER_SIZE];
size_t commandLength = 0;

bool led1State = false;
bool led2State = false;
bool lastSwitch1State = false;
bool lastSwitch2State = false;
bool pendingSwitch1State = false;
bool pendingSwitch2State = false;
unsigned long debounce1Millis = 0;
unsigned long debounce2Millis = 0;
unsigned long lastStatusMillis = 0;

void writeLed(uint8_t pin, uint8_t activeLevel, bool state) {
    digitalWrite(pin, state ? activeLevel : (activeLevel == HIGH ? LOW : HIGH));
}

void setLedState(uint8_t ledNumber, bool state) {
    if (ledNumber == 1) {
        led1State = state;
        writeLed(LED1_PIN, LED1_ACTIVE_LEVEL, led1State);
        return;
    }

    led2State = state;
    writeLed(LED2_PIN, LED2_ACTIVE_LEVEL, led2State);
}

bool readSwitch(uint8_t pin) {
    return digitalRead(pin) == SWITCH_ACTIVE_LEVEL;
}

const char* onOffText(bool state) {
    return state ? "ON" : "OFF";
}

const char* switchText(bool pressed) {
    return pressed ? "PRESSED" : "RELEASED";
}

void printStatus() {
    const bool switch1Pressed = readSwitch(SWITCH1_PIN);
    const bool switch2Pressed = readSwitch(SWITCH2_PIN);

    Serial.print("STATUS | LED1: ");
    Serial.print(onOffText(led1State));
    Serial.print(" | LED2: ");
    Serial.print(onOffText(led2State));
    Serial.print(" | SW1: ");
    Serial.print(switchText(switch1Pressed));
    Serial.print(" | SW2: ");
    Serial.println(switchText(switch2Pressed));
}

void printHelp() {
    Serial.println("Perintah:");
    Serial.println("  LED1 ON   / LED1 OFF");
    Serial.println("  LED2 ON   / LED2 OFF");
    Serial.println("  ALL ON    / ALL OFF");
    Serial.println("  STATUS");
    Serial.println("  HELP");
}

void toUpperInPlace(char* text) {
    while (*text != '\0') {
        *text = static_cast<char>(toupper(static_cast<unsigned char>(*text)));
        ++text;
    }
}

void handleCommand(char* command) {
    toUpperInPlace(command);

    char* firstToken = strtok(command, " ");
    if (firstToken == nullptr) {
        return;
    }

    if (strcmp(firstToken, "HELP") == 0) {
        printHelp();
        return;
    }

    if (strcmp(firstToken, "STATUS") == 0) {
        printStatus();
        return;
    }

    if (strcmp(firstToken, "ALL") == 0) {
        char* secondToken = strtok(nullptr, " ");
        if (secondToken == nullptr) {
            Serial.println("Format salah. Contoh: ALL ON");
            return;
        }

        if (strcmp(secondToken, "ON") == 0) {
            setLedState(1, true);
            setLedState(2, true);
            printStatus();
            return;
        }

        if (strcmp(secondToken, "OFF") == 0) {
            setLedState(1, false);
            setLedState(2, false);
            printStatus();
            return;
        }

        Serial.println("Perintah ALL hanya menerima ON atau OFF");
        return;
    }

    if ((strcmp(firstToken, "LED1") == 0) || (strcmp(firstToken, "LED2") == 0)) {
        char* secondToken = strtok(nullptr, " ");
        if (secondToken == nullptr) {
            Serial.println("Format salah. Contoh: LED1 ON");
            return;
        }

        const uint8_t ledNumber = (strcmp(firstToken, "LED1") == 0) ? 1 : 2;

        if (strcmp(secondToken, "ON") == 0) {
            setLedState(ledNumber, true);
            printStatus();
            return;
        }

        if (strcmp(secondToken, "OFF") == 0) {
            setLedState(ledNumber, false);
            printStatus();
            return;
        }

        Serial.println("Perintah LED hanya menerima ON atau OFF");
        return;
    }

    Serial.println("Perintah tidak dikenal. Ketik HELP");
}

void readSerialCommand() {
    while (Serial.available() > 0) {
        const char incomingChar = static_cast<char>(Serial.read());

        if ((incomingChar == '\r') || (incomingChar == '\n')) {
            if (commandLength == 0) {
                continue;
            }

            commandBuffer[commandLength] = '\0';
            handleCommand(commandBuffer);
            commandLength = 0;
            continue;
        }

        if (commandLength < (COMMAND_BUFFER_SIZE - 1)) {
            commandBuffer[commandLength++] = incomingChar;
        }
    }
}

void monitorSwitches() {
    const unsigned long now = millis();
    const bool raw1 = readSwitch(SWITCH1_PIN);
    const bool raw2 = readSwitch(SWITCH2_PIN);

    // Debounce SW1
    if (raw1 != pendingSwitch1State) {
        pendingSwitch1State = raw1;
        debounce1Millis = now;
    }
    if ((now - debounce1Millis >= DEBOUNCE_MS) && (pendingSwitch1State != lastSwitch1State)) {
        lastSwitch1State = pendingSwitch1State;
        Serial.print("EVENT | SW1: ");
        Serial.println(switchText(lastSwitch1State));
    }

    // Debounce SW2
    if (raw2 != pendingSwitch2State) {
        pendingSwitch2State = raw2;
        debounce2Millis = now;
    }
    if ((now - debounce2Millis >= DEBOUNCE_MS) && (pendingSwitch2State != lastSwitch2State)) {
        lastSwitch2State = pendingSwitch2State;
        Serial.print("EVENT | SW2: ");
        Serial.println(switchText(lastSwitch2State));
    }
}

}  // namespace

void setup() {
    pinMode(LED1_PIN, OUTPUT);
    pinMode(LED2_PIN, OUTPUT);
    pinMode(SWITCH1_PIN, INPUT_PULLUP);
    pinMode(SWITCH2_PIN, INPUT_PULLUP);

    setLedState(1, true);
    setLedState(2, true);
    lastSwitch1State = readSwitch(SWITCH1_PIN);
    lastSwitch2State = readSwitch(SWITCH2_PIN);
    pendingSwitch1State = lastSwitch1State;
    pendingSwitch2State = lastSwitch2State;

    Serial.begin(115200);
    delay(2000);

    Serial.println("Program UART STM32 - Monitoring 2 LED dan 2 Switch");
    Serial.println("Pin LED1=PB13, LED2=PB12, SW1=PA0, SW2=PA1");
    printHelp();
    printStatus();
}

void loop() {
    readSerialCommand();
    monitorSwitches();

    const unsigned long now = millis();
    if (now - lastStatusMillis >= STATUS_INTERVAL_MS) {
        lastStatusMillis = now;
        printStatus();
    }
}
