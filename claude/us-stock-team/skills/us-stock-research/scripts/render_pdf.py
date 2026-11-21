"""Print a rendered stock research HTML document to PDF with Chrome or Chromium."""

import argparse
import os
from pathlib import Path
from shutil import which
import subprocess
from tempfile import TemporaryDirectory


def browser_path(requested):
    if requested:
        return requested
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if path := which(name):
            return path
    path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if path.is_file():
        return str(path)
    raise FileNotFoundError("Chrome or Chromium is required. Set --browser or CHROME_BIN.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--browser", default=os.environ.get("CHROME_BIN"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        source = args.input.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in (".htm", ".html"):
            raise ValueError("Input must be a local HTML file.")
        output = args.output.absolute()
        if output.suffix.lower() != ".pdf":
            raise ValueError("Output path must end in .pdf.")
        if output.exists() and not args.overwrite:
            raise FileExistsError(f"Output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".report-pdf-", dir=output.parent) as directory:
            temporary = Path(directory)
            rendered = temporary / "report.pdf"
            subprocess.run(
                [browser_path(args.browser), "--headless", "--disable-gpu", "--no-first-run",
                 "--no-pdf-header-footer", f"--user-data-dir={temporary / 'profile'}",
                 f"--print-to-pdf={rendered}", source.as_uri()],
                check=True, capture_output=True, timeout=45,
            )
            with rendered.open("rb") as file:
                if file.read(5) != b"%PDF-":
                    raise ValueError("Browser did not produce a PDF.")
            if args.overwrite:
                rendered.replace(output)
            else:
                os.link(rendered, output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
