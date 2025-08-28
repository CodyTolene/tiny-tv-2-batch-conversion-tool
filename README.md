<div align="center">
  <img align="center" src=".github/images/tv.png" />
  <h1 align="center">Batch Conversion Tool for TinyTV® 2</h1>
  <p align="center">
    A tool for mass converting video files for the highly recommended
    <a href="https://tinycircuits.com/products/tinytv-2">TinyTV® 2</a> device
    by <a href="https://tinycircuits.com">Tiny Circuits</a>!
  </p>
</div>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

## Index <a name="index"></a>

- [Intro](#intro)
  - [Official Tool](#official-tool)
  - [Batch Conversion Tool](#batch-tool)
  - [Preview](#preview)
- [User Guide](#user-guide)
  - [Running (Windows)](#running-windows)
- [Development / Code Contribution](#local-development)
  - [Prerequisites](#prerequisites)
  - [Workspace Setup](#workspace-setup)
  - [Build / Run](#build-run)
- [License(s)](#licenses)
- [Wrapping Up](#wrapping-up)

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

## Intro

The **Batch Conversion Tool** is designed to simplify the process of preparing
video files for the TinyTV® 2 device. It offers a user-friendly interface and
powerful features to help you convert and manage your video files with ease.

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

### **Official Tool** <a name="official-tool"></a>

Before we begin, you should know there's an official
[TinyTV® 2 Converter][url-tinytv-2-converter-app] app available for use if you
wish to use that one instead.

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

### **Batch Conversion Tool** <a name="batch-tool"></a>

**Batch Conversion Tool** is an open-source application built with the same
purpose as the [TinyTV® 2 Converter][url-tinytv-2-converter-app] app but
allows you to **batch** convert many video files at once. It also includes
extra features to make preparing your videos easier, such as:

- Converting an entire list of files in sequence.
- Drastically reduce the file size, and display limits for the FAT32 file system.
- Choose from different video quality output settings.
- Automatically prepend filenames with channel numbers for easy sorting.
- Merge multiple videos into a single output file.

#### Preview <a name="preview"></a>

<details>
<summary>Convert Window Preview</summary>

![Convert Tab Screenshot][img-screenshot-01]
</details>

<details>
<summary>Combine Window Preview</summary>

![Combine Tab Screenshot][img-screenshot-02]
</details>

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

## User Guide <a name="user-guide"></a>

### Running (Windows) <a name="running-windows"></a>

Go to the [releases page][url-releases] and download the latest
`TinyTV2.Batch.Conversion.Tool.exe` file. Once downloaded, run the executable
to start the application.

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

## Development / Code Contribution <a name="local-development"></a>

You can contribute to the development of **TinyTV® 2 Batch Conversion Tool** by 
following these steps:

### Prerequisites <a name="prerequisites"></a>

1. Make sure you have `Python` installed and accessible in your `PATH`:

   [python.org/downloads](https://www.python.org/downloads/)

   Test with:

   ```bash
   python --version
   # or
   py --version
   ```

2. Make sure you have `ffmpeg` installed one of two ways:

   - Install locally and accessible in your `PATH`: [ffmpeg.org/download](https://www.ffmpeg.org/download.html) and/or

   - Binaries (optional): [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (placed in `bin/`)

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

### Workspace Setup <a name="workspace-setup"></a>

1. Bootstrap `pip`:

   ```bash
   py -m ensurepip --upgrade
   py -m pip install --upgrade pip setuptools wheel
   ```

2. Install third party dependencies:

   ```base
   py -m pip install -r requirements.txt
   ```

3. If you don't want to install `ffmpeg` locally, place the `ffmpeg.exe` binary in the `bin/` folder. Test:

   ```bash
   cd bin
   ffmpeg -version
   ```

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

### Build / Run <a name="build-run"></a>

To run the application directly from root for development (requires local ffmpeg or from bin):

   ```bash
   py main.py
   ```

To build `dist/main.exe` for production (requires ffmpeg in bin):

   ```bash
   py -m PyInstaller --onefile ^
      --windowed ^
      --noconfirm ^
      --name TinyTV2BatchConversionTool ^
      --icon=icon.ico ^
      --add-data "bin;bin" ^
      main.py
   ```

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

### Linting and Formatting

To ensure code quality and consistency, this project uses the following tools:

- **[Black](https://black.readthedocs.io/en/stable/)**: An opinionated code formatter for Python.
- **[Flake8](https://flake8.pycqa.org/en/latest/)**: A linting tool for Python that checks for style guide enforcement.

Run the following command to format your code with Black:

```bash
py -m black .
```

Run the following command to check your code with Flake8:

```bash
py -m flake8
```

## License(s) <a name="licenses"></a>

This project is licensed under the Creative Commons Attribution-NonCommercial
4.0 International License. See the [license][url-license] file for more
information.

This software uses FFmpeg licensed under the [LGPLv2.1][url-license-lgpl] license. Source code for FFmpeg is available at [https://ffmpeg.org](https://ffmpeg.org).

`SPDX-License-Identifiers: CC-BY-NC-4.0, LGPLv2.1`

> ![Info][img-info] The application code is licensed under `CC-BY-NC-4.0`. FFmpeg is licensed separately under `LGPLv2.1`. These licenses apply independently.

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

## Wrapping Up <a name="wrapping-up"></a>

Thank you to Tiny Circuits for the [TinyTV® 2](https://tinycircuits.com/products/tinytv-2), it's a fun device! If you have any
questions, please let me know by [opening an issue here][url-new-issue].

| Type                                                                      | Info                                                           |
| :------------------------------------------------------------------------ | :------------------------------------------------------------- |
| <img width="48" src=".github/images/ng-icons/email.svg" />                | webmaster@codytolene.com                                       |
| <img width="48" src=".github/images/simple-icons/github.svg" />           | https://github.com/sponsors/CodyTolene                         |
| <img width="48" src=".github/images/simple-icons/buymeacoffee.svg" />     | https://www.buymeacoffee.com/codytolene                        |
| <img width="48" src=".github/images/simple-icons/bitcoin-btc-logo.svg" /> | bc1qfx3lvspkj0q077u3gnrnxqkqwyvcku2nml86wmudy7yf2u8edmqq0a5vnt |

Fin. Happy programming friend!

Cody Tolene

<p align="right">[ <a href="#index">Index</a> ]</p>

<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->
<!---------------------------------------------------------------------------->

<!-- IMAGE REFERENCES -->

[img-info]: .github/images/ng-icons/info.svg
[img-screenshot-01]: .github/images/screenshots/screen_01.png
[img-screenshot-02]: .github/images/screenshots/screen_02.png
[img-warn]: .github/images/ng-icons/warn.svg

<!-- LINK REFERENCES -->

[url-license-lgpl]: /LICENSE-LGPL.md
[url-license]: /LICENSE.md
[url-new-issue]: https://github.com/CodyTolene/tiny-tv-2-batch-conversion-tool/issues
[url-releases]: https://github.com/CodyTolene/tiny-tv-2-batch-conversion-tool/releases
[url-tinytv-2-converter-app]: https://tinytv.us/TinyTV-Converter-App/
[url-tinytv-2]: https://tinycircuits.com/products/tinytv-2
