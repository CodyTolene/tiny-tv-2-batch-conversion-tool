import queue
import shutil
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from lib.utils import _no_console_kwargs

from lib.convert.ui_convert_tab import ConvertTab
from lib.combine.ui_combine_tab import CombineTab

APP_TITLE = "TinyTV® 2 Batch Conversion Tool"
APP_VERSION = "1.2.0"


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Running from bundled EXE (PyInstaller)
        return Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return Path(__file__).resolve().parent


def _bin_candidate(exe_name: str) -> Path:
    # exe_name should include extension on Windows (e.g., "ffmpeg.exe")
    return _app_base_dir() / "bin" / exe_name


def resolve_tool(preferred_name_with_ext: str, path_name_no_ext: str) -> str:
    # Prefer local bin copy
    local_path = _bin_candidate(preferred_name_with_ext)
    if local_path.exists():
        return str(local_path)

    # Fall back to system PATH
    found = shutil.which(path_name_no_ext)
    if found:
        return found

    # Last resort: return the bin path we expected (will fail validation later)
    return str(local_path)


def resolve_ffmpeg_path() -> str:
    # Windows build ships ffmpeg.exe; PATH fallback is "ffmpeg"
    return resolve_tool("ffmpeg.exe", "ffmpeg")


def resolve_ffprobe_path() -> str:
    return resolve_tool("ffprobe.exe", "ffprobe")


FFMPEG_CMD = resolve_ffmpeg_path()
FFPROBE_CMD = resolve_ffprobe_path()


class TinyTVApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} (v{APP_VERSION})")
        self.geometry("980x640")

        self.log_q: queue.Queue[str] = queue.Queue()

        self._build_layout()
        self._wire_tabs()
        self._wire_bottom_bar()
        self._start_log_pump()

        self.log_q.put(f"ffmpeg path resolved to: {FFMPEG_CMD}")
        self.log_q.put(f"{APP_TITLE} ready!")

        self.after(0, self._validate_tools)

    def _build_layout(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        self.nb = ttk.Notebook(self)
        self.nb.grid(row=0, column=0, sticky="nsew")

        self.bottom_bar = ttk.Frame(self)
        self.bottom_bar.grid(row=1, column=0, sticky="we", padx=10, pady=8)
        self.bottom_bar.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(self.bottom_bar, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="we", padx=(0, 8))

        btn_wrap = ttk.Frame(self.bottom_bar)
        btn_wrap.grid(row=0, column=1, sticky="e")

        self.clear_log_btn = ttk.Button(
            btn_wrap, text="Clear log", command=self._clear_log
        )
        self.clear_log_btn.pack(side="left", padx=(0, 8))

        self.convert_btn = ttk.Button(btn_wrap, text="Convert")
        self.convert_btn.pack(side="left")

        self.combine_btn = ttk.Button(btn_wrap, text="Combine")
        self.combine_btn.pack(side="left")
        self.combine_btn.pack_forget()

        self.log_text = tk.Text(self, height=8, wrap="word", state="disabled")
        self.log_text.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 2))
        self.rowconfigure(2, weight=0)

        # Hyperlinks
        link_frame = ttk.Frame(self)
        link_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        # Four even columns
        for i in range(4):
            link_frame.columnconfigure(i, weight=1)

        # Author link
        author_frame = ttk.Frame(link_frame)
        author_frame.grid(row=0, column=0, sticky="w")
        tk.Label(author_frame, text="Author: ").pack(side="left")
        self.link1 = tk.Label(
            author_frame, text="Cody Tolene", fg="blue", cursor="hand2"
        )
        self.link1.pack(side="left")
        self.link1.bind(
            "<Button-1>", lambda e: self._open_link("https://github.com/CodyTolene")
        )

        # Tiny Circuits link
        tinytv_frame = ttk.Frame(link_frame)
        tinytv_frame.grid(row=0, column=1)
        tk.Label(tinytv_frame, text="Purchase TinyTV 2: ").pack(side="left")
        self.link2 = tk.Label(
            tinytv_frame, text="Tiny Circuits", fg="blue", cursor="hand2"
        )
        self.link2.pack(side="left")
        self.link2.bind(
            "<Button-1>", lambda e: self._open_link("https://www.tinycircuits.com/")
        )

        # FFmpeg link
        ffmpeg_frame = ttk.Frame(link_frame)
        ffmpeg_frame.grid(row=0, column=2)
        tk.Label(ffmpeg_frame, text="Powered by ").pack(side="left")
        self.link4 = tk.Label(ffmpeg_frame, text="FFmpeg", fg="blue", cursor="hand2")
        self.link4.pack(side="left")
        self.link4.bind("<Button-1>", lambda e: self._open_link("https://ffmpeg.org/"))
        tk.Label(ffmpeg_frame, text=" (LGPLv2.1)").pack(side="left")

        # Donation link
        donate_frame = ttk.Frame(link_frame)
        donate_frame.grid(row=0, column=3, sticky="e")
        tk.Label(donate_frame, text="Any ").pack(side="left")
        self.link3 = tk.Label(donate_frame, text="donation", fg="blue", cursor="hand2")
        self.link3.pack(side="left")
        self.link3.bind(
            "<Button-1>",
            lambda e: self._open_link("https://github.com/sponsors/CodyTolene"),
        )
        tk.Label(donate_frame, text=" appreciated!").pack(side="left")

    def _wire_tabs(self):
        self.convert_tab = ConvertTab(
            self.nb,
            log_fn=self.log_q.put,
            progress=self.progress,
            convert_btn=self.convert_btn,
            ffmpeg_cmd=FFMPEG_CMD,
        )
        self.nb.add(self.convert_tab, text="Convert")

        self.combine_tab = CombineTab(
            self.nb,
            log_fn=self.log_q,
            ffmpeg_cmd=FFMPEG_CMD,
            progress=self.progress,
            combine_btn=self.combine_btn,
        )
        self.nb.add(self.combine_tab, text="Combine")

        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

    def _wire_bottom_bar(self):
        self.convert_btn.config(command=self._convert_wrapper_start)
        self.combine_btn.config(command=self.combine_tab.start_combine)
        try:
            self.convert_tab.attach_clear_log_button(
                self.clear_log_btn,
                is_empty_fn=lambda: self._log_is_empty(),
                clear_fn=self._clear_log,
            )
        except Exception:
            pass

    def _on_tab_changed(self, _=None):
        idx = self.nb.index(self.nb.select())
        if idx == 0:  # Convert
            self.combine_btn.pack_forget()
            self.convert_btn.pack(side="left")
        else:  # Combine
            self.convert_btn.pack_forget()
            self.combine_btn.pack(side="left")

    def _convert_wrapper_start(self):
        # Disable Combine tab while converting
        try:
            self.nb.tab(1, state="disabled")
        except Exception:
            pass

        try:
            self.convert_tab.start_convert_all()
        finally:
            self.after(200, self._poll_convert_running)

    def _poll_convert_running(self):
        running = False
        try:
            running = bool(self.convert_tab.is_running)
        except Exception:
            pass

        if running:
            self.after(250, self._poll_convert_running)
            return

        try:
            self.nb.tab(1, state="normal")
        except Exception:
            pass

    def _start_log_pump(self):
        self.after(75, self._drain_log)

    def _drain_log(self):
        pushed_any = False
        try:
            while True:
                line = self.log_q.get_nowait()
                self._append_log(line + "\n")
                pushed_any = True
        except queue.Empty:
            pass

        if pushed_any:
            self.log_text.see("end")

        self.after(100, self._drain_log)

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _log_is_empty(self) -> bool:
        content = self.log_text.get("1.0", "end-1c")
        return len(content.strip()) == 0

    def _open_link(self, url: str):
        import webbrowser

        webbrowser.open_new(url)

    def _validate_tools(self):
        def _works(cmd: str) -> bool:
            try:
                subprocess.run(
                    [cmd, "-version"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    **_no_console_kwargs(),
                )
                return True
            except Exception as e:
                self.log_q.put(f"[DEBUG] ffmpeg check failed for '{cmd}': {e!r}")
                return False

        # from pathlib import Path as _P
        # self.log_q.put(f"[DEBUG] _MEIPASS={getattr(sys, '_MEIPASS', None)}")
        # self.log_q.put(
        #     f"[DEBUG] expecting ffmpeg at: {FFMPEG_CMD} "
        #     + f"exists={_P(FFMPEG_CMD).exists()}"
        # )

        if not _works(FFMPEG_CMD):
            self.log_q.put(
                "[ERROR] ffmpeg not found. Install ffmpeg globally (and add to PATH) "
                "or place ffmpeg.exe in the app's bin/ folder."
            )

        # if not _works(FFPROBE_CMD):
        #     self.log_q.put(
        #         "[WARN] ffprobe not found. Some features may be unavailable."
        #     )


if __name__ == "__main__":
    TinyTVApp().mainloop()
