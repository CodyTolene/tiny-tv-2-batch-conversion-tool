import os
import tempfile
import subprocess
import queue
from pathlib import Path
from .utils import _no_console_kwargs


class FFmpegProcess:
    def __init__(self, ffmpeg_cmd: str, log_q: queue.Queue):
        self.ffmpeg = ffmpeg_cmd
        self.log_q = log_q

    def run(self, args: list[str]) -> int:
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            )
            for line in proc.stderr:
                self.log_q.put(line.strip())
            return proc.wait()
        except Exception as e:
            self.log_q.put(f"[ERROR] {e}")
            return 1

    def thumbnail(self, src: Path, vf: str, q: int, jpeg_preferred: bool) -> str | None:
        try:
            ext = ".jpg" if jpeg_preferred else ".png"
            fd, tmp = tempfile.mkstemp(prefix="tinytv_thumb_", suffix=ext)
            os.close(fd)
            cmd = [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                str(src),
                "-vframes",
                "1",
                "-vf",
                vf,
                "-pix_fmt",
                "yuv420p",
            ]
            if jpeg_preferred:
                cmd += ["-q:v", str(q)]
            cmd += [tmp]
            res = subprocess.run(cmd, **_no_console_kwargs())
            if res.returncode == 0 and os.path.exists(tmp):
                return tmp
        except Exception:
            pass
        return None

    def calibrate_video_bps(
        self, src: Path, vf: str, q: int, fps: int, sample_secs: float, vcodec: str
    ) -> float | None:
        try:
            fd, tmp = tempfile.mkstemp(prefix="tinytv_cal_", suffix=".avi")
            os.close(fd)
            cmd = [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "0",
                "-t",
                f"{sample_secs}",
                "-fflags",
                "+genpts",
                "-copytb",
                "0",
                "-i",
                str(src),
                "-vf",
                f"{vf},fps={int(fps)}",
                "-r",
                str(fps),
                "-vsync",
                "cfr",
                "-pix_fmt",
                "yuv420p",
                "-c:v",
                vcodec,
                "-vtag",
                "MJPG",
                "-q:v",
                str(int(q)),
                "-an",
                tmp,
            ]
            res = subprocess.run(cmd, **_no_console_kwargs())
            if res.returncode == 0 and os.path.exists(tmp):
                size = os.path.getsize(tmp)
                if size > 0 and sample_secs > 0:
                    return size / sample_secs
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
        return None
