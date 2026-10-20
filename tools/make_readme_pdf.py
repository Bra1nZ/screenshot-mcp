#!/usr/bin/env python3
"""Собирает PDF из README через headless Chrome.

    python3 tools/make_readme_pdf.py [README.md]

Требуется `markdown` (в requirements-dev.txt) и Chrome/Chromium в системе.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, 'Noto Sans', sans-serif;
       font-size: 11pt; line-height: 1.55; color: #1f2328; max-width: 900px;
       margin: 36px auto; padding: 0 28px; }
h1, h2, h3 { border-bottom: 1px solid #d1d9e0; padding-bottom: 6px; }
h1 { font-size: 22pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
code { background: #f0f2f5; padding: 2px 5px; border-radius: 5px;
       font-family: 'DejaVu Sans Mono', monospace; font-size: 9.5pt; }
pre { background: #f6f8fa; padding: 14px; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 10pt; }
th, td { border: 1px solid #d1d9e0; padding: 7px 10px; text-align: left;
         vertical-align: top; }
th { background: #f6f8fa; }
blockquote { border-left: 4px solid #d1d9e0; margin: 12px 0; padding: 2px 14px;
             color: #59636e; }
a { color: #0969da; text-decoration: none; }
"""


def find_browser() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "README.md"
    if not os.path.exists(source):
        print(f"файл не найден: {source}", file=sys.stderr)
        return 1
    browser = find_browser()
    if not browser:
        print("не найден Chrome/Chromium", file=sys.stderr)
        return 1

    try:
        import markdown
    except ImportError:
        print("не установлен пакет markdown: pip install markdown", file=sys.stderr)
        return 1

    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"

    target = os.path.splitext(source)[0] + ".pdf"
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as fh:
        fh.write(html)
        html_path = fh.name
    try:
        subprocess.run(
            [browser, "--headless", "--disable-gpu", "--no-sandbox",
             "--no-pdf-header-footer", f"--print-to-pdf={target}", html_path],
            check=True, capture_output=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.decode("utf-8", "replace")[:400], file=sys.stderr)
        return 1
    finally:
        os.unlink(html_path)
    print(f"готово: {target} ({os.path.getsize(target)} байт)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
