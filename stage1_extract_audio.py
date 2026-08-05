"""
Stage 1 — Video -> MP3

Extracts audio as mono MP3 from the input video.
Configurable sample rate and bitrate via .env / config.py.
"""

import subprocess
import sys
import os
from typing import Optional

import config
from ffmpeg_utils import probe_duration


def extract_audio(video_path: str, output_path: Optional[str] = None) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if output_path is None:
        base = os.path.splitext(video_path)[0]
        output_path = base + "_audio.mp3"

    if os.path.exists(output_path):
        print(f"[Stage 1]  Skip -- {output_path}\n")
        return output_path

    duration = probe_duration(video_path)
    dur_str = f"{int(duration // 60)}m {int(duration % 60)}s" if duration else "unknown"

    print(f"[Stage 1] Extracting audio")
    print(f"          Source   : {video_path}")
    print(f"          Duration : {dur_str}")
    print(f"          Output   : {output_path}")
    print(f"          Progress    (this may take several minutes for long videos)\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-nostdin",
        "-loglevel", "error",
        "-stats",
        "-i", video_path,
        "-vn",
        "-map", "0:a:0",
        "-ar", str(config.EXTRACT_SAMPLE_RATE),
        "-ac", str(config.EXTRACT_CHANNELS),
        "-b:a", config.EXTRACT_BITRATE,
        output_path,
    ], check=True)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n          Saved    : {output_path}  ({size_mb:.1f} MB)\n")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stage1_extract_audio.py <video_file> [output.mp3]")
        sys.exit(1)

    out = sys.argv[2] if len(sys.argv) > 2 else None
    extract_audio(sys.argv[1], out)
