from pathlib import Path
from .ffmpeg_proc import FFmpegProcess


class SizeEstimator:
    def __init__(
        self,
        ff: FFmpegProcess,
        fps: int,
        frame_w: int,
        frame_h: int,
        a_codec: str,
        a_rate: str,
        a_ch: str,
        p_format: str,
        v_codec: str,
    ):
        self.ff = ff
        self.fps = fps
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.a_codec = a_codec
        self.a_rate = a_rate
        self.a_ch = a_ch
        self.p_format = p_format
        self.v_codec = v_codec
        self.anchor_cache: dict[tuple[str, str, int], tuple[float, float]] = {}
        self.anchor_inflight: set[tuple[str, str, int]] = set()

    def ensure_anchors(
        self, src: Path, vf: str, sample_secs: float = 2.0, on_ready=None
    ):
        key = (str(src), vf, int(self.fps))
        if key in self.anchor_cache or key in self.anchor_inflight:
            return
        self.anchor_inflight.add(key)

        def run():
            try:
                best = self.ff.calibrate_video_bps(
                    src,
                    vf,
                    q_val=2,
                    fps=self.fps,
                    sample_secs=sample_secs,
                    a_codec=self.a_codec,
                    a_rate=self.a_rate,
                    a_ch=self.a_ch,
                    p_format=self.p_format,
                    v_codec=self.v_codec,
                )
                worst = self.ff.calibrate_video_bps(
                    src,
                    vf,
                    q_val=31,
                    fps=self.fps,
                    sample_secs=sample_secs,
                    a_codec=self.a_codec,
                    a_rate=self.a_rate,
                    a_ch=self.a_ch,
                    p_format=self.p_format,
                    v_codec=self.v_codec,
                )
                if best and worst:
                    self.anchor_cache[key] = (best * 1.05, worst * 1.05)
            finally:
                self.anchor_inflight.discard(key)
                if on_ready:
                    on_ready()

        import threading

        threading.Thread(target=run, daemon=True).start()

    def estimate_bytes(
        self,
        duration: float | None,
        q: int,
        *,
        vf: str | None = None,
        src: Path | None = None
    ) -> int | None:
        if not duration or duration <= 0:
            return None
        try:
            rate = int(self.a_rate)
        except Exception:
            rate = 10000
        try:
            ch = int(self.a_ch)
        except Exception:
            ch = 1
        audio_bps = rate * ch
        audio_bytes = int(audio_bps * duration)

        video_bps = None
        if src is not None and vf is not None:
            key = (str(src), vf, int(self.fps))
            anchors = self.anchor_cache.get(key)
            if anchors:
                best_bps, worst_bps = anchors
                q = max(2, min(31, int(q)))
                t = (31 - q) / (31 - 2)
                g = t**0.7
                video_bps = worst_bps + (best_bps - worst_bps) * g

        if video_bps is None:
            q = max(2, min(31, int(q)))
            frac = (31 - q) / (31 - 2)
            bpp = 0.06 + (0.28 - 0.06) * (frac**0.7)
            video_bytes_per_frame = int(self.frame_w * self.frame_h * bpp)
            video_bps = int(video_bytes_per_frame * self.fps) * 1.03

        return int(video_bps * duration) + audio_bytes
