import sqlite3

# connect to database (creates file if not exists)
conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# ---------------- USER TABLE ----------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    password TEXT,
    role TEXT CHECK(role IN ('admin', 'guest')),
    is_active TEXT DEFAULT 'y' CHECK(is_active IN ('y','n')),
    doa DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ---------------- WORKSTATION TABLE ----------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS workstation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workstation_name TEXT,
    system_ip TEXT,
    rtsp_url TEXT,
    frame_rate INTEGER,
    pre_buffer_duration INTEGER,
    post_buffer_duration INTEGER,
    video_quality TEXT,
    video_save_path TEXT,
    api_base TEXT,
    is_active TEXT DEFAULT 'y' CHECK(is_active IN ('y','n')),
    doa DATETIME DEFAULT CURRENT_TIMESTAMP
);
""")

# ---------------- TRACKING TABLE ----------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS tracking_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ws_id INTEGER,
    bar_code_1 TEXT,
    start_time DATETIME,
    bar_code_2 TEXT,
    end_time DATETIME,
    video_path TEXT,
    is_active TEXT DEFAULT 'y' CHECK(is_active IN ('y','n')),
    doa DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("✅ Tables created successfully")
