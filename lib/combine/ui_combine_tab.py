import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

from lib.combine.combine_service import CombineService
from lib.config import (
    VIDEO_CODEC,
    AUDIO_CODEC,
    AUDIO_RATE,
    AUDIO_CHANNEL,
    PIXEL_FORMAT,
)
from lib.utils import _no_console_kwargs

VIDEO_EXTENSIONS = (".avi",)
VIDEO_PATTERNS = ";".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
VIDEO_FILETYPES = [("AVI files", VIDEO_PATTERNS)]

FAT32_MAX_FILE_BYTES = (4 * 1024 * 1024 * 1024) - 1


def is_video(p: Path) -> bool:
    return p.suffix.lower() in set(VIDEO_EXTENSIONS)


def pad2(text: str) -> str | None:
    try:
        return f"{int(text):02d}"
    except Exception:
        return None


def fmt_bytes(n: int) -> str:
    try:
        if n < 1024:
            return f"{n} B"
        kb = n / 1024
        if kb < 1024:
            return f"{kb:.2f} KB"
        mb = kb / 1024
        if mb < 1024:
            return f"{mb:.2f} MB"
        gb = mb / 1024
        return f"{gb:.2f} GB"
    except Exception:
        return "N/A"


class CombineTab(ttk.Frame):
    def __init__(
        self,
        parent,
        *,
        log_fn,
        ffmpeg_cmd: str,
        progress=None,
        combine_btn: ttk.Button | None = None,
    ):
        super().__init__(parent)

        if callable(log_fn):
            self._log_put = log_fn
        elif hasattr(log_fn, "put") and callable(getattr(log_fn, "put")):
            self._log_put = log_fn.put
        else:

            def _noop(msg: str):  # fallback
                pass

            self._log_put = _noop

        self.ffmpeg = ffmpeg_cmd
        self.ffprobe = self._guess_ffprobe(ffmpeg_cmd)

        self.files: list[Path] = []
        self._last_dir = str(Path.home())
        self._combine_btn: ttk.Button | None = combine_btn
        self._estimate_over_limit = False

        self._fps_cache: dict[Path, float] = {}
        self.fps_var = tk.StringVar(value="12")

        self.chan_var = tk.StringVar()
        self.name_var = tk.StringVar(value="combined_episodes")
        self.out_var = tk.StringVar()

        self.service = CombineService(
            ffmpeg_cmd,
            on_log=self.write_log,
            v_codec=VIDEO_CODEC,
            p_format=PIXEL_FORMAT,
            a_codec=AUDIO_CODEC,
            a_rate=int(AUDIO_RATE),
            a_ch=int(AUDIO_CHANNEL),
            q_val=31,
        )

        self._build_ui()
        self._update_buttons()
        self._update_estimate()

        if self._combine_btn is not None:
            self._combine_btn.configure(command=self.start_combine)

    def _guess_ffprobe(self, ffmpeg_cmd: str) -> str:
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

    def _probe_fps(self, path: Path) -> float | None:
        try:
            cmd = [
                self.ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate,r_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
            out = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            )
            lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
            for token in lines:
                if token and token != "0/0":
                    if "/" in token:
                        num, den = token.split("/", 1)
                        try:
                            num = float(num.strip())
                            den = float(den.strip())
                            if den != 0:
                                fps = num / den
                                if fps > 0:
                                    return fps
                        except Exception:
                            continue
                    else:
                        try:
                            fps = float(token)
                            if fps > 0:
                                return fps
                        except Exception:
                            continue
        except Exception:
            pass
        return None

    def _get_cached_fps(self, p: Path) -> float:
        if p not in self._fps_cache:
            fps = self._probe_fps(p)
            if fps is None or fps <= 0:
                fps = 12.0
            self._fps_cache[p] = fps
        return self._fps_cache[p]

    def attach_combine_button(self, btn: ttk.Button):
        self._combine_btn = btn
        self._combine_btn.configure(command=self.start_combine)
        self._update_estimate()

    def _build_ui(self):
        list_wrap = ttk.Frame(self)
        list_wrap.grid(
            row=0,
            column=0,
            columnspan=2,
            rowspan=6,
            sticky="nsew",
            padx=(10, 0),
            pady=10,
        )
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_wrap, selectmode=tk.EXTENDED, height=16, exportselection=False
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", lambda _e=None: self._update_buttons())

        vscroll = ttk.Scrollbar(
            list_wrap, orient="vertical", command=self.listbox.yview
        )
        vscroll.grid(row=0, column=1, sticky="ns")
        self.listbox.config(yscrollcommand=vscroll.set)

        btn_col = ttk.Frame(self)
        btn_col.grid(row=0, column=2, rowspan=6, sticky="ne", padx=10, pady=10)

        self.btn_add = ttk.Button(btn_col, text="Add files", command=self.add_files)
        self.btn_add.pack(pady=(0, 10), fill="x")

        self.btn_up = ttk.Button(
            btn_col, text="Up", width=12, command=lambda: self.move_selected(-1)
        )
        self.btn_up.pack(pady=2, fill="x")

        self.btn_down = ttk.Button(
            btn_col, text="Down", width=12, command=lambda: self.move_selected(+1)
        )
        self.btn_down.pack(pady=2, fill="x")

        self.btn_remove = ttk.Button(
            btn_col, text="Remove", width=12, command=self.remove_selected
        )
        self.btn_remove.pack(pady=2, fill="x")

        self.btn_clear = ttk.Button(
            btn_col, text="Clear", width=12, command=self.clear_list
        )
        self.btn_clear.pack(pady=2, fill="x")

        out_row = ttk.Frame(self)
        out_row.grid(row=6, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 10))
        ttk.Button(out_row, text="Output folder", command=self.pick_folder).pack(
            side="left"
        )
        ttk.Entry(out_row, textvariable=self.out_var).pack(
            side="left", padx=(8, 0), fill="x", expand=True
        )

        # Options row
        options_row = ttk.Frame(self)
        options_row.grid(
            row=7, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 4)
        )
        for c in range(4):
            options_row.grid_columnconfigure(c, weight=1)

        # Channel
        chan_group = ttk.Frame(options_row)
        chan_group.grid(row=0, column=0, sticky="w")
        ttk.Label(chan_group, text="Channel prefix (optional)").pack(side="left")
        self.chan_entry = tk.Entry(chan_group, textvariable=self.chan_var, width=8)
        self.chan_entry.pack(side="left", padx=(8, 0))
        self._attach_placeholder(self.chan_entry, "e.g. 01")

        # Output name
        name_group = ttk.Frame(options_row)
        name_group.grid(row=0, column=1, sticky="we")
        name_group.grid_columnconfigure(0, weight=0)
        name_group.grid_columnconfigure(1, weight=1)
        ttk.Label(name_group, text="Output name").grid(
            row=0, column=0, sticky="e", padx=(0, 8)
        )
        self.name_entry = ttk.Entry(name_group, textvariable=self.name_var, width=32)
        self.name_entry.grid(row=0, column=1, sticky="w")

        # FPS selector
        fps_group = ttk.Frame(options_row)
        fps_group.grid(row=0, column=2, sticky="e")
        ttk.Label(fps_group, text="FPS").pack(side="left", padx=(0, 6))
        self.fps_box = ttk.Combobox(
            fps_group,
            textvariable=self.fps_var,
            values=["12", "24"],
            width=6,
            state="readonly",
        )
        self.fps_box.pack(side="left")
        self.fps_box.bind("<<ComboboxSelected>>", lambda _e=None: self._fps_changed())

        # Estimated size
        size_group = ttk.Frame(options_row)
        size_group.grid(row=0, column=3, sticky="e")
        self.size_label = ttk.Label(
            size_group, text="Estimated size: 0 B", foreground="black"
        )
        self.size_label.pack(side="right")

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=0)
        for r in range(8):
            self.grid_rowconfigure(r, weight=0)
        self.grid_rowconfigure(5, weight=1)

    def _fps_changed(self):
        try:
            fps = int(self.fps_var.get())
        except Exception:
            fps = 12
            self.fps_var.set("12")
        self.write_log(f"[*] Target FPS set to {fps}")
        self._update_estimate()

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

    def _read_entry(self, entry: tk.Entry) -> str:
        val = entry.get().strip()
        try:
            if (
                getattr(entry, "_placeholder", None)
                and val == entry._placeholder
                and entry.cget("foreground") == "gray"
            ):
                return ""
        except Exception:
            pass
        return val

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.files:
            self.listbox.insert(tk.END, p.name)
        self._update_buttons()
        self._update_estimate()

    def _update_buttons(self):
        sel = bool(self.listbox.curselection())
        many = len(self.files) > 1 and sel
        self.btn_up.config(state=("normal" if many else "disabled"))
        self.btn_down.config(state=("normal" if many else "disabled"))
        self.btn_remove.config(state=("normal" if sel else "disabled"))
        self.btn_clear.config(state=("normal" if self.files else "disabled"))

    def _update_estimate(self):
        try:
            target_fps = int(self.fps_var.get())
        except Exception:
            target_fps = 12

        total = 0
        for p in self.files:
            try:
                src_size = p.stat().st_size
            except Exception:
                continue
            src_fps = self._get_cached_fps(p)
            ratio = max(0.1, float(target_fps) / max(0.1, src_fps))
            total += int(src_size * ratio)

        txt = f"Estimated size: {fmt_bytes(total)}"
        over = total > FAT32_MAX_FILE_BYTES

        try:
            self.size_label.config(text=txt, foreground=("red" if over else "black"))
        except Exception:
            pass

        self._estimate_over_limit = over

    def add_files(self):
        paths = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Select AVI videos",
            filetypes=VIDEO_FILETYPES,
            initialdir=self._last_dir,
        )
        if not paths:
            return

        picks = []
        for raw in paths:
            p = Path(raw)
            if not is_video(p):
                continue
            picks.append(p)

        if picks:
            self._last_dir = str(Path(picks[0]).parent)
            self.files.extend(picks)
            for p in picks:
                _ = self._get_cached_fps(p)
            self.refresh_list()

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for idx in reversed(sel):
            if 0 <= idx < len(self.files):
                p = self.files.pop(idx)
                self._fps_cache.pop(p, None)
        self.refresh_list()

    def clear_list(self):
        self.files.clear()
        self._fps_cache.clear()
        self.refresh_list()

    def move_selected(self, delta: int):
        sel = list(self.listbox.curselection())
        if not sel:
            return

        iterate = sel if delta < 0 else list(reversed(sel))
        for i in iterate:
            j = i + delta
            if 0 <= j < len(self.files):
                self.files[i], self.files[j] = self.files[j], self.files[i]

        new_indices = [min(max(0, i + delta), len(self.files) - 1) for i in sel]

        self.refresh_list()
        self.listbox.selection_clear(0, tk.END)
        for idx in new_indices:
            self.listbox.selection_set(idx)
        if new_indices:
            self.listbox.activate(new_indices[0])
            self.listbox.see(new_indices[0])
        self.listbox.focus_set()
        self._update_buttons()
        self._update_estimate()

    def pick_folder(self):
        folder = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="Choose output folder",
            initialdir=self._last_dir,
        )
        if folder:
            self.out_var.set(folder)
            self._last_dir = folder

    def write_log(self, text: str):
        try:
            self._log_put(text)
        except Exception:
            pass

    def start_combine(self):
        files = list(self.files)
        if not files:
            self.write_log("[ERROR] Add some .avi videos first.")
            return

        out_dir = self.out_var.get().strip() or str(Path.cwd())
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        # Channel (optional)
        chan_txt = self._read_entry(self.chan_entry)
        chan_prefix = ""
        if chan_txt:
            p = pad2(chan_txt)
            if not p:
                self.write_log(
                    "[ERROR] Channel must be a number (e.g. 01) or left blank."
                )
                return
            chan_prefix = f"{p}_"

        # Output name
        raw_name = self._read_entry(self.name_entry) or "combined_episodes"
        name = raw_name.strip()
        if name.lower().endswith(".avi"):
            name = name[:-4]
        if not name:
            name = "combined_episodes"

        out_path = Path(out_dir) / f"{chan_prefix}{name}.avi"

        # Target FPS
        try:
            fps = int(self.fps_var.get())
        except Exception:
            fps = 12
            self.fps_var.set("12")

        # Worker
        def worker():
            try:
                self.write_log(
                    f"[*] Combining {len(files)} file(s) @ {fps} fps -> {out_path.name}"
                )
                code = self.service.combine(files, out_path, fps=fps)
                if code == 0 and out_path.exists():
                    self.write_log("[OK] Combine complete.")
                else:
                    self.write_log("[ERROR] Combine failed.")
            except Exception as e:
                self.write_log(f"[ERROR] {e}")

        threading.Thread(target=worker, daemon=True).start()
