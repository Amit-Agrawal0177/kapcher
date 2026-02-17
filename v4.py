#configuration setup also done

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

# ---------------- CONFIG FILE MANAGEMENT ----------------

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "workstation_name": "",
    "rtsp_url": "",
    "frame_rate": 30,
    "pre_buffer_duration": 5,
    "post_buffer_duration": 5,
    "video_quality": "High",
    "video_save_path": "Videos",
    "api_base": "http://192.168.0.135:27189",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJuYW1lIjoiQW1pdCIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc3MTMzMTk2NH0.rnIObtimHttD9IghWrSXfDn2BqKIQbuUJZ7NRFlfacc"
}

def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# ---------------- GLOBAL VARIABLES ----------------

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

# Task tracking
task_list = []
task_lock = threading.Lock()

# Last barcodes
last_barcode_1 = ""
last_barcode_2 = ""


# ---------------- CONFIGURATION SETUP GUI ----------------

class ConfigSetupGUI:
    def __init__(self, root, on_complete):
        self.root = root
        self.on_complete = on_complete
        self.root.title("Setup - Video Recording System")
        self.root.geometry("600x650")
        self.root.configure(bg='#1e1e1e')
        
        # Initialize entries dictionary FIRST
        self.entries = {}
        
        # Main frame
        main_frame = tk.Frame(root, bg='#1e1e1e', padx=40, pady=30)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header = tk.Label(main_frame, text="⚙️ System Configuration", 
                         font=('Arial', 20, 'bold'), 
                         bg='#1e1e1e', fg='#ffffff')
        header.pack(pady=(0, 30))
        
        # Form fields
        fields_frame = tk.Frame(main_frame, bg='#1e1e1e')
        fields_frame.pack(fill=tk.BOTH, expand=True)
        
        # Workstation Name
        self.create_field(fields_frame, "Workstation Name:", "workstation_name", 0)
        
        # Camera RTSP URL
        self.create_field(fields_frame, "Camera RTSP URL:", "rtsp_url", 1,
                         placeholder="rtsp://username:password@ip:port/stream or 0 for webcam")
        
        # FPS
        self.create_field(fields_frame, "FPS (Frames Per Second):", "frame_rate", 2,
                         field_type="number", default=30)
        
        # Pre-record time
        self.create_field(fields_frame, "Pre-Record Time (seconds):", "pre_buffer_duration", 3,
                         field_type="number", default=5)
        
        # Post-record time
        self.create_field(fields_frame, "Post-Record Time (seconds):", "post_buffer_duration", 4,
                         field_type="number", default=5)
        
        # Video Quality
        tk.Label(fields_frame, text="Video Quality:", 
                font=('Arial', 11), bg='#1e1e1e', fg='#ffffff').grid(
                row=5, column=0, sticky=tk.W, pady=(15, 5))
        
        self.quality_var = tk.StringVar(value=config.get('video_quality', 'High'))
        quality_frame = tk.Frame(fields_frame, bg='#1e1e1e')
        quality_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        
        qualities = ['Low (480p)', 'Medium (720p)', 'High (1080p)', 'Ultra (4K)']
        for quality in qualities:
            rb = tk.Radiobutton(quality_frame, text=quality, 
                               variable=self.quality_var, value=quality.split()[0],
                               font=('Arial', 10), bg='#1e1e1e', fg='#ffffff',
                               selectcolor='#2d2d2d', activebackground='#1e1e1e',
                               activeforeground='#ffffff')
            rb.pack(anchor=tk.W, pady=2)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg='#1e1e1e')
        button_frame.pack(pady=(20, 0))
        
        save_btn = tk.Button(button_frame, text="Save & Continue", 
                            font=('Arial', 12, 'bold'),
                            bg='#0078d7', fg='white', 
                            activebackground='#005a9e',
                            relief=tk.FLAT, padx=30, pady=10,
                            command=self.save_config)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="Cancel", 
                              font=('Arial', 12),
                              bg='#d32f2f', fg='white', 
                              activebackground='#b71c1c',
                              relief=tk.FLAT, padx=30, pady=10,
                              command=self.root.quit)
        cancel_btn.pack(side=tk.LEFT, padx=5)
    
    def create_field(self, parent, label_text, key, row, field_type="text", default="", placeholder=""):
        tk.Label(parent, text=label_text, 
                font=('Arial', 11), bg='#1e1e1e', fg='#ffffff').grid(
                row=row*2, column=0, sticky=tk.W, pady=(15, 5))
        
        entry = tk.Entry(parent, font=('Arial', 11), 
                        bg='#2d2d2d', fg='#ffffff', 
                        insertbackground='#ffffff',
                        relief=tk.FLAT, bd=5)
        entry.grid(row=row*2+1, column=0, sticky=(tk.W, tk.E), pady=(0, 0))
        
        # Set current value or default
        current_value = config.get(key, default)
        if current_value:
            entry.insert(0, str(current_value))
        elif placeholder:
            entry.insert(0, placeholder)
            entry.config(fg='#888888')
            
            def on_focus_in(e):
                if entry.get() == placeholder:
                    entry.delete(0, tk.END)
                    entry.config(fg='#ffffff')
            
            def on_focus_out(e):
                if not entry.get():
                    entry.insert(0, placeholder)
                    entry.config(fg='#888888')
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
        
        self.entries[key] = entry
        parent.columnconfigure(0, weight=1)
    
    def save_config(self):
        """Validate and save configuration"""
        global config
        
        new_config = {}
        
        # Get all text field values
        for key, entry in self.entries.items():
            value = entry.get().strip()
            
            # Check if it's a placeholder
            if value in ["rtsp://username:password@ip:port/stream or 0 for webcam"]:
                value = ""
            
            if not value:
                messagebox.showerror("Error", f"Please fill in {key.replace('_', ' ').title()}")
                return
            
            # Convert numeric fields
            if key in ['frame_rate', 'pre_buffer_duration', 'post_buffer_duration']:
                try:
                    value = int(value)
                    if value <= 0:
                        raise ValueError()
                except:
                    messagebox.showerror("Error", f"{key.replace('_', ' ').title()} must be a positive number")
                    return
            
            new_config[key] = value
        
        # Add quality
        new_config['video_quality'] = self.quality_var.get()
        
        # Add other settings from default config
        new_config['video_save_path'] = config.get('video_save_path', 'Videos')
        new_config['api_base'] = config.get('api_base', DEFAULT_CONFIG['api_base'])
        
        # Save to file
        if save_config(new_config):
            config = new_config
            messagebox.showinfo("Success", "Configuration saved successfully!")
            self.root.destroy()
            self.on_complete()
        else:
            messagebox.showerror("Error", "Failed to save configuration")


