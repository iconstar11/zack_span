"""
Stage 3 — Resync Audio

Muxes the dubbed Spanish audio onto the original video track.
Video stream is copied losslessly (-c:v copy). If the Spanish audio
duration differs from the original video (Spanish translations often
run longer or shorter), the audio is padded or trimmed to match.
"""

import os
import sys
from typing import Optional

import config
from ffmpeg_utils import probe_duration, run_ffmpeg


def resync_audio(
    video_path: str,
    dub_mp3_path: str,
    output_path: Optional[str] = None,
) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(dub_mp3_path):
        raise FileNotFoundError(f"Dubbed audio file not found: {dub_mp3_path}")

    if output_path is None:
        base = os.path.splitext(video_path)[0]
        if base.endswith("_audio"):
            base = base[:-6]
        output_path = base + "_es.mp4"

    if os.path.exists(output_path):
        print(f"[Stage 3]  Skip -- {output_path}\n")
        return output_path

    video_dur = probe_duration(video_path)
    dub_dur = probe_duration(dub_mp3_path)
    diff = abs(video_dur - dub_dur)

    print(f"[Stage 3] Re-syncing Spanish audio to video")
    print(f"          Video duration : {video_dur:.2f}s")
    print(f"          Dub duration   : {dub_dur:.2f}s")
    print(f"          Difference     : {diff:.2f}s")

    tolerance = config.MIN_SYNC_TOLERANCE_SEC

    if diff <= tolerance:
        print(f"          Within tolerance ({tolerance}s), direct mux\n")
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dub_mp3_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ])
    elif dub_dur < video_dur:
        print(f"          Padding audio to match video (+{diff:.2f}s)\n")
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dub_mp3_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-af", f"apad=whole_dur={video_dur}",
            "-shortest",
            output_path,
        ])
    else:
        print(f"          Trimming audio to match video (-{diff:.2f}s)\n")
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dub_mp3_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(video_dur),
            output_path,
        ])

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"          Saved : {output_path}  ({size_mb:.1f} MB)\n")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage3_resync_audio.py <video.mp4> <dub_es.mp3> [output.mp4]")
        sys.exit(1)

    out = sys.argv[3] if len(sys.argv) > 3 else None
    resync_audio(sys.argv[1], sys.argv[2], out)
