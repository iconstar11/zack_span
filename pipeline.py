"""
Spanish Video Dubbing Pipeline

Two modes:
    python pipeline.py                  Scan input/ for new videos, process all
    python pipeline.py <video.mp4>      Process a single video (legacy mode)

Stages:
    1. Extract audio (16kHz mono MP3)
    2. ElevenLabs dubbing (Spanish translation + word timestamps)
    3. Re-sync audio to video (replace audio track, pad/trim for duration)
    4. Burn karaoke captions (word-level highlighting from timestamps)

Outputs: es/ folder, with final copy in to_post/
Dedup:   SHA256 hash prevents re-processing the same video
"""

import shutil
import subprocess
import sys
import os
from pathlib import Path

# Fix Unicode output on Windows terminals (emoji in filenames etc.)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent
INPUT_DIR = PROJECT_ROOT / "input"
ES_DIR = PROJECT_ROOT / "es"
TO_POST_DIR = PROJECT_ROOT / "to_post"


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
    """Derive all output paths in the es/ subdirectory."""
    base = os.path.splitext(os.path.basename(video_path))[0]
    return {
        "video": video_path,
        "audio": str(ES_DIR / (base + "_audio.mp3")),
        "dub_mp3": str(ES_DIR / (base + "_es_dub.mp3")),
        "transcript": str(ES_DIR / (base + "_es_transcript.json")),
        "dub_state": str(ES_DIR / (base + "_es_dub_state.json")),
        "synced": str(ES_DIR / (base + "_es.mp4")),
        "captioned": str(ES_DIR / (base + "_es_captioned.mp4")),
    }


def run_single(video_path: str) -> str | None:
    """
    Process a single video through all 4 stages.
    Returns the captioned video path, or None on failure.
    """
    from db import init_db, hash_file, lookup_video, insert_video, update_status

    init_db()

    if not os.path.exists(video_path):
        print(f"ERROR: Video file not found: {video_path}")
        return None

    _check_ffmpeg()

    # -- Dedup check -----------------------------------------------------------
    print("Hashing video for dedup...")
    fhash = hash_file(video_path)
    existing = lookup_video(fhash)
    if existing and existing["status"] in ("completed", "ready", "posted"):
        print(f"  SKIP -- already processed (id={existing['id']}, status={existing['status']})\n")
        return None

    # -- Register in DB --------------------------------------------------------
    if existing:
        video_id = existing["id"]
    else:
        video_id = insert_video(os.path.basename(video_path), fhash, video_path)
    update_status(video_id, "processing")

    paths = _derive_paths(video_path)
    video_name = os.path.basename(video_path)

    print("=" * 60)
    print(f"  Spanish Dubbing Pipeline")
    print(f"  Input : {video_name}")
    print(f"  DB id : {video_id}")
    print("=" * 60)
    print()

    try:
        # -- Stage 1: Extract Audio --------------------------------------------
        from stage1_extract_audio import extract_audio
        extract_audio(paths["video"], paths["audio"])

        # -- Stage 2: ElevenLabs Dubbing ---------------------------------------
        from stage2_elevenlabs_dub import dub_audio
        dub_audio(paths["audio"])

        # -- Stage 3: Re-sync Audio --------------------------------------------
        from stage3_resync_audio import resync_audio
        resync_audio(paths["video"], paths["dub_mp3"], paths["synced"])

        # -- Stage 4: Burn Captions --------------------------------------------
        from stage4_burn_captions import burn_captions
        burn_captions(paths["synced"], paths["transcript"], paths["captioned"])

        # -- Copy to to_post/ --------------------------------------------------
        captioned_name = os.path.basename(paths["captioned"])
        to_post_dst = str(TO_POST_DIR / captioned_name)
        if not os.path.exists(to_post_dst):
            shutil.copy2(paths["captioned"], to_post_dst)

        # -- Update DB ---------------------------------------------------------
        update_status(video_id, "completed",
                      es_video=paths["synced"],
                      es_captioned=paths["captioned"])

        print("=" * 60)
        print("  Pipeline complete")
        print(f"  Dubbed video  : {paths['captioned']}")
        print(f"  Ready to post : {to_post_dst}")
        print(f"  Transcript    : {paths['transcript']}")
        print("=" * 60)

        return paths["captioned"]

    except Exception as e:
        update_status(video_id, "failed", error=str(e)[:500])
        print(f"\n  PIPELINE FAILED: {e}")
        raise


def run_batch() -> dict[str, str | None]:
    """
    Scan input/ for .mp4 files and process all new ones.
    Returns {filename: captioned_path | None} for each video.
    """
    _check_ffmpeg()

    # Ensure directories exist
    INPUT_DIR.mkdir(exist_ok=True)
    ES_DIR.mkdir(exist_ok=True)
    TO_POST_DIR.mkdir(exist_ok=True)

    videos = sorted(INPUT_DIR.glob("*.mp4"))
    if not videos:
        print("No .mp4 files found in input/")
        print(f"Drop videos into: {INPUT_DIR}")
        return {}

    print(f"Found {len(videos)} video(s) in input/")
    print()

    results = {}
    for i, video_path in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {video_path.name}")
        try:
            results[video_path.name] = run_single(str(video_path))
        except Exception:
            results[video_path.name] = None

    # Summary
    success = sum(1 for v in results.values() if v)
    skipped = len(results) - success
    print(f"\nDone: {success} processed, {skipped} skipped/failed")
    return results


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        # Single-video mode
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

        if start == 1:
            run_single(video)
        else:
            # Partial resume: run stages directly (bypasses DB/dedup)
            _check_ffmpeg()
            paths = _derive_paths(video)
            if start <= 1:
                from stage1_extract_audio import extract_audio
                extract_audio(paths["video"], paths["audio"])
            if start <= 2:
                from stage2_elevenlabs_dub import dub_audio
                dub_audio(paths["audio"])
            if start <= 3:
                from stage3_resync_audio import resync_audio
                resync_audio(paths["video"], paths["dub_mp3"], paths["synced"])
            if start <= 4:
                from stage4_burn_captions import burn_captions
                burn_captions(paths["synced"], paths["transcript"], paths["captioned"])
    else:
        # Batch mode: scan input/
        run_batch()