# ---------------- MAIN GUI CLASS ----------------

class VideoRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Video Recording System - {config.get('workstation_name', 'Workstation')}")
        self.root.geometry("1000x700")
        self.root.configure(bg='#1e1e1e')
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure('TFrame', background='#1e1e1e')
        style.configure('TLabel', background='#1e1e1e', foreground='#ffffff', font=('Arial', 10))
        style.configure('Header.TLabel', background='#1e1e1e', foreground='#ffffff', font=('Arial', 16, 'bold'))
        style.configure('Status.TLabel', background='#1e1e1e', foreground='#00ff00', font=('Arial', 12, 'bold'))
        
        # Top Bar - Workstation Info & Barcode Input
        top_bar = tk.Frame(root, bg='#2d2d2d', height=80)
        top_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))
        top_bar.grid_propagate(False)
        
        # Workstation name
        station_label = tk.Label(top_bar, 
                                text=f"🖥️ {config.get('workstation_name', 'Workstation')}", 
                                font=('Arial', 14, 'bold'), 
                                bg='#2d2d2d', fg='#ffffff')
        station_label.pack(side=tk.LEFT, padx=20, pady=10)
        
        # Settings button
        settings_btn = tk.Button(top_bar, text="⚙️ Settings", 
                                font=('Arial', 10),
                                bg='#404040', fg='white', 
                                activebackground='#505050',
                                relief=tk.FLAT, padx=15, pady=5,
                                command=self.open_settings)
        settings_btn.pack(side=tk.RIGHT, padx=20, pady=10)
        
        # Barcode input section
        barcode_frame = tk.Frame(top_bar, bg='#2d2d2d')
        barcode_frame.pack(side=tk.LEFT, padx=20, expand=True)
        
        tk.Label(barcode_frame, text="🔍 Scan Barcode:", 
                font=('Arial', 11, 'bold'), background='#2d2d2d', 
                foreground='#ffffff').pack(side=tk.LEFT, padx=(0, 10))
        
        self.barcode_entry = tk.Entry(barcode_frame, font=('Arial', 13), 
                                      bg='#404040', fg='#ffffff', 
                                      insertbackground='#ffffff',
                                      width=35, relief=tk.FLAT, bd=5)
        self.barcode_entry.pack(side=tk.LEFT, padx=5, ipady=5)
        self.barcode_entry.bind('<Return>', self.on_barcode_enter)
        self.barcode_entry.bind('<FocusOut>', lambda e: self.barcode_entry.focus_set())
        
        # Main container
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Left Panel - Status & Last Barcode
        left_panel = tk.Frame(main_frame, bg='#1e1e1e', padx=10, pady=10)
        left_panel.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Status Frame
        status_frame = tk.Frame(left_panel, bg='#2d2d2d', relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(status_frame, text="📊 Status", 
                font=('Arial', 14, 'bold'), 
                bg='#2d2d2d', fg='#ffffff').pack(pady=(10, 5))
        
        self.status_label = tk.Label(status_frame, text="⚫ Waiting for barcode...", 
                                     font=('Arial', 13, 'bold'),
                                     bg='#2d2d2d', fg='#00ff00',
                                     padx=10, pady=10)
        self.status_label.pack(pady=(0, 10))
        
        # Current Recording Info
        current_info_frame = tk.Frame(left_panel, bg='#2d2d2d', relief=tk.RAISED, bd=2)
        current_info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        tk.Label(current_info_frame, text="📦 Current Recording", 
                font=('Arial', 14, 'bold'), 
                bg='#2d2d2d', fg='#ffffff').pack(pady=(15, 10))
        
        # Info labels with better spacing
        info_content = tk.Frame(current_info_frame, bg='#2d2d2d')
        info_content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        self.packaging_id_label = tk.Label(info_content, text="Packaging ID: --", 
                                           font=('Arial', 11),
                                           bg='#2d2d2d', fg='#ffffff')
        self.packaging_id_label.pack(anchor=tk.W, pady=5)
        
        self.barcode1_label = tk.Label(info_content, text="Barcode 1: --", 
                                       font=('Arial', 11),
                                       bg='#2d2d2d', fg='#ffffff')
        self.barcode1_label.pack(anchor=tk.W, pady=5)
        
        self.barcode2_label = tk.Label(info_content, text="Barcode 2: --", 
                                       font=('Arial', 11),
                                       bg='#2d2d2d', fg='#ffffff')
        self.barcode2_label.pack(anchor=tk.W, pady=5)
        
        self.frames_label = tk.Label(info_content, text="Frames: 0", 
                                     font=('Arial', 11),
                                     bg='#2d2d2d', fg='#ffffff')
        self.frames_label.pack(anchor=tk.W, pady=5)
        
        # Last Barcode Scanned (Large Display)
        last_barcode_frame = tk.Frame(left_panel, bg='#2d2d2d', relief=tk.RAISED, bd=2)
        last_barcode_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(last_barcode_frame, text="🏷️ Last Barcode Scanned", 
                font=('Arial', 14, 'bold'), 
                bg='#2d2d2d', fg='#ffffff').pack(pady=(15, 10))
        
        self.last_barcode_display = tk.Label(last_barcode_frame, 
                                             text="--", 
                                             font=('Arial', 32, 'bold'),
                                             bg='#2d2d2d', fg='#00ff00',
                                             wraplength=400)
        self.last_barcode_display.pack(pady=30, padx=20)
        
        # Right Panel - Task List
        right_panel = ttk.Frame(main_frame, padding="5")
        right_panel.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        
        # Task list header
        task_header_frame = ttk.Frame(right_panel)
        task_header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(task_header_frame, text="📋 Packaging Tasks", 
                 style='Header.TLabel').pack(side=tk.LEFT)
        
        self.task_count_label = ttk.Label(task_header_frame, text="Total: 0", 
                                         font=('Arial', 10))
        self.task_count_label.pack(side=tk.RIGHT)
        
        # Task list with scrollbar
        task_list_frame = ttk.Frame(right_panel)
        task_list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        task_list_frame.columnconfigure(0, weight=1)
        task_list_frame.rowconfigure(0, weight=1)
        
        # Treeview for tasks
        columns = ('ID', 'Barcode 1', 'Barcode 2', 'Status', 'Time')
        self.task_tree = ttk.Treeview(task_list_frame, columns=columns, show='headings', height=15)
        
        # Configure columns
        self.task_tree.heading('ID', text='Packaging ID')
        self.task_tree.heading('Barcode 1', text='Barcode 1')
        self.task_tree.heading('Barcode 2', text='Barcode 2')
        self.task_tree.heading('Status', text='Status')
        self.task_tree.heading('Time', text='Time')
        
        self.task_tree.column('ID', width=80)
        self.task_tree.column('Barcode 1', width=120)
        self.task_tree.column('Barcode 2', width=120)
        self.task_tree.column('Status', width=100)
        self.task_tree.column('Time', width=130)
        
        # Style for treeview
        style.configure('Treeview', background='#2d2d2d', foreground='white', 
                       fieldbackground='#2d2d2d', font=('Arial', 9))
        style.configure('Treeview.Heading', background='#404040', foreground='white',
                       font=('Arial', 10, 'bold'))
        style.map('Treeview', background=[('selected', '#0078d7')])
        
        scrollbar = ttk.Scrollbar(task_list_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        
        self.task_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Log area
        log_frame = ttk.Frame(right_panel)
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        ttk.Label(log_frame, text="📝 Activity Log", font=('Arial', 11, 'bold')).pack(anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, bg='#2d2d2d', 
                                                  fg='#00ff00', font=('Courier', 9),
                                                  relief=tk.SUNKEN, bd=2)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Set focus to barcode entry
        self.root.after(100, lambda: self.barcode_entry.focus_set())
        
        self.update_display()
    
    def open_settings(self):
        """Open settings window"""
        messagebox.showinfo("Settings", "Close the application and delete config.json to reconfigure.")
    
    def on_barcode_enter(self, event):
        global barcode_value, last_barcode_1, last_barcode_2
        code = self.barcode_entry.get().strip()
        if code:
            barcode_value = code
            
            # Update last barcode display
            if not is_recording:
                last_barcode_1 = code
                self.last_barcode_display.configure(text=code, fg='#00ff00')
            else:
                last_barcode_2 = code
                self.last_barcode_display.configure(text=code, fg='#ffaa00')
            
            self.barcode_entry.delete(0, tk.END)
            self.log(f"Barcode scanned: {code}")
            self.barcode_entry.focus_set()
    
    def update_status(self, text, color='#00ff00'):
        self.status_label.configure(text=text, fg=color)
    
    def update_current_info(self, packaging_id=None, barcode1=None, barcode2=None, frames=None):
        if packaging_id is not None:
            self.packaging_id_label.configure(text=f"Packaging ID: {packaging_id}")
        if barcode1 is not None:
            self.barcode1_label.configure(text=f"Barcode 1: {barcode1}")
        if barcode2 is not None:
            self.barcode2_label.configure(text=f"Barcode 2: {barcode2}")
        if frames is not None:
            self.frames_label.configure(text=f"Frames: {frames}")
    
    def add_task(self, task_data):
        """Add or update task in the treeview"""
        with task_lock:
            # Check if task already exists
            for item in self.task_tree.get_children():
                if self.task_tree.item(item)['values'][0] == task_data['id']:
                    # Update existing task
                    self.task_tree.item(item, values=(
                        task_data['id'],
                        task_data.get('barcode1', '--'),
                        task_data.get('barcode2', '--'),
                        task_data['status'],
                        task_data['time']
                    ))
                    return
            
            # Add new task at the top
            self.task_tree.insert('', 0, values=(
                task_data['id'],
                task_data.get('barcode1', '--'),
                task_data.get('barcode2', '--'),
                task_data['status'],
                task_data['time']
            ))
            
            self.task_count_label.configure(text=f"Total: {len(self.task_tree.get_children())}")
    
    def log(self, message):
        """Add message to log"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def update_display(self):
        """Periodic update of display elements"""
        # Keep focus on barcode entry for scanner
        try:
            if self.root.focus_get() != self.barcode_entry:
                self.barcode_entry.focus_set()
        except:
            pass
        
        self.root.after(100, self.update_display)


# ---------------- API FUNCTIONS ----------------

def create_packaging_api(barcode1):
    try:
        res = requests.post(
            f"{config.get('api_base')}/api/packaging/create",
            json={"bar_code_1": barcode1}
        )

        if res.status_code == 201:
            data = res.json()
            packaging_id = data["packaging_id"]
            print("Packaging created:", packaging_id)
            
            # Add to GUI
            gui.log(f"✓ Packaging created: {packaging_id}")
            task_data = {
                'id': packaging_id,
                'barcode1': barcode1,
                'status': 'Recording',
                'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            gui.add_task(task_data)
            
            return packaging_id
        else:
            print("Create packaging failed:", res.text)
            gui.log(f"✗ Failed to create packaging: {res.text}")
            return None

    except Exception as e:
        print("Create API error:", e)
        gui.log(f"✗ API Error: {e}")
        return None


def update_packaging_api(packaging_id, barcode2):
    try:
        res = requests.put(
            f"{config.get('api_base')}/api/packaging/update/{packaging_id}",
            json={
                "bar_code_2": barcode2,
                "end_time": datetime.datetime.now().isoformat()
            }
        )

        print("Update response:", res.text)
        gui.log(f"✓ Packaging updated: {packaging_id}")
        
        # Update task in GUI
        task_data = {
            'id': packaging_id,
            'barcode2': barcode2,
            'status': 'Uploading',
            'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        gui.add_task(task_data)

    except Exception as e:
        print("Update API error:", e)
        gui.log(f"✗ Update error: {e}")


def upload_video_api(packaging_id, video_path):
    try:
        gui.log(f"⬆ Uploading video for {packaging_id}...")
        
        with open(video_path, "rb") as f:
            files = {"video": f}

            res = requests.post(
                f"{config.get('api_base')}/api/packaging/upload-video/{packaging_id}",
                files=files
            )

        if res.status_code == 200:
            print("Video uploaded successfully")
            gui.log(f"✓ Video uploaded successfully for {packaging_id}")
            
            # Update task status
            task_data = {
                'id': packaging_id,
                'status': 'Completed',
                'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            gui.add_task(task_data)
            
            return True
        else:
            print("Upload failed:", res.text)
            gui.log(f"✗ Upload failed: {res.text}")
            return False

    except Exception as e:
        print("Upload error:", e)
        gui.log(f"✗ Upload error: {e}")
        return False


# ---------------- FRAME WRITER THREAD ----------------

def frame_writer_thread():
    global current_writer

    while app_running:
        try:
            try:
                frame_data = frame_queue.get(timeout=1)
            except Empty:
                continue

            if frame_data is None:
                break

            frame_type, frame = frame_data

            with writer_lock:
                if current_writer is not None:
                    current_writer.write(frame)

        except Exception as e:
            print("Error writing frame:", e)


# ---------------- VIDEO RECORDING FUNCTIONS ----------------

def get_video_dimensions(quality):
    """Get video dimensions based on quality setting"""
    dimensions = {
        'Low': (640, 480),
        'Medium': (1280, 720),
        'High': (1920, 1080),
        'Ultra': (3840, 2160)
    }
    return dimensions.get(quality, (1920, 1080))


def start_video_recording(barcode_1, barcode_2):
    global current_writer, current_output_file, frame_width, frame_height

    barcode_1 = barcode_1.replace('\r', '').replace('\n', '')
    barcode_2 = barcode_2.replace('\r', '').replace('\n', '')

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = config.get('video_save_path', 'Videos')
    
    if not os.path.exists(video_path):
        os.makedirs(video_path)
    
    current_output_file = f"{video_path}/{barcode_1}_to_{barcode_2}_{timestamp}.mp4"

    print("\n" + "="*60)
    print("Recording to:", current_output_file)
    print("="*60 + "\n")

    fourcc = cv2.VideoWriter_fourcc(*'H264')
    current_writer = cv2.VideoWriter(
        current_output_file,
        fourcc,
        config.get('frame_rate', 30),
        (frame_width, frame_height)
    )

    if not current_writer.isOpened():
        print("Error: Could not open video writer")
        gui.log("✗ Error: Could not open video writer")
        current_writer = None
        return False

    return True


def stop_video_recording():
    global current_writer, current_output_file

    with writer_lock:
        if current_writer is not None:
            current_writer.release()
            current_writer = None
            print("Video saved:", current_output_file)
            gui.log(f"✓ Video saved: {current_output_file}")
            print("="*60 + "\n")


# ---------------- MAIN VIDEO LOOP ----------------

def video_loop():
    global cap, recording, barcode_value, is_recording, current_packaging_id
    global frame_width, frame_height, app_running, pre_buffer
    
    try:
        # Get RTSP URL from config
        rtsp = config.get('rtsp_url', '0')
        if rtsp.isdigit():
            rtsp = int(rtsp)
        
        cap = cv2.VideoCapture(rtsp)

        if not cap.isOpened():
            print("Error: Could not open video stream.")
            gui.log("✗ Error: Could not open video stream")
            return

        # Get video dimensions from config
        quality = config.get('video_quality', 'High')
        frame_width, frame_height = get_video_dimensions(quality)
        
        # Try to set resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
        
        # Get actual dimensions
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or frame_width
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or frame_height

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Update pre_buffer size based on config
        pre_buffer_duration = config.get('pre_buffer_duration', 5)
        frame_rate = config.get('frame_rate', 30)
        pre_buffer = deque(maxlen=pre_buffer_duration * frame_rate)

        print("="*60)
        print("Camera started...")
        print(f"Resolution: {frame_width}x{frame_height}")
        print("="*60)
        
        gui.log("✓ Camera started successfully")
        gui.log(f"✓ Resolution: {frame_width}x{frame_height}")
        gui.update_status("🟢 Ready - Waiting for first barcode", '#00ff00')

        barcode_1 = None
        frames_written = 0

        while recording and app_running:

            ret, frame = cap.read()

            if not ret:
                time.sleep(0.01)
                continue

            # Resize frame if needed
            if frame.shape[1] != frame_width or frame.shape[0] != frame_height:
                frame = cv2.resize(frame, (frame_width, frame_height))

            if not is_recording:
                pre_buffer.append(frame)

            if is_recording:
                try:
                    frame_queue.put(("frame", frame), timeout=1)
                    frames_written += 1
                    if frames_written % 30 == 0:  # Update every second
                        gui.update_current_info(frames=frames_written)
                except:
                    pass

            if barcode_value:
                current_barcode = barcode_value
                barcode_value = None

                # ---------- SCAN 1 ----------
                if not is_recording:

                    barcode_1 = current_barcode
                    frames_written = 0

                    print("\n>>> SCAN 1 - START <<<")
                    print("Barcode 1:", barcode_1)
                    
                    gui.update_status("🔴 Recording...", '#ff0000')
                    gui.log(f"▶ START - Barcode 1: {barcode_1}")

                    current_packaging_id = create_packaging_api(barcode_1)

                    if not current_packaging_id:
                        print("Packaging creation failed")
                        gui.update_status("⚠ Packaging creation failed", '#ff9900')
                        continue

                    is_recording = True
                    
                    gui.update_current_info(
                        packaging_id=current_packaging_id,
                        barcode1=barcode_1,
                        barcode2="--",
                        frames=0
                    )

                    if not start_video_recording(barcode_1, "processing"):
                        is_recording = False
                        continue

                    for pre_frame in pre_buffer:
                        frame_queue.put(("frame", pre_frame))
                        frames_written += 1

                # ---------- SCAN 2 ----------
                else:
                    is_recording = False
                    barcode_2 = current_barcode

                    print("\n>>> SCAN 2 - STOP <<<")
                    print("Barcode 2:", barcode_2)
                    
                    gui.update_status("⏸ Processing...", '#ffff00')
                    gui.log(f"⏹ STOP - Barcode 2: {barcode_2}")
                    gui.update_current_info(barcode2=barcode_2)

                    if current_packaging_id:
                        update_packaging_api(current_packaging_id, barcode_2)

                    post_start_time = time.time()
                    post_duration = config.get('post_buffer_duration', 5)

                    while time.time() - post_start_time < post_duration:
                        ret, frame = cap.read()
                        if not ret:
                            continue

                        if frame.shape[1] != frame_width or frame.shape[0] != frame_height:
                            frame = cv2.resize(frame, (frame_width, frame_height))

                        frame_queue.put(("frame", frame))
                        frames_written += 1

                    stop_video_recording()

                    final_video_path = None

                    if current_output_file:
                        old_file = current_output_file
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        video_path = config.get('video_save_path', 'Videos')
                        new_file = f"{video_path}/{barcode_1}_to_{barcode_2}_{timestamp}.mp4"

                        try:
                            os.rename(old_file, new_file)
                            final_video_path = new_file
                        except:
                            final_video_path = old_file

                        print("Saved video:", final_video_path)

                        if current_packaging_id and final_video_path:
                            print("Uploading video...")
                            success = upload_video_api(current_packaging_id, final_video_path)

                            if success:
                                try:
                                    os.remove(final_video_path)
                                    print("Local video deleted")
                                    gui.log(f"✓ Local video deleted")
                                except:
                                    print("Could not delete local file")

                    barcode_1 = None
                    pre_buffer.clear()
                    
                    # Reset current info
                    gui.update_current_info(
                        packaging_id="--",
                        barcode1="--",
                        barcode2="--",
                        frames=0
                    )
                    
                    gui.update_status("🟢 Ready - Waiting for next barcode", '#00ff00')
                    gui.log("✓ Ready for next recording")

    except Exception as e:
        print("Error:", e)
        gui.log(f"✗ Error: {e}")

    finally:
        cleanup()


def cleanup():
    global app_running, is_recording, cap
    
    app_running = False
    is_recording = False

    if cap and cap.isOpened():
        cap.release()

    stop_video_recording()
    time.sleep(1)
    frame_queue.put(None)


# ---------------- MAIN ----------------

def start_main_app():
    global gui, writer_thread, video_thread
    
    # Create main GUI
    root = tk.Tk()
    gui = VideoRecorderGUI(root)
    
    # Start writer thread
    writer_thread = threading.Thread(target=frame_writer_thread, daemon=False)
    writer_thread.start()
    
    # Start video loop in separate thread
    video_thread = threading.Thread(target=video_loop, daemon=True)
    video_thread.start()
    
    # Handle window close
    def on_closing():
        global app_running, recording
        app_running = False
        recording = False
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Start GUI
    root.mainloop()
    
    # Wait for threads to finish
    cleanup()
    writer_thread.join(timeout=5)
    
    print("Application closed.")


if __name__ == "__main__":
    # Check if config exists
    if not load_config():
        # Show setup screen
        setup_root = tk.Tk()
        ConfigSetupGUI(setup_root, start_main_app)
        setup_root.mainloop()
    else:
        # Start main app directly
        start_main_app()