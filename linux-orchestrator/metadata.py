import os
import json
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any, Tuple

logger = logging.getLogger("metadata")

def extract_file_metadata(filepath: str) -> Dict[str, Any]:
    """Uses exiftool CLI to extract comprehensive in-file metadata as JSON."""
    try:
        cmd = ["exiftool", "-json", "-G1", "-a", "-s", filepath]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        if data and isinstance(data, list):
            return data[0]
    except Exception as e:
        logger.error(f"Error extracting exiftool metadata for {filepath}: {e}")
    return {}

def extract_exif_date(filepath: str) -> str:
    """Extracts DateTimeOriginal or falls back to CreateDate or file mtime."""
    meta = extract_file_metadata(filepath)
    date_str = (
        meta.get("EXIF:DateTimeOriginal") or
        meta.get("QuickTime:CreateDate") or
        meta.get("QuickTime:CreationDate") or
        meta.get("H264:DateTimeOriginal")
    )
    if date_str:
        parts = date_str.split(" ")
        if len(parts) >= 2:
            date_part = parts[0].replace(":", "-")
            return f"{date_part} {parts[1]}"
    
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

def create_sidecar_json(media_filepath: str, icloud_meta: Dict[str, Any] = None) -> str:
    """Creates a .meta.json sidecar file preserving both in-file metadata summary and out-of-file iCloud DB fields."""
    sidecar_path = f"{media_filepath}.meta.json"
    in_file_meta = extract_file_metadata(media_filepath)
    
    combined = {
        "filepath": media_filepath,
        "filename": os.path.basename(media_filepath),
        "file_size": os.path.getsize(media_filepath),
        "exif_date": extract_exif_date(media_filepath),
        "in_file_metadata_summary": {
            "GPS": {
                "latitude": in_file_meta.get("EXIF:GPSLatitude") or in_file_meta.get("Composite:GPSLatitude"),
                "longitude": in_file_meta.get("EXIF:GPSLongitude") or in_file_meta.get("Composite:GPSLongitude"),
                "altitude": in_file_meta.get("EXIF:GPSAltitude") or in_file_meta.get("Composite:GPSAltitude"),
            },
            "device": {
                "make": in_file_meta.get("EXIF:Make") or in_file_meta.get("QuickTime:Make"),
                "model": in_file_meta.get("EXIF:Model") or in_file_meta.get("QuickTime:Model"),
                "lens": in_file_meta.get("EXIF:LensModel"),
            },
            "live_photo_id": in_file_meta.get("MakerNotes:ContentIdentifier") or in_file_meta.get("QuickTime:ContentIdentifier")
        },
        "icloud_db_metadata": icloud_meta or {
            "is_favorite": False,
            "albums": [],
            "description": "",
            "keywords": [],
            "faces": []
        }
    }
    
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)
    
    return sidecar_path

def copy_all_metadata(source_filepath: str, target_filepath: str) -> bool:
    """Uses exiftool to copy ALL tags from source_filepath to target_filepath without stripping."""
    try:
        cmd = [
            "exiftool",
            "-TagsFromFile", source_filepath,
            "-All:All",
            "-ICC_Profile",
            "-overwrite_original",
            target_filepath
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.returncode == 0
    except Exception as e:
        logger.error(f"Error copying metadata from {source_filepath} to {target_filepath}: {e}")
        return False

def verify_metadata_preservation(original_filepath: str, compressed_filepath: str, is_video: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """Verifies that critical tags are preserved in compressed_filepath compared to original_filepath."""
    critical_tags = [
        "EXIF:DateTimeOriginal" if not is_video else "QuickTime:CreateDate",
        "EXIF:Make" if not is_video else "QuickTime:Make",
        "EXIF:Model" if not is_video else "QuickTime:Model",
    ]
    
    orig_meta = extract_file_metadata(original_filepath)
    comp_meta = extract_file_metadata(compressed_filepath)
    
    missing_tags = []
    for tag in critical_tags:
        if orig_meta.get(tag) and not comp_meta.get(tag):
            missing_tags.append(tag)
            
    passed = len(missing_tags) == 0
    return passed, {
        "passed": passed,
        "missing_tags": missing_tags,
        "original_tag_count": len(orig_meta),
        "compressed_tag_count": len(comp_meta)
    }

def compare_metadata_side_by_side(orig_filepath: str, comp_filepath: str) -> Dict[str, Any]:
    """Generates a detailed key-by-key comparison between original and compressed metadata."""
    orig_meta = extract_file_metadata(orig_filepath)
    comp_meta = extract_file_metadata(comp_filepath)
    
    all_keys = sorted(list(set(orig_meta.keys()).union(set(comp_meta.keys()))))
    comparison = []
    
    for k in all_keys:
        val1 = orig_meta.get(k, "MISSING")
        val2 = comp_meta.get(k, "MISSING")
        match = val1 == val2
        comparison.append({
            "key": k,
            "original": str(val1),
            "compressed": str(val2),
            "match": match
        })
        
    return {
        "original_path": orig_filepath,
        "compressed_path": comp_filepath,
        "total_tags_original": len(orig_meta),
        "total_tags_compressed": len(comp_meta),
        "tags": comparison
    }
