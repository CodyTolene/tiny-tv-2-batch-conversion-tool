import os
import tempfile
import subprocess
import queue
from pathlib import Path
from lib.utils import _no_console_kwargs


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
        self,
        src: Path,
        vf: str,
        q_val: int,
        fps: int,
        sample_secs: float,
        a_codec: str,  # Unused
        a_rate: str,  # Unused
        a_ch: str,  # Unused
        p_format: str,
        v_codec: str,
    ) -> float | None:
        try:
            fd, tmp = tempfile.mkstemp(prefix="tinytv_cal_", suffix=".avi")
            os.close(fd)

            # Command tuples
            logLevel = ["-hide_banner", "-loglevel", "error", "-stats"]
            overwriteIfExists = ["-y"]
            inputSource = ["-i", str(src)]
            videoFilters = ["-vf", vf]
            outputRate = ["-r", str(int(fps))]
            pixelFormat = ["-pix_fmt", p_format]
            videoCodec = ["-c:v", v_codec]
            videoQuality = ["-q:v", str(int(q_val))]

            # Unused
            # constantFrameRate = ["-vsync", "cfr"]
            # videoCodecTag = ["-vtag", "MJPG"]
            # audioCodec = ["-acodec", str(a_codec)]
            # audioRate = ["-ar", str(a_rate)]
            # audioChannels = ["-ac", str(a_ch)]

            # Specific for check
            startingFrame = ["-ss", "0"]
            duration = ["-t", f"{sample_secs}"]
            generatePresentationTimestamps = ["-fflags", "+genpts"]
            copyTimeBase = ["-copytb", "0"]
            disableAudio = ["-an"]

            cmd = [
                self.ffmpeg,
                *logLevel,
                *overwriteIfExists,
                *startingFrame,
                *duration,
                *generatePresentationTimestamps,
                *copyTimeBase,
                *inputSource,
                *videoFilters,
                *outputRate,
                *pixelFormat,
                *videoCodec,
                *videoQuality,
                *disableAudio,
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
