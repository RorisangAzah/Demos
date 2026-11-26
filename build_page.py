#!/usr/bin/env python3
"""Build the shareable page from output/brief.json.

Usage:
    python3 build_page.py                    # writes docs/index.html (works on GitHub Pages)
    python3 build_page.py --fragment FILE    # also writes the page without the <html> wrapper
"""
from __future__ import annotations

import argparse
import json

from brief.common import ROOT

HEAD_OPEN = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
             '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')


def build(brief_path=ROOT / "output" / "brief.json", template_path=ROOT / "page" / "template.html"):
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    template = template_path.read_text(encoding="utf-8")
    # "</" inside a script block would end it early, so escape it.
    data = json.dumps(brief, ensure_ascii=False).replace("</", "<\\/")
    fragment = template.replace("<!--BRIEF_JSON-->", data)
    head, body = fragment.split("<!--BODY-->", 1)
    full = HEAD_OPEN + head + "</head>\n<body>" + body + "</body>\n</html>\n"
    return fragment, full


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fragment", help="also write the page without the html/head/body wrapper to this path")
    args = parser.parse_args()
    fragment, full = build()
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(full, encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(full) // 1024} KB)")
    if args.fragment:
        from pathlib import Path
        Path(args.fragment).write_text(fragment.replace("<!--BODY-->", ""), encoding="utf-8")
        print(f"Wrote {args.fragment}")


if __name__ == "__main__":
    main()
