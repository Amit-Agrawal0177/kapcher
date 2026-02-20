import cv2
import sys
from collections import deque
import time
import datetime
import requests
import threading
import os
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
from PIL import Image, ImageDraw, ImageFont, ImageTk
import io
import socket
import math

APP_PATH = os.path.join(os.getenv("LOCALAPPDATA"), "Kapcher")
os.makedirs(APP_PATH, exist_ok=True)

VIDEO_FOLDER = os.path.join(APP_PATH, "Videos")
os.makedirs(VIDEO_FOLDER, exist_ok=True)

print("Uploads folder:", VIDEO_FOLDER)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

CONFIG_FILE  = os.path.join(APP_PATH, "config.json")

SETTINGS_PASSWORD = "1"
LOGO_PATH = "logo.png"

DEFAULT_CONFIG = {
    "workstation_name": "",
    "rtsp_url": "",
    "frame_rate": 30,
    "pre_buffer_duration": 5,
    "post_buffer_duration": 5,
    "video_quality": "High",
    "video_save_path": "Videos",
    "api_base": "http://192.168.0.135:27189",
    "system_ip": "",
    "ws_id": 0,
}

# ── Premium dark industrial palette ──────────
C = {
    "bg":           "#0d1117",   # near-black base
    "bg2":          "#161b22",   # panel background
    "bg3":          "#1c2230",   # elevated surface
    "surface":      "#21262d",   # card surface
    "border":       "#30363d",   # subtle border
    "border2":      "#3d4450",   # active border
    "accent":       "#10b981",   # emerald green
    "accent2":      "#059669",   # deep green
    "accent3":      "#34d399",   # bright mint
    "accent_dim":   "#064e3b",   # very dark green
    "warn":         "#f59e0b",   # amber
    "danger":       "#ef4444",   # red
    "red_dim":      "#7f1d1d",   # dark red
    "text":         "#e6edf3",   # primary text
    "text2":        "#8b949e",   # secondary text
    "text3":        "#484f58",   # muted text
    "rec":          "#ff3b55",   # recording red
    "rec_dim":      "#4a0011",   # dark recording
    "green_glow":   "#052e16",   # deep green bg
    "input_bg":     "#0d1117",   # input background
    "input_border": "#30363d",   # input border
    "cam_bg":       "#080c10",   # camera area bg
    "overlay":      "#000000cc", # semi-transparent
}

FONTS = {
    "mono":    ("Consolas", 10),
    "mono_sm": ("Consolas", 9),
    "mono_lg": ("Consolas", 13, "bold"),
    "ui":      ("Segoe UI", 10),
    "ui_sm":   ("Segoe UI", 9),
    "ui_bold": ("Segoe UI", 10, "bold"),
    "ui_lg":   ("Segoe UI", 12, "bold"),
    "ui_xl":   ("Segoe UI", 15, "bold"),
    "ui_hd":   ("Segoe UI", 20, "bold"),
    "display": ("Segoe UI", 28, "bold"),
    "scan":    ("Consolas", 18, "bold"),
    "big":     ("Consolas", 32, "bold"),
}

def get_system_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def parse_api_base(api_base):
    """Parse api_base into (protocol, ip, port)"""
    try:
        # http://192.168.0.135:27189
        parts = api_base.replace("http://", "").replace("https://", "")
        proto = "https" if api_base.startswith("https") else "http"
        if ":" in parts:
            ip_part, port_part = parts.rsplit(":", 1)
        else:
            ip_part = parts
            port_part = "80"
        return proto, ip_part.strip("/"), port_part.strip("/")
    except:
        return "http", "192.168.0.135", "27189"

# ─────────────────────────────────────────────
#  GLOBALS
# ─────────────────────────────────────────────

config = load_config() or DEFAULT_CONFIG.copy()
pre_buffer = deque(maxlen=config.get('pre_buffer_duration', 5) * config.get('frame_rate', 30))
recording = True
cap = None
frame_width = 640
frame_height = 480
barcode_value = None
is_recording = False
current_packaging_id = None
frame_queue = Queue(maxsize=300)
app_running = True
current_writer = None
current_output_file = None
writer_lock = threading.Lock()
task_lock = threading.Lock()
last_barcode_1 = ""
last_barcode_2 = ""
gui = None
dialog_open = False

# Live preview shared frame
preview_frame = None
preview_lock = threading.Lock()

# ─────────────────────────────────────────────
#  WIDGET HELPERS
# ─────────────────────────────────────────────

def mk_entry(parent, width=30, show=None, font=None, **kw):
    opts = dict(
        font=font or FONTS["mono"],
        bg=C["input_bg"],
        fg=C["text"],
        insertbackground=C["accent"],
        relief=tk.FLAT, bd=0,
        width=width,
        highlightthickness=1,
        highlightbackground=C["input_border"],
        highlightcolor=C["accent"],
    )
    if show:
        opts["show"] = show
    opts.update(kw)
    e = tk.Entry(parent, **opts)
    e.bind("<FocusIn>",  lambda ev, w=e: w.config(highlightbackground=C["accent"], highlightthickness=2))
    e.bind("<FocusOut>", lambda ev, w=e: w.config(highlightbackground=C["input_border"], highlightthickness=1))
    return e

def mk_btn(parent, text, cmd, color=None, fg=None, px=18, py=8, hover=True, font=None):
    bg = color or C["accent"]
    btn = tk.Button(
        parent, text=text, command=cmd,
        font=font or FONTS["ui_bold"],
        bg=bg,
        fg=fg or C["bg"],
        activebackground=C["accent3"] if hover else bg,
        activeforeground=C["bg"],
        relief=tk.FLAT, bd=0,
        padx=px, pady=py,
        cursor="hand2",
    )
    if hover:
        def on_enter(e, b=btn):
            b.config(bg=C["accent3"])
        def on_leave(e, b=btn, c=bg):
            b.config(bg=c)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
    return btn

def mk_label(parent, text, font=None, fg=None, bg=None, **kw):
    return tk.Label(parent, text=text,
                    font=font or FONTS["ui"],
                    fg=fg or C["text"],
                    bg=bg or C["bg2"],
                    **kw)

class SectionHeader(tk.Frame):
    """Styled section header with left accent bar"""
    def __init__(self, parent, title, bg=None, icon="", **kw):
        bg = bg or C["bg2"]
        super().__init__(parent, bg=bg, **kw)
        tk.Frame(self, bg=C["accent"], width=3).pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        if icon:
            tk.Label(self, text=icon, font=("Segoe UI", 10),
                     bg=bg, fg=C["accent"]).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(self, text=title,
                 font=FONTS["ui_sm"],
                 bg=bg, fg=C["text2"]).pack(side=tk.LEFT)

