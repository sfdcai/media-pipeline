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
    if _icloud_service is None:
        if not username or not password:
            import database
            username = database.get_setting("icloud_username")
            password = database.get_setting("icloud_password")
        if username and password:
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
    """Runs pyicloud to pull new photos from iCloud."""
    logger.info(f"Triggering pyicloud download to {directory}...")
    try:
        api = get_pyicloud_session()
        if not api or api.requires_2fa:
            logger.error("iCloud authentication failed or 2FA required.")
            return {"success": False, "error": "Authentication failed or 2FA required"}
            
        os.makedirs(directory, exist_ok=True)
        photos = api.photos.all
        count = 0
        for photo in photos:
            target_file = os.path.join(directory, photo.filename)
            if not os.path.exists(target_file):
                logger.info(f"Downloading {photo.filename}...")
                download = photo.download()
                with open(target_file, 'wb') as f:
                    f.write(download)
                try:
                    dt = photo.created
                    mtime = dt.timestamp()
                    os.utime(target_file, (mtime, mtime))
                except Exception:
                    pass
                count += 1
        return {"success": True, "stdout": f"Downloaded {count} files via pyicloud"}
    except Exception as e:
        logger.error(f"pyicloud download failed: {e}")
        return {"success": False, "error": str(e)}

def download_single_file_from_icloud(filename: str, target_dir: str = ICLOUD_DOWNLOAD_DIR) -> Dict[str, Any]:
    """Downloads a single photo/video by filename for testing."""
    logger.info(f"Downloading single file '{filename}' from iCloud...")
    try:
        api = get_pyicloud_session()
        if not api or api.requires_2fa:
            return {"success": False, "error": "Authentication failed or 2FA required"}
            
        os.makedirs(target_dir, exist_ok=True)
        photos = api.photos.all
        matched_photo = None
        for photo in photos:
            if photo.filename == filename:
                matched_photo = photo
                break
                
        if not matched_photo:
            return {"success": False, "error": f"File {filename} not found in iCloud"}
            
        target_file = os.path.join(target_dir, filename)
        download = matched_photo.download()
        with open(target_file, 'wb') as f:
            f.write(download)
        try:
            dt = matched_photo.created
            mtime = dt.timestamp()
            os.utime(target_file, (mtime, mtime))
        except Exception:
            pass
            
        return {
            "success": True,
            "filepath": target_file,
            "stdout": f"Successfully downloaded {filename} via pyicloud"
        }
    except Exception as e:
        logger.error(f"Failed single file download: {e}")
        return {"success": False, "error": str(e)}

def upload_compressed_to_icloud(file_path: str) -> bool:
    """Uploads a compressed copy to iCloud using pyicloud."""
    try:
        api = get_pyicloud_session()
        if not api or api.requires_2fa:
            logger.error("iCloud authentication failed or 2FA required for upload.")
            return False
            
        logger.info(f"Uploading {file_path} to iCloud via pyicloud...")
        asset = api.photos.upload(file_path)
        if asset:
            logger.info(f"Successfully uploaded {file_path} to iCloud. Asset: {asset}")
            return True
        else:
            logger.error(f"Upload returned None for {file_path}")
            return False
    except Exception as e:
        logger.error(f"Error uploading to iCloud: {e}")
        return False
