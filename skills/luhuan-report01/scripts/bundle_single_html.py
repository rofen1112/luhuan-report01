#!/usr/bin/env python3
"""Bundle a report folder into one Feishu-friendly HTML file.

Usage:
  python bundle_single_html.py path/to/index.html path/to/report-feishu.html
  python bundle_single_html.py path/to/index.html path/to/report-feishu.html --embed-linked-files
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit


REMOTE_PREFIXES = ("http://", "https://", "//", "data:", "blob:", "mailto:", "tel:", "#")


def is_local_reference(value: str) -> bool:
    lowered = value.strip().lower()
    return bool(lowered) and not lowered.startswith(REMOTE_PREFIXES)


def resolve_local(base_dir: Path, reference: str, report_root: Path) -> Path:
    path_part = unquote(urlsplit(unescape(reference).strip()).path)
    candidate = (base_dir / path_part).resolve()
    if not candidate.is_relative_to(report_root):
        raise ValueError(f"Refusing to inline a file outside the report folder: {reference}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Missing local asset: {reference}")
    return candidate


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def inline_css_urls(css: str, css_dir: Path, report_root: Path, counters: dict[str, int]) -> str:
    pattern = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", re.IGNORECASE)

    def replace(match: re.Match[str]) -> str:
        reference = match.group(2).strip()
        if not is_local_reference(reference):
            return match.group(0)
        asset = resolve_local(css_dir, reference, report_root)
        counters["css_assets"] += 1
        return f'url("{data_uri(asset)}")'

    return pattern.sub(replace, css)


def bundle(input_html: Path, output_html: Path, *, embed_linked_files: bool = False) -> dict[str, object]:
    input_html = input_html.resolve()
    output_html = output_html.resolve()
    report_root = input_html.parent
    html = input_html.read_text(encoding="utf-8")
    counters = {"stylesheets": 0, "scripts": 0, "images": 0, "css_assets": 0, "linked_files": 0}

    stylesheet_pattern = re.compile(
        r'<link\b(?=[^>]*\brel\s*=\s*["\']stylesheet["\'])(?=[^>]*\bhref\s*=\s*["\']([^"\']+)["\'])[^>]*>',
        re.IGNORECASE,
    )

    def replace_stylesheet(match: re.Match[str]) -> str:
        reference = match.group(1)
        if not is_local_reference(reference):
            return match.group(0)
        css_path = resolve_local(report_root, reference, report_root)
        css = css_path.read_text(encoding="utf-8")
        css = inline_css_urls(css, css_path.parent, report_root, counters)
        counters["stylesheets"] += 1
        return f"<style>\n/* Inlined from {reference} */\n{css}\n</style>"

    html = stylesheet_pattern.sub(replace_stylesheet, html)

    script_pattern = re.compile(
        r'<script\b([^>]*?)\bsrc\s*=\s*["\']([^"\']+)["\']([^>]*)>\s*</script\s*>',
        re.IGNORECASE,
    )

    def replace_script(match: re.Match[str]) -> str:
        reference = match.group(2)
        if not is_local_reference(reference):
            return match.group(0)
        script_path = resolve_local(report_root, reference, report_root)
        script = script_path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
        counters["scripts"] += 1
        return f"<script>\n/* Inlined from {reference} */\n{script}\n</script>"

    html = script_pattern.sub(replace_script, html)

    media_pattern = re.compile(
        r'(?P<prefix>\b(?:src|poster)\s*=\s*["\'])(?P<reference>[^"\']+)(?P<suffix>["\'])',
        re.IGNORECASE,
    )

    def replace_media(match: re.Match[str]) -> str:
        reference = match.group("reference")
        if not is_local_reference(reference):
            return match.group(0)
        asset = resolve_local(report_root, reference, report_root)
        counters["images"] += 1
        return f'{match.group("prefix")}{data_uri(asset)}{match.group("suffix")}'

    html = media_pattern.sub(replace_media, html)
    if embed_linked_files:
        anchor_pattern = re.compile(
            r'(?P<prefix><a\b[^>]*?\bhref\s*=\s*["\'])(?P<reference>[^"\']+)(?P<suffix>["\'][^>]*>)',
            re.IGNORECASE,
        )

        def replace_anchor(match: re.Match[str]) -> str:
            reference = unescape(match.group("reference"))
            if not is_local_reference(reference):
                return match.group(0)
            asset = resolve_local(report_root, reference, report_root)
            counters["linked_files"] += 1
            return f'{match.group("prefix")}{data_uri(asset)}{match.group("suffix")}'

        html = anchor_pattern.sub(replace_anchor, html)
    html = html.replace("<head>", "<head>\n  <!-- Bundled single-file edition for external preview. -->", 1)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8", newline="\n")

    unresolved = re.findall(
        r'\b(?:src|poster|href)\s*=\s*["\'](?!https?://|//|data:|blob:|mailto:|tel:|#)([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    result: dict[str, object] = {
        "input": str(input_html),
        "output": str(output_html),
        "bytes": output_html.stat().st_size,
        "inlined": counters,
        "unresolved_local_references": unresolved,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_html", type=Path)
    parser.add_argument("output_html", type=Path)
    parser.add_argument(
        "--embed-linked-files", action="store_true",
        help="Also embed local anchor targets (for example evidence downloads). Review their distribution scope first.",
    )
    args = parser.parse_args()
    result = bundle(args.input_html, args.output_html, embed_linked_files=args.embed_linked_files)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["unresolved_local_references"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
