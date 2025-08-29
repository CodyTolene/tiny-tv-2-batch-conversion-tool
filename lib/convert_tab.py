import os
import tempfile
import threading
import queue
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False
    Image = None
    ImageTk = None

FRAME_WIDTH, FRAME_HEIGHT = 210, 135
TARGET_FPS = 12
VIDEO_CODEC = "mjpeg"
AUDIO_CODEC = "pcm_u8"
AUDIO_RATE = "8000"
AUDIO_CHANNELS = "1"

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


def _no_console_kwargs() -> dict:
    try:
        import sys
        import subprocess as _sp

        if sys.platform.startswith("win"):
            si = _sp.STARTUPINFO()
            si.dwFlags |= _sp.STARTF_USESHOWWINDOW
            return {"startupinfo": si, "creationflags": _sp.CREATE_NO_WINDOW}
    except Exception:
        pass
    return {}


def fmt_bytes(n: int | None) -> str:
    if not n or n <= 0:
        return "N/A"
    mb = n / (1024 * 1024)
    return f"{mb:.2f} MB"


def fmt_hms(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "N/A"
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"


def is_video(path: Path) -> bool:
    return path.suffix.lower() in set(VIDEO_EXTENSIONS)


def pad2(text: str) -> str | None:
    try:
        return f"{int(text):02d}"
    except Exception:
        return None


class PathTools:
    @staticmethod
    def normalize(p: Path) -> str:
        try:
            abs_path = os.path.abspath(str(p))
        except Exception:
            abs_path = str(p)
        return os.path.normcase(abs_path)


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

    def duration(self, src: Path) -> float | None:
        try:
            cmd = [
                self.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ]
            out = subprocess.run(
                cmd,
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
            cmd = [
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
            ]
            out = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            ).stdout
            for line in out.splitlines():
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k in info:
                    info[k] = v
                if k == "duration" and not info["duration"]:
                    info["duration"] = v
            return info
        except Exception:
            return info


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
                "yuvj420p",
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
                self.ffmpeg,  # Path to the ffmpeg executable
                # Suppresses startup banner/info from ffmpeg for cleaner logs
                "-hide_banner",
                "-loglevel",
                "error",  # Only show error messages (no warnings or info)
                "-y",  # Automatically overwrite output files without asking
                "-ss",
                "0",  # Start time offset, 0 means start from the beginning
                "-t",
                f"{sample_secs}",  # Duration, only process this many seconds of video
                "-fflags",
                # Force ffmpeg to generate presentation timestamps, avoids sync issues
                "+genpts",
                # Reset time base when copying streams, keep timestamps consistent
                "-copytb",
                "0",
                "-i",
                str(src),  # Input file (path to source video)
                # `vf` → user-supplied filter string (like scaling, cropping, etc.)
                "-vf",
                # `fps={fps}` → enforce a fixed frames-per-second output
                f"{vf},fps={int(fps)}",
                "-r",
                # Explicitly set output frame rate, ensures fps is locked
                str(fps),
                "-vsync",
                "cfr",  # Constant frame rate output (duplicate/drop frames as needed)
                "-pix_fmt",
                # Pixel format: YUV 4:2:0 JPEG variant (TinyTV 2 Expects this)
                "yuvj420p",
                "-c:v",
                # Video codec, `mjpeg` for TinyTV AVI support
                vcodec,
                "-vtag",
                # Force AVI FourCC tag to "MJPG" to ensure device compatibility
                "MJPG",
                "-q:v",
                # Video quality level (1 = best, 31 = worst).
                str(int(q)),
                "-an",
                tmp,  # Output file path
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


class SizeEstimator:
    def __init__(
        self,
        ff: FFmpegProcess,
        fps: int,
        frame_w: int,
        frame_h: int,
        a_rate: str,
        a_ch: str,
        vcodec: str,
    ):
        self.ff = ff
        self.fps = fps
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.a_rate = a_rate
        self.a_ch = a_ch
        self.vcodec = vcodec
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
                    q=2,
                    fps=self.fps,
                    sample_secs=sample_secs,
                    vcodec=self.vcodec,
                )
                worst = self.ff.calibrate_video_bps(
                    src,
                    vf,
                    q=31,
                    fps=self.fps,
                    sample_secs=sample_secs,
                    vcodec=self.vcodec,
                )
                if best and worst:
                    self.anchor_cache[key] = (best * 1.05, worst * 1.05)
            finally:
                self.anchor_inflight.discard(key)
                if on_ready:
                    on_ready()

        threading.Thread(target=run, daemon=True).start()

    def estimate_bytes(
        self,
        duration: float | None,
        q: int,
        *,
        vf: str | None = None,
        src: Path | None = None,
    ) -> int | None:
        if not duration or duration <= 0:
            return None

        try:
            rate = int(self.a_rate)
        except Exception:
            rate = 8000
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


