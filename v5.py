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

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

CONFIG_FILE = "config.json"
SETTINGS_PASSWORD = "11225577"

DEFAULT_CONFIG = {
    "workstation_name": "",
    "rtsp_url": "",
    "frame_rate": 30,
    "pre_buffer_duration": 5,
    "post_buffer_duration": 5,
    "video_quality": "High",
    "video_save_path": "Videos",
    "api_base": "http://192.168.0.135:27189",
    "token": ""
}

C = {
    "bg":       "#0d1117",
    "surface":  "#161b22",
    "card":     "#1c2128",
    "border":   "#30363d",
    "accent":   "#58a6ff",
    "accent2":  "#3fb950",
    "warn":     "#d29922",
    "danger":   "#f85149",
    "text":     "#e6edf3",
    "muted":    "#8b949e",
    "dim":      "#484f58",
    "rec":      "#ff4444",
    "input_bg": "#0d1117",
    "btn_bg":   "#21262d",
    "btn_hover":"#30363d",
}

FONTS = {
    "mono":    ("Consolas", 10),
    "ui":      ("Segoe UI", 10),
    "ui_sm":   ("Segoe UI", 9),
    "ui_bold": ("Segoe UI", 10, "bold"),
    "ui_lg":   ("Segoe UI", 12, "bold"),
    "ui_xl":   ("Segoe UI", 16, "bold"),
    "ui_hd":   ("Segoe UI", 20, "bold"),
}

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
dialog_open = False   # prevents _tick from stealing focus when a dialog is visible

# ─────────────────────────────────────────────
#  WIDGET HELPERS
# ─────────────────────────────────────────────

def mk_entry(parent, width=30, show=None, **kw):
    opts = dict(
        font=FONTS["mono"],
        bg=C["input_bg"], fg=C["text"],
        insertbackground=C["accent"],
        relief=tk.FLAT, bd=0,
        width=width,
        highlightthickness=1,
        highlightbackground=C["border"],
        highlightcolor=C["accent"],
    )
    if show:
        opts["show"] = show
    opts.update(kw)
    return tk.Entry(parent, **opts)

def mk_btn(parent, text, cmd, color=None, fg=None, px=18, py=8):
    return tk.Button(
        parent, text=text, command=cmd,
        font=FONTS["ui_bold"],
        bg=color or C["btn_bg"],
        fg=fg or C["text"],
        activebackground=C["btn_hover"],
        activeforeground=C["text"],
        relief=tk.FLAT, bd=0,
        padx=px, pady=py,
        cursor="hand2",
    )

class ScrollFrame(tk.Frame):
    """Vertically scrollable container."""
    def __init__(self, parent, bg=None, **kw):
        bg = bg or C["bg"]
        super().__init__(parent, bg=bg, **kw)
        cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(self, orient=tk.VERTICAL, command=cv.yview)
        self.inner = tk.Frame(cv, bg=bg)
        self.inner.bind("<Configure>",
            lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0,0), window=self.inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        def _wheel(e):
            cv.yview_scroll(int(-1*(e.delta/120)), "units")
        cv.bind_all("<MouseWheel>", _wheel)

def _center_win(win, parent):
    """Center win over parent after it has been drawn."""
    def _do():
        win.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - win.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")
    win.after(20, _do)

# ─────────────────────────────────────────────
#  FIRST-RUN CONFIG GUI
# ─────────────────────────────────────────────

