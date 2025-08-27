import sys
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from lib.convert_tab import ConvertTab
from lib.combine_tab import CombineTab

APP_TITLE = "TinyTV 2 Batch Conversion Tool"

def find_ffmpeg():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)).resolve()
    local = base / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"

FFMPEG = find_ffmpeg()

class TinyTVApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x660")

        self.log_q = queue.Queue()

        # Tabs
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # Convert tab
        convert_frame = ttk.Frame(self.nb)
        self.nb.add(convert_frame, text="Convert")

        # Combine tab
        combine_frame = ttk.Frame(self.nb)
        self.nb.add(combine_frame, text="Combine")

        # Log
        self.log = ScrolledText(self, height=10, state="disabled")
        self.log.pack(fill="both", expand=False, padx=10, pady=(0, 8))

        # Progress bar and Convert button
        self.cv_progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self.cv_progress.pack(fill="x", padx=10, pady=(0, 8))

        bottom_bar = ttk.Frame(self)
        bottom_bar.pack(fill="x", padx=10, pady=(0, 10))
        self.convert_btn = ttk.Button(bottom_bar, text="Convert")  # command is bound by ConvertTab
        self.convert_btn.pack(side="right")

        # Mount tabs
        self.convert_tab = ConvertTab(
            convert_frame,
            log_q=self.log_q,
            progress=self.cv_progress,
            convert_btn=self.convert_btn,
            ffmpeg_cmd=FFMPEG,
        )
        self.convert_tab.pack(fill="both", expand=True)

        self.combine_tab = CombineTab(
            combine_frame,
            log_q=self.log_q,
            ffmpeg_cmd=FFMPEG,
        )
        self.combine_tab.pack(fill="both", expand=True)

        # Reset progress bar after completion on any interaction
        self.bind_all("<Button>", self.convert_tab.on_interaction, add="+")
        self.bind_all("<Key>", self.convert_tab.on_interaction, add="+")
        self.nb.bind("<<NotebookTabChanged>>", self.convert_tab.on_interaction, add="+")

        # Drain log every oncce in a while
        self.after(100, self.drain_log)
    
    def write_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert(tk.END, text.rstrip() + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def drain_log(self):
        while True:
            try:
                line = self.log_q.get_nowait()
            except queue.Empty:
                break
            self.write_log(line)
        self.after(100, self.drain_log)


if __name__ == "__main__":
    app = TinyTVApp()
    app.mainloop()
