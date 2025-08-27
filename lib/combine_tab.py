import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

# Allowed video types
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v", ".mpg", ".mpeg", ".flv")
VIDEO_PATTERNS = ";".join(f"*{ext}" for ext in VIDEO_EXTS) # Windows uses ';' between patterns
VIDEO_FILETYPES = [("Video files", VIDEO_PATTERNS)]

def is_video(p: Path) -> bool:
    return p.suffix.lower() in set(VIDEO_EXTS)


def pad2(s: str) -> str | None:
    try:
        return f"{int(s):02d}"
    except Exception:
        return None


class CombineTab(ttk.Frame):
    """UI + behavior for the 'Combine' tab."""
    def __init__(self, parent, *, log_q, ffmpeg_cmd: str):
        super().__init__(parent)
        self.log_q = log_q
        self.ffmpeg = ffmpeg_cmd

        # State
        self.files: list[Path] = []

        # UI
        self.build_ui()
        self.update_buttons()

    def build_ui(self):
        # Listbox (files)
        self.listbox = tk.Listbox(self, selectmode=tk.EXTENDED, height=14)
        self.listbox.grid(row=0, column=0, rowspan=6, sticky="nsew", padx=(10, 0), pady=10)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.update_buttons())

        # Buttons
        btn_col = ttk.Frame(self)
        btn_col.grid(row=0, column=1, sticky="ns", padx=10, pady=10)

        self.btn_add = ttk.Button(btn_col, text="Add files", command=self.add_files)
        self.btn_add.pack(pady=(0, 10), fill="x")

        self.btn_up = ttk.Button(btn_col, text="Up", width=12, command=lambda: self.move_selected(-1))
        self.btn_up.pack(pady=2, fill="x")

        self.btn_down = ttk.Button(btn_col, text="Down", width=12, command=lambda: self.move_selected(+1))
        self.btn_down.pack(pady=2, fill="x")

        self.btn_remove = ttk.Button(btn_col, text="Remove", width=12, command=self.remove_selected)
        self.btn_remove.pack(pady=2, fill="x")

        self.btn_clear = ttk.Button(btn_col, text="Clear", width=12, command=self.clear_list)
        self.btn_clear.pack(pady=2, fill="x")

        # Output
        self.out_var = tk.StringVar()
        out_row = ttk.Frame(self)
        out_row.grid(row=6, column=0, columnspan=2, sticky="we", padx=10, pady=(0, 10))
        ttk.Button(out_row, text="Output folder", command=self.pick_folder).pack(side="left")
        ttk.Entry(out_row, textvariable=self.out_var, width=70).pack(side="left", padx=(8, 0), fill="x", expand=True)

        # Channel (optional)
        ttk.Label(self, text="Channel").grid(row=7, column=0, sticky="w", padx=10)
        self.chan_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.chan_var, width=8).grid(row=7, column=0, sticky="w", padx=(70, 0))

        # Output name and start button
        ttk.Label(self, text="Output name").grid(row=8, column=0, sticky="w", padx=10)
        self.name_var = tk.StringVar(value="combined_episodes.avi")
        ttk.Entry(self, textvariable=self.name_var, width=40).grid(row=8, column=0, sticky="w", padx=(100, 0))
        ttk.Button(self, text="Start Combine", command=self.start_combine).grid(row=8, column=0, sticky="e", padx=(0, 10))

        # Grid
        for i in range(2):
            self.grid_columnconfigure(i, weight=1)
        self.grid_rowconfigure(5, weight=1)

    def write_log(self, text: str):
        self.log_q.put(text)

    def update_buttons(self):
        n = len(self.files)
        sel = list(self.listbox.curselection())

        up_down_state = ("normal" if (n > 1 and sel) else "disabled")
        self.btn_up.config(state=up_down_state)
        self.btn_down.config(state=up_down_state)

        self.btn_remove.config(state=("normal" if sel else "disabled"))
        self.btn_clear.config(state=("normal" if n >= 1 else "disabled"))

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.files:
            self.listbox.insert(tk.END, p.name)
        self.update_buttons()

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select videos", filetypes=VIDEO_FILETYPES)
        if not paths:
            return
        picks = [Path(p) for p in paths if is_video(Path(p))]
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
        if delta < 0:
            for i in sel:
                j = i + delta
                if j >= 0:
                    self.files[i], self.files[j] = self.files[j], self.files[i]
        else:
            for i in reversed(sel):
                j = i + delta
                if j < len(self.files):
                    self.files[i], self.files[j] = self.files[j], self.files[i]
        self.refresh_list()
        # Reselect moved
        for i in [min(max(0, i + delta), len(self.files) - 1) for i in sel]:
            self.listbox.selection_set(i)

    def pick_folder(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.out_var.set(folder)

    def spawn_ffmpeg(self, args: list[str]) -> int:
        try:
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, universal_newlines=True)
            for line in proc.stderr:
                self.log_q.put(line.strip())
            return proc.wait()
        except Exception as e:
            self.write_log(f"[ERROR] {e}")
            return 1

    def start_combine(self):
        files = list(self.files)
        if not files:
            self.write_log("[ERROR] Add some videos first.")
            return

        out_dir = self.out_var.get().strip() or str(Path.cwd())
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        chan_txt = self.chan_var.get().strip()
        chan_prefix = ""
        if chan_txt:
            p = pad2(chan_txt)
            if not p:
                self.write_log("[ERROR] Channel must be a number (e.g. 01) or left blank.")
                return
            chan_prefix = f"{p}_"

        out_name = (self.name_var.get().strip() or "combined_episodes.avi")
        out_path = Path(out_dir) / f"{chan_prefix}{out_name}"

        def worker():
            lst = out_path.with_suffix(".txt")
            with open(lst, "w", encoding="utf-8") as f:
                for p in files:
                    f.write(f"file '{Path(p).as_posix()}'\n")

            self.write_log(f"[*] Joining {len(files)} files -> {out_path.name}")
            cmd = [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-stats", "-y",
                "-f", "concat", "-safe", "0", "-i", str(lst),
                "-c", "copy", str(out_path)
            ]
            code = self.spawn_ffmpeg(cmd)

            try:
                lst.unlink(missing_ok=True)
            except Exception:
                pass

            if code == 0:
                self.write_log("[OK] Combine complete.")
            else:
                self.write_log("[ERROR] Combine failed.")

        threading.Thread(target=worker, daemon=True).start()
