import tkinter as tk
from tkinter import ttk
import serial
import serial.tools.list_ports
import threading

class ESP32ControllerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32 Control Panel") 
        self.root.geometry("400x350")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.serial_port = None
        self.is_connected = False

        # --- Frame Koneksi ---
        conn_frame = ttk.LabelFrame(root, text="Koneksi Serial")
        conn_frame.pack(pady=10, padx=10, fill="x")

        self.port_combo = ttk.Combobox(conn_frame)
        self.port_combo.pack(side="left", padx=5, expand=True, fill="x")
        
        self.btn_refresh = ttk.Button(conn_frame, text="Refresh", command=self.refresh_ports)
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_connect = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=5)

        self.refresh_ports()

        # --- Frame Kontrol LED ---
        led_frame = ttk.LabelFrame(root, text="Kontrol LED")
        led_frame.pack(pady=10, padx=10, fill="x")

        self.btn_led1 = tk.Button(led_frame, text="LED 1: OFF", bg="red", fg="white", width=15, command=lambda: self.toggle_led(1))
        self.btn_led1.pack(side="left", padx=20, pady=10, expand=True)

        self.btn_led2 = tk.Button(led_frame, text="LED 2: OFF", bg="red", fg="white", width=15, command=lambda: self.toggle_led(2))
        self.btn_led2.pack(side="left", padx=20, pady=10, expand=True)

        self.leds = {
            1: {'state': False, 'button': self.btn_led1},
            2: {'state': False, 'button': self.btn_led2}
        }

        # --- Frame Monitoring Switch ---
        sw_frame = ttk.LabelFrame(root, text="Monitoring Switch")
        sw_frame.pack(pady=10, padx=10, fill="x")

        self.lbl_sw1 = tk.Label(sw_frame, text="Switch 1: RELEASED", bg="lightgray", width=20, height=2, relief="sunken")
        self.lbl_sw1.pack(side="left", padx=10, pady=10, expand=True)

        self.lbl_sw2 = tk.Label(sw_frame, text="Switch 2: RELEASED", bg="lightgray", width=20, height=2, relief="sunken")
        self.lbl_sw2.pack(side="left", padx=10, pady=10, expand=True)

        # --- Frame Status ---
        status_frame = ttk.Frame(root)
        status_frame.pack(pady=5, padx=10, fill="x")
        self.lbl_status = tk.Label(status_frame, text="Status: Disconnected", fg="gray", anchor="w")
        self.lbl_status.pack(fill="x")
    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        self.port_combo['values'] = [port.device for port in ports]
        if ports:
            self.port_combo.current(0)

    def toggle_connection(self):
        if not self.is_connected:
            try:
                port = self.port_combo.get()
                self.serial_port = serial.Serial(port, 115200, timeout=1)
                self.is_connected = True
                self.btn_connect.config(text="Disconnect")
                self.lbl_status.config(text=f"Status: Connecting to {port}...", fg="orange")
                
                # Mulai thread untuk membaca data serial
                self.read_thread = threading.Thread(target=self.read_serial)
                self.read_thread.daemon = True
                self.read_thread.start()
            except Exception as e:
                error_msg = str(e)
                self.lbl_status.config(text=f"Status: Error - {error_msg}", fg="red")
                print(f"Error connecting: {error_msg}")
        else:
            # Disconnect initiated by user
            self.handle_disconnection_event(user_initiated=True)
    def toggle_led(self, led_num):
        if not self.is_connected: return

        # Refactored logic to avoid code duplication
        led_info = self.leds.get(led_num)
        if not led_info: return

        led_info['state'] = not led_info['state']
        state_str = 'ON' if led_info['state'] else 'OFF'
        bg_color = 'green' if led_info['state'] else 'red'

        cmd = f"LED{led_num}:{state_str}\n"
        led_info['button'].config(text=f"LED {led_num}: {state_str}", bg=bg_color)

        self.serial_port.write(cmd.encode())

    def read_serial(self):
        while self.is_connected and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode().strip()
                    if line:
                        # Update UI harus dilakukan di main thread, gunakan root.after
                        self.root.after(0, self.process_data, line)
            except (serial.SerialException, OSError) as e:
                # This typically happens if the device is unplugged
                print(f"Serial connection lost: {e}")
                self.root.after(0, self.handle_disconnection_event)
                break
            except Exception as e:
                print(f"Read error: {e}")
                self.root.after(0, self.handle_disconnection_event)
                break

    def process_data(self, data):
        # Format data dari ESP32: "KEY:VALUE"
        try:
            if ":" in data:
                key, value = data.split(":", 1)
                if key == "SW1":
                    if value == "1":
                        self.lbl_sw1.config(text="Switch 1: PRESSED", bg="lime")
                    elif value == "0":
                        self.lbl_sw1.config(text="Switch 1: RELEASED", bg="lightgray")
                elif key == "SW2":
                    if value == "1":
                        self.lbl_sw2.config(text="Switch 2: PRESSED", bg="lime")
                    elif value == "0":
                        self.lbl_sw2.config(text="Switch 2: RELEASED", bg="lightgray")
            elif "SYSTEM_READY" in data:
                print("ESP32 is ready.")
                self.lbl_status.config(text=f"Status: Connected to {self.serial_port.port}", fg="green")
        except Exception as e:
            print(f"Error processing data '{data}': {e}")

    def handle_disconnection_event(self, user_initiated=False):
        if not self.is_connected:
            return # Already disconnected

        self.is_connected = False
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.btn_connect.config(text="Connect")
        status_text = "Status: Disconnected" if user_initiated else "Status: Connection Lost!"
        status_color = "gray" if user_initiated else "red"
        self.lbl_status.config(text=status_text, fg=status_color)
        print("Disconnected." if user_initiated else "Connection lost.")

    def on_closing(self):
        if self.is_connected:
            self.serial_port.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ESP32ControllerApp(root)
    root.mainloop()