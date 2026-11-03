#!/usr/bin/env python3
"""Install this repository's skill locally, without overwriting another skill."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import uuid

SKILL_NAME = "luhuan-report01"
REPO_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = REPO_ROOT / "skills" / SKILL_NAME
ALLOWED_SUFFIXES = {
    "references": {".md", ".json"},
    "scripts": {".py"},
    "assets": {".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp"},
}
IGNORED_PARTS = {"__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini"}
SECRET_PATTERNS = (
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class PackageError(ValueError):
    """An installation source or destination violates this package's contract."""


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    # lstat exposes Windows reparse attributes before Path.is_junction (3.12).
    # Reject junctions and other reparse points on every supported Python version.
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _allowed(relative: PurePosixPath) -> bool:
    parts = relative.parts
    if relative.is_absolute() or not parts or any(p in {"", ".", ".."} for p in parts):
        return False
    if len(parts) == 1:
        return parts[0] in {"SKILL.md", "LICENSE"}
    if parts[0] == "agents":
        return parts == ("agents", "openai.yaml")
    return parts[0] in ALLOWED_SUFFIXES and relative.suffix.lower() in ALLOWED_SUFFIXES[parts[0]]


def collect_skill_files(source: Path = SKILL_ROOT) -> list[tuple[Path, PurePosixPath]]:
    """Return only approved portable payload files; never follow links."""
    if _is_link(source) or not source.is_dir():
        raise PackageError(f"Skill source must be a real directory: {source}")
    result: list[tuple[Path, PurePosixPath]] = []
    for directory, dirs, files in os.walk(source, followlinks=False):
        current = Path(directory)
        for name in list(dirs):
            child = current / name
            if _is_link(child):
                raise PackageError(f"Symbolic links and junctions are not allowed: {child}")
            if name in IGNORED_PARTS:
                dirs.remove(name)
        for name in files:
            file = current / name
            if _is_link(file):
                raise PackageError(f"Symbolic links are not allowed: {file}")
            relative = PurePosixPath(file.relative_to(source).as_posix())
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if not _allowed(relative):
                raise PackageError(f"Unexpected file in skill payload: {relative}")
            content = file.read_bytes()
            if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                raise PackageError(f"Possible credential in skill payload: {relative}")
            result.append((file, relative))
    if not any(str(relative) == "SKILL.md" for _, relative in result):
        raise PackageError("Skill payload has no SKILL.md")
    return sorted(result, key=lambda item: str(item[1]))


def default_destination() -> Path:
    codex_root = os.environ.get("CODEX_HOME")
    return Path(codex_root).expanduser() / "skills" if codex_root else Path.home() / ".codex" / "skills"


def _remove_owned_temporary(path: Path, parent: Path, marker_name: str, marker_value: str) -> None:
    """Remove only a directory created by this invocation, checked by path and marker."""
    if not path.exists() or _is_link(path):
        return
    if path.resolve().parent != parent.resolve():
        raise PackageError("Refusing cleanup outside the selected skill destination")
    marker = path / marker_name
    if not marker.is_file() or marker.read_text(encoding="utf-8") != marker_value:
        raise PackageError("Refusing cleanup of a directory not owned by this installation")
    shutil.rmtree(path)


def install(destination: Path, *, dry_run: bool = False, source: Path = SKILL_ROOT) -> dict[str, object]:
    files = collect_skill_files(source)
    parent = destination.expanduser().absolute()
    target = parent / SKILL_NAME
    if target.exists() or _is_link(target):
        raise FileExistsError(f"Already exists; no files were overwritten: {target}")
    summary: dict[str, object] = {
        "skill": SKILL_NAME,
        "destination": str(target),
        "files": len(files),
        "dry_run": dry_run,
    }
    if dry_run:
        return summary
    parent.mkdir(parents=True, exist_ok=True)
    # Complete the payload in a hidden directory before reserving the final name.
    stage = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}-install-", dir=parent))
    marker_name = ".installation-owner"
    marker_value = str(uuid.uuid4())
    (stage / marker_name).write_text(marker_value, encoding="utf-8")
    owned_target = False
    try:
        for file, relative in files:
            copy = stage.joinpath(*relative.parts)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, copy)
        # mkdir is an exclusive claim, including on POSIX where rename can
        # otherwise replace an empty directory created by another process.
        target.mkdir(exist_ok=False)
        owned_target = True
        (target / marker_name).write_text(marker_value, encoding="utf-8")
        for child in list(stage.iterdir()):
            if child.name != marker_name:
                child.rename(target / child.name)
        (target / marker_name).unlink()
        owned_target = False
    except Exception:
        if owned_target:
            _remove_owned_temporary(target, parent, marker_name, marker_value)
        raise
    finally:
        _remove_owned_temporary(stage, parent, marker_name, marker_value)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=None, help="Parent skills directory; the skill name is appended")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show the install plan without writing files")
    args = parser.parse_args()
    try:
        result = install(args.dest if args.dest is not None else default_destination(), dry_run=args.dry_run)
    except (OSError, PackageError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.dry_run:
        print("Installed. The skill is available on your next Codex turn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
