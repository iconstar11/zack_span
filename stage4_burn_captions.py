"""
Stage 4 — Burn Spanish Captions

Reads word-level transcript JSON (from ElevenLabs dubbing output),
groups words into caption cards, builds karaoke-style ASS subtitles,
and burns them onto the video.

Aspect-ratio agnostic: font size and margins scale proportionally
to the probed video dimensions. PlayResX/Y match the source video.
"""

import json
import os
import sys
from typing import Optional

import config
from ffmpeg_utils import run_ffmpeg, esc_path_for_filter, probe_video_size


# ---------------------------------------------------------------------------
#  ASS TIME FORMATTER
# ---------------------------------------------------------------------------

def _fmt_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
#  WORD CHUNKER
# ---------------------------------------------------------------------------

def _chunk_words(words: list[dict], max_w: int) -> list[list[dict]]:
    """Group words into caption cards of at most max_w words each."""
    chunks: list[list[dict]] = []
    i = 0
    while i < len(words):
        chunk = words[i:i + max_w]
        chunks.append(chunk)
        i += max_w
    return chunks


# ---------------------------------------------------------------------------
#  ASS HEADER (aspect-ratio agnostic)
# ---------------------------------------------------------------------------

def _ass_header(
    width: int,
    height: int,
    font: str,
    fontsize: int,
    margin_v: int,
    primary: str = "&H00FFFFFF",
    spoken: str = "&H0000FFFF",
    outline_c: str = "&H00000000",
) -> str:
    """Build the ASS script header with styles scaled to the video dimensions."""
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
        "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{font},{fontsize},{primary},&H000000FF,"
        f"{outline_c},&H00000000,-1,0,0,0,"
        f"100,100,0,0,1,3,2,"
        f"5,10,10,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )


# ---------------------------------------------------------------------------
#  KARAOKE ASS BUILDER
# ---------------------------------------------------------------------------

def _build_karaoke_ass(
    words: list[dict],
    ass_path: str,
    width: int,
    height: int,
    font: str,
    fontsize: int,
    margin_v: int,
) -> None:
    """
    Generate a karaoke ASS file where each word gets its own Dialogue line
    and the active word is highlighted in yellow while others stay white.
    """
    spoken = "&H0000FFFF"    # yellow — active word
    unspoken = "&H00FFFFFF"  # white  — waiting words

    chunks = _chunk_words(words, config.MAX_WORDS_PER_CHUNK)
    lines = [_ass_header(width, height, font, fontsize, margin_v,
                         primary=unspoken, spoken=spoken)]

    for chunk in chunks:
        if not chunk:
            continue
        for active_idx, active_word in enumerate(chunk):
            w_start = active_word["start"]
            w_end = active_word["end"]

            parts = []
            for idx, w in enumerate(chunk):
                text = w["word"].upper()
                if idx == active_idx:
                    parts.append(f"{{\\c{spoken}}}{text}{{\\c{unspoken}}}")
                else:
                    parts.append(f"{{\\c{unspoken}}}{text}")
            card_text = " ".join(parts)

            lines.append(
                f"Dialogue: 0,{_fmt_ass_time(w_start)},{_fmt_ass_time(w_end)},"
                f"Default,,0,0,0,,{{\\c{unspoken}}}{card_text}\n"
            )

    with open(ass_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
#  MAIN
# ---------------------------------------------------------------------------

def burn_captions(
    video_path: str,
    transcript_json_path: str,
    output_path: Optional[str] = None,
) -> tuple[str, str]:
    """
    Burn karaoke captions onto video_path using word timestamps from
    transcript_json_path. Returns (output_video_path, ass_path).
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(transcript_json_path):
        raise FileNotFoundError(f"Transcript file not found: {transcript_json_path}")

    if output_path is None:
        base = os.path.splitext(video_path)[0]
        output_path = base + "_captioned.mp4"

    ass_path = os.path.splitext(output_path)[0] + ".ass"

    if os.path.exists(output_path):
        print(f"[Stage 4]  Skip -- {output_path}\n")
        return output_path, ass_path

    # Probe video dimensions for aspect-ratio-agnostic caption sizing
    width, height = probe_video_size(video_path)
    if width == 0 or height == 0:
        width, height = 1080, 1920

    fontsize = round(width * config.CAPTION_FONT_SCALE)
    margin_v = round(height * config.CAPTION_MARGIN_FRACTION)

    # Resolve font path
    font_path = os.path.join(os.path.dirname(__file__), "fonts", config.CAPTION_FONT)
    if not os.path.exists(font_path):
        font_path = config.CAPTION_FONT  # fall back to system font name

    # Load transcript and flatten words
    with open(transcript_json_path, encoding="utf-8") as f:
        transcript = json.load(f)

    words = _flatten_words(transcript)

    print(f"[Stage 4] Burning captions")
    print(f"          Video      : {video_path}")
    print(f"          Resolution : {width}x{height}")
    print(f"          Font       : {os.path.basename(font_path)}  ({fontsize}px)")
    print(f"          Words      : {len(words)}")
    print(f"          Output     : {output_path}\n")

    # Build ASS and burn
    _build_karaoke_ass(words, ass_path, width, height, font_path, fontsize, margin_v)

    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass={esc_path_for_filter(ass_path)}",
        "-c:v", "libx264", "-crf", str(config.X264_CRF),
        "-preset", config.X264_PRESET,
        "-c:a", "copy",
        output_path,
    ])

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"          Saved     : {output_path}  ({size_mb:.1f} MB)")
    print(f"          ASS       : {ass_path}\n")
    return output_path, ass_path


# ---------------------------------------------------------------------------
#  TRANSCRIPT FLATTENER
# ---------------------------------------------------------------------------

def _flatten_words(transcript: dict) -> list[dict]:
    """
    Normalise ElevenLabs transcript JSON into a flat list of
    {"word": str, "start": float, "end": float} dicts.

    Accepts nested layouts (paragraphs -> sentences -> words) and
    flat layouts. Tolerates both "start"/"start_s" field names.
    """
    # Already flat?
    if isinstance(transcript.get("words"), list):
        raw = transcript["words"]
    elif isinstance(transcript.get("utterances"), list):
        raw = []
        for utt in transcript["utterances"]:
            raw.extend(utt.get("words", []))
    else:
        paragraphs = transcript.get("paragraphs", [])
        raw = []
        for para in paragraphs:
            for sent in para.get("sentences", []):
                raw.extend(sent.get("words", []))

    if not raw:
        raise ValueError(
            "Could not extract words from transcript. "
            f"First 200 chars: {json.dumps(transcript)[:200]}"
        )

    out = []
    for w in raw:
        word_text = w.get("word", w.get("text", ""))
        start_val = w.get("start", w.get("start_s"))
        end_val = w.get("end", w.get("end_s"))

        if not word_text or start_val is None or end_val is None:
            continue
        if start_val < 0 or end_val < 0:
            continue

        out.append({"word": word_text, "start": float(start_val), "end": float(end_val)})

    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage4_burn_captions.py <video.mp4> <transcript.json> [output.mp4]")
        sys.exit(1)

    out = sys.argv[3] if len(sys.argv) > 3 else None
    burn_captions(sys.argv[1], sys.argv[2], out)
