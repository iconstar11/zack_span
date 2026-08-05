"""
Spanish Video Dubbing Pipeline

Takes a video, extracts audio, sends it to ElevenLabs for Spanish
dubbing, re-syncs the dubbed audio to the original video, and burns
karaoke-style Spanish captions.

Usage:
    python pipeline.py <video.mp4> [--start-stage N]

Stages:
    1. Extract audio (16kHz mono MP3)
    2. ElevenLabs dubbing (Spanish translation + word timestamps)
    3. Re-sync audio to video (replace audio track, pad/trim for duration)
    4. Burn karaoke captions (word-level highlighting from timestamps)
"""

import subprocess
import sys
import os


def _check_ffmpeg():
    """Verify ffmpeg and ffprobe are on PATH."""
    for tool in ["ffmpeg", "ffprobe"]:
        try:
            subprocess.run([tool, "-version"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"ERROR: {tool} not found on PATH. Install ffmpeg to continue.")
            sys.exit(1)


def _derive_paths(video_path: str) -> dict:
    """Derive all intermediate output paths from the input video basename."""
    base = os.path.splitext(video_path)[0]
    return {
        "video": video_path,
        "audio": base + "_audio.mp3",
        "dub_mp3": base + "_es_dub.mp3",
        "transcript": base + "_es_transcript.json",
        "dub_state": base + "_es_dub_state.json",
        "synced": base + "_es.mp4",
        "captioned": base + "_es_captioned.mp4",
    }


def run_pipeline(video_path: str, start_stage: int = 1):
    if not os.path.exists(video_path):
        print(f"ERROR: Video file not found: {video_path}")
        sys.exit(1)

    _check_ffmpeg()

    paths = _derive_paths(video_path)
    video_name = os.path.basename(video_path)

    print("=" * 60)
    print(f"  Spanish Dubbing Pipeline")
    print(f"  Input : {video_name}")
    print("=" * 60)
    print()

    # -- Stage 1: Extract Audio ----------------------------------------------
    if start_stage <= 1:
        from stage1_extract_audio import extract_audio
        extract_audio(paths["video"], paths["audio"])
    else:
        print(f"[Stage 1]  Skipping (--start-stage {start_stage})\n")

    # -- Stage 2: ElevenLabs Dubbing -----------------------------------------
    if start_stage <= 2:
        from stage2_elevenlabs_dub import dub_audio
        dub_audio(paths["audio"])
    else:
        print(f"[Stage 2]  Skipping (--start-stage {start_stage})\n")

    # -- Stage 3: Re-sync Audio ----------------------------------------------
    if start_stage <= 3:
        from stage3_resync_audio import resync_audio
        resync_audio(paths["video"], paths["dub_mp3"], paths["synced"])
    else:
        print(f"[Stage 3]  Skipping (--start-stage {start_stage})\n")

    # -- Stage 4: Burn Captions ----------------------------------------------
    if start_stage <= 4:
        from stage4_burn_captions import burn_captions
        burn_captions(paths["synced"], paths["transcript"], paths["captioned"])
    else:
        print(f"[Stage 4]  Skipping (--start-stage {start_stage})\n")

    # -- Summary -------------------------------------------------------------
    print("=" * 60)
    print("  Pipeline complete")
    print(f"  Dubbed video  : {paths['captioned']}")
    print(f"  Transcript    : {paths['transcript']}")
    print(f"  Dub audio     : {paths['dub_mp3']}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <video.mp4> [--start-stage N]")
        print()
        print("  --start-stage N   Resume from stage N (1-4)")
        sys.exit(1)

    video = sys.argv[1]
    start = 1

    if len(sys.argv) >= 4 and sys.argv[2] == "--start-stage":
        try:
            start = int(sys.argv[3])
            if start < 1 or start > 4:
                print("--start-stage must be 1-4")
                sys.exit(1)
        except ValueError:
            print("--start-stage must be an integer (1-4)")
            sys.exit(1)

    run_pipeline(video, start_stage=start)
