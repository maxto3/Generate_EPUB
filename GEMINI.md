# Generate EPUB Project

## Project Overview

**Generate EPUB** is a Python-based utility designed to streamline the conversion of Markdown-formatted text (`.txt` files) into professional EPUB ebooks. It features a modern GUI, automatic text preprocessing, and metadata management, leveraging **Pandoc** for the core conversion and **Nuitka** for creating standalone executables.

### Key Technologies
- **Python 3.12+**: Main logic and GUI.
- **ttkbootstrap**: Modernized Tkinter-based user interface.
- **Pandoc**: Backend engine for Markdown to EPUB conversion.
- **Nuitka**: Compilation tool to bundle the Python script into a single `.exe` (for Windows).
- **PyYAML**: For managing metadata (`meta.yaml`) and Pandoc configurations (`pandocconfig.yaml`).
- **chardet**: Robust encoding detection for input text files.

---

## Building and Running

### Prerequisites
1. **Python 3.x** (Tested on 3.12.9)
2. **Pandoc**: Must be installed and accessible in the system PATH.
   - Install via winget: `winget install JohnMacFarlane.Pandoc`
3. **Visual Studio 2022**: Required for the MSVC compiler (Nuitka dependency).
4. **Python Dependencies**:
   ```bash
   pip install ttkbootstrap pyyaml chardet nuitka
   ```

### Key Commands

#### 1. Running from Source
To launch the GUI directly:
```bash
python generate_epub.py
```

#### 2. Compiling to Executable
The project provides several scripts for compilation using Nuitka:
- **Windows (CMD):** Run `compile.bat`
- **Windows (PowerShell):** Run `compile.ps1`
- **Linux/Unix:** Run `compile.sh`

The compilation command used is:
```bash
python -m nuitka --standalone --onefile --windows-console-mode=disable --windows-icon-from-ico=icon.ico --enable-plugin=tk-inter --output-dir=build --msvc=latest generate_epub.py
```
Output executable will be located in the `build/` directory.

---

## Project Structure & Key Files

- **`generate_epub.py`**: The core application. Handles the GUI, calls the preprocessing module, and invokes Pandoc via `pandocconfig.yaml`.
- **`epub_preprocess.py`**: Standalone (stdlib-only) preprocessing module: encoding detection, ad-line cleanup, paragraph normalization, and volume/chapter heading detection. Also usable from the CLI (`python epub_preprocess.py <txt> --dry-run --list-headings`).
- **`tests/test_preprocess.py`**: stdlib `unittest` suite covering the heading rules, ad filtering, encoding fallback, and a regression run against the real sample novel (skipped when the sample is missing).
- **`meta.yaml`**: Stores persistent metadata for the book (title, author, description).
- **`pandocconfig.yaml`**: Configures Pandoc parameters (CSS, cover image, output format).
- **`style.css`**: Default styling applied to the generated EPUB.
- **`compile.*`**: Scripts to automate the Nuitka build process.
- **`icon.ico`**: Application icon for the compiled executable.

---

## Development Conventions

### Input Format Requirements
Input `.txt` files are preprocessed automatically by `epub_preprocess.py`:
1. **Encoding**: Auto-detected (chardet when available, then gb18030/gbk/big5/utf-16 fallback); no manual conversion needed.
2. **Headings**: Detected structurally — volumes `第X卷` / `卷X`, chapters `第X章` / `第X回` / `第X节` (an explicit numeric index is required), plus whole-line intro markers (`内容简介`, `引子`, `序章`, `楔子`, `后记`, …). Guards: volume titles ≤ 40 chars, chapter titles ≤ 60 chars, plus a sentence-period policy.
3. **Spacing**: Blank lines around headings and between paragraphs are generated automatically.
4. **Indentation**: Leading/trailing whitespace (including U+3000) is stripped; visual indent comes from `style.css` (2em).
5. **Escape hatch**: Lines that already start with `#` / `##` are passed through untouched.

> Regression rule of thumb: never widen heading detection to "starts with 卷/第". Always require an explicit numeric index plus a boundary, otherwise prose such as `卷牍室比杨狱想象的要大，也更热闹。` gets promoted to a heading again.

### Code Style
- **GUI**: Follows `ttkbootstrap` patterns for theming.
- **Error Handling**: Uses `messagebox` and a status bar for user feedback.
- **Logging**: Supports optional logging to `epub_generator.log` for debugging conversion issues.
- **Surgical Preprocessing**: The preprocessing module cleans common "web novel" artifacts (ad banners, URLs, HTML-entity watermarks, excessive dividers) and normalizes headings using regex, then hands the markdown to Pandoc.

---

## TODO / Future Enhancements
- [ ] Add support for multiple CSS templates.
- [ ] Implement batch conversion for multiple TXT files.
- [ ] Add a progress bar for long-running Pandoc tasks.