class ConfigSetupGUI:
    def __init__(self, root, on_complete):
        self.root = root
        self.on_complete = on_complete
        self.entries = {}

        root.title("System Configuration")
        root.geometry("640x680")
        root.configure(bg=C["bg"])
        root.resizable(True, True)

        tk.Frame(root, bg=C["accent"], height=4).pack(fill=tk.X)

        sf = ScrollFrame(root)
        sf.pack(fill=tk.BOTH, expand=True)
        w = sf.inner
        w.configure(padx=48, pady=32)

        tk.Label(w, text="⚙  System Configuration",
                 font=FONTS["ui_hd"], bg=C["bg"], fg=C["text"]).pack(anchor=tk.W)
        tk.Label(w, text="Configure your workstation before starting.",
                 font=FONTS["ui_sm"], bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(4,28))

        for label, key, ph in [
            ("Workstation Name",         "workstation_name",    "e.g. Line-A Station 3"),
            ("Camera RTSP URL",          "rtsp_url",            "rtsp://user:pass@ip:port  or  0"),
            ("API Server URL",           "api_base",            "http://192.168.0.135:27189"),
            ("FPS",                      "frame_rate",          "30"),
            ("Pre-Record Buffer (sec)",  "pre_buffer_duration", "5"),
            ("Post-Record Buffer (sec)", "post_buffer_duration","5"),
        ]:
            self._field(w, label, key, ph)

        # Quality
        tk.Label(w, text="Video Quality", font=FONTS["ui_bold"],
                 bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(8,4))
        self.quality_var = tk.StringVar(value=config.get('video_quality','High'))
        qr = tk.Frame(w, bg=C["bg"])
        qr.pack(anchor=tk.W, pady=(0,12))
        for q, lbl in [('Low','480p'),('Medium','720p'),('High','1080p'),('Ultra','4K')]:
            tk.Radiobutton(qr, text=f" {q} ({lbl})",
                           variable=self.quality_var, value=q,
                           font=FONTS["ui"], bg=C["bg"], fg=C["text"],
                           selectcolor=C["surface"],
                           activebackground=C["bg"],
                           activeforeground=C["text"]).pack(side=tk.LEFT, padx=(0,16))

        # Bottom bar (outside scroll so it's always visible)
        bar = tk.Frame(root, bg=C["surface"], padx=48, pady=14)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bar, bg=C["border"], height=1).pack(fill=tk.X, pady=(0,12))
        mk_btn(bar, "  Save & Start  ", self._save,
               color=C["accent"], fg="#0d1117", py=10).pack(side=tk.LEFT, padx=(0,10))
        mk_btn(bar, "  Cancel  ", root.quit,
               color=C["danger"], py=10).pack(side=tk.LEFT)

    def _field(self, parent, label, key, placeholder=""):
        grp = tk.Frame(parent, bg=C["bg"])
        grp.pack(fill=tk.X, pady=(0,16))
        tk.Label(grp, text=label, font=FONTS["ui_bold"],
                 bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(0,4))
        e = mk_entry(grp, width=58)
        e.pack(fill=tk.X, ipady=8)
        val = config.get(key,"")
        if val:
            e.insert(0, str(val))
        elif placeholder:
            e.insert(0, placeholder); e.config(fg=C["dim"])
            def _in(ev, en=e, ph=placeholder):
                if en.get()==ph: en.delete(0,tk.END); en.config(fg=C["text"])
            def _out(ev, en=e, ph=placeholder):
                if not en.get(): en.insert(0,ph); en.config(fg=C["dim"])
            e.bind('<FocusIn>',_in); e.bind('<FocusOut>',_out)
        self.entries[key] = e

    def _save(self):
        global config
        ph_skip = {
            "workstation_name": "e.g. Line-A Station 3",
            "rtsp_url":  "rtsp://user:pass@ip:port  or  0",
            "api_base":  "http://192.168.0.135:27189",
        }
        new = {}
        new['api_base'] = config.get('api_base', DEFAULT_CONFIG['api_base'])
        
        for key, e in self.entries.items():
            v = e.get().strip()
            if v == ph_skip.get(key,""): v = ""
            print(v)
            if not v and key != "api_base":
                messagebox.showerror("Missing", f"Please fill in: {key.replace('_',' ').title()}", parent=self.root)
                return
            if key in ['frame_rate','pre_buffer_duration','post_buffer_duration']:
                try:
                    v = int(v)
                    assert v > 0
                except:
                    messagebox.showerror("Invalid", f"{key.replace('_',' ').title()} must be a positive integer", parent=self.root)
                    return
            new[key] = v
        new['video_quality']  = self.quality_var.get()
        new['video_save_path']= config.get('video_save_path','Videos')
        new['token']          = config.get('token','')

        if save_config(new):
            config = new
            self.root.destroy()
            self.on_complete()
        else:
            messagebox.showerror("Error","Failed to save configuration", parent=self.root)

