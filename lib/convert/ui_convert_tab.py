import os
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from lib.config import (
    AUDIO_CHANNEL,
    AUDIO_CODEC,
    AUDIO_RATE,
    FPS_CHOICES,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    VIDEO_CODEC,
    VIDEO_EXTENSIONS,
    VIDEO_FILETYPES,
)
from lib.convert.utils import fmt_bytes, fmt_hms, pad2, is_video, PathTools
from lib.convert.convert_service import ConvertService

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False
    Image = None
    ImageTk = None


class ConvertTab(ttk.Frame):
    on_running_changed = None

    def __init__(
        self,
        master,
        *,
        log_fn,
        progress: ttk.Progressbar,
        convert_btn: ttk.Button,
        ffmpeg_cmd: str,
        out_w: int = FRAME_WIDTH,
        out_h: int = FRAME_HEIGHT,
        fps: int = FPS_CHOICES[0],
        v_codec: str = VIDEO_CODEC,
        a_codec: str = AUDIO_CODEC,
        a_rate: str = AUDIO_RATE,
        a_ch: str = AUDIO_CHANNEL,
    ):
        super().__init__(master)
        self.log = log_fn
        self.progress = progress
        self.convert_btn = convert_btn

        self.files: list[Path] = []
        self._preview_target: Path | None = None
        self._preview_img = None
        self._last_dir = str(Path.home())
        self._preview_after = None
        self._duration_cache: dict[Path, float] = {}
        self._known_paths: set[str] = set()
        self.is_running = False
        self.convert_finished_once = False
        self.frame_w, self.frame_h = out_w, out_h

        self.service = ConvertService(
            ffmpeg_cmd,
            out_w=out_w,
            out_h=out_h,
            fps=fps,
            v_codec=v_codec,
            a_codec=a_codec,
            a_rate=a_rate,
            a_ch=a_ch,
            on_log=self.log,
            on_progress=self._on_progress_tick,
            on_running_changed=self._on_running_changed,
        )

        # Build UI
        self._build_ui(fps_initial=fps)
        self.update_controls()
        self._clear_preview()
        self.after(0, self._set_initial_minsize)

    def _build_ui(self, fps_initial: int):
        # Preview area
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

        # File list buttons
        btns = ttk.Frame(self)
        btns.grid(row=0, column=3, rowspan=6, sticky="ne", padx=10, pady=10)
        ttk.Button(btns, text="Add files", command=lambda: self.add_files()).pack(
            pady=(0, 10), fill="x"
        )
        self.btn_up = ttk.Button(
            btns, text="Up", width=12, command=lambda: self.move_selected(-1)
        )
        self.btn_up.pack(pady=2, fill="x")
        self.btn_down = ttk.Button(
            btns, text="Down", width=12, command=lambda: self.move_selected(+1)
        )
        self.btn_down.pack(pady=2, fill="x")
        self.btn_remove = ttk.Button(
            btns, text="Remove", width=12, command=self.remove_selected
        )
        self.btn_remove.pack(pady=2, fill="x")
        self.btn_clear = ttk.Button(
            btns, text="Clear", width=12, command=self.clear_list
        )
        self.btn_clear.pack(pady=2, fill="x")

        # Output directory row
        self.output_dir_var = tk.StringVar()
        self.output_dir_var.trace_add("write", lambda *_: self.update_controls())
        out_row = ttk.Frame(self)
        out_row.grid(row=6, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 10))
        ttk.Button(out_row, text="Output folder", command=self.pick_folder).pack(
            side="left"
        )
        self.output_entry = ttk.Entry(out_row, textvariable=self.output_dir_var)
        self.output_entry.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # Options row
        options_row = ttk.Frame(self)
        options_row.grid(
            row=7, column=0, columnspan=4, sticky="we", padx=10, pady=(0, 4)
        )
        for col in range(4):
            options_row.grid_columnconfigure(col, weight=1)

        # Channel prefix
        chan_group = ttk.Frame(options_row)
        chan_group.grid(row=0, column=0, sticky="w")
        ttk.Label(chan_group, text="Channel prefix (optional)").pack(side="left")
        self.channel_var = tk.StringVar()
        self.channel_entry = tk.Entry(
            chan_group, textvariable=self.channel_var, width=8
        )
        self.channel_entry.pack(side="left", padx=(8, 0))
        self._attach_placeholder(self.channel_entry, "e.g. 01")

        # Scaling options
        scale_group = ttk.Frame(options_row)
        scale_group.grid(row=0, column=1, sticky="we")
        ttk.Label(scale_group, text="Scaling:").pack(side="left", padx=(0, 8))
        self.scale_mode = tk.StringVar(value="stretch")
        for label, val in [
            ("Contain / Letterbox", "contain"),
            ("Cover / Zoom", "cover"),
            ("Fill / Stretch", "stretch"),
        ]:
            ttk.Radiobutton(
                scale_group,
                text=label,
                variable=self.scale_mode,
                value=val,
                command=lambda: self._schedule_preview_update(),
            ).pack(side="left", padx=(0, 8))

        # Audio normalization
        norm_group = ttk.Frame(options_row)
        norm_group.grid(row=0, column=2, sticky="e")
        self.normalize_audio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            norm_group,
            text="Normalize / Boost audio",
            variable=self.normalize_audio_var,
        ).pack(side="right")

        # FPS Dropdown 12/24
        fps_group = ttk.Frame(options_row)
        fps_group.grid(row=0, column=3, sticky="e", padx=(8, 0))
        ttk.Label(fps_group, text="FPS:").pack(side="left")
        self.fps_var = tk.StringVar(value=str(self.service.fps))
        self.fps_box = ttk.Combobox(
            fps_group,
            textvariable=self.fps_var,
            values=[str(v) for v in FPS_CHOICES],
            width=5,
            state="readonly",
        )
        self.fps_box.pack(side="left", padx=(6, 0))
        self.fps_box.bind("<<ComboboxSelected>>", self._on_fps_change)

        # Quality Slider
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

        # Layout
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=2)
        self.grid_columnconfigure(3, weight=0)
        for r in range(9):
            self.grid_rowconfigure(r, weight=0)
        self.grid_rowconfigure(5, weight=1)

        # Convert button
        self.convert_btn.config(text="Convert", command=self.start_convert_all)

    def _on_progress_tick(self, current: int, total: int):
        try:
            self.progress["mode"] = "determinate"
            self.progress["maximum"] = total
            self.progress["value"] = current
            self.progress.update_idletasks()
        except Exception:
            pass

    def _on_running_changed(self, is_running: bool):
        self.is_running = is_running
        if callable(self.on_running_changed):
            self.on_running_changed(is_running)
        self.update_controls()

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

    def _read_entry(self, entry: tk.Entry) -> str:
        val = entry.get().strip()
        if (
            getattr(entry, "_placeholder", None)
            and val == entry._placeholder
            and entry.cget("foreground") == "gray"
        ):
            return ""
        return val

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
            if new_fps not in FPS_CHOICES:
                new_fps = FPS_CHOICES[0]
        except Exception:
            new_fps = FPS_CHOICES[0]
        self.service.fps = new_fps
        self.update_controls()
        self._schedule_preview_update(debounce=True)
        self.log(f"[info] Target FPS set to {self.service.fps}")

    def add_files(self):
        try:
            paths = filedialog.askopenfilenames(
                parent=self.winfo_toplevel(),
                title="Select videos",
                filetypes=VIDEO_FILETYPES,
                initialdir=self._last_dir,
            )
        except Exception as e:
            self.log(f"[ERROR] Open dialog failed: {e}")
            return
        if not paths:
            self.update_controls()
            return
        self._last_dir = str(Path(paths[0]).parent)
        picked: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if not is_video(p, VIDEO_EXTENSIONS):
                continue
            key = PathTools.normalize(p)
            if key in self._known_paths:
                continue
            self._known_paths.add(key)
            picked.append(p)
        if not picked:
            self.update_controls()
            return
        self.files.extend(picked)
        self._refresh_list()
        self.update_controls()
        if self.file_list.size() and not self.file_list.curselection():
            self.file_list.selection_set(0)
            self._schedule_preview_update()

    def remove_selected(self):
        sel = list(self.file_list.curselection())
        if not sel:
            return
        first_idx = sel[0]
        for idx in reversed(sel):
            if 0 <= idx < len(self.files):
                try:
                    self._known_paths.discard(PathTools.normalize(self.files[idx]))
                except Exception:
                    pass
                self.files.pop(idx)
        self._refresh_list()
        if self.files:
            target = max(0, min(first_idx - 1, len(self.files) - 1))
            self.file_list.selection_clear(0, tk.END)
            self.file_list.selection_set(target)
        self.update_controls()
        self._schedule_preview_update()

    def clear_list(self):
        self.files.clear()
        self._known_paths.clear()
        self._refresh_list()
        self.update_controls()
        self._clear_preview()

    def move_selected(self, delta: int):
        sel = list(self.file_list.curselection())
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
        self._refresh_list()
        for i in [min(max(0, i + delta), len(self.files) - 1) for i in sel]:
            self.file_list.selection_set(i)
        self.update_controls()
        self._schedule_preview_update()

    def _refresh_list(self):
        self.file_list.delete(0, tk.END)
        for p in self.files:
            self.file_list.insert(tk.END, p.name)
        if self.files and not self.file_list.curselection():
            self.file_list.selection_set(0)
        self._toggle_empty_hint()

    def pick_folder(self):
        folder = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="Choose output folder",
            initialdir=self._last_dir,
        )
        if folder:
            self.output_dir_var.set(folder)
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
            import threading

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
            duration = self.service.probe.duration(src)
            if duration is not None:
                self._duration_cache[src] = duration

        vf = self.service.build_vf(self.scale_mode.get())
        self.log(f"[preview vf]  {vf}")
        q_now = int(self.quality_var.get())
        self.service.ensure_size_anchors(src, vf, on_ready=self._update_estimate_only)
        thumb = self.service.thumbnail(src, vf, q_now, jpeg_preferred=PIL_AVAILABLE)
        est_bytes = self.service.estimate_size(duration, q_now, vf=vf, src=src)
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
            duration = self.service.probe.duration(src)
            if duration is not None:
                self._duration_cache[src] = duration
        est_bytes = self.service.estimate_size(
            duration,
            int(self.quality_var.get()),
            vf=self.service.build_vf(self.scale_mode.get()),
            src=src,
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
            self.log("[ERROR] Add at least one video.")
            return

        chan = None
        raw = self._read_entry(self.channel_entry)
        if raw:
            chan = pad2(raw)
            if not chan:
                self.log("[ERROR] Channel must be a number (e.g. 01) or left blank.")
                return

        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            self.log("[ERROR] Please choose an output folder.")
            return

        q_val = int(self.quality_var.get())
        self.service.convert_files(
            self.files,
            output_dir=Path(out_dir),
            q_val=q_val,
            scale_mode=self.scale_mode.get(),
            normalize_audio=self.normalize_audio_var.get(),
            channel_prefix=chan,
        )
