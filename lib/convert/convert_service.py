import threading
from pathlib import Path
from typing import Callable, Iterable
from lib.probe import Probe
from lib.ffmpeg_proc import FFmpegProcess
from lib.convert.size_estimator import SizeEstimator

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int], None]  # current, total
RunningFn = Callable[[bool], None]


class ConvertService:
    def __init__(
        self,
        ffmpeg_cmd: str,
        *,
        out_w: int,
        out_h: int,
        fps: int,
        v_codec: str,
        a_codec: str,
        a_rate: str,
        a_ch: str,
        p_format: str,
        on_log: LogFn,
        on_progress: ProgressFn,
        on_running_changed: RunningFn | None = None,
    ):
        self.probe = Probe(ffmpeg_cmd)
        self.ff = FFmpegProcess(ffmpeg_cmd, log_q=_QueueAdapter(on_log))
        self.sizer = SizeEstimator(
            self.ff,
            fps=fps,
            frame_w=out_w,
            frame_h=out_h,
            a_codec=a_codec,
            a_rate=a_rate,
            a_ch=a_ch,
            p_format=p_format,
            v_codec=v_codec,
        )

        self.out_w = out_w
        self.out_h = out_h
        self.fps = fps
        self.a_codec = a_codec
        self.a_rate = a_rate
        self.a_ch = a_ch
        self.p_format = p_format
        self.v_codec = v_codec

        self.on_log = on_log
        self.on_progress = on_progress
        self.on_running_changed = on_running_changed or (lambda _b: None)

    def thumbnail(self, src: Path, vf: str, q: int, jpeg_preferred: bool) -> str | None:
        return self.ff.thumbnail(src, vf, q, jpeg_preferred)

    def ensure_size_anchors(self, src: Path, vf: str, *, on_ready=None):
        self.sizer.ensure_anchors(src, vf, on_ready=on_ready)

    def estimate_size(
        self, duration: float | None, q: int, *, vf: str, src: Path
    ) -> int | None:
        return self.sizer.estimate_bytes(duration, q, vf=vf, src=src)

    def build_vf(self, scale_mode: str) -> str:
        w = self.out_w
        h = self.out_h
        # Scale
        if scale_mode == "contain":
            s = f"min({w}/iw\\,{h}/ih)"
            we = f"trunc(iw*{s}/2)*2"
            he = f"trunc(ih*{s}/2)*2"
            return f"scale={we}:{he},setsar=1,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        # Cover
        if scale_mode == "cover":
            s = f"max({w}/iw\\,{h}/ih)"
            we = f"trunc(iw*{s}/2)*2"
            he = f"trunc(ih*{s}/2)*2"
            return f"scale={we}:{he},setsar=1,crop={w}:{h}"
        # Stretch
        return f"scale={w}:{h},setsar=1"

    def build_cmd(
        self,
        src: Path,
        dst: Path,
        q_val: int,
        scale_mode: str,
        normalize_audio: bool,
    ) -> list[str]:
        vf_str = self.build_vf(scale_mode)

        # Command tuples
        logLevel = ["-hide_banner", "-loglevel", "error", "-stats"]
        overwriteIfExists = ["-y"]
        inputSource = ["-i", str(src)]
        outputRate = ["-r", str(int(self.fps))]
        pixelFormat = ["-pix_fmt", self.p_format]
        videoFilters = ["-vf", vf_str]
        videoCodec = ["-c:v", self.v_codec]
        videoQuality = ["-q:v", str(int(q_val))]
        audioCodec = ["-acodec", str(self.a_codec)]
        audioRate = ["-ar", str(self.a_rate)]
        audioChannels = ["-ac", str(self.a_ch)]
        normalizeAudio = ["-af", "volume=+6dB,alimiter=limit=0.97"]
        dstArg = [str(dst)]

        cmd = [
            self.ff.ffmpeg,
            *logLevel,
            *overwriteIfExists,
            *inputSource,
            *outputRate,
            *pixelFormat,
            *videoFilters,
            *videoCodec,
            *videoQuality,
            *audioCodec,
            *audioRate,
            *audioChannels,
        ]

        if normalize_audio:
            cmd += normalizeAudio

        cmd += dstArg

        return cmd

    def convert_files(
        self,
        files: Iterable[Path],
        *,
        output_dir: Path,
        q_val: int,
        scale_mode: str,
        normalize_audio: bool,
        channel_prefix: str | None,
    ):
        files = list(files)
        if not files:
            self.on_log("[ERROR] Add at least one video.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        self.on_running_changed(True)

        def worker():
            ok = True
            total = len(files)
            for idx, src in enumerate(files, start=1):
                base = src.stem
                prefix = f"{channel_prefix}_" if channel_prefix else ""
                dst = output_dir / f"{prefix}{base}.avi"

                self.on_log(f"[*] Converting {src.name} -> {dst.name}")
                cmd = self.build_cmd(src, dst, q_val, scale_mode, normalize_audio)
                code = self.ff.run(cmd)
                self.on_progress(idx, total)

                if code != 0 or not dst.exists():
                    self.on_log(f"[ERROR] Conversion failed: {src}")
                    ok = False
                    break

            if ok:
                self.on_log("[OK] Convert complete.")
            self.on_running_changed(False)

        threading.Thread(target=worker, daemon=True).start()


class _QueueAdapter:
    """Adapts service on_log(str) to the .put interface used by FFmpegProcess."""

    def __init__(self, on_log: LogFn):
        self.on_log = on_log

    def put(self, msg: str):
        self.on_log(msg)