class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=None, **kw):
        bg = bg or C["bg2"]
        super().__init__(parent, bg=bg, **kw)
        cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(self, orient=tk.VERTICAL, command=cv.yview)
        sb.configure(bg=C["bg2"], troughcolor=C["bg"], relief=tk.FLAT)
        self.inner = tk.Frame(cv, bg=bg)
        self.inner.bind("<Configure>",
            lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=self.inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        cv.bind_all("<MouseWheel>",
            lambda e: cv.yview_scroll(int(-1 * (e.delta / 120)), "units"))

def _center_win(win, parent):
    def _do():
        win.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - win.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")
    win.after(20, _do)

def divider(parent, bg=None, pady=8):
    f = tk.Frame(parent, bg=bg or C["bg2"])
    tk.Frame(f, bg=C["border"], height=1).pack(fill=tk.X)
    f.pack(fill=tk.X, pady=pady)
    return f

# ─────────────────────────────────────────────
#  SPLASH SCREEN
# ─────────────────────────────────────────────

class SplashScreen:
    def __init__(self, parent, duration=3.0, logo_path=None):
        self.root = tk.Toplevel(parent)
        self.duration = duration
        self.root.attributes('-topmost', True)
        self.root.geometry("560x380")
        self.root.configure(bg=C["bg"])
        self.root.overrideredirect(True)

        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 280
        y = (self.root.winfo_screenheight() // 2) - 190
        self.root.geometry(f"+{x}+{y}")

        # Top accent bar
        tk.Frame(self.root, bg=C["accent"], height=3).pack(fill=tk.X)

        # Main content
        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=48, pady=40)

        # Icon + Brand
        brand = tk.Frame(main, bg=C["bg"])
        brand.pack(expand=True)

        # Camera icon (unicode)
        tk.Label(brand, text="⬛", font=("Segoe UI", 60),
                 bg=C["bg"], fg=C["bg3"]).place(x=80, y=-10)
        tk.Label(brand, text="◉", font=("Segoe UI", 48),
                 bg=C["bg"], fg=C["accent"]).pack()

        tk.Label(brand, text="KAPCHER",
                 font=("Consolas", 36, "bold"),
                 bg=C["bg"], fg=C["text"]).pack(pady=(4, 0))
        tk.Label(brand, text="PROFESSIONAL VIDEO RECORDING",
                 font=("Consolas", 9),
                 bg=C["bg"], fg=C["text3"]).pack()

        # Progress bar
        prog_frame = tk.Frame(main, bg=C["bg"])
        prog_frame.pack(fill=tk.X, pady=(30, 0))

        self.prog_bg = tk.Canvas(prog_frame, height=2, bg=C["border"],
                                  highlightthickness=0, bd=0)
        self.prog_bg.pack(fill=tk.X)
        self.prog_bar = self.prog_bg.create_rectangle(0, 0, 0, 2, fill=C["accent"], width=0)

        self.status_lbl = tk.Label(main, text="Initializing system…",
                                    font=FONTS["mono_sm"],
                                    bg=C["bg"], fg=C["text2"])
        self.status_lbl.pack(pady=(8, 0))

        # Bottom bar
        tk.Frame(self.root, bg=C["accent2"], height=3).pack(fill=tk.X, side=tk.BOTTOM)

        self.is_running = True
        self.start_time = time.time()
        self._animate()

        messages = ["Loading camera modules…", "Connecting to services…",
                    "Starting video engine…", "Ready."]
        for i, msg in enumerate(messages):
            self.root.after(int(duration * 250 * (i + 1)), lambda m=msg: self._set_status(m))

        self.root.after(int(duration * 1000), self.close)

    def _set_status(self, msg):
        try:
            if self.root.winfo_exists() and self.is_running:
                self.status_lbl.config(text=msg)
        except:
            pass

    def _animate(self):
        if not self.is_running:
            return
        try:
            if self.root.winfo_exists():
                elapsed = time.time() - self.start_time
                fraction = min(elapsed / self.duration, 1.0)
                w = self.prog_bg.winfo_width()
                self.prog_bg.coords(self.prog_bar, 0, 0, w * fraction, 2)
                self.root.after(30, self._animate)
        except:
            pass

    def close(self):
        try:
            self.is_running = False
            self.root.destroy()
        except:
            pass

# ─────────────────────────────────────────────
#  FIRST-RUN CONFIG GUI
# ─────────────────────────────────────────────

class ConfigSetupGUI:
    def __init__(self, root, on_complete):
        self.root = root
        self.on_complete = on_complete
        self.entries = {}

        root.title("Kapcher — First Run Setup")
        root.geometry("620x820")
        root.configure(bg=C["bg2"])
        root.resizable(True, True)

        # Top accent
        tk.Frame(root, bg=C["accent"], height=3).pack(fill=tk.X)

        sf = ScrollFrame(root, bg=C["bg2"])
        sf.pack(fill=tk.BOTH, expand=True)
        w = sf.inner
        w.configure(padx=40, pady=28)

        # Header
        tk.Label(w, text="KAPCHER", font=("Consolas", 22, "bold"),
                 bg=C["bg2"], fg=C["accent"]).pack(anchor=tk.W)
        tk.Label(w, text="First-time Workstation Setup",
                 font=FONTS["ui_lg"], bg=C["bg2"], fg=C["text"]).pack(anchor=tk.W, pady=(2, 4))
        tk.Label(w, text="Configure your system once and get recording.",
                 font=FONTS["ui_sm"], bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W)
        divider(w, bg=C["bg2"], pady=16)

        # Section: Identity
        SectionHeader(w, "WORKSTATION", bg=C["bg2"], icon="◈").pack(anchor=tk.W, pady=(0, 10))
        self._field(w, "Workstation Name", "workstation_name", "e.g. Line-A Station 3")
        self._field(w, "Camera RTSP URL", "rtsp_url", "rtsp://user:pass@ip:554/stream  or  0")

        divider(w, bg=C["bg2"], pady=14)

        # Section: Server
        SectionHeader(w, "SERVER CONNECTION", bg=C["bg2"], icon="◈").pack(anchor=tk.W, pady=(0, 10))

        # Server IP + Port as separate fields
        srv_row = tk.Frame(w, bg=C["bg2"])
        srv_row.pack(fill=tk.X, pady=(0, 14))

        ip_grp = tk.Frame(srv_row, bg=C["bg2"])
        ip_grp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        tk.Label(ip_grp, text="Server IP", font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
        e_ip = mk_entry(ip_grp, width=24)
        e_ip.pack(fill=tk.X, ipady=9)
        self.entries["_server_ip"] = e_ip

        port_grp = tk.Frame(srv_row, bg=C["bg2"])
        port_grp.pack(side=tk.LEFT, fill=tk.X)
        tk.Label(port_grp, text="Port", font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
        e_port = mk_entry(port_grp, width=10)
        e_port.pack(fill=tk.X, ipady=9)
        self.entries["_server_port"] = e_port

        # Pre-fill from existing config
        existing = config.get("api_base", "http://192.168.0.135:27189")
        _, ex_ip, ex_port = parse_api_base(existing)
        e_ip.insert(0, ex_ip)
        e_port.insert(0, ex_port)

        divider(w, bg=C["bg2"], pady=14)

        # Section: Recording
        SectionHeader(w, "RECORDING PARAMETERS", bg=C["bg2"], icon="◈").pack(anchor=tk.W, pady=(0, 10))

        params_row = tk.Frame(w, bg=C["bg2"])
        params_row.pack(fill=tk.X, pady=(0, 14))
        for label, key, ph, width in [
            ("FPS", "frame_rate", "30", 8),
            ("Pre-Buffer (sec)", "pre_buffer_duration", "5", 8),
            ("Post-Buffer (sec)", "post_buffer_duration", "5", 8),
        ]:
            grp = tk.Frame(params_row, bg=C["bg2"])
            grp.pack(side=tk.LEFT, padx=(0, 16))
            tk.Label(grp, text=label, font=FONTS["ui_bold"],
                     bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
            e = mk_entry(grp, width=width)
            e.pack(ipady=9)
            val = config.get(key, "")
            if val:
                e.insert(0, str(val))
            elif ph:
                e.insert(0, ph)
            self.entries[key] = e

        # Quality
        tk.Label(w, text="Video Quality", font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(4, 8))
        self.quality_var = tk.StringVar(value=config.get('video_quality', 'High'))
        qr = tk.Frame(w, bg=C["bg2"])
        qr.pack(anchor=tk.W, pady=(0, 16))
        for q, res in [('Low', '480p'), ('Medium', '720p'), ('High', '1080p'), ('Ultra', '4K')]:
            rb = tk.Radiobutton(qr, text=f"  {q} / {res}  ",
                                variable=self.quality_var, value=q,
                                font=FONTS["ui_sm"],
                                bg=C["bg2"], fg=C["text2"],
                                selectcolor=C["accent_dim"],
                                activebackground=C["bg2"],
                                activeforeground=C["accent"],
                                indicatoron=0,
                                relief=tk.FLAT,
                                bd=1,
                                highlightthickness=1,
                                highlightbackground=C["border"],
                                cursor="hand2",
                                padx=10, pady=6)
            rb.pack(side=tk.LEFT, padx=(0, 6))

        # Save button
        bar = tk.Frame(root, bg=C["bg2"], padx=40, pady=16)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bar, bg=C["border"], height=1).pack(fill=tk.X, pady=(0, 14))

        btn_row = tk.Frame(bar, bg=C["bg2"])
        btn_row.pack(fill=tk.X)
        mk_btn(btn_row, "  ✓  Save & Launch  ", self._save,
               color=C["accent"], fg=C["bg"], py=11, px=22).pack(side=tk.LEFT, padx=(0, 10))
        mk_btn(btn_row, "  Cancel  ", root.quit,
               color=C["surface"], fg=C["text2"], py=11).pack(side=tk.LEFT)

    def _field(self, parent, label, key, placeholder=""):
        grp = tk.Frame(parent, bg=C["bg2"])
        grp.pack(fill=tk.X, pady=(0, 14))
        tk.Label(grp, text=label, font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
        e = mk_entry(grp, width=58)
        e.pack(fill=tk.X, ipady=9)
        val = config.get(key, "")
        if val:
            e.insert(0, str(val))
        elif placeholder:
            e.insert(0, placeholder)
            e.config(fg=C["text3"])
            def _in(ev, en=e, ph=placeholder):
                if en.get() == ph:
                    en.delete(0, tk.END)
                    en.config(fg=C["text"])
            def _out(ev, en=e, ph=placeholder):
                if not en.get():
                    en.insert(0, ph)
                    en.config(fg=C["text3"])
            e.bind('<FocusIn>', _in)
            e.bind('<FocusOut>', _out)
        self.entries[key] = e

    def _save(self):
        global config
        new = {}
        placeholder_keys = {"rtsp_url", "workstation_name"}

        for key, e in self.entries.items():
            if key.startswith("_"):
                continue
            v = e.get().strip()
            if not v or (key in {"rtsp_url", "workstation_name"} and
                         v in ["rtsp://user:pass@ip:554/stream  or  0",
                                "e.g. Line-A Station 3"]):
                messagebox.showerror("Missing",
                    f"Please fill in: {key.replace('_', ' ').title()}", parent=self.root)
                return
            if key in ['frame_rate', 'pre_buffer_duration', 'post_buffer_duration']:
                try:
                    v = int(v)
                    assert v > 0
                except:
                    messagebox.showerror("Invalid",
                        f"{key.replace('_', ' ').title()} must be a positive integer",
                        parent=self.root)
                    return
            new[key] = v

        # Concat server IP + port → api_base
        srv_ip   = self.entries["_server_ip"].get().strip()
        srv_port = self.entries["_server_port"].get().strip()
        if not srv_ip or not srv_port:
            messagebox.showerror("Missing", "Server IP and Port are required.", parent=self.root)
            return
        new["api_base"] = f"http://{srv_ip}:{srv_port}"

        new['video_quality']  = self.quality_var.get()
        new['video_save_path'] = config.get('video_save_path', 'Videos')
        new['system_ip'] = get_system_ip()

        ws_id = create_workstation_api(new)
        if ws_id is not None:
            new['ws_id'] = ws_id
            if save_config(new):
                config = new
                self.root.destroy()
                self.on_complete()
            else:
                messagebox.showerror("Error", "Failed to save configuration.", parent=self.root)
        else:
            messagebox.showerror("Error", "Failed to connect to server. Check IP/Port.", parent=self.root)

# ─────────────────────────────────────────────
#  SETTINGS DIALOG
# ─────────────────────────────────────────────

class SettingsDialog:
    def __init__(self, parent):
        self.parent = parent
        self._ask_password()

    def _make_win(self, title, w, h, resizable=False):
        global dialog_open
        dialog_open = True
        win = tk.Toplevel(self.parent)
        win.title(title)
        win.geometry(f"{w}x{h}")
        win.configure(bg=C["bg2"])
        win.resizable(resizable, resizable)
        _center_win(win, self.parent)

        def _close():
            global dialog_open
            dialog_open = False
            try:
                win.grab_release()
            except:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _close)
        win.after(30, lambda: (win.grab_set(), win.lift(), win.focus_force()))
        return win, _close

    def _ask_password(self):
        if is_recording:
            messagebox.showwarning(
                "Recording Active",
                "Settings cannot be changed while recording.\nFinish the current recording first.",
                parent=self.parent)
            return

        win, close = self._make_win("Kapcher — Authentication", 440, 280)
        tk.Frame(win, bg=C["accent"], height=3).pack(fill=tk.X)

        body = tk.Frame(win, bg=C["bg2"], padx=36, pady=28)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="SETTINGS ACCESS",
                 font=("Consolas", 14, "bold"),
                 bg=C["bg2"], fg=C["accent"]).pack(anchor=tk.W)
        tk.Label(body, text="Enter admin password to continue.",
                 font=FONTS["ui_sm"], bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(4, 20))

        pw = mk_entry(body, show="●", width=32)
        pw.pack(fill=tk.X, ipady=10)

        err = tk.Label(body, text="",
                        font=FONTS["ui_sm"], bg=C["bg2"], fg=C["danger"])
        err.pack(anchor=tk.W, pady=(6, 0))

        br = tk.Frame(body, bg=C["bg2"])
        br.pack(fill=tk.X, pady=(16, 0))

        def check():
            global dialog_open
            if pw.get() == SETTINGS_PASSWORD:
                dialog_open = False
                try:
                    win.grab_release()
                except:
                    pass
                win.destroy()
                self._open_settings()
            else:
                err.config(text="✗  Incorrect password.")
                pw.delete(0, tk.END)
                pw.focus_set()

        win.after(80, pw.focus_set)
        pw.bind('<Return>', lambda e: check())
        mk_btn(br, "  Unlock  ", check, color=C["accent"], fg=C["bg"], py=9).pack(side=tk.LEFT, padx=(0, 10))
        mk_btn(br, "  Cancel  ", close, color=C["surface"], fg=C["text2"], py=9).pack(side=tk.LEFT)

    def _open_settings(self):
        global config
        config = load_config() or DEFAULT_CONFIG.copy()
        win, close = self._make_win("Kapcher — Settings", 640, 820, resizable=True)
        tk.Frame(win, bg=C["accent"], height=3).pack(fill=tk.X)

        sf = ScrollFrame(win, bg=C["bg2"])
        sf.pack(fill=tk.BOTH, expand=True)
        w = sf.inner
        w.configure(padx=38, pady=26)

        tk.Label(w, text="SETTINGS", font=("Consolas", 18, "bold"),
                 bg=C["bg2"], fg=C["accent"]).pack(anchor=tk.W)
        tk.Label(w, text="Changes to RTSP or FPS take effect on restart.",
                 font=FONTS["ui_sm"], bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(3, 0))

        divider(w, bg=C["bg2"], pady=14)

        # ── Workstation ──────────────────────
        SectionHeader(w, "WORKSTATION", bg=C["bg2"], icon="◈").pack(anchor=tk.W, pady=(0, 10))

        self._ents = {}
        for label, key in [("Workstation Name", "workstation_name"),
                            ("Camera RTSP URL",  "rtsp_url")]:
            grp = tk.Frame(w, bg=C["bg2"])
            grp.pack(fill=tk.X, pady=(0, 12))
            tk.Label(grp, text=label, font=FONTS["ui_bold"],
                     bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
            e = mk_entry(grp, width=58)
            e.pack(fill=tk.X, ipady=9)
            v = config.get(key, "")
            if v:
                e.insert(0, str(v))
            self._ents[key] = e

        divider(w, bg=C["bg2"], pady=14)

        # ── Server ────────────────────────────
        SectionHeader(w, "SERVER CONNECTION", bg=C["bg2"], icon="◈").pack(anchor=tk.W, pady=(0, 10))

        srv_row = tk.Frame(w, bg=C["bg2"])
        srv_row.pack(fill=tk.X, pady=(0, 14))

        _, ex_ip, ex_port = parse_api_base(config.get("api_base", "http://192.168.0.135:27189"))

        ip_grp = tk.Frame(srv_row, bg=C["bg2"])
        ip_grp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        tk.Label(ip_grp, text="Server IP", font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
        self._e_ip = mk_entry(ip_grp, width=24)
        self._e_ip.pack(fill=tk.X, ipady=9)
        self._e_ip.insert(0, ex_ip)

        port_grp = tk.Frame(srv_row, bg=C["bg2"])
        port_grp.pack(side=tk.LEFT)
        tk.Label(port_grp, text="Port", font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
        self._e_port = mk_entry(port_grp, width=10)
        self._e_port.pack(fill=tk.X, ipady=9)
        self._e_port.insert(0, ex_port)

        divider(w, bg=C["bg2"], pady=14)

        # ── Recording ─────────────────────────
        SectionHeader(w, "RECORDING PARAMETERS", bg=C["bg2"], icon="◈").pack(anchor=tk.W, pady=(0, 10))

        params_row = tk.Frame(w, bg=C["bg2"])
        params_row.pack(fill=tk.X, pady=(0, 14))
        for label, key in [("FPS", "frame_rate"),
                            ("Pre-Buffer (sec)", "pre_buffer_duration"),
                            ("Post-Buffer (sec)", "post_buffer_duration")]:
            grp = tk.Frame(params_row, bg=C["bg2"])
            grp.pack(side=tk.LEFT, padx=(0, 16))
            tk.Label(grp, text=label, font=FONTS["ui_bold"],
                     bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(0, 4))
            e = mk_entry(grp, width=8)
            e.pack(ipady=9)
            v = config.get(key, "")
            if v:
                e.insert(0, str(v))
            self._ents[key] = e

        # Quality
        tk.Label(w, text="Video Quality", font=FONTS["ui_bold"],
                 bg=C["bg2"], fg=C["text2"]).pack(anchor=tk.W, pady=(8, 8))
        self._qv = tk.StringVar(value=config.get('video_quality', 'High'))
        qr = tk.Frame(w, bg=C["bg2"])
        qr.pack(anchor=tk.W, pady=(0, 8))
        for q, res in [('Low', '480p'), ('Medium', '720p'), ('High', '1080p'), ('Ultra', '4K')]:
            rb = tk.Radiobutton(qr, text=f"  {q} / {res}  ",
                                variable=self._qv, value=q,
                                font=FONTS["ui_sm"],
                                bg=C["bg2"], fg=C["text2"],
                                selectcolor=C["accent_dim"],
                                activebackground=C["bg2"],
                                activeforeground=C["accent"],
                                indicatoron=0, relief=tk.FLAT, bd=1,
                                highlightthickness=1,
                                highlightbackground=C["border"],
                                cursor="hand2",
                                padx=10, pady=6)
            rb.pack(side=tk.LEFT, padx=(0, 6))

        # Save bar
        bar = tk.Frame(win, bg=C["bg2"], padx=38, pady=16)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bar, bg=C["border"], height=1).pack(fill=tk.X, pady=(0, 14))

        def do_save():
            global config, dialog_open
            new = {}
            for key, e in self._ents.items():
                v = e.get().strip()
                if not v:
                    messagebox.showerror("Missing",
                        f"Please fill in: {key.replace('_', ' ').title()}", parent=win)
                    return
                if key in ['frame_rate', 'pre_buffer_duration', 'post_buffer_duration']:
                    try:
                        v = int(v)
                        assert v > 0
                    except:
                        messagebox.showerror("Invalid",
                            f"{key.replace('_', ' ').title()} must be a positive integer",
                            parent=win)
                        return
                new[key] = v

            # Concat IP + port
            srv_ip   = self._e_ip.get().strip()
            srv_port = self._e_port.get().strip()
            if not srv_ip or not srv_port:
                messagebox.showerror("Missing", "Server IP and Port are required.", parent=win)
                return
            new["api_base"] = f"http://{srv_ip}:{srv_port}"

            new['video_quality']   = self._qv.get()
            new['video_save_path'] = config.get('video_save_path', 'Videos')
            new['system_ip']       = get_system_ip()

            r = update_workstation_api(config['ws_id'], new)
            if r is True:
                new['ws_id'] = config['ws_id']
                if save_config(new):
                    config = new
                    dialog_open = False
                    try:
                        win.grab_release()
                    except:
                        pass
                    win.destroy()
                    messagebox.showinfo("Saved",
                        "Configuration saved!\nRTSP / FPS changes take effect on restart.",
                        parent=self.parent)
                else:
                    messagebox.showerror("Error", "Failed to save configuration.", parent=win)
            else:
                messagebox.showerror("Error", str(r), parent=win)

        btn_row = tk.Frame(bar, bg=C["bg2"])
        btn_row.pack(fill=tk.X)
        mk_btn(btn_row, "  ✓  Save Changes  ", do_save,
               color=C["accent"], fg=C["bg"], py=11, px=20).pack(side=tk.LEFT, padx=(0, 10))
        mk_btn(btn_row, "  Cancel  ", close,
               color=C["surface"], fg=C["text2"], py=11).pack(side=tk.LEFT)

# ─────────────────────────────────────────────
#  MAIN GUI
# ─────────────────────────────────────────────

class VideoRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Kapcher — {config.get('workstation_name', 'Workstation')}")
        self.root.geometry("1340x860")
        self.root.configure(bg=C["bg"])
        self.root.minsize(1100, 720)
        self._blink_state = True
        self._blink_job   = None
        self._preview_job = None

        # Treeview style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Pkg.Treeview',
            background=C["bg3"], foreground=C["text"],
            fieldbackground=C["bg3"], rowheight=30,
            font=FONTS["ui_sm"], borderwidth=0)
        style.configure('Pkg.Treeview.Heading',
            background=C["surface"], foreground=C["text2"],
            font=FONTS["ui_bold"], relief=tk.FLAT, borderwidth=0)
        style.map('Pkg.Treeview',
            background=[('selected', C["accent_dim"])],
            foreground=[('selected', C["accent"])])
        style.configure('TScrollbar',
            background=C["bg3"], troughcolor=C["bg"], arrowcolor=C["text3"])

        self._build()
        self.root.bind_all("<Tab>", lambda e: self.barcode_entry.focus_set())
        self.root.after(100, lambda: self.barcode_entry.focus_set())
        self.tick_id = None
        self._tick()
        self._start_preview_loop()

    # ── Layout ───────────────────────────────

    def _build(self):
        root = self.root
        root.columnconfigure(0, weight=0)   # left panel fixed
        root.columnconfigure(1, weight=1)   # right content
        root.rowconfigure(1, weight=1)

        # Top accent line
        tk.Frame(root, bg=C["accent"], height=2).grid(
            row=0, column=0, columnspan=2, sticky="ew")

        # Header
        self._build_header(root)

        # Left panel
        self._build_left_panel(root)

        # Right panel
        self._build_right_panel(root)

    def _build_header(self, root):
        hdr = tk.Frame(root, bg=C["bg2"], height=60)
        hdr.grid(row=1, column=0, columnspan=2, sticky="ew")
        hdr.grid_propagate(False)
        root.rowconfigure(1, weight=0)

        # Left vertical accent
        tk.Frame(hdr, bg=C["accent"], width=4).pack(side=tk.LEFT, fill=tk.Y)

        # Brand
        brand = tk.Frame(hdr, bg=C["bg2"])
        brand.pack(side=tk.LEFT, padx=(14, 0))
        tk.Label(brand, text="KAPCHER",
                 font=("Consolas", 18, "bold"),
                 bg=C["bg2"], fg=C["accent"]).pack(side=tk.LEFT)
        tk.Label(brand, text=f"  /  {config.get('workstation_name', 'Workstation')}",
                 font=("Consolas", 14),
                 bg=C["bg2"], fg=C["text3"]).pack(side=tk.LEFT)

        # Status pill
        self.header_status = tk.Label(hdr, text="● IDLE",
            font=FONTS["ui_bold"],
            bg=C["bg2"], fg=C["text3"], padx=14, pady=4)
        self.header_status.pack(side=tk.LEFT, padx=22)

        # Settings
        mk_btn(hdr, "⚙  Settings", self.open_settings,
               color=C["surface"], fg=C["text2"], py=7, px=14).pack(
            side=tk.RIGHT, padx=(0, 16), pady=0)

        # Barcode entry
        scan_frame = tk.Frame(hdr, bg=C["bg2"])
        scan_frame.pack(side=tk.RIGHT, padx=(0, 20))

        tk.Label(scan_frame, text="SCAN  ›",
                 font=FONTS["mono_sm"],
                 bg=C["bg2"], fg=C["text3"]).pack(side=tk.LEFT, padx=(0, 8))

        self.barcode_entry = tk.Entry(scan_frame,
            font=("Consolas", 15, "bold"),
            bg=C["bg"],
            fg=C["accent3"],
            insertbackground=C["accent"],
            relief=tk.FLAT, bd=0, width=28,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"])
        self.barcode_entry.pack(side=tk.LEFT, ipady=9, padx=(0, 0))
        self.barcode_entry.bind('<Return>', self.on_barcode_enter)
        self.barcode_entry.bind("<Tab>", lambda e: "break")
        self.barcode_entry.bind("<Shift-Tab>", lambda e: "break")

    def _build_left_panel(self, root):
        """Left panel: camera feed + config readout"""
        lp = tk.Frame(root, bg=C["bg2"], width=330)
        lp.grid(row=2, column=0, sticky="nsew", padx=(0, 0))
        lp.grid_propagate(False)
        root.rowconfigure(2, weight=1)
        lp.columnconfigure(0, weight=1)
        lp.rowconfigure(1, weight=1)  # camera feed expands

        # ── Camera Feed ──────────────────────
        cam_outer = tk.Frame(lp, bg=C["cam_bg"])
        cam_outer.grid(row=0, column=0, sticky="ew")

        # Header
        cam_hdr = tk.Frame(cam_outer, bg=C["cam_bg"])
        cam_hdr.pack(fill=tk.X, padx=10, pady=(8, 4))
        tk.Frame(cam_hdr, bg=C["accent"], width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(cam_hdr, text="  LIVE FEED",
                 font=FONTS["mono_sm"],
                 bg=C["cam_bg"], fg=C["text2"]).pack(side=tk.LEFT)
        self.cam_status_dot = tk.Label(cam_hdr, text="●",
                                        font=("Segoe UI", 8),
                                        bg=C["cam_bg"], fg=C["text3"])
        self.cam_status_dot.pack(side=tk.RIGHT)

        # Camera canvas
        self.cam_canvas = tk.Canvas(cam_outer, width=330, height=200,
                                     bg=C["cam_bg"],
                                     highlightthickness=0, bd=0)
        self.cam_canvas.pack(fill=tk.X, padx=0, pady=(2, 0))

        # Placeholder text on canvas
        self.cam_canvas.create_text(
            165, 100,
            text="◉  NO FEED",
            font=("Consolas", 12), fill=C["text3"],
            tags="placeholder")

        # REC overlay badge (hidden by default)
        self._rec_badge = tk.Frame(cam_outer, bg=C["rec_dim"], padx=8, pady=3)
        self._rec_dot_lbl = tk.Label(self._rec_badge, text="⏺ REC",
                                      font=FONTS["mono_sm"],
                                      bg=C["rec_dim"], fg=C["rec"])
        self._rec_dot_lbl.pack()

        # ── Camera Config Readout ────────────
        cfg_outer = tk.Frame(lp, bg=C["bg2"])
        cfg_outer.grid(row=1, column=0, sticky="nsew", pady=(0, 0))
        cfg_outer.columnconfigure(0, weight=1)

        # Scrollable config area
        cfg_scroll = tk.Frame(cfg_outer, bg=C["bg2"])
        cfg_scroll.pack(fill=tk.BOTH, expand=True)

        SectionHeader(cfg_scroll, "CAMERA CONFIG",
                      bg=C["bg2"], icon="◈").pack(fill=tk.X, padx=10, pady=(12, 8))

        self._cfg_rows = {}
        cfg_items = [
            ("rtsp_url",           "RTSP",      "url"),
            ("frame_rate",         "FPS",        "val"),
            ("video_quality",      "QUALITY",    "val"),
            ("pre_buffer_duration","PRE-BUF",    "sec"),
            ("post_buffer_duration","POST-BUF",  "sec"),
            ("api_base",           "SERVER",     "url"),
            ("system_ip",          "LOCAL IP",   "ip"),
            ("ws_id",              "WS-ID",      "id"),
        ]

        for key, label, kind in cfg_items:
            row = tk.Frame(cfg_scroll, bg=C["bg2"])
            row.pack(fill=tk.X, padx=10, pady=2)

            lbl = tk.Label(row, text=label,
                           font=("Consolas", 8),
                           bg=C["bg2"], fg=C["text3"],
                           width=9, anchor=tk.W)
            lbl.pack(side=tk.LEFT)

            val_text = str(config.get(key, "—"))
            if kind == "url" and len(val_text) > 28:
                val_text = "…" + val_text[-26:]

            val_lbl = tk.Label(row, text=val_text,
                                font=("Consolas", 8),
                                bg=C["bg2"], fg=C["accent"],
                                anchor=tk.W, wraplength=210, justify=tk.LEFT)
            val_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._cfg_rows[key] = val_lbl

            tk.Frame(cfg_scroll, bg=C["border"], height=1).pack(fill=tk.X, padx=10)

        # ── Status card ──────────────────────
        divider(cfg_scroll, bg=C["bg2"], pady=6)

        SectionHeader(cfg_scroll, "STATUS", bg=C["bg2"], icon="◈").pack(
            fill=tk.X, padx=10, pady=(0, 8))

        stat_row = tk.Frame(cfg_scroll, bg=C["bg2"])
        stat_row.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._status_dot = tk.Canvas(stat_row, width=10, height=10,
                                      bg=C["bg2"], highlightthickness=0)
        self._status_dot.pack(side=tk.LEFT, padx=(0, 8))
        self._sdot_oval = self._status_dot.create_oval(1, 1, 9, 9,
                                                         fill=C["text3"], outline="")
        self.status_label = tk.Label(stat_row, text="Waiting for barcode…",
                                      font=FONTS["ui_bold"],
                                      bg=C["bg2"], fg=C["text2"])
        self.status_label.pack(side=tk.LEFT)

        # ── Current session ──────────────────
        divider(cfg_scroll, bg=C["bg2"], pady=6)
        SectionHeader(cfg_scroll, "CURRENT SESSION", bg=C["bg2"], icon="◈").pack(
            fill=tk.X, padx=10, pady=(0, 8))

        self._sr = {}
        for key, lbl in [("pkg_id", "PKG-ID"), ("barcode1", "ORDER"),
                          ("barcode2", "B-CODE 2"), ("frames", "FRAMES")]:
            row = tk.Frame(cfg_scroll, bg=C["bg2"])
            row.pack(fill=tk.X, padx=10, pady=2)
            tk.Label(row, text=lbl,
                     font=("Consolas", 8),
                     bg=C["bg2"], fg=C["text3"],
                     width=9, anchor=tk.W).pack(side=tk.LEFT)
            v = tk.Label(row, text="—",
                          font=("Consolas", 9, "bold"),
                          bg=C["bg2"], fg=C["accent"],
                          anchor=tk.W)
            v.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._sr[key] = v
            tk.Frame(cfg_scroll, bg=C["border"], height=1).pack(fill=tk.X, padx=10)

        # ── Last scan ────────────────────────
        divider(cfg_scroll, bg=C["bg2"], pady=6)
        scan_card = tk.Frame(cfg_scroll, bg=C["bg2"])
        scan_card.pack(fill=tk.X, padx=10, pady=(0, 16))

        self.last_bc_lbl = tk.Label(scan_card, text="—",
                                     font=("Consolas", 20, "bold"),
                                     bg=C["bg2"], fg=C["accent"],
                                     wraplength=280, justify=tk.CENTER)
        self.last_bc_lbl.pack(expand=True, pady=(8, 2))
        self.scan_sub = tk.Label(scan_card,
                                  text="scan #1 → starts recording",
                                  font=("Consolas", 8),
                                  bg=C["bg2"], fg=C["text3"])
        self.scan_sub.pack(pady=(0, 8))

    def _build_right_panel(self, root):
        rp = tk.Frame(root, bg=C["bg"])
        rp.grid(row=2, column=1, sticky="nsew", padx=(0, 0))
        rp.columnconfigure(0, weight=1)
        rp.rowconfigure(1, weight=1)

        # ── Task table ──────────────────────
        tbl_header = tk.Frame(rp, bg=C["bg"])
        tbl_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        SectionHeader(tbl_header, "PACKAGING TASKS", bg=C["bg"], icon="◈").pack(side=tk.LEFT)
        self.task_count = tk.Label(tbl_header, text="0 records",
                                    font=FONTS["mono_sm"],
                                    bg=C["bg"], fg=C["text3"])
        self.task_count.pack(side=tk.RIGHT)

        tbl_frame = tk.Frame(rp, bg=C["border"], bd=1)
        tbl_frame.grid(row=1, column=0, sticky="nsew", padx=16)
        tbl_frame.columnconfigure(0, weight=1)
        tbl_frame.rowconfigure(0, weight=1)

        cols = ('ID', 'Order ID', 'Barcode 2', 'Status', 'Timestamp')
        self.task_tree = ttk.Treeview(tbl_frame, columns=cols,
                                       show='headings', style='Pkg.Treeview')
        for col, w in zip(cols, [80, 170, 170, 120, 190]):
            self.task_tree.heading(col, text=col.upper())
            self.task_tree.column(col, width=w, minwidth=60, anchor=tk.W)

        self.task_tree.tag_configure('recording', foreground=C["rec"])
        self.task_tree.tag_configure('uploading', foreground=C["warn"])
        self.task_tree.tag_configure('completed', foreground=C["accent"])
        self.task_tree.tag_configure('failed',    foreground=C["danger"])

        sb = ttk.Scrollbar(tbl_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=sb.set)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        # ── Activity Log ────────────────────
        log_frame = tk.Frame(rp, bg=C["bg"])
        log_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 12))

        log_hdr = tk.Frame(log_frame, bg=C["bg"])
        log_hdr.pack(fill=tk.X, pady=(0, 6))
        SectionHeader(log_hdr, "ACTIVITY LOG", bg=C["bg"], icon="◈").pack(side=tk.LEFT)

        self.log_text = tk.Text(log_frame, height=9,
            bg=C["bg2"],
            fg=C["text"],
            font=("Consolas", 9),
            relief=tk.FLAT, bd=0,
            insertbackground=C["accent"],
            padx=12, pady=10,
            state=tk.DISABLED,
            highlightthickness=1,
            highlightbackground=C["border"])
        self.log_text.pack(fill=tk.X)

        for tag, col in [("ok", C["accent"]), ("err", C["danger"]),
                          ("warn", C["warn"]), ("info", C["text2"])]:
            self.log_text.tag_configure(tag, foreground=col)

    # ── Preview Loop ─────────────────────────

    def _start_preview_loop(self):
        self._update_preview()

    def _update_preview(self):
        global preview_frame
        try:
            if not self.root.winfo_exists():
                return
            with preview_lock:
                frame = preview_frame

            w = self.cam_canvas.winfo_width()  or 330
            h = self.cam_canvas.winfo_height() or 200

            if frame is not None:
                # Convert BGR → RGB, resize to canvas
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img = img.resize((w, h), Image.Resampling.LANCZOS)

                # If recording, tint with subtle red overlay
                if is_recording:
                    overlay = Image.new("RGBA", img.size, (255, 0, 0, 18))
                    img = img.convert("RGBA")
                    img = Image.alpha_composite(img, overlay).convert("RGB")

                self._cam_photo = ImageTk.PhotoImage(img)
                self.cam_canvas.delete("all")
                self.cam_canvas.create_image(0, 0, anchor=tk.NW, image=self._cam_photo)

                # REC badge overlay when recording
                if is_recording:
                    self.cam_canvas.create_rectangle(
                        w - 70, 8, w - 6, 26,
                        fill=C["rec_dim"], outline=C["rec"], width=1)
                    self.cam_canvas.create_text(
                        w - 38, 17,
                        text="⏺  REC",
                        font=("Consolas", 8, "bold"),
                        fill=C["rec"])

                # Timestamp overlay
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.cam_canvas.create_text(
                    8, h - 8, anchor=tk.SW,
                    text=ts, font=("Consolas", 8),
                    fill=C["text3"])

                self.cam_status_dot.config(fg=C["accent"])
            else:
                # No feed — show placeholder
                self.cam_canvas.delete("all")
                self.cam_canvas.create_rectangle(
                    0, 0, w, h, fill=C["cam_bg"], outline="")
                self.cam_canvas.create_text(
                    w // 2, h // 2,
                    text="◉  NO FEED",
                    font=("Consolas", 12), fill=C["text3"])
                self.cam_status_dot.config(fg=C["text3"])

        except Exception as e:
            pass

        self._preview_job = self.root.after(40, self._update_preview)  # ~25 fps

    # ── Refresh config readout ────────────────

    def refresh_config_display(self):
        for key, lbl in self._cfg_rows.items():
            val = str(config.get(key, "—"))
            if key in ("rtsp_url", "api_base") and len(val) > 28:
                val = "…" + val[-26:]
            lbl.config(text=val)

    # ── Public API ───────────────────────────

    def open_settings(self):
        SettingsDialog(self.root)

    def on_barcode_enter(self, event):
        global barcode_value, last_barcode_1, last_barcode_2
        code = self.barcode_entry.get().strip()
        if code:
            barcode_value = code
            if not is_recording:
                last_barcode_1 = code
                self.last_bc_lbl.configure(text=code, fg=C["accent3"])
                self.scan_sub.configure(text="scan #1 received — starting…", fg=C["accent"])
            else:
                last_barcode_2 = code
                self.last_bc_lbl.configure(text=code, fg=C["warn"])
                self.scan_sub.configure(text="scan #2 received — stopping…", fg=C["warn"])
            self.barcode_entry.delete(0, tk.END)
            self.log(f"Barcode scanned: {code}", "info")
            self.barcode_entry.focus_set()

    def update_status(self, text, state="idle"):
        cols = {
            "idle":       C["text2"],
            "recording":  C["rec"],
            "processing": C["warn"],
            "error":      C["danger"],
        }
        col = cols.get(state, C["text2"])
        self.status_label.configure(text=text, fg=col)
        self._status_dot.itemconfig(self._sdot_oval, fill=col)

        pills = {
            "idle":       ("● IDLE",         C["text3"]),
            "recording":  ("⏺  REC",         C["rec"]),
            "processing": ("⟳  PROCESSING",  C["warn"]),
            "error":      ("✗  ERROR",        C["danger"]),
        }
        pt, pc = pills.get(state, ("● IDLE", C["text3"]))
        self.header_status.configure(text=pt, fg=pc)

        if state == "recording":
            self._start_blink()
        else:
            self._stop_blink()

    def _start_blink(self):
        self._stop_blink()
        self.blink_state = False
        self._do_blink()

    def _do_blink(self):
        if self.root.winfo_exists():
            self.blink_state = not self.blink_state
            self.header_status.configure(fg=C["rec"] if self.blink_state else C["bg2"])
            self._blink_job = self.root.after(600, self._do_blink)

    def _stop_blink(self):
        if self._blink_job:
            self.root.after_cancel(self._blink_job)
            self._blink_job = None

    def update_current_info(self, packaging_id=None, barcode1=None,
                             barcode2=None, frames=None):
        for key, val in [("pkg_id", packaging_id), ("barcode1", barcode1),
                          ("barcode2", barcode2),   ("frames",   frames)]:
            if val is not None:
                self._sr[key].configure(text=str(val))

    def add_task(self, td):
        tag = td.get('status', '').lower()
        vals = (td['id'], td.get('barcode1', '—'), td.get('barcode2', '—'),
                td['status'], td['time'])
        with task_lock:
            for item in self.task_tree.get_children():
                if self.task_tree.item(item)['values'][0] == td['id']:
                    self.task_tree.item(item, values=vals, tags=(tag,))
                    return
            self.task_tree.insert('', 0, values=vals, tags=(tag,))
            n = len(self.task_tree.get_children())
            self.task_count.configure(text=f"{n} record{'s' if n != 1 else ''}")

    def log(self, msg, tag="ok"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        ic = {"ok": "✓", "err": "✗", "warn": "⚠", "info": "›"}.get(tag, "›")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}]  {ic}  {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _tick(self):
        if not dialog_open:
            try:
                fw = self.root.focus_get()
                if fw == self.root or fw is None:
                    self.barcode_entry.focus_set()
            except Exception:
                pass
        self.tick_id = self.root.after(300, self._tick)

# ─────────────────────────────────────────────
#  API CALLS
# ─────────────────────────────────────────────

def create_workstation_api(cfg):
    try:
        res = requests.post(f"{cfg['api_base']}/api/workstation/create",
                            json=cfg, timeout=10)
        if res.status_code == 201:
            wid = res.json()["workstation_id"]
            print(f"workstation created: {wid}")
            return wid
        print(f"Create failed: {res.text}")
        return None
    except Exception as e:
        print(f"API Error: {e}")
        return None

def update_workstation_api(ws_id, cfg):
    try:
        requests.put(f"{cfg['api_base']}/api/workstation/update/{ws_id}",
                     json=cfg, timeout=10)
        print(f"workstation updated: {ws_id}")
        return True
    except Exception as e:
        print(f"Update error: {e}")
        return f"Update error: {e}"

def create_packaging_api(barcode1):
    try:
        res = requests.post(f"{config.get('api_base')}/api/packaging/create",
                            json={"bar_code_1": barcode1, "ws_id": config['ws_id']},
                            timeout=10)
        if res.status_code == 201:
            pid = res.json()["packaging_id"]
            gui.log(f"Packaging created: {pid}", "ok")
            gui.add_task({'id': pid, 'barcode1': barcode1, 'status': 'Recording',
                          'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return pid
        gui.log(f"Create failed: {res.text}", "err")
        return None
    except Exception as e:
        gui.log(f"API Error: {e}", "err")
        return None

def update_packaging_api(packaging_id, barcode2):
    try:
        requests.put(f"{config.get('api_base')}/api/packaging/update/{packaging_id}",
                     json={"bar_code_2": barcode2,
                           "end_time": datetime.datetime.now().isoformat()},
                     timeout=10)
        gui.log(f"Packaging updated: {packaging_id}", "ok")
        gui.add_task({'id': packaging_id, 'barcode2': barcode2, 'status': 'Uploading',
                      'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        gui.log(f"Update error: {e}", "err")

def upload_video_api(packaging_id, video_path):
    try:
        gui.log(f"Uploading video for {packaging_id}…", "warn")
        with open(video_path, "rb") as f:
            res = requests.post(
                f"{config.get('api_base')}/api/packaging/upload-video/{packaging_id}",
                files={"video": f}, timeout=120)
        if res.status_code == 200:
            gui.log(f"Video uploaded: {packaging_id}", "ok")
            gui.add_task({'id': packaging_id, 'status': 'Completed',
                          'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return True
        gui.log(f"Upload failed: {res.text}", "err")
        return False
    except Exception as e:
        gui.log(f"Upload error: {e}", "err")
        return False

# ─────────────────────────────────────────────
#  FRAME WRITER THREAD
# ─────────────────────────────────────────────

def frame_writer_thread():
    while app_running:
        try:
            try:
                fd = frame_queue.get(timeout=1)
            except Empty:
                continue
            if fd is None:
                break
            with writer_lock:
                if current_writer:
                    current_writer.write(fd[1])
        except Exception as e:
            print("Writer error:", e)

# ─────────────────────────────────────────────
#  VIDEO RECORDING
# ─────────────────────────────────────────────

def get_dims(quality):
    return {'Low': (640, 480), 'Medium': (1280, 720),
            'High': (1920, 1080), 'Ultra': (3840, 2160)}.get(quality, (1920, 1080))

def start_video_recording(b1, _):
    global current_writer, current_output_file, frame_width, frame_height
    b1 = b1.replace('\r', '').replace('\n', '')
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    vp = VIDEO_FOLDER
    os.makedirs(vp, exist_ok=True)
    current_output_file = f"{vp}/{b1}_{ts}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'H264')
    current_writer = cv2.VideoWriter(
        current_output_file, fourcc,
        config.get('frame_rate', 30), (frame_width, frame_height))
    if not current_writer.isOpened():
        gui.log("Could not open video writer", "err")
        current_writer = None
        return False
    return True

def stop_video_recording():
    global current_writer
    with writer_lock:
        if current_writer:
            current_writer.release()
            current_writer = None
            gui.log(f"Video saved: {current_output_file}", "ok")

# ─────────────────────────────────────────────
#  MAIN VIDEO LOOP
# ─────────────────────────────────────────────

def video_loop():
    global cap, recording, barcode_value, is_recording, current_packaging_id
    global frame_width, frame_height, app_running, pre_buffer, preview_frame

    try:
        rtsp = config.get('rtsp_url', '0')
        if str(rtsp).isdigit():
            rtsp = int(rtsp)
        cap = cv2.VideoCapture(rtsp)
        if not cap.isOpened():
            gui.log("Could not open video stream", "err")
            return
        frame_width, frame_height = get_dims(config.get('video_quality', 'High'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
        frame_width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or frame_width
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or frame_height
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        pre_buffer = deque(maxlen=config.get('pre_buffer_duration', 5)
                           * config.get('frame_rate', 30))
        gui.log(f"Camera started — {frame_width}×{frame_height}", "ok")
        gui.update_status("Waiting for first barcode…", "idle")
        b1 = None
        frames_written = 0

        while recording and app_running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            if frame.shape[1] != frame_width or frame.shape[0] != frame_height:
                frame = cv2.resize(frame, (frame_width, frame_height))

            # Share frame for preview (throttled — every Nth frame)
            with preview_lock:
                preview_frame = frame.copy()

            if not is_recording:
                pre_buffer.append(frame)

            if is_recording:
                try:
                    frame_queue.put(("f", frame), timeout=1)
                    frames_written += 1
                    if frames_written % 30 == 0:
                        gui.update_current_info(frames=frames_written)
                except:
                    pass

            if barcode_value:
                bc = barcode_value
                barcode_value = None

                if not is_recording:
                    b1 = bc
                    frames_written = 0
                    gui.update_status("⏺  Recording…", "recording")
                    gui.log(f"START — Order ID: {b1}", "ok")
                    current_packaging_id = create_packaging_api(b1)
                    if not current_packaging_id:
                        gui.update_status("Packaging creation failed", "error")
                        continue
                    is_recording = True
                    gui.update_current_info(packaging_id=current_packaging_id,
                                            barcode1=b1, barcode2="—", frames=0)
                    if not start_video_recording(b1, "processing"):
                        is_recording = False
                        continue
                    for pf in pre_buffer:
                        frame_queue.put(("f", pf))
                        frames_written += 1
                else:
                    is_recording = False
                    b2 = bc
                    gui.update_status("Processing…", "processing")
                    gui.log(f"STOP — Barcode 2: {b2}", "ok")
                    gui.update_current_info(barcode2=b2)
                    if current_packaging_id:
                        update_packaging_api(current_packaging_id, b2)
                    t0 = time.time()
                    pd = config.get('post_buffer_duration', 5)
                    while time.time() - t0 < pd:
                        ret, frame = cap.read()
                        if not ret:
                            continue
                        if frame.shape[1] != frame_width or frame.shape[0] != frame_height:
                            frame = cv2.resize(frame, (frame_width, frame_height))
                        frame_queue.put(("f", frame))
                        frames_written += 1
                    stop_video_recording()
                    if current_output_file:
                        old = current_output_file
                        ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        new = f"{VIDEO_FOLDER}/{b1}_to_{b2}_{ts}.mp4"
                        try:
                            os.rename(old, new)
                            fp = new
                        except:
                            fp = old
                        if current_packaging_id:
                            ok = upload_video_api(current_packaging_id, fp)
                            if ok:
                                try:
                                    os.remove(fp)
                                    gui.log("Local video deleted", "info")
                                except:
                                    pass
                    b1 = None
                    pre_buffer.clear()
                    gui.update_current_info(
                        packaging_id="—", barcode1="—", barcode2="—", frames=0)
                    gui.update_status("Ready — waiting for barcode…", "idle")
                    gui.log("Ready for next recording", "info")
                    gui.scan_sub.configure(text="scan #1 → starts recording",
                                           fg=C["text3"])

    except Exception as e:
        gui.log(f"Fatal error: {e}", "err")
    finally:
        cleanup()

def cleanup():
    global app_running, is_recording, cap
    app_running  = False
    is_recording = False
    if cap and cap.isOpened():
        cap.release()
    stop_video_recording()
    time.sleep(0.5)
    frame_queue.put(None)
    if gui and gui.tick_id:
        try:
            gui.root.after_cancel(gui.tick_id)
        except:
            pass
    if gui and gui._preview_job:
        try:
            gui.root.after_cancel(gui._preview_job)
        except:
            pass

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def start_main_app():
    global gui
    root = tk.Tk()
    gui = VideoRecorderGUI(root)
    wt = threading.Thread(target=frame_writer_thread, daemon=False)
    wt.start()
    vt = threading.Thread(target=video_loop, daemon=True)
    vt.start()

    def on_close():
        global app_running, recording
        app_running = False
        recording   = False
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    cleanup()
    wt.join(timeout=5)
    print("Application closed.")

def start_application():
    global gui
    root = tk.Tk()
    root.withdraw()

    def after_splash():
        try:
            splash.root.destroy()
        except:
            pass
        cfg = load_config()
        if not cfg or not cfg.get("workstation_name"):
            show_config(root)
        else:
            start_main(root)

    def show_config(root):
        cfg_win = tk.Toplevel(root)
        ConfigSetupGUI(cfg_win, lambda: start_main(root))

    def start_main(root):
        global gui
        root.deiconify()
        gui = VideoRecorderGUI(root)

        wt = threading.Thread(target=frame_writer_thread, daemon=False)
        wt.start()
        vt = threading.Thread(target=video_loop, daemon=True)
        vt.start()

        def on_close():
            global app_running, recording
            app_running = False
            recording   = False
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

    splash = SplashScreen(root, duration=3, logo_path=LOGO_PATH)
    root.after(3000, after_splash)
    root.mainloop()
    cleanup()

if __name__ == "__main__":
    start_application()
