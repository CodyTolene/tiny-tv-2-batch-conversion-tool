FRAME_WIDTH = 210
FRAME_HEIGHT = 135
FPS_CHOICES = (12, 24)

VIDEO_CODEC = "mjpeg"
AUDIO_CODEC = "pcm_u8"
AUDIO_RATE = "10000"
AUDIO_CHANNEL = "1"
PIXEL_FORMAT = "yuv420p"

VIDEO_EXTENSIONS = (
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".wmv",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".flv",
)

VIDEO_FILETYPES = [
    ("Video files", [f"*{ext}" for ext in VIDEO_EXTENSIONS]),
    ("All files", "*.*"),
]