# ─────────────────────────────────────────────
#  SETTINGS DIALOG  (password-protected)
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
        win.configure(bg=C["bg"])
        win.resizable(resizable, resizable)
        _center_win(win, self.parent)

        def _close():
            global dialog_open
            dialog_open = False
            try: win.grab_release()
            except: pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _close)
        win.after(30, lambda: (win.grab_set(), win.lift(), win.focus_force()))
        return win, _close

    def _ask_password(self):
        if is_recording:
            messagebox.showwarning(
                "Recording Active",
                "Settings cannot be changed while a recording is in progress.\n"
                "Please finish the current recording first.",
                parent=self.parent)
            return

        win, close = self._make_win("Settings — Authentication", 440, 270)
        tk.Frame(win, bg=C["accent"], height=3).pack(fill=tk.X)

        body = tk.Frame(win, bg=C["bg"], padx=36, pady=28)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="🔐  Settings Access",
                 font=FONTS["ui_xl"], bg=C["bg"], fg=C["text"]).pack(anchor=tk.W)
        tk.Label(body, text="Enter the admin password to continue.",
                 font=FONTS["ui_sm"], bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(4,18))

        pw = mk_entry(body, show="*", width=32)
        pw.pack(fill=tk.X, ipady=9)

        err = tk.Label(body, text="", font=FONTS["ui_sm"], bg=C["bg"], fg=C["danger"])
        err.pack(anchor=tk.W, pady=(6,0))

        br = tk.Frame(body, bg=C["bg"])
        br.pack(fill=tk.X, pady=(16,0))

        def check():
            global dialog_open
            if pw.get() == SETTINGS_PASSWORD:
                dialog_open = False
                try: win.grab_release()
                except: pass
                win.destroy()
                self._open_settings()
            else:
                err.config(text="✗  Incorrect password. Try again.")
                pw.delete(0, tk.END)
                pw.focus_set()

        win.after(80, pw.focus_set)
        pw.bind('<Return>', lambda e: check())
        mk_btn(br, "  Unlock  ", check, color=C["accent"], fg="#0d1117", py=8).pack(side=tk.LEFT, padx=(0,10))
        mk_btn(br, "  Cancel  ", close, color=C["btn_bg"], py=8).pack(side=tk.LEFT)

    def _open_settings(self):
        win, close = self._make_win("Settings", 660, 580, resizable=True)
        tk.Frame(win, bg=C["accent"], height=3).pack(fill=tk.X)

        # Scrollable content
        sf = ScrollFrame(win)
        sf.pack(fill=tk.BOTH, expand=True)
        w = sf.inner
        w.configure(padx=40, pady=26)

        tk.Label(w, text="⚙  Edit Configuration",
                 font=FONTS["ui_hd"], bg=C["bg"], fg=C["text"]).pack(anchor=tk.W)
        tk.Label(w, text="RTSP / FPS / Resolution changes require a restart.",
                 font=FONTS["ui_sm"], bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(4,22))

        self._ents = {}
        for label, key in [
            ("Workstation Name",          "workstation_name"),
            ("Camera RTSP URL",           "rtsp_url"),
            ("API Server URL",            "api_base"),
            ("FPS",                       "frame_rate"),
            ("Pre-Record Buffer (sec)",   "pre_buffer_duration"),
            ("Post-Record Buffer (sec)",  "post_buffer_duration"),
        ]:
            grp = tk.Frame(w, bg=C["bg"])
            grp.pack(fill=tk.X, pady=(0,14))
            tk.Label(grp, text=label, font=FONTS["ui_bold"],
                     bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(0,4))
            e = mk_entry(grp, width=56)
            e.pack(fill=tk.X, ipady=8)
            v = config.get(key,"")
            if v: e.insert(0, str(v))
            self._ents[key] = e

        # Quality
        tk.Label(w, text="Video Quality", font=FONTS["ui_bold"],
                 bg=C["bg"], fg=C["muted"]).pack(anchor=tk.W, pady=(4,6))
        self._qv = tk.StringVar(value=config.get('video_quality','High'))
        qr = tk.Frame(w, bg=C["bg"])
        qr.pack(anchor=tk.W, pady=(0,8))
        for q, lbl in [('Low','480p'),('Medium','720p'),('High','1080p'),('Ultra','4K')]:
            tk.Radiobutton(qr, text=f" {q} ({lbl})",
                           variable=self._qv, value=q,
                           font=FONTS["ui"], bg=C["bg"], fg=C["text"],
                           selectcolor=C["surface"],
                           activebackground=C["bg"],
                           activeforeground=C["text"]).pack(side=tk.LEFT, padx=(0,16))

        # Fixed bottom bar — packed to BOTTOM of win (not inside scrollframe)
        bar = tk.Frame(win, bg=C["surface"], padx=40, pady=14)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bar, bg=C["border"], height=1).pack(fill=tk.X, pady=(0,12))

        def do_save():
            global config, dialog_open
            new = {}
            for key, e in self._ents.items():
                v = e.get().strip()
                if not v:
                    messagebox.showerror("Missing", f"Please fill in: {key.replace('_',' ').title()}", parent=win)
                    return
                if key in ['frame_rate','pre_buffer_duration','post_buffer_duration']:
                    try:
                        v = int(v)
                        assert v > 0
                    except:
                        messagebox.showerror("Invalid", f"{key.replace('_',' ').title()} must be a positive integer", parent=win)
                        return
                new[key] = v
            new['video_quality']   = self._qv.get()
            new['video_save_path'] = config.get('video_save_path','Videos')
            new['token']           = config.get('token','')
            if save_config(new):
                config = new
                dialog_open = False
                try: win.grab_release()
                except: pass
                win.destroy()
                messagebox.showinfo("Saved",
                    "Configuration saved!\nRTSP / FPS / Resolution changes take effect on next start.",
                    parent=self.parent)
            else:
                messagebox.showerror("Error","Failed to save configuration.", parent=win)

        mk_btn(bar, "  Save Changes  ", do_save,
               color=C["accent"], fg="#0d1117", py=10).pack(side=tk.LEFT, padx=(0,10))
        mk_btn(bar, "  Cancel  ", close,
               color=C["btn_bg"], py=10).pack(side=tk.LEFT)

