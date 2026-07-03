import os
import subprocess
import logging
from typing import Tuple, Dict, Any
import metadata

logger = logging.getLogger("compression")

# Tier presets for video and photo
VIDEO_TIERS = {
    "original": None,
    "high": {"scale": "-2:1080", "crf": "26", "preset": "medium"},
    "medium": {"scale": "-2:720", "crf": "28", "preset": "slow"},
    "compact": {"scale": "-2:480", "crf": "30", "preset": "slow"}
}

PHOTO_TIERS = {
    "original": None,
    "high": {"size": "3024", "quality": "75"},
    "medium": {"size": "2048", "quality": "65"},
    "compact": {"size": "1440", "quality": "55"}
}

def is_video_file(filepath: str) -> bool:
    ext = filepath.split(".")[-1].lower()
    return ext in ["mp4", "mov", "m4v", "avi", "mts", "mkv", "3gp"]

def compress_video(original_path: str, target_tier: str, output_path: str) -> bool:
    preset = VIDEO_TIERS.get(target_tier)
    if not preset:
        logger.error(f"Invalid video tier: {target_tier}")
        return False
        
    cmd = [
        "ffmpeg", "-y",
        "-i", original_path,
        "-map", "0",
        "-map_metadata", "0",
        "-movflags", "use_metadata_tags+faststart",
        "-c:v", "libx265",
        "-crf", preset["crf"],
        "-preset", preset["preset"],
        "-vf", f"scale={preset['scale']}",
        "-c:a", "copy",
        "-c:s", "copy",
        "-tag:v", "hvc1",
        output_path
    ]
    logger.info(f"Running ffmpeg compression for {original_path} to {target_tier}...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0

def compress_photo(original_path: str, target_tier: str, output_path: str) -> bool:
    preset = PHOTO_TIERS.get(target_tier)
    if not preset:
        logger.error(f"Invalid photo tier: {target_tier}")
        return False
        
    cmd = [
        "vipsthumbnail", original_path,
        f"--size={preset['size']}",
        "-o", f"{output_path}[Q={preset['quality']}]"
    ]
    logger.info(f"Running libvips thumbnail compression for {original_path} to {target_tier}...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0

def compress_media_tier(original_path: str, target_tier: str, output_dir: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Compresses NAS original to target tier, copies metadata, and runs metadata verification gate."""
    if target_tier == "original":
        return True, original_path, {"status": "original_kept"}
        
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(original_path)
    is_video = is_video_file(original_path)
    output_path = os.path.join(output_dir, f"compressed_{target_tier}_{filename}")
    
    if is_video:
        success = compress_video(original_path, target_tier, output_path)
    else:
        success = compress_photo(original_path, target_tier, output_path)
        
    if not success:
        return False, "", {"error": "compression_failed"}
        
    # Copy metadata from original
    meta_copied = metadata.copy_all_metadata(original_path, output_path)
    if not meta_copied:
        logger.warning(f"Metadata copy failed or had warnings for {output_path}")
        
    # Run Verification Gate
    verified, report = metadata.verify_metadata_preservation(original_path, output_path, is_video=is_video)
    if not verified:
        logger.error(f"Metadata Verification GATE FAILED for {output_path}! Report: {report}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False, "", {"error": "metadata_verification_gate_failed", "report": report}
        
    orig_size = os.path.getsize(original_path)
    comp_size = os.path.getsize(output_path)
    ratio = comp_size / float(orig_size) if orig_size > 0 else 1.0
    
    report["original_size"] = orig_size
    report["compressed_size"] = comp_size
    report["compression_ratio"] = ratio
    
    return True, output_path, report
