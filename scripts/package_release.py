#!/usr/bin/env python3
"""Build deterministic ZIP and .skill payloads using only the standard library."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_installer():
    spec = importlib.util.spec_from_file_location("luhuan_report_install", ROOT / "install.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build(output: Path | None = None) -> dict[str, object]:
    installer = load_installer()
    version_file = ROOT / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "1.0.0"
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", version):
        raise ValueError("VERSION must contain one semantic version without path components")
    files = installer.collect_skill_files()
    scaffold = re.compile(r"\b(?:TODO|TBD|FIXME|INSERT[_ -]HERE)\b|\[describe[^\]]*\]", re.IGNORECASE)
    for file, relative in files:
        # Report templates deliberately contain {{...}} tokens. Only authoring
        # scaffold in instructions/metadata should block a release.
        if str(relative) == "SKILL.md" or relative.parts[0] == "agents":
            if scaffold.search(file.read_text(encoding="utf-8")):
                raise ValueError(f"Unfinished skill scaffold: {relative}")
    output = output if output is not None else ROOT / "dist"
    output.mkdir(parents=True, exist_ok=True)
    basename = f"{installer.SKILL_NAME}-v{version}"
    archive = output / f"{basename}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for file, relative in files:
            archive_name = installer.SKILL_NAME + "/" + str(relative)
            info = zipfile.ZipInfo(archive_name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(info, file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    skill_archive = output / f"{basename}.skill"
    skill_archive.write_bytes(archive.read_bytes())
    checksums = []
    for file in (archive, skill_archive):
        checksums.append(f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}")
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return {"version": version, "files": len(files), "zip": archive.name, "skill": skill_archive.name, "sha256": checksums[0].split()[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Output folder; defaults to repository dist/")
    args = parser.parse_args()
    try:
        result = build(args.output)
    except (OSError, ValueError) as error:
        print(f"Package failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
