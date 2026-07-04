import os
import requests
import subprocess
import logging
from typing import Dict, Any, List

logger = logging.getLogger("pixel_client")

def get_pixel_config():
    import database
    ip = database.get_setting("pixel_ip", "192.168.1.198")
    port = database.get_setting("pixel_port", "8080")
    return ip, port

def discover_pixel_ip_via_adb() -> str:
    """Uses ADB to query the active IP address of the connected Pixel device."""
    try:
        # Get list of adb devices
        res = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        if "device" not in res.stdout:
            return ""
            
        # Run ip route on device
        cmd = ["adb", "shell", "ip", "route"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                if "src" in line:
                    parts = line.split()
                    if "src" in parts:
                        idx = parts.index("src")
                        if idx + 1 < len(parts):
                            found_ip = parts[idx + 1]
                            if found_ip != "127.0.0.1":
                                return found_ip
    except Exception as e:
        logger.debug(f"ADB IP discovery error: {e}")
    return ""

def ensure_adb_forward_and_connection():
    """Ensures ADB connection and port forwarding (tcp:8765 -> tcp:8080) are active."""
    try:
        # Check adb connection
        res = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if "device" not in res.stdout:
            ip, _ = get_pixel_config()
            subprocess.run(["adb", "connect", f"{ip}:5555"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            
        # Forward port 8765 to Pixel Ktor port
        _, port = get_pixel_config()
        subprocess.run(["adb", "forward", "tcp:8765", f"tcp:{port}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        
        # Check if IP changed dynamically
        discovered_ip = discover_pixel_ip_via_adb()
        if discovered_ip:
            import database
            current_ip = database.get_setting("pixel_ip")
            if discovered_ip != current_ip:
                logger.info(f"Detected Pixel IP change: {current_ip} -> {discovered_ip}. Updating settings.")
                database.set_setting("pixel_ip", discovered_ip)
    except Exception as e:
        logger.debug(f"ensure_adb_forward error: {e}")

def get_health() -> Dict[str, Any]:
    ensure_adb_forward_and_connection()
    ip, port = get_pixel_config()
    
    # Try localhost ADB forwarded port first, then direct LAN IP
    urls = [f"http://localhost:8765", f"http://{ip}:{port}"]
    for url in urls:
        try:
            resp = requests.get(f"{url}/api/health", timeout=3)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    
    return {"status": "unreachable", "adb_fallback": check_adb_connection()}

def check_adb_connection() -> bool:
    try:
        res = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return "device" in res.stdout
    except Exception:
        return False

def stage_files(file_paths: List[str]) -> Dict[str, Any]:
    ensure_adb_forward_and_connection()
    ip, port = get_pixel_config()
    urls = [f"http://localhost:8765", f"http://{ip}:{port}"]
    
    for url in urls:
        try:
            resp = requests.post(f"{url}/api/stage", json={"files": file_paths}, timeout=60)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return {"status": "error", "count": 0}

def verify_sync(filenames: List[str]) -> Dict[str, bool]:
    if not filenames:
        return {}
    ensure_adb_forward_and_connection()
    ip, port = get_pixel_config()
    files_param = ",".join(filenames)
    urls = [f"http://localhost:8765", f"http://{ip}:{port}"]
    
    for url in urls:
        try:
            resp = requests.get(f"{url}/api/verify", params={"files": files_param}, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return {f: False for f in filenames}

def restart_photos() -> bool:
    ensure_adb_forward_and_connection()
    ip, port = get_pixel_config()
    urls = [f"http://localhost:8765", f"http://{ip}:{port}"]
    for url in urls:
        try:
            resp = requests.post(f"{url}/api/photos/restart", timeout=10)
            if resp.status_code == 200:
                return True
        except Exception:
            continue
    return False

def mount_drive() -> bool:
    ensure_adb_forward_and_connection()
    ip, port = get_pixel_config()
    urls = [f"http://localhost:8765", f"http://{ip}:{port}"]
    for url in urls:
        try:
            resp = requests.post(f"{url}/api/mount", timeout=15)
            if resp.status_code == 200 and resp.json().get("status") == "success":
                return True
        except Exception:
            continue
    return False

def unmount_drive() -> bool:
    ensure_adb_forward_and_connection()
    ip, port = get_pixel_config()
    urls = [f"http://localhost:8765", f"http://{ip}:{port}"]
    for url in urls:
        try:
            resp = requests.post(f"{url}/api/unmount", timeout=15)
            if resp.status_code == 200 and resp.json().get("status") == "success":
                return True
        except Exception:
            continue
    return False

def push_file(local_path: str, remote_path: str) -> bool:
    """Pushes a file from the server to the Pixel's storage via ADB."""
    ensure_adb_forward_and_connection()
    remote_dir = os.path.dirname(remote_path)
    try:
        # Create directory structure as root
        subprocess.run(["adb", "shell", "su", "-c", f"mkdir -p \"{remote_dir}\""], check=True, timeout=15)
        # Push to public temp directory
        temp_path = f"/data/local/tmp/{os.path.basename(local_path)}"
        subprocess.run(["adb", "push", local_path, temp_path], check=True, timeout=120)
        # Move to destination directory as root
        subprocess.run(["adb", "shell", "su", "-c", f"mv \"{temp_path}\" \"{remote_path}\""], check=True, timeout=15)
        # Set permissions
        subprocess.run(["adb", "shell", "su", "-c", f"chmod 777 \"{remote_path}\""], check=True, timeout=15)
        return True
    except Exception as e:
        logger.error(f"Failed to push file {local_path} to Pixel: {e}")
        return False
