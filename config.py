import os
from dotenv import load_dotenv

load_dotenv()

# -- API Keys --------------------------------------------------------------------
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# -- Dubbing settings ------------------------------------------------------------
ELEVENLABS_SOURCE_LANG = os.getenv("ELEVENLABS_SOURCE_LANG", "en")
ELEVENLABS_TARGET_LANG = os.getenv("ELEVENLABS_TARGET_LANG", "es")
ELEVENLABS_POLL_INTERVAL_SEC = int(os.getenv("ELEVENLABS_POLL_INTERVAL_SEC", "10"))
ELEVENLABS_POLL_TIMEOUT_MIN = int(os.getenv("ELEVENLABS_POLL_TIMEOUT_MIN", "120"))

# -- Audio extraction ------------------------------------------------------------
EXTRACT_SAMPLE_RATE = int(os.getenv("EXTRACT_SAMPLE_RATE", "16000"))
EXTRACT_CHANNELS = int(os.getenv("EXTRACT_CHANNELS", "1"))
EXTRACT_BITRATE = os.getenv("EXTRACT_BITRATE", "32k")

# -- Caption settings ------------------------------------------------------------
CAPTION_MODE = os.getenv("CAPTION_MODE", "karaoke")       # karaoke | static
CAPTION_CHUNK_MAX_WORDS = int(os.getenv("CAPTION_CHUNK_MAX_WORDS", "3"))
CAPTION_FONT = os.getenv("CAPTION_FONT", "Poppins-Bold.ttf")
CAPTION_FONT_SCALE = float(os.getenv("CAPTION_FONT_SCALE", "0.045"))
CAPTION_MARGIN_FRACTION = float(os.getenv("CAPTION_MARGIN_FRACTION", "0.10"))
MIN_WORDS_PER_CHUNK = 1
MAX_WORDS_PER_CHUNK = CAPTION_CHUNK_MAX_WORDS

# -- Video encoding --------------------------------------------------------------
X264_CRF = int(os.getenv("X264_CRF", "17"))
X264_PRESET = os.getenv("X264_PRESET", "medium")

# -- Sync tolerance --------------------------------------------------------------
MIN_SYNC_TOLERANCE_SEC = float(os.getenv("MIN_SYNC_TOLERANCE_SEC", "0.5"))

# -- Sanity checks ---------------------------------------------------------------
if not ELEVENLABS_API_KEY:
    raise EnvironmentError("ELEVENLABS_API_KEY not found in .env")