# ─────────────────────────────────────────────
#  MAIN GUI
# ─────────────────────────────────────────────

class VideoRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PackagingOps — {config.get('workstation_name','Workstation')}")
        self.root.geometry("1120x740")
        self.root.configure(bg=C["bg"])
        self.root.minsize(900, 640)
        self._blink_state = True
        self._blink_job = None

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=C["bg"])
        style.configure('TScrollbar',
            background=C["surface"], troughcolor=C["bg"], arrowcolor=C["dim"])
        style.configure('Pkg.Treeview',
            background=C["card"], foreground=C["text"],
            fieldbackground=C["card"], rowheight=28,
            font=FONTS["ui_sm"], borderwidth=0)
        style.configure('Pkg.Treeview.Heading',
            background=C["surface"], foreground=C["muted"],
            font=FONTS["ui_bold"], relief=tk.FLAT, borderwidth=0)
        style.map('Pkg.Treeview',
            background=[('selected',C["accent"])],
            foreground=[('selected',"#0d1117")])

        self._build(root)
        self.root.after(100, lambda: self.barcode_entry.focus_set())
        self._tick()

    def _build(self, root):
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        tk.Frame(root, bg=C["accent"], height=3).grid(row=0, column=0, sticky="ew")
        self._build_header(root)
        body = tk.Frame(root, bg=C["bg"])
        body.grid(row=2, column=0, sticky="nsew", padx=16, pady=12)
        body.columnconfigure(0, weight=0, minsize=310)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_left(body)
        self._build_right(body)

    def _build_header(self, root):
        hdr = tk.Frame(root, bg=C["surface"], height=64)
        hdr.grid(row=1, column=0, sticky="ew")
        hdr.grid_propagate(False)
        tk.Frame(hdr, bg=C["accent"], width=5).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(hdr, text=f"  🖥  {config.get('workstation_name','Workstation')}",
                 font=FONTS["ui_xl"], bg=C["surface"], fg=C["text"]).pack(side=tk.LEFT, padx=(12,0))
        self.header_status = tk.Label(hdr, text="● IDLE",
                 font=FONTS["ui_bold"], bg=C["surface"], fg=C["muted"], padx=14, pady=4)
        self.header_status.pack(side=tk.LEFT, padx=18)
        # Settings on right
        mk_btn(hdr, "⚙  Settings", self.open_settings,
               color=C["btn_bg"], py=6, px=16).pack(side=tk.RIGHT, padx=(0,16))
        # Barcode input
        bc = tk.Frame(hdr, bg=C["surface"])
        bc.pack(side=tk.LEFT, expand=True, fill=tk.Y, padx=20)
        tk.Label(bc, text="SCAN", font=FONTS["ui_sm"],
                 bg=C["surface"], fg=C["muted"]).pack(side=tk.LEFT, padx=(0,8))
        self.barcode_entry = tk.Entry(bc, font=("Consolas",14),
            bg=C["input_bg"], fg=C["accent"],
            insertbackground=C["accent"],
            relief=tk.FLAT, bd=0, width=32,
            highlightthickness=2,
            highlightbackground=C["border"],
            highlightcolor=C["accent"])
        self.barcode_entry.pack(side=tk.LEFT, ipady=8)
        self.barcode_entry.bind('<Return>', self.on_barcode_enter)

    def _card(self, parent, title=""):
        outer = tk.Frame(parent, bg=C["border"], bd=1)
        inner = tk.Frame(outer, bg=C["card"])
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        if title:
            tk.Label(inner, text=title, font=FONTS["ui_sm"],
                     bg=C["card"], fg=C["dim"], padx=16, pady=8).pack(anchor=tk.W)
            tk.Frame(inner, bg=C["border"], height=1).pack(fill=tk.X)
        return inner

    def _build_left(self, body):
        lp = tk.Frame(body, bg=C["bg"], width=310)
        lp.grid(row=0, column=0, sticky="ns", padx=(0,12))
        lp.grid_propagate(False)
        lp.columnconfigure(0, weight=1)

        sc = self._card(lp, "STATUS")
        sc.pack(fill=tk.X, pady=(0,10))
        dr = tk.Frame(sc, bg=C["card"])
        dr.pack(fill=tk.X, padx=16, pady=14)
        self.status_ind = tk.Canvas(dr, width=14, height=14,
                                    bg=C["card"], highlightthickness=0)
        self.status_ind.pack(side=tk.LEFT)
        self._dot = self.status_ind.create_oval(2,2,12,12, fill=C["accent2"], outline="")
        self.status_label = tk.Label(dr, text="Waiting for barcode…",
                                     font=FONTS["ui_bold"], bg=C["card"], fg=C["accent2"])
        self.status_label.pack(side=tk.LEFT, padx=10)

        sess = self._card(lp, "CURRENT SESSION")
        sess.pack(fill=tk.X, pady=(0,10))
        self._sr = {}
        for key, lbl in [("pkg_id","Packaging ID"),("barcode1","Order ID"),
                          ("barcode2","Barcode 2"),("frames","Frames")]:
            row = tk.Frame(sess, bg=C["card"])
            row.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(row, text=lbl, font=FONTS["ui_sm"],
                     bg=C["card"], fg=C["muted"], width=15, anchor=tk.W).pack(side=tk.LEFT)
            v = tk.Label(row, text="—", font=FONTS["mono"],
                         bg=C["card"], fg=C["text"], anchor=tk.W)
            v.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._sr[key] = v
        tk.Frame(sess, bg=C["card"], height=8).pack()

        sc2 = self._card(lp, "LAST SCAN")
        sc2.pack(fill=tk.BOTH, expand=True)
        self.last_bc_lbl = tk.Label(sc2, text="—",
                                    font=("Consolas",22,"bold"),
                                    bg=C["card"], fg=C["accent2"],
                                    wraplength=270, justify=tk.CENTER)
        self.last_bc_lbl.pack(expand=True, pady=18, padx=16)
        self.scan_sub = tk.Label(sc2, text="scan #1 — start recording",
                                 font=FONTS["ui_sm"], bg=C["card"], fg=C["muted"])
        self.scan_sub.pack(pady=(0,14))

    def _build_right(self, body):
        rp = tk.Frame(body, bg=C["bg"])
        rp.grid(row=0, column=1, sticky="nsew")
        rp.columnconfigure(0, weight=1)
        rp.rowconfigure(1, weight=1)

        th = tk.Frame(rp, bg=C["bg"])
        th.grid(row=0, column=0, sticky="ew", pady=(0,8))
        tk.Label(th, text="PACKAGING TASKS", font=FONTS["ui_lg"],
                 bg=C["bg"], fg=C["text"]).pack(side=tk.LEFT)
        self.task_count = tk.Label(th, text="0 records", font=FONTS["ui_sm"],
                                   bg=C["bg"], fg=C["muted"])
        self.task_count.pack(side=tk.RIGHT)

        tbl = tk.Frame(rp, bg=C["border"], bd=1)
        tbl.grid(row=1, column=0, sticky="nsew")
        tbl.columnconfigure(0, weight=1)
        tbl.rowconfigure(0, weight=1)
        cols = ('ID','Order ID','Barcode 2','Status','Time')
        self.task_tree = ttk.Treeview(tbl, columns=cols,
                                      show='headings', style='Pkg.Treeview')
        for col, w in zip(cols, [90,150,150,110,160]):
            self.task_tree.heading(col, text=col.upper())
            self.task_tree.column(col, width=w, minwidth=60, anchor=tk.W)
        self.task_tree.tag_configure('recording', foreground=C["rec"])
        self.task_tree.tag_configure('uploading', foreground=C["warn"])
        self.task_tree.tag_configure('completed', foreground=C["accent2"])
        self.task_tree.tag_configure('failed',    foreground=C["danger"])
        sb2 = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=sb2.set)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        sb2.grid(row=0, column=1, sticky="ns")

        lw = tk.Frame(rp, bg=C["bg"])
        lw.grid(row=2, column=0, sticky="ew", pady=(10,0))
        tk.Label(lw, text="ACTIVITY LOG", font=FONTS["ui_lg"],
                 bg=C["bg"], fg=C["text"]).pack(anchor=tk.W, pady=(0,6))
        self.log_text = tk.Text(lw, height=7,
            bg=C["surface"], fg=C["accent2"],
            font=("Consolas",9), relief=tk.FLAT, bd=0,
            insertbackground=C["accent"],
            padx=12, pady=8, state=tk.DISABLED,
            highlightthickness=1, highlightbackground=C["border"])
        self.log_text.pack(fill=tk.X)
        for tag, col in [("ok",C["accent2"]),("err",C["danger"]),
                          ("warn",C["warn"]),("info",C["muted"])]:
            self.log_text.tag_configure(tag, foreground=col)

    # ── public methods ───────────────────────────

    def open_settings(self):
        SettingsDialog(self.root)

    def on_barcode_enter(self, event):
        global barcode_value, last_barcode_1, last_barcode_2
        code = self.barcode_entry.get().strip()
        if code:
            barcode_value = code
            if not is_recording:
                last_barcode_1 = code
                self.last_bc_lbl.configure(text=code, fg=C["accent2"])
                self.scan_sub.configure(text="scan #1 received — starting…", fg=C["accent2"])
            else:
                last_barcode_2 = code
                self.last_bc_lbl.configure(text=code, fg=C["warn"])
                self.scan_sub.configure(text="scan #2 received — stopping…", fg=C["warn"])
            self.barcode_entry.delete(0, tk.END)
            self.log(f"Barcode scanned: {code}", "info")
            self.barcode_entry.focus_set()

    def update_status(self, text, state="idle"):
        cols = {"idle":C["accent2"],"recording":C["rec"],
                "processing":C["warn"],"error":C["danger"]}
        col = cols.get(state, C["muted"])
        self.status_label.configure(text=text, fg=col)
        self.status_ind.itemconfig(self._dot, fill=col)
        pills = {
            "idle":       ("● IDLE",        C["muted"]),
            "recording":  ("⏺  REC",        C["rec"]),
            "processing": ("⟳  PROCESSING", C["warn"]),
            "error":      ("✗  ERROR",       C["danger"]),
        }
        pt, pc = pills.get(state, ("● IDLE", C["muted"]))
        self.header_status.configure(text=pt, fg=pc)
        if state == "recording": self._start_blink()
        else: self._stop_blink()

    def _start_blink(self):
        self._stop_blink()
        def blink():
            self._blink_state = not self._blink_state
            self.header_status.configure(fg=C["rec"] if self._blink_state else C["surface"])
            self._blink_job = self.root.after(600, blink)
        self._blink_job = self.root.after(600, blink)

    def _stop_blink(self):
        if self._blink_job:
            self.root.after_cancel(self._blink_job)
            self._blink_job = None

    def update_current_info(self, packaging_id=None, barcode1=None,
                            barcode2=None, frames=None):
        for key, val in [("pkg_id",packaging_id),("barcode1",barcode1),
                          ("barcode2",barcode2),("frames",frames)]:
            if val is not None:
                self._sr[key].configure(text=str(val))

    def add_task(self, td):
        tag = td.get('status','').lower()
        vals = (td['id'], td.get('barcode1','—'), td.get('barcode2','—'),
                td['status'], td['time'])
        with task_lock:
            for item in self.task_tree.get_children():
                if self.task_tree.item(item)['values'][0] == td['id']:
                    self.task_tree.item(item, values=vals, tags=(tag,))
                    return
            self.task_tree.insert('', 0, values=vals, tags=(tag,))
            n = len(self.task_tree.get_children())
            self.task_count.configure(text=f"{n} record{'s' if n!=1 else ''}")

    def log(self, msg, tag="ok"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        ic = {"ok":"✓","err":"✗","warn":"⚠","info":"›"}.get(tag,"›")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}]  {ic}  {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _tick(self):
        # Only reclaim focus when NO dialog is open AND the root window itself is focused
        if not dialog_open:
            try:
                fw = self.root.focus_get()
                if fw == self.root or fw is None:
                    self.barcode_entry.focus_set()
            except Exception:
                pass
        self.root.after(300, self._tick)

# ─────────────────────────────────────────────
#  API
# ─────────────────────────────────────────────

def create_packaging_api(barcode1):
    try:
        res = requests.post(f"{config.get('api_base')}/api/packaging/create",
            json={"bar_code_1": barcode1}, timeout=10)
        if res.status_code == 201:
            pid = res.json()["packaging_id"]
            gui.log(f"Packaging created: {pid}", "ok")
            gui.add_task({'id':pid,'barcode1':barcode1,'status':'Recording',
                          'time':datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return pid
        gui.log(f"Create failed: {res.text}", "err"); return None
    except Exception as e:
        gui.log(f"API Error: {e}", "err"); return None

def update_packaging_api(packaging_id, barcode2):
    try:
        requests.put(f"{config.get('api_base')}/api/packaging/update/{packaging_id}",
            json={"bar_code_2":barcode2,"end_time":datetime.datetime.now().isoformat()},
            timeout=10)
        gui.log(f"Packaging updated: {packaging_id}", "ok")
        gui.add_task({'id':packaging_id,'barcode2':barcode2,'status':'Uploading',
                      'time':datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        gui.log(f"Update error: {e}", "err")

def upload_video_api(packaging_id, video_path):
    try:
        gui.log(f"Uploading video for {packaging_id}…", "warn")
        with open(video_path,"rb") as f:
            res = requests.post(
                f"{config.get('api_base')}/api/packaging/upload-video/{packaging_id}",
                files={"video":f}, timeout=120)
        if res.status_code == 200:
            gui.log(f"Video uploaded: {packaging_id}", "ok")
            gui.add_task({'id':packaging_id,'status':'Completed',
                          'time':datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return True
        gui.log(f"Upload failed: {res.text}", "err"); return False
    except Exception as e:
        gui.log(f"Upload error: {e}", "err"); return False

# ─────────────────────────────────────────────
#  FRAME WRITER THREAD
# ─────────────────────────────────────────────

def frame_writer_thread():
    while app_running:
        try:
            try: fd = frame_queue.get(timeout=1)
            except Empty: continue
            if fd is None: break
            with writer_lock:
                if current_writer: current_writer.write(fd[1])
        except Exception as e:
            print("Writer error:", e)

# ─────────────────────────────────────────────
#  VIDEO RECORDING
# ─────────────────────────────────────────────

def get_dims(quality):
    return {'Low':(640,480),'Medium':(1280,720),'High':(1920,1080),'Ultra':(3840,2160)}.get(quality,(1920,1080))

def start_video_recording(b1, _):
    global current_writer, current_output_file, frame_width, frame_height
    b1 = b1.replace('\r','').replace('\n','')
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    vp = config.get('video_save_path','Videos')
    os.makedirs(vp, exist_ok=True)
    current_output_file = f"{vp}/{b1}_{ts}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'H264')
    current_writer = cv2.VideoWriter(current_output_file, fourcc,
                                     config.get('frame_rate',30), (frame_width,frame_height))
    if not current_writer.isOpened():
        gui.log("Could not open video writer","err"); current_writer=None; return False
    return True

def stop_video_recording():
    global current_writer
    with writer_lock:
        if current_writer:
            current_writer.release(); current_writer=None
            gui.log(f"Video saved: {current_output_file}","ok")

# ─────────────────────────────────────────────
#  MAIN VIDEO LOOP
# ─────────────────────────────────────────────

def video_loop():
    global cap, recording, barcode_value, is_recording, current_packaging_id
    global frame_width, frame_height, app_running, pre_buffer
    try:
        rtsp = config.get('rtsp_url','0')
        if str(rtsp).isdigit(): rtsp = int(rtsp)
        cap = cv2.VideoCapture(rtsp)
        if not cap.isOpened(): gui.log("Could not open video stream","err"); return
        frame_width, frame_height = get_dims(config.get('video_quality','High'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
        frame_width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or frame_width
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or frame_height
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        pre_buffer = deque(maxlen=config.get('pre_buffer_duration',5)*config.get('frame_rate',30))
        gui.log(f"Camera started — {frame_width}×{frame_height}","ok")
        gui.update_status("Waiting for first barcode…","idle")
        b1 = None; frames_written = 0
        while recording and app_running:
            ret, frame = cap.read()
            if not ret: time.sleep(0.01); continue
            if frame.shape[1]!=frame_width or frame.shape[0]!=frame_height:
                frame = cv2.resize(frame,(frame_width,frame_height))
            if not is_recording: pre_buffer.append(frame)
            if is_recording:
                try:
                    frame_queue.put(("f",frame),timeout=1)
                    frames_written+=1
                    if frames_written%30==0: gui.update_current_info(frames=frames_written)
                except: pass
            if barcode_value:
                bc = barcode_value; barcode_value=None
                if not is_recording:
                    b1=bc; frames_written=0
                    gui.update_status("⏺  Recording…","recording")
                    gui.log(f"START — Order ID: {b1}","ok")
                    current_packaging_id = create_packaging_api(b1)
                    if not current_packaging_id:
                        gui.update_status("Packaging creation failed","error"); continue
                    is_recording=True
                    gui.update_current_info(packaging_id=current_packaging_id,
                                            barcode1=b1,barcode2="—",frames=0)
                    if not start_video_recording(b1,"processing"):
                        is_recording=False; continue
                    for pf in pre_buffer: frame_queue.put(("f",pf)); frames_written+=1
                else:
                    is_recording=False; b2=bc
                    gui.update_status("Processing…","processing")
                    gui.log(f"STOP — Barcode 2: {b2}","ok")
                    gui.update_current_info(barcode2=b2)
                    if current_packaging_id: update_packaging_api(current_packaging_id,b2)
                    t0=time.time(); pd=config.get('post_buffer_duration',5)
                    while time.time()-t0<pd:
                        ret,frame=cap.read()
                        if not ret: continue
                        if frame.shape[1]!=frame_width or frame.shape[0]!=frame_height:
                            frame=cv2.resize(frame,(frame_width,frame_height))
                        frame_queue.put(("f",frame)); frames_written+=1
                    stop_video_recording()
                    if current_output_file:
                        old=current_output_file
                        ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        new=f"{config.get('video_save_path','Videos')}/{b1}_to_{b2}_{ts}.mp4"
                        try: os.rename(old,new); fp=new
                        except: fp=old
                        if current_packaging_id:
                            ok=upload_video_api(current_packaging_id,fp)
                            if ok:
                                try: os.remove(fp); gui.log("Local video deleted","info")
                                except: pass
                    b1=None; pre_buffer.clear()
                    gui.update_current_info(packaging_id="—",barcode1="—",barcode2="—",frames=0)
                    gui.update_status("Ready — waiting for barcode…","idle")
                    gui.log("Ready for next recording","info")
                    gui.scan_sub.configure(text="scan #1 — start recording",fg=C["muted"])
    except Exception as e:
        gui.log(f"Fatal error: {e}","err")
    finally:
        cleanup()

def cleanup():
    global app_running, is_recording, cap
    app_running=False; is_recording=False
    if cap and cap.isOpened(): cap.release()
    stop_video_recording()
    time.sleep(0.5)
    frame_queue.put(None)

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def start_main_app():
    global gui
    root = tk.Tk()
    gui = VideoRecorderGUI(root)
    wt = threading.Thread(target=frame_writer_thread, daemon=False); wt.start()
    vt = threading.Thread(target=video_loop, daemon=True); vt.start()
    def on_close():
        global app_running, recording
        app_running=False; recording=False; root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    cleanup(); wt.join(timeout=5)
    print("Application closed.")

if __name__ == "__main__":
    if not load_config():
        r = tk.Tk()
        ConfigSetupGUI(r, start_main_app)
        r.mainloop()
    else:
        start_main_app()