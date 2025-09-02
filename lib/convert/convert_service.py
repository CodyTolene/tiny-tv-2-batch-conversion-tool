import threading
from pathlib import Path
from typing import Callable, Iterable
from .probe import Probe
from .ffmpeg_proc import FFmpegProcess
from .size_estimator import SizeEstimator

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
            a_rate=a_rate,
            a_ch=a_ch,
            v_codec=v_codec,
        )

        self.out_w = out_w
        self.out_h = out_h
        self.fps = fps
        self.a_codec = a_codec
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

    def build_vf(self, _scale_mode: str) -> str:
        """
        Minimal shim for the UI preview/estimator.
        Ignores scale_mode and returns the fixed chain that matches build_cmd.
        """
        return (
            f"scale={self.out_w}:{self.out_h}:force_original_aspect_ratio=increase,"
            f"crop={self.out_w}:{self.out_h}:exact=1,hqdn3d"
        )

    def build_cmd(
        self, 
        src: Path, 
        dst: Path, 
        q_val: int,
        scale_mode: str,        # TODO: USE
        normalize_audio: bool,  # TODO: USE
    ) -> list[str]:
        vf = (
            f"scale={self.out_w}:{self.out_h}:force_original_aspect_ratio=increase,"
            f"crop={self.out_w}:{self.out_h}:exact=1,hqdn3d"
        )
        return [
            self.ff.ffmpeg,
            "-i", str(src),
            "-r", str(int(self.fps)),
            "-pix_fmt", "yuv420p",
            "-vf", vf,
            "-c:v", str(self.v_codec),
            "-q:v", str(int(q_val)),
            "-acodec", str(self.a_codec),
            "-ar", "10000",
            "-ac", "1",
            str(dst),
        ]

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
                cmd = self.build_cmd(
                    src, 
                    dst, 
                    q_val,
                    scale_mode,
                    normalize_audio
                )
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
