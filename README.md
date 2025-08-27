### Run

1. Make sure you have ffmpeg installed and accessible in your PATH.

2. Run the application:

   ```bash
   py main.py
   ```

### Project Init

1. Install Python (check “Add Python to PATH” if offered).

2. Bootstrap pip:

   ```bash
   py -m ensurepip --upgrade
   py -m pip install --upgrade pip setuptools wheel
   ```

3. Install PyInstaller:

   ```bash
   py -m pip install pyinstaller
   ```

4. Put ffmpeg.exe next to TinyTVTool.py (or make sure ffmpeg is in PATH). Test:

   ```bash
   ffmpeg -version
   ```

5. Run the app:

   ```bash
   py TinyTVTool.py
   ```

6. Build a single exe (optional):

   ```bash
   py -m PyInstaller --onefile --windowed TinyTVTool.py
   # -> dist\TinyTVTool.exe
   ```
