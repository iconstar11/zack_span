"""
Stage 2 — Audio -> ElevenLabs Dubbing (Spanish)

Uploads extracted audio to ElevenLabs Dubbing API, polls until complete,
downloads the dubbed Spanish MP3 and word-level transcript JSON.

Resumability: persists a state file with the dubbing_id so a crashed/
interrupted run can resume polling the same job instead of creating a
duplicate (which would double-charge credits).
"""

import json
import os
import sys
import time
from typing import Optional

from elevenlabs import ElevenLabs

import config
from ffmpeg_utils import write_atomic


# ---------------------------------------------------------------------------
#  RETRY WRAPPER
# ---------------------------------------------------------------------------

def _retry_call(fn, max_attempts: int = 5, label: str = "API call"):
    """
    Call fn() with exponential backoff on transient errors.
    Retries on connection errors, HTTP 429, and 5xx.
    Fatal errors (401, 403, 422) are re-raised immediately.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            is_transient = (
                "429" in msg
                or "5" in str(getattr(e, "status_code", ""))
                or "connection" in msg
                or "timeout" in msg
                or "rate" in msg
            )
            if not is_transient or attempt == max_attempts:
                raise
            wait = 2 ** attempt
            print(f"          {label} failed (attempt {attempt}/{max_attempts}), "
                  f"retrying in {wait}s...")
            time.sleep(wait)


# ---------------------------------------------------------------------------
#  MAIN
# ---------------------------------------------------------------------------

def dub_audio(audio_path: str, base_path: Optional[str] = None) -> tuple[str, str]:
    """
    Send audio to ElevenLabs for Spanish dubbing.

    Returns (dubbed_mp3_path, transcript_json_path).

    State file (base_path + "_dub_state.json") persists the dubbing_id
    so a crashed run can resume without creating a duplicate job.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if base_path is None:
        base_path = os.path.splitext(audio_path)[0]
        # Strip _audio suffix if present so intermediates are named after the video
        if base_path.endswith("_audio"):
            base_path = base_path[:-6]

    dub_mp3_path = base_path + "_es_dub.mp3"
    transcript_path = base_path + "_es_transcript.json"
    state_path = base_path + "_es_dub_state.json"

    # -- Already done? -------------------------------------------------------
    if os.path.exists(dub_mp3_path) and os.path.exists(transcript_path):
        print(f"[Stage 2]  Skip -- {dub_mp3_path}\n")
        return dub_mp3_path, transcript_path

    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    # -- Resume or create ----------------------------------------------------
    dubbing_id = None
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            dubbing_id = state.get("dubbing_id")
            print(f"[Stage 2] Resuming dubbing job: {dubbing_id}")
        except (json.JSONDecodeError, KeyError):
            print("[Stage 2]  Corrupt state file, creating new dubbing job")

    if not dubbing_id:
        print(f"[Stage 2] Sending audio to ElevenLabs for Spanish dubbing")
        print(f"          Source : {audio_path}")
        print(f"          Target : {config.ELEVENLABS_SOURCE_LANG} -> "
              f"{config.ELEVENLABS_TARGET_LANG}")

        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        est_cost_min = file_size_mb / 0.4 * 0.05  # rough ~$0.33–0.50/min of source
        print(f"          Size   : {file_size_mb:.1f} MB")
        print(f"          Uploading...")

        def _create():
            with open(audio_path, "rb") as f:
                return client.dubbing.dub_a_video_or_an_audio_file(
                    file=f,
                    source_lang=config.ELEVENLABS_SOURCE_LANG,
                    target_lang=config.ELEVENLABS_TARGET_LANG,
                    num_speakers=0,
                )

        resp = _retry_call(_create, label="Create dubbing job")
        dubbing_id = resp.dubbing_id
        print(f"          Dubbing ID : {dubbing_id}")

        # Persist state immediately
        write_atomic(state_path, json.dumps({
            "dubbing_id": dubbing_id,
            "source_lang": config.ELEVENLABS_SOURCE_LANG,
            "target_lang": config.ELEVENLABS_TARGET_LANG,
        }, indent=2))

    # -- Poll until complete -------------------------------------------------
    poll_interval = config.ELEVENLABS_POLL_INTERVAL_SEC
    timeout_sec = config.ELEVENLABS_POLL_TIMEOUT_MIN * 60
    elapsed = 0
    last_status = ""

    print(f"          Polling (every {poll_interval}s, timeout {config.ELEVENLABS_POLL_TIMEOUT_MIN}m)...")

    while True:
        def _poll():
            return client.dubbing.get_dubbing_project_metadata(dubbing_id=dubbing_id)

        meta = _retry_call(_poll, label="Poll dubbing status")
        status = "dubbing" if getattr(meta, "in_progress", True) else "completed"

        if status != last_status:
            print(f"          Status : {status}")
            last_status = status

        if not getattr(meta, "in_progress", True):
            break

        if elapsed >= timeout_sec:
            raise TimeoutError(
                f"Dubbing timed out after {config.ELEVENLABS_POLL_TIMEOUT_MIN} minutes. "
                f"State file preserved at {state_path} — re-run to resume."
            )

        time.sleep(poll_interval)
        elapsed += poll_interval

    # Check for failure
    if hasattr(meta, "status") and getattr(meta, "status", "") == "failed":
        error_msg = getattr(meta, "error_message", "Unknown error")
        raise RuntimeError(f"ElevenLabs dubbing failed: {error_msg}")

    print(f"          Dubbing complete")

    # -- Download dubbed audio -----------------------------------------------
    if not os.path.exists(dub_mp3_path):
        print(f"          Downloading Spanish audio...")

        def _download_audio():
            chunks = []
            for chunk in client.dubbing.get_dubbed_file(
                dubbing_id=dubbing_id,
                language_code=config.ELEVENLABS_TARGET_LANG,
            ):
                chunks.append(chunk)
            return b"".join(chunks)

        audio_bytes = _retry_call(_download_audio, label="Download audio")
        write_atomic(dub_mp3_path, audio_bytes)
        size_mb = len(audio_bytes) / (1024 * 1024)
        print(f"          Audio saved : {dub_mp3_path}  ({size_mb:.1f} MB)")

    # -- Download transcript -------------------------------------------------
    if not os.path.exists(transcript_path):
        print(f"          Downloading transcript...")

        def _download_transcript():
            return client.dubbing.get_dubbed_transcript(
                dubbing_id=dubbing_id,
                language_code=config.ELEVENLABS_TARGET_LANG,
                format_type="json",
            )

        transcript = _retry_call(_download_transcript, label="Download transcript")
        # The SDK may return a dict or a raw string
        if isinstance(transcript, str):
            data = transcript
        elif isinstance(transcript, dict):
            data = json.dumps(transcript, indent=2, ensure_ascii=False)
        else:
            data = str(transcript)

        write_atomic(transcript_path, data)
        print(f"          Transcript saved : {transcript_path}")

    print()
    return dub_mp3_path, transcript_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stage2_elevenlabs_dub.py <audio.mp3> [base_path]")
        sys.exit(1)

    bp = sys.argv[2] if len(sys.argv) > 2 else None
    dub_audio(sys.argv[1], bp)
