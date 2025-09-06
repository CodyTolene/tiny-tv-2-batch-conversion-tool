from __future__ import annotations
import tempfile
from pathlib import Path
from typing import Iterable, Callable

from lib.ffmpeg_proc import FFmpegProcess

LogFn = Callable[[str], None]

# When there are many files, use concat demuxer to avoid Windows command-length
# limits
CONCAT_LIST_THRESHOLD = 50


class CombineService:
    def __init__(
        self,
        ffmpeg_cmd: str,
        *,
        on_log: LogFn,
        v_codec: str,
        p_format: str,
        a_codec: str,
        a_rate: int,
        a_ch: int,
        q_val: int,
    ):
        self.ff = FFmpegProcess(ffmpeg_cmd, log_q=_QueueAdapter(on_log))
        self.on_log = on_log

        self.v_codec = v_codec
        self.p_format = p_format
        self.a_codec = a_codec
        self.a_rate = a_rate
        self.a_ch = a_ch
        self.q_val = q_val

    def _common_tuples(self, fps: int):
        return {
            "logLevel": ["-hide_banner", "-loglevel", "error", "-stats"],
            "overwrite": ["-y"],
            "pixFmt": ["-pix_fmt", self.p_format],
            "vCodec": ["-c:v", self.v_codec],
            "vQuality": ["-q:v", str(int(self.q_val))],
            "vRate": ["-r", str(int(fps))],
            "aCodec": ["-c:a", self.a_codec],
            "aRate": ["-ar", str(int(self.a_rate))],
            "aCh": ["-ac", str(int(self.a_ch))],
        }

    def _run(self, args: list[str]) -> int:
        return self.ff.run(args)

    def build_cmd_single(self, src: Path, out_path: Path, fps: int) -> list[str]:
        C = self._common_tuples(fps)
        # Normalize video timing minimally (no setpts), just ensure fps/format/SAR
        vf = f"fps={fps},format={self.p_format},setsar=1"

        cmd = [
            self.ff.ffmpeg,
            *C["logLevel"],
            *C["overwrite"],
            "-i",
            str(src),
            "-vf",
            vf,
            *C["vRate"],
            *C["pixFmt"],
            *C["vCodec"],
            *C["vQuality"],
            *C["aCodec"],
            *C["aRate"],
            *C["aCh"],
            str(out_path),
        ]
        return cmd

    # Concat demuxer path (many files)
    def build_cmd_concat_list(
        self, list_file: Path, out_path: Path, fps: int
    ) -> list[str]:
        C = self._common_tuples(fps)
        vf = f"fps={fps},format={self.p_format},setsar=1"

        cmd = [
            self.ff.ffmpeg,
            *C["logLevel"],
            *C["overwrite"],
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-fflags",
            "+genpts",
            "-copytb",
            "0",
            "-vf",
            vf,
            *C["vRate"],
            *C["pixFmt"],
            *C["vCodec"],
            *C["vQuality"],
            *C["aCodec"],
            *C["aRate"],
            *C["aCh"],
            str(out_path),
        ]
        return cmd

    def build_cmd_filter_complex(
        self, files: list[Path], out_path: Path, fps: int
    ) -> list[str]:
        C = self._common_tuples(fps)

        # Inputs
        inputs: list[str] = []
        for p in files:
            inputs += ["-i", str(p)]

        # Normalize video/audio per input, then concat
        parts: list[str] = []
        interleaved: list[str] = []

        for idx in range(len(files)):
            v_lbl = f"v{idx}"
            a_lbl = f"a{idx}"

            # Video
            parts.append(
                f"[{idx}:v:0]fps={fps},format={self.p_format},setsar=1[{v_lbl}]"
            )
            # Audio
            parts.append(
                f"[{idx}:a:0]aresample={int(self.a_rate)},"
                f"aformat=sample_fmts=u8:channel_layouts=mono[{a_lbl}]"
            )

            interleaved += [f"[{v_lbl}]", f"[{a_lbl}]"]

        n = len(files)
        parts.append("".join(interleaved) + f"concat=n={n}:v=1:a=1[v][a]")
        filter_complex = ";".join(parts)

        cmd = [
            self.ff.ffmpeg,
            *C["logLevel"],
            *C["overwrite"],
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            *C["vRate"],
            *C["pixFmt"],
            *C["vCodec"],
            *C["vQuality"],
            *C["aCodec"],
            *C["aRate"],
            *C["aCh"],
            str(out_path),
        ]
        return cmd

    def combine(self, files: Iterable[Path], out_path: Path, fps: int) -> int:
        files = list(files)
        if not files:
            self.on_log("[ERROR] No input files provided.")
            return 1

        if len(files) == 1:
            self.on_log(f"[*] Transcoding single file @ {fps} fps -> {out_path.name}")
            return self._run(self.build_cmd_single(files[0], out_path, fps))

        if len(files) >= CONCAT_LIST_THRESHOLD:
            self.on_log(
                f"[*] Using concat list ({len(files)} files) with re-encode @ {fps} fps"
            )
            # Build temporary concat list file
            fd, list_path = tempfile.mkstemp(prefix="tinytv_concat_", suffix=".txt")
            list_file = Path(list_path)
            try:
                list_file.write_text(
                    "".join(f"file '{p.as_posix()}'\n" for p in files),
                    encoding="utf-8",
                )
                return self._run(self.build_cmd_concat_list(list_file, out_path, fps))
            finally:
                try:
                    list_file.unlink(missing_ok=True)
                except Exception:
                    pass

        self.on_log(f"[*] Concat {len(files)} inputs via filter_complex @ {fps} fps")
        return self._run(self.build_cmd_filter_complex(files, out_path, fps))


class _QueueAdapter:
    def __init__(self, on_log: LogFn):
        self.on_log = on_log

    def put(self, msg: str):
        self.on_log(msg)
