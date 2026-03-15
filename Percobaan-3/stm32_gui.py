"""
STM32 UART Monitor — 4 LED & 2 Switch
Referensi: tampilan compact dengan indikator lingkaran besar
Requires: pip install pyserial
"""

import tkinter as tk
from tkinter import ttk
import serial
import serial.tools.list_ports
import threading
import queue
import time
import math

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = "#1c1a2e"
BG_PANEL    = "#252340"
BG_INPUT    = "#2e2c4a"
BORDER      = "#3a3660"
FG          = "#e0deff"
FG_DIM      = "#8888aa"
FG_RED      = "#ff6b6b"

CIRCLE_OFF  = "#3a3660"
CIRCLE_NUM_OFF = "#8888aa"

BTN_PURPLE  = "#6c5cbf"
BTN_HOVER   = "#7d6fd0"
BTN_RED     = "#8b2424"

BTN_ON_BG   = "#27ae60"
BTN_ON_FG   = "#ffffff"
BTN_OFF_BG  = "#8b1a1a"
BTN_OFF_FG  = "#ffcccc"

BTN_ALLON_BG  = "#1a5c1a"
BTN_ALLOFF_BG = "#6b1a1a"

HOLD_COL    = "#b66d00"

LED_COLORS  = ["#ff3333", "#ff3333", "#ff3333", "#ff3333"]
SW_COLOR    = "#e59400"

LED_NAMES   = ["LED 1", "LED 2", "LED 3", "LED 4"]
LED_PINS    = ["PA0",   "PA1",   "PB12",  "PB13"]
SW_PINS     = ["PB0",   "PB1"]

BAUD_DEFAULT = 115200
POLL_MS      = 15


# ── Helpers ───────────────────────────────────────────────────────────────────
def clamp(v):
    return max(0, min(255, int(v)))

def dimcol(h, f):
    h = h.lstrip("#")
    r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)
    return "#{:02x}{:02x}{:02x}".format(clamp(r * f), clamp(g * f), clamp(b * f))


# ── Circular Indicator ────────────────────────────────────────────────────────
class CircleIndicator(tk.Canvas):
    """Large numbered circle that glows when active."""
    R = 34

    def __init__(self, parent, number, color_on, bg=BG_PANEL):
        d = self.R * 2 + 10
        super().__init__(parent, width=d, height=d,
                         bg=bg, highlightthickness=0)
        self.color_on = color_on
        self.cbg      = bg
        self.num      = str(number)
        self.is_on    = False
        self.phase    = 0.0
        self.job      = None
        self._draw()

    def _draw(self):
        self.delete("all")
        r  = self.R
        ox = 5
        oy = 5
        if self.is_on:
            # outer glow
            self.create_oval(ox - 4, oy - 4, ox + r * 2 + 4, oy + r * 2 + 4,
                             fill=dimcol(self.color_on, 0.25), outline="")
            self.create_oval(ox, oy, ox + r * 2, oy + r * 2,
                             fill=self.color_on, outline="")
            num_col = self.cbg
        else:
            self.create_oval(ox, oy, ox + r * 2, oy + r * 2,
                             fill=CIRCLE_OFF, outline="")
            num_col = CIRCLE_NUM_OFF
        cx = ox + r
        cy = oy + r
        self.create_text(cx, cy, text=self.num,
                         font=("Segoe UI", 17, "bold"), fill=num_col)

    def _pulse(self):
        self.phase = (self.phase + 0.08) % 2.0
        # subtle brightness oscillation
        f = 0.85 + 0.15 * math.sin(self.phase * math.pi)
        h = self.color_on.lstrip("#")
        r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)
        col = "#{:02x}{:02x}{:02x}".format(clamp(r * f), clamp(g * f), clamp(b * f))
        self.itemconfigure(2, fill=col)  # oval item 2 = filled circle
        self.job = self.after(50, self._pulse)

    def set_on(self, v: bool):
        if v == self.is_on:
            return
        self.is_on = v
        if self.job:
            self.after_cancel(self.job)
            self.job = None
        self._draw()
        if v:
            self._pulse()


