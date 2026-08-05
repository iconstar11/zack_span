import subprocess
import os


def probe_duration(path: str) -> float:
    """Return media duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def probe_video_size(path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream."""
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0",
         path],
        capture_output=True, text=True,
    )
    try:
        w, h = result.stdout.strip().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 0, 0


def run_ffmpeg(cmd: list[str]) -> None:
    """Run ffmpeg; on failure print captured stderr then re-raise."""
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("\n-- ffmpeg stderr -----------------------------------------")
        print(result.stderr.decode("utf-8", errors="replace").strip())
        print("----------------------------------------------------------\n")
        raise subprocess.CalledProcessError(result.returncode, cmd)


def esc_path_for_filter(path: str) -> str:
    """
    Escape a file path for use inside an ffmpeg filtergraph value.

    On Windows the colon in 'C:/...' is treated by ffmpeg's filter parser as
    an option separator. Using a relative path avoids the drive-letter colon
    entirely, which is more reliable than backslash escaping.
    """
    cwd = os.getcwd()
    try:
        rel = os.path.relpath(path, cwd)
        if len(rel) < 2 or rel[1] != ':':
            path = rel
    except ValueError:
        pass
    path = path.replace("\\", "/")
    return path


def build_encoder_args(crf: int) -> list[str]:
    """Return ffmpeg libx264 encoder arguments."""
    return ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium"]


def write_atomic(path: str, data: str | bytes) -> None:
    """Write data to path atomically via temp file + os.replace."""
    tmp = path + ".tmp"
    mode = "wb" if isinstance(data, bytes) else "w"
    encoding = "utf-8" if mode == "w" else None
    with open(tmp, mode, encoding=encoding) as f:
        f.write(data)
    os.replace(tmp, path)
