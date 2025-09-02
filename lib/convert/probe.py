import subprocess
from pathlib import Path
from .utils import _no_console_kwargs


class Probe:
    def __init__(self, ffmpeg_cmd: str):
        self.ffprobe = self._guess_ffprobe(ffmpeg_cmd)

    @staticmethod
    def _guess_ffprobe(ffmpeg_cmd: str) -> str:
        try:
            p = Path(ffmpeg_cmd)
            name = p.name.lower()
            if name.startswith("ffmpeg"):
                candidate = p.with_name(name.replace("ffmpeg", "ffprobe"))
                if candidate.exists():
                    return str(candidate)
        except Exception:
            pass
        return "ffprobe"

    def audio_info(self, src: Path) -> dict:
        info = {"codec_name": None, "sample_rate": None, "channels": None}
        try:
            out = subprocess.run(
                [
                    self.ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_streams",
                    "-of",
                    "default=noprint_wrappers=1",
                    str(src),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            ).stdout
            for line in out.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k in info:
                        info[k] = v
        except Exception:
            pass
        return info

    def duration(self, src: Path) -> float | None:
        try:
            out = subprocess.run(
                [
                    self.ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(src),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            )
            val = out.stdout.strip()
            return float(val) if val else None
        except Exception:
            return None

    def stream_info(self, src: Path) -> dict:
        info = {
            "r_frame_rate": None,
            "avg_frame_rate": None,
            "nb_frames": None,
            "duration": None,
            "codec_tag_string": None,
        }
        try:
            out = subprocess.run(
                [
                    self.ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "default=noprint_wrappers=1",
                    str(src),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            ).stdout
            for line in out.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k in info:
                        info[k] = v
                    if k == "duration" and not info["duration"]:
                        info["duration"] = v
        except Exception:
            pass
        return info
