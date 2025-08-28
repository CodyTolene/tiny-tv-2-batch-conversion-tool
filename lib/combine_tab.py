import threading
import subprocess
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog

# AVI files only
VIDEO_EXTENSIONS = (".avi",)
VIDEO_PATTERNS = ";".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
VIDEO_FILETYPES = [("AVI files", VIDEO_PATTERNS)]

FAT32_MAX_FILE_BYTES = (4 * 1024 * 1024 * 1024) - 1  # 4GB - 1 byte

# When there are many files, use concat demuxer to avoid Windows command-length limits
CONCAT_LIST_THRESHOLD = 50


def _no_console_kwargs() -> dict:
    """Return subprocess kwargs that suppress the console window on Windows."""
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
    def __init__(self, parent, *, log_q, ffmpeg_cmd: str):
        super().__init__(parent)
        self.log_q = log_q
        self.ffmpeg = ffmpeg_cmd

        self.files: list[Path] = []
        self._last_dir = str(Path.home())
        self._combine_btn: ttk.Button | None = None
        self._estimate_over_limit = False

        self._build_ui()
        self._update_buttons()
        self._update_estimate()

    def attach_combine_button(self, btn: ttk.Button):
        self._combine_btn = btn
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

        # Keep selection
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

        self.out_var = tk.StringVar()
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
        for c in range(3):
            options_row.grid_columnconfigure(c, weight=1)

        chan_group = ttk.Frame(options_row)
        chan_group.grid(row=0, column=0, sticky="w")
        ttk.Label(chan_group, text="Channel prefix (optional)").pack(side="left")
        self.chan_var = tk.StringVar()
        self.chan_entry = tk.Entry(chan_group, textvariable=self.chan_var, width=8)
        self.chan_entry.pack(side="left", padx=(8, 0))
        self._attach_placeholder(self.chan_entry, "e.g. 01")

        name_group = ttk.Frame(options_row)
        name_group.grid(row=0, column=1, sticky="we")
        name_group.grid_columnconfigure(0, weight=0)
        name_group.grid_columnconfigure(1, weight=1)
        ttk.Label(name_group, text="Output name").grid(
            row=0, column=0, sticky="e", padx=(0, 8)
        )
        self.name_var = tk.StringVar(value="combined_episodes.avi")
        self.name_entry = ttk.Entry(name_group, textvariable=self.name_var, width=32)
        self.name_entry.grid(row=0, column=1, sticky="w")

        size_group = ttk.Frame(options_row)
        size_group.grid(row=0, column=2, sticky="e")
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
        # File final size estimate
        total = 0
        for p in self.files:
            try:
                total += p.stat().st_size
            except Exception:
                pass

        txt = f"Estimated size: {fmt_bytes(total)}"
        over = total > FAT32_MAX_FILE_BYTES

        # Update label color, red if over limit
        try:
            self.size_label.config(text=txt, foreground=("red" if over else "black"))
        except Exception:
            pass

        # Enable/disable combine button
        if self._combine_btn is not None:
            try:
                self._combine_btn.config(
                    state=("disabled" if over or not self.files else "normal")
                )
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
            self.refresh_list()

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for idx in reversed(sel):
            if 0 <= idx < len(self.files):
                self.files.pop(idx)
        self.refresh_list()

    def clear_list(self):
        self.files.clear()
        self.refresh_list()

    def move_selected(self, delta: int):
        sel = list(self.listbox.curselection())
        if not sel:
            return

        # Reorder based on move direction
        iterate = sel if delta < 0 else list(reversed(sel))
        for i in iterate:
            j = i + delta
            if 0 <= j < len(self.files):
                self.files[i], self.files[j] = self.files[j], self.files[i]

        new_indices = [min(max(0, i + delta), len(self.files) - 1) for i in sel]

        # Refresh and reselect
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
            self.log_q.put(text)
        except Exception:
            pass

    def spawn_ffmpeg(self, args: list[str]) -> int:
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                **_no_console_kwargs(),
            )
            for line in proc.stderr:
                self.write_log(line.strip())
            return proc.wait()
        except Exception as e:
            self.write_log(f"[ERROR] {e}")
            return 1

    def _run_concat_demuxer_reencode(self, files: list[Path], out_path: Path) -> int:
        fd, list_path = tempfile.mkstemp(prefix="tinytv_concat_", suffix=".txt")
        try:
            path = Path(list_path)
            with open(path, "w", encoding="utf-8") as f:
                for p in files:
                    f.write(f"file '{p.as_posix()}'\n")

            self.write_log(
                f"[*] Using concat list ({len(files)} files) with re-encode for sync"
            )
            cmd = [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-stats",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(path),
                "-fflags",
                "+genpts",
                # Video timing + format
                "-vf",
                "fps=12,format=yuvj420p,setsar=1",
                "-r",
                "12",
                "-c:v",
                "mjpeg",
                "-q:v",
                "16",
                # Audio timing + format
                "-af",
                "aresample=async=1:min_hard_comp=0.100:first_pts=0,"
                "aformat=sample_fmts=u8:channel_layouts=mono,"
                "asetpts=PTS",
                "-c:a",
                "pcm_u8",
                "-ar",
                "8000",
                "-ac",
                "1",
                str(out_path),
            ]
            return self.spawn_ffmpeg(cmd)
        finally:
            try:
                Path(list_path).unlink(missing_ok=True)
            except Exception:
                pass

    def start_combine(self):
        files = list(self.files)
        if not files:
            self.write_log("[ERROR] Add some .avi videos first.")
            return

        # Block if over FAT32 limit
        if self._estimate_over_limit:
            self.write_log(
                "[ERROR] Estimated output exceeds FAT32 single-file limit (~4GB). "
                + "Remove files or split the batch."
            )
            return

        out_dir = self.out_var.get().strip() or str(Path.cwd())
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        chan_txt = self.chan_var.get().strip()
        chan_prefix = ""
        if chan_txt:
            p = pad2(chan_txt)
            if not p:
                self.write_log(
                    "[ERROR] Channel must be a number (e.g. 01) or left blank."
                )
                return
            chan_prefix = f"{p}_"

        out_name = self.name_var.get().strip() or "combined_episodes.avi"
        out_path = Path(out_dir) / f"{chan_prefix}{out_name}"

        def worker():
            try:
                if len(files) == 1:
                    src = files[0]
                    self.write_log(f"[*] Transcoding single file -> {out_path.name}")
                    cmd = [
                        self.ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-stats",
                        "-y",
                        "-i",
                        str(src),
                        "-vf",
                        "fps=12,format=yuvj420p,setsar=1,setpts=N/12/TB",
                        "-r",
                        "12",
                        "-c:v",
                        "mjpeg",
                        "-q:v",
                        "16",
                        "-c:a",
                        "pcm_u8",
                        "-ar",
                        "8000",
                        "-ac",
                        "1",
                        "-af",
                        "aresample=async=1:min_hard_comp=0.100:first_pts=0,"
                        "aformat=sample_fmts=u8:channel_layouts=mono,"
                        "asetpts=N/SR/TB",
                        str(out_path),
                    ]
                    code = self.spawn_ffmpeg(cmd)
                    if code == 0:
                        self.write_log("[OK] Combine complete.")
                    else:
                        self.write_log("[ERROR] Combine failed.")
                    return

                # Use concat demuxer for MANY files (Windows string limits)
                if len(files) >= CONCAT_LIST_THRESHOLD:
                    self.write_log(
                        f"[*] Joining {len(files)} AVI files with concat demuxer "
                        + f"(re-encode) -> {out_path.name}"
                    )
                    code = self._run_concat_demuxer_reencode(files, out_path)
                    if code == 0:
                        self.write_log("[OK] Combine complete.")
                    else:
                        self.write_log("[ERROR] Combine failed.")
                    return

                # Otherwise, keep normalized filter
                inputs: list[str] = []
                for p in files:
                    inputs.extend(["-i", str(p)])

                parts: list[str] = []
                interleaved: list[str] = []
                for idx in range(len(files)):
                    v_lbl = f"v{idx}"
                    a_lbl = f"a{idx}"
                    parts.append(
                        f"[{idx}:v:0]fps=12,format=yuvj420p,setsar=1,"
                        + f"setpts=N/12/TB[{v_lbl}]"
                    )
                    parts.append(
                        f"[{idx}:a:0]aresample=async=1:min_hard_comp=0.100:first_pts=0,"
                        f"aformat=sample_fmts=u8:channel_layouts=mono,"
                        f"asetpts=N/SR/TB[{a_lbl}]"
                    )
                    interleaved.extend([f"[{v_lbl}]", f"[{a_lbl}]"])

                n = len(files)
                parts.append("".join(interleaved) + f"concat=n={n}:v=1:a=1[v][a]")
                filter_complex = ";".join(parts)

                cmd = [
                    self.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-stats",
                    "-y",
                    *inputs,
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-r",
                    "12",
                    "-c:v",
                    "mjpeg",
                    "-q:v",
                    "16",
                    "-c:a",
                    "pcm_u8",
                    "-ar",
                    "8000",
                    "-ac",
                    "1",
                    str(out_path),
                ]

                self.write_log(f"[*] Joining {len(files)} AVI files -> {out_path.name}")
                code = self.spawn_ffmpeg(cmd)
                if code == 0:
                    self.write_log("[OK] Combine complete.")
                else:
                    self.write_log("[ERROR] Combine failed.")
            except Exception as e:
                self.write_log(f"[ERROR] {e}")

        threading.Thread(target=worker, daemon=True).start()
