"""
Stage 5 — YouTube Metadata Generation

Extracts the original English title from the video, translates it to
Spanish, and builds a description from the dubbed transcript.

Output: _meta.json alongside the captioned video.
"""

import json
import os
import re
import subprocess
import sys
from typing import Optional

# Fix Unicode output on Windows terminals (emoji in filenames etc.)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from deep_translator import GoogleTranslator


def _extract_title(video_path: str) -> str:
    """
    Extract the English title from the video's MP4 metadata tag.
    Falls back to a cleaned version of the filename.
    """
    # Try ffprobe metadata first
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format_tags=title",
             "-of", "default=noprint_wrappers=1:nokey=1",
             video_path],
            capture_output=True, text=True,
        )
        tag = result.stdout.strip()
        if tag:
            return tag
    except Exception:
        pass

    # Fallback: clean the filename
    name = os.path.splitext(os.path.basename(video_path))[0]
    # Strip suffixes we added
    for suffix in ("_es_captioned", "_es", "_audio"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    # Strip resolution/codec info in parentheses
    name = re.sub(r'\s*\([^)]*(?:720p|1080p|h264|mp4)[^)]*\)\s*', '', name)
    return name.strip()


def _translate_title(en_title: str) -> str:
    """Translate the English title to Spanish using Google Translate."""
    try:
        translated = GoogleTranslator(source="en", target="es").translate(en_title)
        return translated
    except Exception as e:
        print(f"          [WARN] Title translation failed: {e}")
        return en_title


def _build_description(transcript: dict) -> str:
    """
    Build a Spanish description from the first 2 utterances of the transcript.
    """
    utterances = transcript.get("utterances", [])
    if not utterances:
        return ""

    # Take first 1-2 utterances as the hook (max ~300 chars for YouTube Shorts)
    parts = []
    chars = 0
    for utt in utterances[:2]:
        text = utt.get("text", "").strip()
        if text and chars + len(text) <= 300:
            parts.append(text)
            chars += len(text)

    description = " ".join(parts)
    return description


def _build_hashtags() -> list[str]:
    """Return standard hashtags from the channel guide."""
    return [
        "#ZackSpanish", "#Curiosidades", "#DatosIncreibles",
        "#YouTubeShorts", "#Historia", "#Ciencia",
    ]


def generate_metadata(
    video_path: str,
    transcript_path: str,
    output_path: Optional[str] = None,
) -> dict:
    """
    Generate YouTube metadata for a dubbed video.

    Returns the metadata dict. If output_path is given, writes _meta.json.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(transcript_path):
        raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

    if output_path is None:
        base = os.path.splitext(video_path)[0]
        # Strip suffixes to get clean base name
        for sfx in ("_es_captioned", "_es"):
            if base.endswith(sfx):
                base = base[:-len(sfx)]
                break
        output_path = base + "_meta.json"

    if os.path.exists(output_path):
        print(f"[Stage 5]  Skip -- {output_path}\n")
        with open(output_path, encoding="utf-8") as f:
            return json.load(f)

    print(f"[Stage 5] Generating YouTube metadata")

    # Extract and translate title
    en_title = _extract_title(video_path)
    print(f"          Title (en) : {en_title}")

    es_title = _translate_title(en_title)
    print(f"          Title (es) : {es_title}")

    # Build description from transcript
    with open(transcript_path, encoding="utf-8") as f:
        transcript = json.load(f)

    description = _build_description(transcript)
    print(f"          Description : {description[:80]}...")

    # Hashtags
    hashtags = _build_hashtags()

    meta = {
        "title_es": es_title,
        "title_en": en_title,
        "description": description,
        "hashtags": hashtags,
    }

    # Atomic write
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    os.replace(tmp, output_path)

    print(f"          Saved : {output_path}\n")
    return meta


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage5_metadata.py <video.mp4> <transcript.json> [output.json]")
        sys.exit(1)

    out = sys.argv[3] if len(sys.argv) > 3 else None
    generate_metadata(sys.argv[1], sys.argv[2], out)
