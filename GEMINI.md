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

- **`generate_epub.py`**: The core application. Handles GUI, text cleaning (regex-based), encoding conversion, and calls Pandoc.
- **`meta.yaml`**: Stores persistent metadata for the book (title, author, description).
- **`pandocconfig.yaml`**: Configures Pandoc parameters (CSS, cover image, output format).
- **`style.css`**: Default styling applied to the generated EPUB.
- **`compile.*`**: Scripts to automate the Nuitka build process.
- **`icon.ico`**: Application icon for the compiled executable.

---

## Development Conventions

### Input Format Requirements
The tool expects input `.txt` files to follow a specific "EPUB-ready" Markdown format:
1. **Encoding**: UTF-8 (The script attempts auto-conversion, but UTF-8 is preferred).
2. **Headers**: Use `#` for volumes/chapters (e.g., `# Chapter 1`).
3. **Spacing**: Chapters and paragraphs must be separated by a single empty line.
4. **Indentation**: Paragraphs should NOT have leading whitespace (the script provides a CSS-based 2em indent).

### Code Style
- **GUI**: Follows `ttkbootstrap` patterns for theming.
- **Error Handling**: Uses `messagebox` and a status bar for user feedback.
- **Logging**: Supports optional logging to `epub_generator.log` for debugging conversion issues.
- **Surgical Preprocessing**: The script includes a `preprocessed` step that cleans common "web novel" artifacts (ad banners, URLs, excessive dividers) using regex.

---

## TODO / Future Enhancements
- [ ] Add support for multiple CSS templates.
- [ ] Implement batch conversion for multiple TXT files.
- [ ] Add a progress bar for long-running Pandoc tasks.