# ── Main Application ──────────────────────────────────────────────────────────
class STM32Monitor(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("STM32 UART Monitor \u2014 4 LED & 2 Switch")
        self.configure(bg=BG)
        self.geometry("860x640")
        self.minsize(780, 560)
        self.resizable(True, True)

        self.ser       = None
        self.rq        = queue.Queue()
        self._running  = False
        self.led_state = [False] * 4
        self.baud_var  = tk.StringVar(value=str(BAUD_DEFAULT))

        # widget lists — must exist before _build (used in _set_btns_state)
        self._led_circles  = []
        self._led_on_btns  = []
        self._led_off_btns = []
        self._led_hold_btns = []
        self._sw_circles   = []
        self._sw_state_lbl = []

        self._ttk_style()
        self._build()
        self._refresh_ports()
        self.after(POLL_MS, self._poll)

    # ── TTK style ─────────────────────────────────────────────────────────────
    def _ttk_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TCombobox",
                    fieldbackground=BG_INPUT, background=BG_INPUT,
                    foreground=FG, arrowcolor=FG_DIM, borderwidth=0)
        s.map("TCombobox",
              fieldbackground=[("readonly", BG_INPUT)],
              arrowcolor=[("readonly", FG_DIM)])
        s.configure("Vertical.TScrollbar",
                    troughcolor=BG_PANEL, background=BG_INPUT,
                    borderwidth=0, relief="flat", arrowsize=10)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_topbar()
        self._build_main()
        self._build_cmdbar()
        self._build_log()

    # ── Top bar ───────────────────────────────────────────────────────────────
    def _build_topbar(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(12, 8))

        tk.Label(bar, text="Port:", fg=FG_DIM, bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")

        self.port_var = tk.StringVar()
        self.port_cb  = ttk.Combobox(bar, textvariable=self.port_var,
                                     width=8, state="readonly",
                                     font=("Segoe UI", 9))
        self.port_cb.pack(side="left", padx=(4, 2))

        tk.Button(bar, text="\u21bb", command=self._refresh_ports,
                  bg=BG_INPUT, fg=FG, font=("Segoe UI", 11),
                  relief="flat", bd=0, cursor="hand2",
                  padx=5, pady=1).pack(side="left", padx=(0, 14))

        tk.Label(bar, text="Baud:", fg=FG_DIM, bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(bar, textvariable=self.baud_var,
                 width=8, bg=BG_INPUT, fg=FG,
                 insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9)).pack(side="left", padx=(4, 16), ipady=4)

        self._btn_conn = tk.Button(bar, text="Connect",
                                   command=self._toggle_connect,
                                   bg=BTN_PURPLE, fg=FG,
                                   activebackground=BTN_HOVER,
                                   activeforeground=FG,
                                   font=("Segoe UI", 10, "bold"),
                                   relief="flat", bd=0, cursor="hand2",
                                   padx=18, pady=5)
        self._btn_conn.pack(side="left", padx=(0, 14))

        self._status_dot = tk.Label(bar, text="\u25cf", fg=FG_RED, bg=BG,
                                    font=("Segoe UI", 11))
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(bar, text=" Tidak Terhubung",
                                    fg=FG_RED, bg=BG, font=("Segoe UI", 9))
        self._status_lbl.pack(side="left")

    # ── Main area (LED + Switch) ───────────────────────────────────────────────
    def _build_main(self):
        main = tk.Frame(self, bg=BG)
        main.pack(fill="x", padx=16, pady=(0, 8))
        self._build_led_panel(main)
        self._build_sw_panel(main)

    def _make_panel(self, parent, title, side="left", expand=True, padright=8):
        f = tk.Frame(parent, bg=BG_PANEL,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(side=side, expand=expand, fill="both",
               padx=(0, padright), pady=0)
        tk.Label(f, text=title, font=("Segoe UI", 11, "bold"),
                 fg=FG, bg=BG_PANEL).pack(anchor="w", padx=14, pady=(10, 4))
        return f

    # ── LED Panel ─────────────────────────────────────────────────────────────
    def _build_led_panel(self, parent):
        panel = self._make_panel(parent, "LED Control",
                                 side="left", expand=True, padright=8)

        body = tk.Frame(panel, bg=BG_PANEL)
        body.pack(fill="x", padx=8, pady=(0, 10))

        # 2×2 grid of LED indicators (left side of body)
        grid = tk.Frame(body, bg=BG_PANEL)
        grid.pack(side="left", expand=True, fill="x")

        for i in range(4):
            col = i % 2
            row = i // 2
            cell = tk.Frame(grid, bg=BG_PANEL)
            cell.grid(row=row, column=col, padx=10, pady=6, sticky="nsew")

            circ = CircleIndicator(cell, i + 1, LED_COLORS[i], bg=BG_PANEL)
            circ.pack()
            self._led_circles.append(circ)

            tk.Label(cell, text=LED_NAMES[i], fg=FG, bg=BG_PANEL,
                     font=("Segoe UI", 9, "bold")).pack()
            tk.Label(cell, text=LED_PINS[i], fg=FG_DIM, bg=BG_PANEL,
                     font=("Segoe UI", 8)).pack()

            brow = tk.Frame(cell, bg=BG_PANEL)
            brow.pack(pady=(5, 0))

            bon = tk.Button(brow, text="ON",
                            command=lambda n=i: self._led_on(n),
                            bg=BTN_ON_BG, fg=BTN_ON_FG,
                            activebackground=dimcol(BTN_ON_BG, 1.4),
                            font=("Segoe UI", 8, "bold"),
                            relief="flat", bd=0, cursor="hand2",
                            width=5, pady=3)
            bon.pack(side="left", padx=(0, 3))

            boff = tk.Button(brow, text="OFF",
                             command=lambda n=i: self._led_off(n),
                             bg=BTN_OFF_BG, fg=BTN_OFF_FG,
                             activebackground=dimcol(BTN_OFF_BG, 1.5),
                             font=("Segoe UI", 8, "bold"),
                             relief="flat", bd=0, cursor="hand2",
                             width=5, pady=3)
            boff.pack(side="left")

            self._led_on_btns.append(bon)
            self._led_off_btns.append(boff)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # "Semua" box (right side of body)
        semua = tk.Frame(body, bg=BG_INPUT,
                         highlightthickness=1, highlightbackground=BORDER)
        semua.pack(side="left", padx=(14, 4), pady=4, anchor="n")

        tk.Label(semua, text="Semua", fg=FG_DIM, bg=BG_INPUT,
                 font=("Segoe UI", 9, "bold")).pack(padx=18, pady=(10, 8))

        tk.Button(semua, text="ALL ON",
                  command=self._all_on,
                  bg=BTN_ALLON_BG, fg=BTN_ON_FG,
                  activebackground=dimcol(BTN_ALLON_BG, 1.4),
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, cursor="hand2",
                  width=10, pady=6).pack(padx=14, pady=(0, 6))

        tk.Button(semua, text="ALL OFF",
                  command=self._all_off,
                  bg=BTN_ALLOFF_BG, fg="#ffaaaa",
                  activebackground=dimcol(BTN_ALLOFF_BG, 1.4),
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, cursor="hand2",
                  width=10, pady=6).pack(padx=14, pady=(0, 14))

        # Hold row (below grid, full width of panel)
        hold_f = tk.Frame(panel, bg=BG_PANEL)
        hold_f.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(hold_f, text="Tahan (HOLD = ON saat ditekan, OFF saat dilepas):",
                 fg=FG_DIM, bg=BG_PANEL, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
        hrow = tk.Frame(hold_f, bg=BG_PANEL)
        hrow.pack(fill="x")
        for i in range(4):
            bh = self._make_hold_btn(hrow, f"LED {i+1}", i)
            bh.pack(side="left", padx=(0, 6))
            self._led_hold_btns.append(bh)

    def _make_hold_btn(self, parent, text, idx):
        b = tk.Button(parent, text=text,
                      font=("Segoe UI", 8, "bold"),
                      bg=HOLD_COL, fg=BG,
                      activebackground=dimcol(HOLD_COL, 1.3),
                      relief="flat", bd=0, cursor="hand2",
                      padx=8, pady=4, width=7)

        def _press(e):
            b.configure(bg=dimcol(HOLD_COL, 1.4), relief="sunken")
            self._led_on(idx)

        def _release(e):
            b.configure(bg=HOLD_COL, relief="flat")
            self._led_off(idx)

        b.bind("<ButtonPress-1>",   _press)
        b.bind("<ButtonRelease-1>", _release)
        b.bind("<Leave>", lambda e: _release(e) if b.cget("relief") == "sunken" else None)
        return b

    # ── Switch Panel ──────────────────────────────────────────────────────────
    def _build_sw_panel(self, parent):
        panel = self._make_panel(parent, "Switch Monitor",
                                 side="left", expand=False, padright=0)
        panel.configure(width=230)
        panel.pack_propagate(False)

        body = tk.Frame(panel, bg=BG_PANEL)
        body.pack(fill="x", padx=10, pady=(0, 14))

        for i in range(2):
            cell = tk.Frame(body, bg=BG_PANEL)
            cell.pack(side="left", expand=True, padx=8, pady=8)

            circ = CircleIndicator(cell, i + 1, SW_COLOR, bg=BG_PANEL)
            circ.pack()
            self._sw_circles.append(circ)

            tk.Label(cell, text=f"SW {i+1}", fg=FG, bg=BG_PANEL,
                     font=("Segoe UI", 9, "bold")).pack(pady=(2, 0))
            tk.Label(cell, text=SW_PINS[i], fg=FG_DIM, bg=BG_PANEL,
                     font=("Segoe UI", 8)).pack()

            sl = tk.Label(cell, text="RELEASED", fg=FG_DIM, bg=BG_PANEL,
                          font=("Segoe UI", 8, "bold"))
            sl.pack(pady=(3, 0))
            self._sw_state_lbl.append(sl)

    # ── Command bar ───────────────────────────────────────────────────────────
    def _build_cmdbar(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 6))

        tk.Label(bar, text="Perintah:", fg=FG_DIM, bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")

        self.cmd_var = tk.StringVar()
        ent = tk.Entry(bar, textvariable=self.cmd_var,
                       bg=BG_INPUT, fg=FG, insertbackground=FG,
                       relief="flat", font=("Segoe UI", 10), width=26)
        ent.pack(side="left", padx=(6, 8), ipady=5)
        ent.bind("<Return>", lambda _: self._send_cmd())

        for label, cmd, bg in [
            ("Kirim",  None,       BTN_PURPLE),
            ("STATUS", "STATUS",   BG_INPUT),
            ("HELP",   "HELP",     BG_INPUT),
        ]:
            act = (lambda: self._send_cmd()) if cmd is None else (lambda c=cmd: self._send(c))
            tk.Button(bar, text=label, command=act,
                      bg=bg, fg=FG,
                      activebackground=dimcol(bg, 1.3),
                      activeforeground=FG,
                      font=("Segoe UI", 9, "bold") if bg == BTN_PURPLE else ("Segoe UI", 9),
                      relief="flat", bd=0, cursor="hand2",
                      padx=14, pady=4).pack(side="left", padx=(0, 6))

    # ── Serial log ────────────────────────────────────────────────────────────
    def _build_log(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(hdr, text="Log Serial", fg=FG, bg=BG,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Button(hdr, text="Bersihkan Log", command=self._clear_log,
                  bg=BG_INPUT, fg=FG_DIM, activebackground=BORDER,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  cursor="hand2", padx=10, pady=2).pack(side="right")

        lf = tk.Frame(self, bg=BG_PANEL,
                      highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        self.log = tk.Text(lf, bg=BG_PANEL, fg="#aaaacc",
                           font=("Cascadia Code", 8),
                           state="disabled", relief="flat",
                           insertbackground=FG,
                           selectbackground=BG_INPUT,
                           padx=8, pady=6)
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self.log.tag_config("tx",   foreground="#7c9cfc")
        self.log.tag_config("rx",   foreground="#7ddc96")
        self.log.tag_config("sw",   foreground="#e59400")
        self.log.tag_config("err",  foreground="#ff6b6b")
        self.log.tag_config("info", foreground="#bc8cff")
        self.log.tag_config("ts",   foreground="#555577")

    # ── Ports ─────────────────────────────────────────────────────────────────
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        self.port_var.set(ports[0] if ports else "")

    # ── Connect / Disconnect ──────────────────────────────────────────────────
    def _toggle_connect(self):
        if self.ser and self.ser.is_open:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_var.get()
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            baud = BAUD_DEFAULT
        try:
            self.ser = serial.Serial(port, baud, timeout=0.1)
            self._running = True
            threading.Thread(target=self._rx_thread, daemon=True).start()
            self._set_status(True)
            self._log(f"Koneksi berhasil: {port} @ {baud} baud\n", "info")
            self._set_btns_state("normal")
        except serial.SerialException as e:
            self._log(f"Gagal connect: {e}\n", "err")

    def _disconnect(self):
        self._running = False
        if self.ser:
            self.ser.close()
            self.ser = None
        self._set_status(False)
        self._log("Koneksi diputus.\n", "info")
        self._set_btns_state("disabled")

    def _set_status(self, connected: bool):
        if connected:
            col, text, btn_txt, btn_bg = "#4dffaa", " Terhubung", "Disconnect", BTN_RED
        else:
            col, text, btn_txt, btn_bg = FG_RED, " Tidak Terhubung", "Connect", BTN_PURPLE
        self._status_dot.configure(fg=col)
        self._status_lbl.configure(fg=col, text=text)
        self._btn_conn.configure(text=btn_txt, bg=btn_bg,
                                 activebackground=dimcol(btn_bg, 1.2))

    # ── RX Thread ─────────────────────────────────────────────────────────────
    def _rx_thread(self):
        buf = ""
        while self._running and self.ser and self.ser.is_open:
            try:
                d = self.ser.read(256).decode("utf-8", errors="replace")
                if d:
                    buf += d
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        self.rq.put(line.strip())
            except serial.SerialException:
                break
            time.sleep(0.005)

    # ── Poll ──────────────────────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                self._process(self.rq.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _process(self, line: str):
        for i in range(2):
            tag = f"SW{i+1}"
            if f"[{tag}] PRESSED" in line:
                self._upd_sw(i, True);  self._log(f"{line}\n", "sw"); return
            elif f"[{tag}] RELEASED" in line:
                self._upd_sw(i, False); self._log(f"{line}\n", "sw"); return
        for i in range(4):
            if line.strip() == f"LED{i+1} ON":
                self._upd_led(i, True);  self._log(f"{line}\n", "rx"); return
            elif line.strip() == f"LED{i+1} OFF":
                self._upd_led(i, False); self._log(f"{line}\n", "rx"); return
        self._log(f"{line}\n", "rx")

    # ── LED actions ───────────────────────────────────────────────────────────
    def _led_on(self, i):  self._send(f"LED{i+1}_ON")
    def _led_off(self, i): self._send(f"LED{i+1}_OFF")
    def _all_on(self):     [self._led_on(i)  for i in range(4)]
    def _all_off(self):    [self._led_off(i) for i in range(4)]

    def _upd_led(self, i, on: bool):
        self.led_state[i] = on
        self._led_circles[i].set_on(on)

    # ── Switch ────────────────────────────────────────────────────────────────
    def _upd_sw(self, i, pressed: bool):
        self._sw_circles[i].set_on(pressed)
        if pressed:
            self._sw_state_lbl[i].configure(text="PRESSED", fg=SW_COLOR)
        else:
            self._sw_state_lbl[i].configure(text="RELEASED", fg=FG_DIM)

    # ── Send ──────────────────────────────────────────────────────────────────
    def _send(self, cmd: str):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((cmd + "\n").encode())
                self._log(f"\u2192 {cmd}\n", "tx")
            except serial.SerialException as e:
                self._log(f"Error: {e}\n", "err")
        else:
            self._log("Koneksi serial terputus.\n", "err")

    def _send_cmd(self):
        cmd = self.cmd_var.get().strip()
        if cmd:
            self._send(cmd)
            self.cmd_var.set("")

    # ── Log ───────────────────────────────────────────────────────────────────
    def _log(self, text: str, tag="rx"):
        self.log.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] ", "ts")
        self.log.insert("end", text, tag)
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 800:
            self.log.delete("1.0", f"{lines - 800}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ── Button state ──────────────────────────────────────────────────────────
    def _set_btns_state(self, state):
        for b in self._led_on_btns + self._led_off_btns + self._led_hold_btns:
            b.configure(state=state)

    # ── Close ─────────────────────────────────────────────────────────────────
    def on_close(self):
        self._running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.destroy()


if __name__ == "__main__":
    app = STM32Monitor()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
