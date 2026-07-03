import os
import subprocess
import logging
from typing import Dict, Any, List
from pyicloud import PyiCloudService

logger = logging.getLogger("icloud_sync")

ICLOUD_DOWNLOAD_DIR = os.environ.get("ICLOUD_DOWNLOAD_DIR", "/mnt/my_drive/Backup/shares/Amit/Photographs/Inbox")

_icloud_service = None

def get_pyicloud_session(username: str = "", password: str = "") -> PyiCloudService:
    global _icloud_service
    if _icloud_service is None and username and password:
        try:
            _icloud_service = PyiCloudService(username, password)
        except Exception as e:
            logger.error(f"Error authenticating PyiCloudService: {e}")
    return _icloud_service

def submit_2fa_code(code: str) -> Dict[str, Any]:
    global _icloud_service
    if _icloud_service is None:
        return {"status": "error", "message": "No active iCloud authentication session. Submit username and password first."}
    
    if _icloud_service.requires_2fa:
        result = _icloud_service.validate_2fa_code(code)
        if result:
            return {"status": "success", "message": "2FA Authentication Successful!"}
        else:
            return {"status": "error", "message": "Invalid 2FA code. Please try again."}
    elif _icloud_service.requires_2sa:
        devices = _icloud_service.trusted_devices
        device = devices[0]
        result = _icloud_service.validate_2sa_code(code, device)
        return {"status": "success" if result else "error", "message": "2SA Result"}
    else:
        return {"status": "info", "message": "2FA is not currently required."}

def run_icloud_download(directory: str = ICLOUD_DOWNLOAD_DIR) -> Dict[str, Any]:
    """Runs icloudpd command to pull new photos from iCloud."""
    os.makedirs(directory, exist_ok=True)
    cmd = [
        "icloudpd",
        "--directory", directory,
        "--folder-structure", "{yyyy}/{mm}/{dd}",
        "--set-mtime"
    ]
    logger.info(f"Triggering icloudpd download to {directory}...")
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3600)
        return {
            "success": res.returncode == 0,
            "stdout": res.stdout[-1000:],
            "stderr": res.stderr[-1000:]
        }
    except Exception as e:
        logger.error(f"icloudpd execution failed: {e}")
        return {"success": False, "error": str(e)}

def download_single_file_from_icloud(filename: str, target_dir: str = ICLOUD_DOWNLOAD_DIR) -> Dict[str, Any]:
    """Downloads a single photo/video by filename for testing."""
    os.makedirs(target_dir, exist_ok=True)
    cmd = [
        "icloudpd",
        "--directory", target_dir,
        "--match-filename", filename,
        "--set-mtime"
    ]
    logger.info(f"Downloading single file '{filename}' from iCloud...")
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        target_file = os.path.join(target_dir, filename)
        exists = os.path.exists(target_file)
        return {
            "success": res.returncode == 0 and exists,
            "filepath": target_file if exists else "",
            "stdout": res.stdout[-500:]
        }
    except Exception as e:
        logger.error(f"Failed single file download: {e}")
        return {"success": False, "error": str(e)}

def upload_compressed_to_icloud(file_path: str) -> bool:
    """Uploads a compressed copy to iCloud using pyicloud / icloud CLI."""
    try:
        cmd = ["python3", "-m", "pyicloud", "--upload", file_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        return res.returncode == 0
    except Exception as e:
        logger.error(f"Error uploading to iCloud: {e}")
        return False
