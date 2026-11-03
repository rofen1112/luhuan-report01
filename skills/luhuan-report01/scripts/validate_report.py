#!/usr/bin/env python3
"""Run structural and external-sharing checks on a standard report HTML."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED_SECTION_GROUPS = [
    ("executive", {"executive"}),
    ("open-source", {"open-source"}),
    ("classification", {"classification", "model-or-engineering"}),
    ("problems", {"problems"}),
    ("local-test", {"local-test"}),
    ("industry-value", {"industry-value", "interior"}),
    ("physical-ai", {"physical-ai"}),
    ("ark", {"ark"}),
    ("data", {"data"}),
    ("collaboration", {"collaboration"}),
    ("roadmap", {"roadmap"}),
    ("risks", {"risks"}),
    ("decision", {"decision"}),
    ("sources", {"sources"}),
]

REMOTE_PREFIXES = ("http://", "https://", "//", "data:", "blob:", "mailto:", "tel:", "#", "javascript:")


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.local_refs: list[str] = []
        self.images_without_alt: list[str] = []
        self.external_blank_without_rel: list[str] = []
        self.evidence_badges = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        classes = values.get("class", "").split()
        if "evidence" in classes:
            self.evidence_badges += 1
        if tag == "img" and not values.get("alt", "").strip():
            self.images_without_alt.append(values.get("src", "<missing src>"))
        for key in ("src", "href", "poster"):
            reference = values.get(key, "").strip()
            if reference and not reference.lower().startswith(REMOTE_PREFIXES):
                self.local_refs.append(reference)
        if tag == "a" and values.get("target") == "_blank":
            reference = values.get("href", "")
            rel = set(values.get("rel", "").lower().split())
            if reference.startswith(("http://", "https://")) and not {"noreferrer", "noopener"}.intersection(rel):
                self.external_blank_without_rel.append(reference)


def validate(html_path: Path) -> dict[str, object]:
    html_path = html_path.resolve()
    root = html_path.parent
    text = html_path.read_text(encoding="utf-8")
    parser = ReportParser()
    parser.feed(text)
    errors: list[str] = []
    warnings: list[str] = []

    missing_sections = [
        label for label, accepted_ids in REQUIRED_SECTION_GROUPS
        if not parser.ids.intersection(accepted_ids)
    ]
    if missing_sections:
        errors.append("Missing required sections: " + ", ".join(missing_sections))

    placeholders = sorted(set(re.findall(r"\{\{[^{}]+\}\}", text)))
    if placeholders:
        errors.append("Unresolved template placeholders: " + ", ".join(placeholders[:20]))

    missing_assets: list[str] = []
    outside_assets: list[str] = []
    for reference in parser.local_refs:
        path_part = unquote(urlsplit(reference).path)
        target = (root / path_part).resolve()
        if not target.is_relative_to(root):
            outside_assets.append(reference)
        elif not target.is_file():
            missing_assets.append(reference)
    if outside_assets:
        errors.append("References outside report folder: " + ", ".join(sorted(set(outside_assets))))
    if missing_assets:
        errors.append("Missing local assets: " + ", ".join(sorted(set(missing_assets))))

    if parser.images_without_alt:
        errors.append(f"Images without alt text: {len(parser.images_without_alt)}")
    if parser.evidence_badges == 0:
        errors.append("No evidence badges found")
    if parser.external_blank_without_rel:
        warnings.append(f"External _blank links without noopener/noreferrer: {len(parser.external_blank_without_rel)}")

    sensitive_patterns = {
        "possible OpenAI-style secret": r"\bsk-[A-Za-z0-9_-]{16,}\b",
        "possible Hugging Face token": r"\bhf_[A-Za-z0-9]{16,}\b",
        "Windows absolute path": r"\b[A-Za-z]:\\(?:Users|ProgramData|Windows|code-program)\\",
        "password assignment": r"(?i)\b(?:password|passwd|密码)\s*[:=]\s*[^<\s]{4,}",
    }
    for label, pattern in sensitive_patterns.items():
        if re.search(pattern, text):
            warnings.append(label)

    result: dict[str, object] = {
        "html": str(html_path),
        "valid": not errors,
        "required_sections": len(REQUIRED_SECTION_GROUPS) - len(missing_sections),
        "evidence_badges": parser.evidence_badges,
        "local_references": len(parser.local_refs),
        "errors": errors,
        "warnings": warnings,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    args = parser.parse_args()
    result = validate(args.html)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
