import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.environ.get("ORCHESTRATOR_DB_PATH", "/root/media_orchestrator/orchestrator.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Default settings
    defaults = {
        "pixel_ip": "192.168.1.198",
        "pixel_port": "8080",
        "icloud_username": "",
        "icloud_password": "",
        "nas_inbox_path": "/mnt/my_drive/Backup/shares/Amit/Photographs/Inbox",
        "nas_sorted_root": "/mnt/my_drive/Backup/shares/Amit/Photographs/Sorted",
        "nas_staging_path": "/mnt/my_drive/_stage",
        "tier_high_months": "6",
        "tier_medium_months": "12",
        "tier_compact_months": "24",
        "quarantine_days": "7",
        "pixel_upload_enabled": "true",
        "icloud_sync_enabled": "true",
        "screen_always_active": "false",
        "battery_saver_enabled": "true",
        "disable_charging_completely": "false"
    }

    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS media_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_filename TEXT NOT NULL,
        original_hash_sha256 TEXT,
        exif_date TEXT,
        file_size_bytes INTEGER,
        media_type TEXT,
        duration_seconds REAL,
        resolution_width INTEGER,
        resolution_height INTEGER,
        
        nas_path TEXT UNIQUE,
        nas_archived_at TIMESTAMP,
        nas_hash_verified BOOLEAN DEFAULT 0,
        
        pixel_staged_at TIMESTAMP,
        pixel_chunk_id TEXT,
        gphotos_synced BOOLEAN DEFAULT 0,
        gphotos_synced_at TIMESTAMP,
        upload_bytes_verified BOOLEAN DEFAULT 0,
        
        current_icloud_tier TEXT DEFAULT 'original',
        icloud_compressed_size INTEGER,
        compression_ratio REAL,
        last_tier_change_at TIMESTAMP,
        icloud_reuploaded BOOLEAN DEFAULT 0,
        icloud_original_deleted BOOLEAN DEFAULT 0,
        
        is_exempt BOOLEAN DEFAULT 0,
        exempt_reason TEXT,
        max_compression_tier TEXT,
        
        quarantine_expires_at TIMESTAMP,
        
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tier_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        media_file_id INTEGER REFERENCES media_files(id),
        from_tier TEXT,
        to_tier TEXT,
        compressed_size INTEGER,
        transitioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

def get_setting(key: str, default_val: str = "") -> str:
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default_val

def set_setting(key: str, value: str):
    conn = get_db_connection()
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()

def log_event(level: str, message: str):
    conn = get_db_connection()
    conn.execute("INSERT INTO pipeline_logs (level, message) VALUES (?, ?)", (level, message))
    conn.commit()
    conn.close()
