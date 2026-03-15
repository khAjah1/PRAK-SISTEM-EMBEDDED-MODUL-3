"""
GUI Monitor - STM32 UART: 2 LED & 2 Switch Control
Requires: pip install pyserial
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import serial
import serial.tools.list_ports
import threading
import queue
import time


# ── Konstanta ──────────────────────────────────────────────────────────────────
BAUD_RATE = 115200
POLL_INTERVAL_MS = 100       # interval baca serial (ms)
STATUS_REQUEST_INTERVAL = 2  # kirim STATUS tiap N detik

COLOR_BG        = "#1e1e2e"
COLOR_PANEL     = "#2a2a3e"
COLOR_ACCENT    = "#7c6af7"
COLOR_LED_ON    = "#f5c542"
COLOR_LED_OFF   = "#444466"
COLOR_SW_ON     = "#42f57e"
COLOR_SW_OFF    = "#444466"
COLOR_TEXT      = "#cdd6f4"
COLOR_LOG_BG    = "#181825"
COLOR_LOG_FG    = "#a6e3a1"
COLOR_ERR_FG    = "#f38ba8"
COLOR_WARN_FG   = "#fab387"


class STM32Monitor:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("STM32 UART Monitor — 2 LED & 2 Switch")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        self.serial_port: serial.Serial | None = None
        self.read_thread: threading.Thread | None = None
        self.rx_queue: queue.Queue[str] = queue.Queue()
        self.running = False

        self.led1_state = False
        self.led2_state = False
        self.sw1_state  = False
        self.sw2_state  = False
        self._last_status_time = 0.0

        self._build_ui()
        self._refresh_ports()
        self.root.after(POLL_INTERVAL_MS, self._process_rx_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Builder ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 8}

        # ── Baris atas: koneksi ─────────────────────────────────────────────
        conn_frame = tk.Frame(self.root, bg=COLOR_PANEL, bd=0)
        conn_frame.pack(fill="x", padx=12, pady=(12, 0))

        tk.Label(conn_frame, text="Port:", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).pack(side="left", **pad)

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var,
                                       width=14, state="readonly",
                                       font=("Segoe UI", 10))
        self.port_combo.pack(side="left", padx=(0, 6), pady=8)

        self.btn_refresh = tk.Button(conn_frame, text="↻", width=3,
                                     bg=COLOR_PANEL, fg=COLOR_TEXT,
                                     font=("Segoe UI", 11),
                                     relief="flat", cursor="hand2",
                                     command=self._refresh_ports)
        self.btn_refresh.pack(side="left", padx=(0, 10))

        tk.Label(conn_frame, text="Baud:", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        self.baud_var = tk.StringVar(value=str(BAUD_RATE))
        baud_entry = tk.Entry(conn_frame, textvariable=self.baud_var, width=8,
                              bg=COLOR_LOG_BG, fg=COLOR_TEXT,
                              font=("Segoe UI", 10), relief="flat",
                              insertbackground=COLOR_TEXT)
        baud_entry.pack(side="left", padx=(4, 14), pady=8)

        self.btn_connect = tk.Button(conn_frame, text="Connect",
                                     bg=COLOR_ACCENT, fg="white",
                                     font=("Segoe UI", 10, "bold"),
                                     width=10, relief="flat", cursor="hand2",
                                     command=self._toggle_connection)
        self.btn_connect.pack(side="left", pady=8)

        self.lbl_status = tk.Label(conn_frame, text="● Tidak Terhubung",
                                   bg=COLOR_PANEL, fg=COLOR_ERR_FG,
                                   font=("Segoe UI", 9))
        self.lbl_status.pack(side="left", padx=14)

        # ── Tengah: LED + Switch ─────────────────────────────────────────────
        mid_frame = tk.Frame(self.root, bg=COLOR_BG)
        mid_frame.pack(fill="x", padx=12, pady=10)

        self._build_led_panel(mid_frame)
        self._build_switch_panel(mid_frame)

        # ── Baris perintah ───────────────────────────────────────────────────
        cmd_frame = tk.Frame(self.root, bg=COLOR_PANEL)
        cmd_frame.pack(fill="x", padx=12, pady=(0, 8))

        tk.Label(cmd_frame, text="Perintah:", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).pack(side="left", **pad)

        self.cmd_var = tk.StringVar()
        cmd_entry = tk.Entry(cmd_frame, textvariable=self.cmd_var, width=28,
                             bg=COLOR_LOG_BG, fg=COLOR_TEXT,
                             font=("Courier New", 10), relief="flat",
                             insertbackground=COLOR_TEXT)
        cmd_entry.pack(side="left", padx=(0, 8), pady=8)
        cmd_entry.bind("<Return>", lambda _: self._send_manual_command())

        tk.Button(cmd_frame, text="Kirim", bg=COLOR_ACCENT, fg="white",
                  font=("Segoe UI", 10, "bold"), width=8, relief="flat",
                  cursor="hand2",
                  command=self._send_manual_command).pack(side="left", pady=8)

        tk.Button(cmd_frame, text="STATUS", bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=("Segoe UI", 10), width=8, relief="flat",
                  cursor="hand2",
                  command=lambda: self._send("STATUS")).pack(side="left",
                                                              padx=(10, 0),
                                                              pady=8)

        tk.Button(cmd_frame, text="HELP", bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=("Segoe UI", 10), width=6, relief="flat",
                  cursor="hand2",
                  command=lambda: self._send("HELP")).pack(side="left",
                                                           padx=4, pady=8)

        # ── Log ──────────────────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=COLOR_BG)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        tk.Label(log_frame, text="Log Serial", bg=COLOR_BG, fg=COLOR_TEXT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self.log_box = scrolledtext.ScrolledText(
            log_frame, height=12, width=72,
            bg=COLOR_LOG_BG, fg=COLOR_LOG_FG,
            font=("Courier New", 9), relief="flat",
            state="disabled", wrap="word",
            insertbackground=COLOR_TEXT
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("err",  foreground=COLOR_ERR_FG)
        self.log_box.tag_config("warn", foreground=COLOR_WARN_FG)
        self.log_box.tag_config("tx",   foreground="#89b4fa")

        tk.Button(log_frame, text="Bersihkan Log", bg=COLOR_PANEL,
                  fg=COLOR_TEXT, font=("Segoe UI", 8), relief="flat",
                  cursor="hand2",
                  command=self._clear_log).pack(anchor="e", pady=(4, 0))

    def _build_led_panel(self, parent: tk.Frame) -> None:
        frame = tk.LabelFrame(parent, text="  LED Control  ",
                               bg=COLOR_PANEL, fg=COLOR_TEXT,
                               font=("Segoe UI", 10, "bold"),
                               bd=1, relief="flat")
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        for i, (name, pin) in enumerate([("LED 1", "PB13"), ("LED 2", "PB12")]):
            col = tk.Frame(frame, bg=COLOR_PANEL)
            col.pack(side="left", expand=True, padx=14, pady=12)

            # Indikator bulat
            canvas = tk.Canvas(col, width=54, height=54,
                                bg=COLOR_PANEL, highlightthickness=0)
            canvas.pack()
            circle = canvas.create_oval(4, 4, 50, 50, fill=COLOR_LED_OFF,
                                        outline="")
            canvas.create_text(27, 27, text=name[4], fill="#1e1e2e",
                                font=("Segoe UI", 14, "bold"))

            tk.Label(col, text=f"{name}\n{pin}",
                     bg=COLOR_PANEL, fg=COLOR_TEXT,
                     font=("Segoe UI", 9), justify="center").pack(pady=4)

            btn_frame = tk.Frame(col, bg=COLOR_PANEL)
            btn_frame.pack()

            num = i + 1
            tk.Button(btn_frame, text="ON", width=5,
                      bg="#2d4a2d", fg=COLOR_SW_ON,
                      font=("Segoe UI", 9, "bold"), relief="flat",
                      cursor="hand2",
                      command=lambda n=num: self._led_cmd(n, True)
                      ).pack(side="left", padx=2)
            tk.Button(btn_frame, text="OFF", width=5,
                      bg="#4a2d2d", fg=COLOR_ERR_FG,
                      font=("Segoe UI", 9, "bold"), relief="flat",
                      cursor="hand2",
                      command=lambda n=num: self._led_cmd(n, False)
                      ).pack(side="left", padx=2)

            if i == 0:
                self.led1_canvas  = canvas
                self.led1_circle  = circle
            else:
                self.led2_canvas  = canvas
                self.led2_circle  = circle

        # Tombol ALL
        all_frame = tk.Frame(frame, bg=COLOR_PANEL)
        all_frame.pack(side="left", padx=10, pady=12)
        tk.Label(all_frame, text="Semua", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Segoe UI", 9)).pack(pady=(0, 6))
        tk.Button(all_frame, text="ALL ON", width=8,
                  bg="#2d4a2d", fg=COLOR_SW_ON,
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  cursor="hand2",
                  command=lambda: self._all_cmd(True)).pack(pady=2)
        tk.Button(all_frame, text="ALL OFF", width=8,
                  bg="#4a2d2d", fg=COLOR_ERR_FG,
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  cursor="hand2",
                  command=lambda: self._all_cmd(False)).pack(pady=2)

    def _build_switch_panel(self, parent: tk.Frame) -> None:
        frame = tk.LabelFrame(parent, text="  Switch Monitor  ",
                               bg=COLOR_PANEL, fg=COLOR_TEXT,
                               font=("Segoe UI", 10, "bold"),
                               bd=1, relief="flat")
        frame.pack(side="left", fill="both", expand=True)

        for i, (name, pin) in enumerate([("SW 1", "PA0"), ("SW 2", "PA1")]):
            col = tk.Frame(frame, bg=COLOR_PANEL)
            col.pack(side="left", expand=True, padx=20, pady=12)

            canvas = tk.Canvas(col, width=54, height=54,
                                bg=COLOR_PANEL, highlightthickness=0)
            canvas.pack()
            circle = canvas.create_oval(4, 4, 50, 50, fill=COLOR_SW_OFF,
                                        outline="")
            canvas.create_text(27, 27, text=name[3], fill="#1e1e2e",
                                font=("Segoe UI", 14, "bold"))

            lbl = tk.Label(col, text=f"{name}\n{pin}\nRELEASED",
                           bg=COLOR_PANEL, fg=COLOR_TEXT,
                           font=("Segoe UI", 9), justify="center")
            lbl.pack(pady=4)

            if i == 0:
                self.sw1_canvas = canvas
                self.sw1_circle = circle
                self.sw1_label  = lbl
            else:
                self.sw2_canvas = canvas
                self.sw2_circle = circle
                self.sw2_label  = lbl

    # ── Serial ─────────────────────────────────────────────────────────────────

    def _refresh_ports(self) -> None:
        import winreg

        EXCLUDE_KEYWORDS = ("intel", "amt", "management", "eterlogic", "virtual")
        USB_KEYWORDS = ("usb", "ftdi", "ch34", "cp210", "uart", "prolific")

        # Ambil semua port dari registry (termasuk yang driver-nya Unknown)
        reg_ports: list[str] = []
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DEVICEMAP\SERIALCOMM")
            i = 0
            while True:
                try:
                    _, val, _ = winreg.EnumValue(key, i)
                    reg_ports.append(str(val))
                    i += 1
                except OSError:
                    break
        except OSError:
            pass

        # Ambil deskripsi dari pyserial
        desc_map = {p.device: (p.description or "").lower()
                    for p in serial.tools.list_ports.comports()}

        usb_ports: list[str] = []
        other_ports: list[str] = []

        all_known = set(desc_map.keys()) | set(reg_ports)
        for port in sorted(all_known):
            desc = desc_map.get(port, "")
            if any(kw in desc for kw in EXCLUDE_KEYWORDS):
                continue
            if "com3" == port.upper().replace("\\", "").replace(".", ""):
                continue
            if any(kw in desc for kw in USB_KEYWORDS) or port not in desc_map:
                usb_ports.append(port)
            else:
                other_ports.append(port)

        ports = usb_ports + other_ports
        self.port_combo["values"] = ports
        if ports:
            self.port_var.set(ports[0])
        else:
            self.port_var.set("")
            self._log("Tidak ada port terdeteksi. Colok FTDI/CH340 lalu klik ↻", "warn")

    def _toggle_connection(self) -> None:
        if self.running:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        port = self.port_var.get()
        if not port:
            self._log("Pilih port terlebih dahulu.", "err")
            return
        try:
            baud = int(self.baud_var.get())
            self.serial_port = serial.Serial(port, baud, timeout=0.1)
            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop,
                                                daemon=True)
            self.read_thread.start()
            self.btn_connect.config(text="Disconnect", bg="#e64553")
            self.lbl_status.config(text=f"● Terhubung ({port})",
                                   fg=COLOR_SW_ON)
            self._log(f"Terhubung ke {port} @ {baud} baud")
        except serial.SerialException as exc:
            self._log(f"Gagal connect: {exc}", "err")

    def _disconnect(self) -> None:
        self.running = False
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.serial_port = None
        self.btn_connect.config(text="Connect", bg=COLOR_ACCENT)
        self.lbl_status.config(text="● Tidak Terhubung", fg=COLOR_ERR_FG)
        self._log("Koneksi diputus.")

    def _read_loop(self) -> None:
        """Thread: baca data serial dan masukkan ke queue."""
        while self.running and self.serial_port:
            try:
                line = self.serial_port.readline().decode("utf-8",
                                                          errors="replace")
                if line.strip():
                    self.rx_queue.put(line.strip())
            except serial.SerialException:
                self.rx_queue.put("__SERIAL_ERROR__")
                break

    def _send(self, command: str) -> None:
        if not self.running or not self.serial_port:
            self._log("Belum terhubung.", "warn")
            return
        try:
            self.serial_port.write((command + "\r\n").encode())
            self._log(f"→ {command}", "tx")
        except serial.SerialException as exc:
            self._log(f"Gagal kirim: {exc}", "err")

    def _led_cmd(self, led_num: int, state: bool) -> None:
        """Update indikator langsung lalu kirim perintah ke hardware."""
        self._update_led(led_num, state)
        self._send(f"LED{led_num} {'ON' if state else 'OFF'}")

    def _all_cmd(self, state: bool) -> None:
        self._update_led(1, state)
        self._update_led(2, state)
        self._send(f"ALL {'ON' if state else 'OFF'}")

    def _send_manual_command(self) -> None:
        cmd = self.cmd_var.get().strip()
        if cmd:
            self._send(cmd)
            self.cmd_var.set("")

    # ── RX Queue Processor ─────────────────────────────────────────────────────

    def _process_rx_queue(self) -> None:
        while not self.rx_queue.empty():
            line = self.rx_queue.get_nowait()
            if line == "__SERIAL_ERROR__":
                self._disconnect()
                self._log("Koneksi serial terputus.", "err")
            else:
                self._parse_line(line)
                self._log(f"← {line}")

        # Minta STATUS berkala
        if self.running:
            now = time.time()
            if now - self._last_status_time >= STATUS_REQUEST_INTERVAL:
                self._last_status_time = now
                self._send("STATUS")

        self.root.after(POLL_INTERVAL_MS, self._process_rx_queue)

    def _parse_line(self, line: str) -> None:
        """Parse baris STATUS dari STM32 dan update UI."""
        upper = line.upper()
        if "STATUS" in upper or "LED1:" in upper:
            led1 = "LED1: ON" in upper
            led2 = "LED2: ON" in upper
            sw1  = "SW1: PRESSED" in upper
            sw2  = "SW2: PRESSED" in upper
            self._update_led(1, led1)
            self._update_led(2, led2)
            self._update_switch(1, sw1)
            self._update_switch(2, sw2)

        elif "SW1:" in upper and "EVENT" in upper:
            self._update_switch(1, "PRESSED" in upper)
        elif "SW2:" in upper and "EVENT" in upper:
            self._update_switch(2, "PRESSED" in upper)

    # ── UI Update ──────────────────────────────────────────────────────────────

    def _update_led(self, led_num: int, state: bool) -> None:
        color = COLOR_LED_ON if state else COLOR_LED_OFF
        if led_num == 1:
            self.led1_canvas.itemconfig(self.led1_circle, fill=color)
            self.led1_state = state
        else:
            self.led2_canvas.itemconfig(self.led2_circle, fill=color)
            self.led2_state = state

    def _update_switch(self, sw_num: int, pressed: bool) -> None:
        color  = COLOR_SW_ON if pressed else COLOR_SW_OFF
        text   = "PRESSED" if pressed else "RELEASED"
        prefix = f"SW {sw_num}\n{'PA0' if sw_num == 1 else 'PA1'}\n"
        if sw_num == 1:
            self.sw1_canvas.itemconfig(self.sw1_circle, fill=color)
            self.sw1_label.config(text=prefix + text)
            self.sw1_state = pressed
        else:
            self.sw2_canvas.itemconfig(self.sw2_circle, fill=color)
            self.sw2_label.config(text=prefix + text)
            self.sw2_state = pressed

    # ── Log ────────────────────────────────────────────────────────────────────

    def _log(self, message: str, tag: str = "") -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        if tag:
            self.log_box.insert("end", f"[{timestamp}] {message}\n", tag)
        else:
            self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _clear_log(self) -> None:
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self._disconnect()
        self.root.destroy()


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.minsize(680, 520)
    app = STM32Monitor(root)
    root.mainloop()