class ConvertTab(ttk.Frame):
    on_running_changed = None

    def __init__(
        self,
        master,
        *,
        log_q: queue.Queue,
        progress: ttk.Progressbar,
        convert_btn: ttk.Button,
        ffmpeg_cmd: str,
        out_w: int = FRAME_WIDTH,
        out_h: int = FRAME_HEIGHT,
        fps: int = TARGET_FPS,
        v_codec: str = VIDEO_CODEC,
        a_codec: str = AUDIO_CODEC,
        a_rate: str = AUDIO_RATE,
        a_ch: str = AUDIO_CHANNELS,
    ):
        super().__init__(master)

        self.log_q = log_q
        self.progress = progress
        self.convert_btn = convert_btn
        self.frame_w, self.frame_h = out_w, out_h
        self.fps = fps
        self.vcodec = v_codec
        self.acodec = a_codec
        self.arate = a_rate
        self.ach = a_ch

        self.probe = Probe(ffmpeg_cmd)
        self.ff = FFmpegProcess(ffmpeg_cmd, log_q)
        self.sizer = SizeEstimator(
            self.ff,
            fps=self.fps,
            frame_w=self.frame_w,
            frame_h=self.frame_h,
            a_rate=self.arate,
            a_ch=self.ach,
            vcodec=self.vcodec,
        )

        self.is_running = False
        self.convert_finished_once = False
        self.files: list[Path] = []
        self._preview_target: Path | None = None
        self._preview_img = None
        self._thumb_path: Path | None = None
        self._last_dir = str(Path.home())
        self._preview_after = None
        self._duration_cache: dict[Path, float] = {}
        self._known_paths: set[str] = set()

        # Preview
        self.preview_panel = ttk.Frame(self)
        self.preview_panel.grid(
            row=0, column=0, rowspan=6, sticky="nw", padx=(10, 10), pady=10
        )

        self.preview_canvas = tk.Canvas(
            self.preview_panel,
            width=self.frame_w,
            height=self.frame_h,
            highlightthickness=1,
            highlightbackground="#a0a0a0",
        )
        self.preview_canvas.pack(side="top")

        ttk.Label(self.preview_panel, text="(Preview)").pack(side="top", pady=(4, 6))

        self.length_label = ttk.Label(self.preview_panel, text="Length: N/A")
        self.length_label.pack(side="top", anchor="w")

        self.orig_size_label = ttk.Label(self.preview_panel, text="Original size: N/A")
        self.orig_size_label.pack(side="top", anchor="w")

        self.size_label = ttk.Label(self.preview_panel, text="Estimated size: N/A")
        self.size_label.pack(side="top", anchor="w")

        # File list
        list_wrap = ttk.Frame(self)
        list_wrap.grid(
            row=0,
            column=1,
            columnspan=2,
            rowspan=6,
            sticky="nsew",
            padx=(0, 0),
            pady=10,
        )
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)

        self.file_list = tk.Listbox(list_wrap, selectmode=tk.EXTENDED, height=16)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        self.file_list.bind("<<ListboxSelect>>", self._on_list_select)

        list_scroll = ttk.Scrollbar(
            list_wrap, orient="vertical", command=self.file_list.yview
        )
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.file_list.config(yscrollcommand=list_scroll.set)

        self.empty_hint = ttk.Label(self, text="No files selected.", foreground="#666")
        self._toggle_empty_hint()

        # Buttons
        btns = ttk.Frame(self)
        btns.grid(row=0, column=3, rowspan=6, sticky="ne", padx=10, pady=10)

        self.btn_add = ttk.Button(
            btns,
            text="Add files",
            command=lambda: self.add_files(self.file_list, self.files),
        )
        self.btn_add.pack(pady=(0, 10), fill="x")

        self.btn_up = ttk.Button(
            btns,
            text="Up",
            width=12,
            command=lambda: self.move_selected(self.file_list, self.files, -1),
        )
        self.btn_up.pack(pady=2, fill="x")

        self.btn_down = ttk.Button(
            btns,
            text="Down",
            width=12,
            command=lambda: self.move_selected(self.file_list, self.files, +1),
        )
        self.btn_down.pack(pady=2, fill="x")

        self.btn_remove = ttk.Button(
            btns,
            text="Remove",
            width=12,
            command=lambda: self.remove_selected(self.file_list, self.files),
        )
        self.btn_remove.pack(pady=2, fill="x")

        self.btn_clear = ttk.Button(
            btns,
            text="Clear",
            width=12,
            command=lambda: self.clear_list(self.file_list, self.files),
        )
        self.btn_clear.pack(pady=2, fill="x")

        # Output folder row
        self.output_dir_var = tk.StringVar()
        self.output_dir_var.trace_add("write", lambda *_: self.update_controls())

        out_row = ttk.Frame(self)
        out_row.grid(row=6, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 10))
        ttk.Button(
            out_row,
            text="Output folder",
            command=lambda: self.pick_folder(self.output_dir_var),
        ).pack(side="left")
        self.output_entry = ttk.Entry(out_row, textvariable=self.output_dir_var)
        self.output_entry.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # Options row
        options_row = ttk.Frame(self)
        options_row.grid(
            row=7, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 4)
        )
        for col in range(4):
            options_row.grid_columnconfigure(col, weight=1)

        # Channel
        chan_group = ttk.Frame(options_row)
        chan_group.grid(row=0, column=0, sticky="w")
        ttk.Label(chan_group, text="Channel prefix (optional)").pack(side="left")
        self.channel_var = tk.StringVar()
        self.channel_entry = tk.Entry(
            chan_group, textvariable=self.channel_var, width=8
        )
        self.channel_entry.pack(side="left", padx=(8, 0))
        self._attach_placeholder(self.channel_entry, "e.g. 01")

        # Scaling
        scale_group = ttk.Frame(options_row)
        scale_group.grid(row=0, column=1, sticky="we")
        ttk.Label(scale_group, text="Scaling:").pack(side="left", padx=(0, 8))
        self.scale_mode = tk.StringVar(value="stretch")
        ttk.Radiobutton(
            scale_group,
            text="Contain / Letterbox",
            variable=self.scale_mode,
            value="contain",
            command=self._schedule_preview_update,
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            scale_group,
            text="Cover / Zoom",
            variable=self.scale_mode,
            value="cover",
            command=self._schedule_preview_update,
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            scale_group,
            text="Fill / Stretch",
            variable=self.scale_mode,
            value="stretch",
            command=self._schedule_preview_update,
        ).pack(side="left")

        # Audio normalize
        norm_group = ttk.Frame(options_row)
        norm_group.grid(row=0, column=2, sticky="e")
        self.normalize_audio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            norm_group,
            text="Normalize / Boost audio",
            variable=self.normalize_audio_var,
        ).pack(side="right")

        # FPS selector
        fps_group = ttk.Frame(options_row)
        fps_group.grid(row=0, column=3, sticky="e", padx=(8, 0))
        ttk.Label(fps_group, text="FPS:").pack(side="left")
        self.fps_var = tk.StringVar(value=str(self.fps))
        self.fps_box = ttk.Combobox(
            fps_group,
            textvariable=self.fps_var,
            values=["12", "24"],
            width=5,
            state="readonly",
        )
        self.fps_box.pack(side="left", padx=(6, 0))
        self.fps_box.bind("<<ComboboxSelected>>", self._on_fps_change)

        # Quality row
        q_row = ttk.Frame(self)
        q_row.grid(row=8, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 8))
        ttk.Label(q_row, text="Quality:").pack(side="left", padx=(0, 8))
        ttk.Label(q_row, text="Smaller file / lower quality").pack(side="left")
        self.quality_var = tk.IntVar(value=16)
        self.quality_scale = ttk.Scale(
            q_row,
            from_=31,
            to=2,
            orient="horizontal",
            variable=self.quality_var,
            command=lambda _v: self._on_quality_change(),
        )
        self.quality_scale.pack(side="left", padx=8, fill="x", expand=True)
        ttk.Label(q_row, text="Larger file / higher quality").pack(side="left")

        # Layout stretch
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=2)
        self.grid_columnconfigure(3, weight=0)
        for r in range(9):
            self.grid_rowconfigure(r, weight=0)
        self.grid_rowconfigure(5, weight=1)

        # Convert button
        self.convert_btn.config(text="Convert", command=self.start_convert_all)

        self.update_controls()
        self._clear_preview()
        self.after(0, self._set_initial_minsize)

    def _set_initial_minsize(self):
        try:
            top = self.winfo_toplevel()
            top.update_idletasks()
            w = top.winfo_width()
            h = top.winfo_height()
            if w > 1 and h > 1:
                top.minsize(w, h)
        except Exception:
            pass

    def _attach_placeholder(self, entry: tk.Entry, placeholder: str):
        entry._placeholder = placeholder
        entry._default_fg = entry.cget("foreground")

        def show():
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(foreground="gray")

        def clear(_=None):
            if entry.get() == placeholder and entry.cget("foreground") == "gray":
                entry.delete(0, tk.END)
                entry.config(foreground=entry._default_fg)

        def restore(_=None):
            if not entry.get():
                show()

        show()
        entry.bind("<FocusIn>", clear)
        entry.bind("<FocusOut>", restore)

    @staticmethod
    def _read_entry(entry: tk.Entry) -> str:
        val = entry.get().strip()
        if (
            getattr(entry, "_placeholder", None)
            and val == entry._placeholder
            and entry.cget("foreground") == "gray"
        ):
            return ""
        return val

    def _vf(self) -> str:
        w, h = self.frame_w, self.frame_h
        mode = self.scale_mode.get()
        if mode == "contain":
            s = f"min({w}/iw\\,{h}/ih)"
            we = f"trunc(iw*{s}/2)*2"
            he = f"trunc(ih*{s}/2)*2"
            return f"scale={we}:{he},setsar=1,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        if mode == "cover":
            s = f"max({w}/iw\\,{h}/ih)"
            we = f"trunc(iw*{s}/2)*2"
            he = f"trunc(ih*{s}/2)*2"
            return f"scale={we}:{he},setsar=1,crop={w}:{h}"
        return f"scale={w}:{h},setsar=1"

    def _af(self) -> list[str]:
        return (
            ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
            if self.normalize_audio_var.get()
            else []
        )

    def on_interaction(self, _event=None):
        if not self.is_running and self.convert_finished_once:
            try:
                self.progress["value"] = 0
            except Exception:
                pass
            self.convert_finished_once = False

    def update_controls(self):
        count = len(self.files)
        selected = list(self.file_list.curselection())
        has_output = bool(self.output_dir_var.get().strip())

        move_ok = count > 1 and selected and not self.is_running
        self.btn_up.config(state=("normal" if move_ok else "disabled"))
        self.btn_down.config(state=("normal" if move_ok else "disabled"))
        self.btn_remove.config(
            state=("normal" if (selected and not self.is_running) else "disabled")
        )
        self.btn_clear.config(
            state=("normal" if (count >= 1 and not self.is_running) else "disabled")
        )

        can_convert_all = (count >= 1) and has_output and (not self.is_running)
        self.convert_btn.config(state=("normal" if can_convert_all else "disabled"))

        if count > 0 and not selected:
            self.file_list.selection_set(0)

        self._toggle_empty_hint()

    def _toggle_empty_hint(self):
        if len(self.files) == 0:
            self.empty_hint.grid(
                row=0, column=1, columnspan=2, sticky="n", padx=0, pady=(12, 0)
            )
        else:
            try:
                self.empty_hint.grid_forget()
            except Exception:
                pass

    def _on_fps_change(self, _evt=None):
        try:
            new_fps = int(self.fps_var.get())
            if new_fps not in (12, 24):
                new_fps = 12
        except Exception:
            new_fps = 12
        self.fps = new_fps
        self.sizer.fps = new_fps
        self.update_controls()
        self._schedule_preview_update(debounce=True)
        self.log_q.put(f"[info] Target FPS set to {self.fps}")

    def add_files(self, listbox: tk.Listbox, store: list[Path]):
        try:
            paths = filedialog.askopenfilenames(
                parent=self.winfo_toplevel(),
                title="Select videos",
                filetypes=VIDEO_FILETYPES,
                initialdir=self._last_dir,
            )
        except Exception as e:
            self.log_q.put(f"[ERROR] Open dialog failed: {e}")
            return

        if not paths:
            self.update_controls()
            return

        self._last_dir = str(Path(paths[0]).parent)

        picked: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if not is_video(p):
                continue
            key = PathTools.normalize(p)
            if key in self._known_paths:
                continue
            self._known_paths.add(key)
            picked.append(p)

        if not picked:
            self.update_controls()
            return

        store.extend(picked)
        self._refresh_list(listbox, store)
        self.update_controls()

        if listbox.size() and not listbox.curselection():
            listbox.selection_set(0)
            self._schedule_preview_update()

    def remove_selected(self, listbox: tk.Listbox, store: list[Path]):
        sel = list(listbox.curselection())
        if not sel:
            return

        first_idx = sel[0]
        for idx in reversed(sel):
            if 0 <= idx < len(store):
                try:
                    self._known_paths.discard(PathTools.normalize(store[idx]))
                except Exception:
                    pass
                store.pop(idx)

        self._refresh_list(listbox, store)

        if store:
            target = max(0, min(first_idx - 1, len(store) - 1))
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(target)

        self.update_controls()
        self._schedule_preview_update()

    def clear_list(self, listbox: tk.Listbox, store: list[Path]):
        store.clear()
        self._known_paths.clear()
        self._refresh_list(listbox, store)
        self.update_controls()
        self._clear_preview()

    def move_selected(self, listbox: tk.Listbox, store: list[Path], delta: int):
        sel = list(listbox.curselection())
        if not sel:
            return

        if delta < 0:
            for i in sel:
                j = i + delta
                if j >= 0:
                    store[i], store[j] = store[j], store[i]
        else:
            for i in reversed(sel):
                j = i + delta
                if j < len(store):
                    store[i], store[j] = store[j], store[i]

        self._refresh_list(listbox, store)
        for i in [min(max(0, i + delta), len(store) - 1) for i in sel]:
            listbox.selection_set(i)

        self.update_controls()
        self._schedule_preview_update()

    def _refresh_list(self, listbox: tk.Listbox, store: list[Path]):
        listbox.delete(0, tk.END)
        for p in store:
            listbox.insert(tk.END, p.name)
        if store and not listbox.curselection():
            listbox.selection_set(0)
        self._toggle_empty_hint()

    def pick_folder(self, var: tk.StringVar):
        folder = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="Choose output folder",
            initialdir=self._last_dir,
        )
        if folder:
            var.set(folder)
            self._last_dir = folder
        self.update_controls()

    def _on_list_select(self, _event=None):
        self.update_controls()
        self._schedule_preview_update()

    def _on_quality_change(self):
        try:
            self.quality_var.set(int(round(float(self.quality_var.get()))))
        except Exception:
            pass
        self._update_estimate_only()
        self._schedule_preview_update(debounce=True)

    def _schedule_preview_update(self, debounce: bool = False):
        sel = self.file_list.curselection()
        if not sel:
            self._clear_preview()
            return

        idx = sel[0]
        if not (0 <= idx < len(self.files)):
            self._clear_preview()
            return

        path = self.files[idx]
        self._preview_target = path

        delay_ms = 250 if debounce else 0
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except Exception:
                pass
            self._preview_after = None

        def go():
            threading.Thread(
                target=self._build_preview_and_info, args=(path,), daemon=True
            ).start()
            self._preview_after = None

        self._preview_after = self.after(delay_ms, go)

    def _clear_preview(self):
        self._preview_img = None
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(
            self.frame_w // 2, self.frame_h // 2, text="No preview"
        )
        self.length_label.config(text="Length: N/A")
        self.orig_size_label.config(text="Original size: N/A")
        self.size_label.config(text="Estimated size: N/A")

    def _build_preview_and_info(self, src: Path):
        duration = self._duration_cache.get(src)
        if duration is None:
            duration = self.probe.duration(src)
            if duration is not None:
                self._duration_cache[src] = duration

        vf = self._vf()
        self.log_q.put(f"[preview vf]  {vf}")

        q_now = int(self.quality_var.get())

        self.sizer.ensure_anchors(src, vf, on_ready=self._update_estimate_only)
        thumb = self.ff.thumbnail(src, vf, q_now, jpeg_preferred=PIL_AVAILABLE)

        est_bytes = self.sizer.estimate_bytes(duration, q_now, vf=vf, src=src)

        if self._preview_target != src:
            return

        def apply():
            if self._preview_target != src:
                return
            self.length_label.config(text=f"Length: {fmt_hms(duration)}")

            try:
                self.orig_size_label.config(
                    text=f"Original size: {fmt_bytes(os.path.getsize(src))}"
                )
            except Exception:
                self.orig_size_label.config(text="Original size: N/A")

            if est_bytes is not None:
                mb = est_bytes / (1024 * 1024)
                self.size_label.config(text=f"Estimated size: {mb:.2f} MB")
            else:
                self.size_label.config(text="Estimated size: N/A")

            self.preview_canvas.delete("all")
            if thumb and Path(thumb).exists():
                try:
                    if PIL_AVAILABLE and str(thumb).lower().endswith((".jpg", ".jpeg")):
                        img = Image.open(str(thumb))
                        self._preview_img = ImageTk.PhotoImage(img)
                    else:
                        self._preview_img = tk.PhotoImage(file=str(thumb))
                    self.preview_canvas.create_image(
                        self.frame_w // 2, self.frame_h // 2, image=self._preview_img
                    )
                except Exception:
                    self.preview_canvas.create_text(
                        self.frame_w // 2,
                        self.frame_h // 2,
                        text="(Preview unsupported)",
                    )
            else:
                self.preview_canvas.create_text(
                    self.frame_w // 2, self.frame_h // 2, text="No preview"
                )

        self.after(0, apply)

    def _update_estimate_only(self):
        sel = self.file_list.curselection()
        if not sel:
            self.size_label.config(text="Estimated size: N/A")
            return
        idx = sel[0]
        if not (0 <= idx < len(self.files)):
            self.size_label.config(text="Estimated size: N/A")
            return

        src = self.files[idx]

        try:
            self.orig_size_label.config(
                text=f"Original size: {fmt_bytes(os.path.getsize(src))}"
            )
        except Exception:
            self.orig_size_label.config(text="Original size: N/A")

        duration = self._duration_cache.get(src)
        if duration is None:
            duration = self.probe.duration(src)
            if duration is not None:
                self._duration_cache[src] = duration
        est_bytes = self.sizer.estimate_bytes(
            duration, int(self.quality_var.get()), vf=self._vf(), src=src
        )
        if est_bytes is None:
            self.size_label.config(text="Estimated size: N/A")
        else:
            mb = est_bytes / (1024 * 1024)
            self.size_label.config(text=f"Estimated size: {mb:.2f} MB")

    def start_convert_all(self):
        if self.is_running:
            return
        if not self.files:
            self.log_q.put("[ERROR] Add at least one video.")
            return
        self._convert_files(list(self.files))

    def _build_base_cmd(
        self, src: Path, dst: Path, vf_fps: str, q_val: int, fix_pass: bool
    ) -> list[str]:
        pre_input = []
        if fix_pass:
            pre_input = ["-fflags", "+genpts", "-copytb", "0"]

        cmd = [
            self.ff.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-stats",
            "-y",
            *pre_input,
            "-i",
            str(src),
            "-vf",
            vf_fps,
            "-r",
            str(int(self.fps)),
            "-vsync",
            "cfr",
            "-pix_fmt",
            "yuvj420p",
            "-c:v",
            self.vcodec,
            "-vtag",
            "MJPG",
            "-q:v",
            str(q_val),
            "-c:a",
            self.acodec,
            "-ar",
            self.arate,
            "-ac",
            self.ach,
        ]
        af = self._af()
        cmd += af
        cmd += [str(dst)]
        return cmd

    def _validate_and_maybe_fix(
        self, dst: Path, src: Path, vf_fps: str, q_val: int
    ) -> bool:
        """
        Returns True if the file is valid (or fixed successfully), False if failed.
        Validation rules:
          - r_frame_rate == "{fps}/1"
          - avg_frame_rate == "{fps}/1"
          - if nb_frames and duration are present, |nb_frames/fps - duration| < 0.25s
        If validation fails, re-encode once with extra flags to regenerate timestamps.
        """
        fps_str = f"{int(self.fps)}/1"
        info = self.probe.stream_info(dst)
        r = (info.get("r_frame_rate") or "").strip()
        a = (info.get("avg_frame_rate") or "").strip()
        nb = info.get("nb_frames")
        dur = info.get("duration")
        tag = (info.get("codec_tag_string") or "").strip()
        ok_rates = (r == fps_str) and (a == fps_str)
        ok_tag = (tag.upper() in ("MJPG", "MJPG0", "MJPG ")) or (tag == "")

        ok_duration = True
        try:
            if nb and nb.isdigit() and dur:
                nb_i = int(nb)
                dur_f = float(dur)
                expected = nb_i / float(self.fps)
                ok_duration = abs(expected - dur_f) < 0.25
        except Exception:
            ok_duration = True

        if ok_rates and ok_duration and ok_tag:
            self.log_q.put(f"[ok] Validated {dst.name} (r={r}, avg={a}, tag={tag})")
            return True

        self.log_q.put(
            f"[warn] Validation failed for {dst.name} (r={r}, avg={a}, tag={tag});"
            + " re-encoding with PTS fix..."
        )
        tmp_fixed = dst.with_suffix(".tmp_fix.avi")
        cmd_fix = self._build_base_cmd(src, tmp_fixed, vf_fps, q_val, fix_pass=True)
        code2 = self.ff.run(cmd_fix)
        if code2 != 0 or not tmp_fixed.exists():
            self.log_q.put(f"[ERROR] Re-encode with PTS fix failed for {dst.name}")
            try:
                if tmp_fixed.exists():
                    tmp_fixed.unlink()
            except Exception:
                pass
            return False

        try:
            dst.unlink(missing_ok=True)
            tmp_fixed.replace(dst)
        except Exception as e:
            self.log_q.put(f"[ERROR] Could not replace original with fixed file: {e}")
            try:
                if tmp_fixed.exists():
                    tmp_fixed.unlink()
            except Exception:
                pass
            return False

        info2 = self.probe.stream_info(dst)
        r2 = (info2.get("r_frame_rate") or "").strip()
        a2 = (info2.get("avg_frame_rate") or "").strip()
        tag2 = (info2.get("codec_tag_string") or "").strip()
        nb2 = info2.get("nb_frames")
        dur2 = info2.get("duration")
        ok_rates2 = (r2 == fps_str) and (a2 == fps_str)
        ok_tag2 = (tag2.upper() in ("MJPG", "MJPG0", "MJPG ")) or (tag2 == "")
        ok_duration2 = True
        try:
            if nb2 and nb2.isdigit() and dur2:
                nb_i2 = int(nb2)
                dur_f2 = float(dur2)
                expected2 = nb_i2 / float(self.fps)
                ok_duration2 = abs(expected2 - dur_f2) < 0.25
        except Exception:
            ok_duration2 = True

        if ok_rates2 and ok_tag2 and ok_duration2:
            self.log_q.put(
                f"[ok] Fixed & validated {dst.name} (r={r2}, avg={a2}, tag={tag2})"
            )
            return True

        self.log_q.put(
            f"[warn] File still looks odd after fix (r={r2}, avg={a2}, tag={tag2}). "
            + "Proceeding anyway."
        )
        return True

    def _convert_files(self, files: list[Path]):
        if self.is_running:
            return

        chan_raw = self._read_entry(self.channel_entry)
        chan = None
        if chan_raw:
            chan = pad2(chan_raw)
            if not chan:
                self.log_q.put(
                    "[ERROR] Channel must be a number (e.g. 01) or left blank."
                )
                return

        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            self.log_q.put("[ERROR] Please choose an output folder.")
            return
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        self.is_running = True
        if callable(self.on_running_changed):
            self.on_running_changed(True)

        self.convert_finished_once = False
        self.update_controls()
        self.progress["mode"] = "determinate"
        self.progress["maximum"] = len(files)
        self.progress["value"] = 0

        vf = self._vf()
        vf_fps = f"{vf},fps={int(self.fps)}"
        q_val = int(self.quality_var.get())

        def worker():
            ok = True
            for idx, src in enumerate(files, start=1):
                base = src.stem
                prefix = f"{chan}_" if chan else ""
                dst = Path(out_dir) / f"{prefix}{base}.avi"
                self.log_q.put(f"[*] Converting {src.name} -> {dst.name}")

                cmd = self._build_base_cmd(src, dst, vf_fps, q_val, fix_pass=False)
                code = self.ff.run(cmd)
                self.progress["value"] = idx
                self.progress.update_idletasks()
                if code != 0 or not dst.exists():
                    self.log_q.put(f"[ERROR] Conversion failed: {src}")
                    ok = False
                    break

                if not self._validate_and_maybe_fix(dst, src, vf_fps, q_val):
                    ok = False
                    break

            if ok:
                self.log_q.put("[OK] Convert complete.")
            self.is_running = False
            if callable(self.on_running_changed):
                self.on_running_changed(False)
            self.convert_finished_once = True
            self.update_controls()

        threading.Thread(target=worker, daemon=True).start()
