"""Exercise the local install/release contracts without touching global skills."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load("tested_installer", ROOT / "install.py")
packager = load("tested_packager", ROOT / "scripts/package_release.py")


class InstallAndPackageTests(unittest.TestCase):
    def test_reparse_points_rejected_without_path_is_junction(self):
        legacy_path = SimpleNamespace(is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x400))
        regular_path = SimpleNamespace(is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x20))
        self.assertTrue(installer._is_link(legacy_path))
        self.assertFalse(installer._is_link(regular_path))

    def test_install_and_duplicate_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "skills"
            other = parent / "other-skill"
            other.mkdir(parents=True)
            (other / "keep.txt").write_bytes(b"existing user skill")
            summary = installer.install(parent)
            target = parent / installer.SKILL_NAME
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual(summary["destination"], str(target))
            expected = {str(relative): file.read_bytes() for file, relative in installer.collect_skill_files()}
            actual = {file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()}
            self.assertEqual(expected, actual)
            with self.assertRaises(FileExistsError):
                installer.install(parent)
            self.assertEqual((other / "keep.txt").read_bytes(), b"existing user skill")
            self.assertEqual(actual, {file.relative_to(target).as_posix(): file.read_bytes() for file in target.rglob("*") if file.is_file()})
            self.assertEqual(sorted(p.name for p in parent.iterdir()), [installer.SKILL_NAME, "other-skill"])

    def test_dry_run_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "not-created" / "skills"
            result = installer.install(destination, dry_run=True)
            self.assertTrue(result["dry_run"])
            self.assertFalse(destination.parent.exists())

    def test_payload_rejects_unapproved_paths_and_secrets(self):
        self.assertFalse(installer._allowed(PurePosixPath("../SKILL.md")))
        self.assertFalse(installer._allowed(PurePosixPath("/SKILL.md")))
        self.assertFalse(installer._allowed(PurePosixPath("scripts/.env")))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "SKILL.md").write_text("---\nname: luhuan-report01\ndescription: fixture\n---\n", encoding="utf-8")
            (source / ".env").write_text("fixture", encoding="utf-8")
            with self.assertRaises(installer.PackageError):
                installer.collect_skill_files(source)
            (source / ".env").unlink()
            (source / "SKILL.md").write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
            with self.assertRaises(installer.PackageError):
                installer.collect_skill_files(source)

    def test_payload_rejects_symbolic_links_when_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            source = parent / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("skill fixture", encoding="utf-8")
            outside = parent / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            try:
                (source / "LICENSE").symlink_to(outside)
            except OSError:
                self.skipTest("OS does not permit unprivileged symlink creation")
            with self.assertRaises(installer.PackageError):
                installer.collect_skill_files(source)

    def test_zip_skill_root_checksums_and_determinism(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = packager.build(output)
            zip_file = output / first["zip"]
            before = zip_file.read_bytes()
            self.assertEqual(before, (output / first["skill"]).read_bytes())
            with zipfile.ZipFile(zip_file) as zipped:
                self.assertIn("luhuan-report01/SKILL.md", zipped.namelist())
                expected = {"luhuan-report01/" + str(relative) for _, relative in installer.collect_skill_files()}
                self.assertEqual(set(zipped.namelist()), expected)
                for name in zipped.namelist():
                    parts = PurePosixPath(name).parts
                    self.assertFalse(PurePosixPath(name).is_absolute())
                    self.assertNotIn("..", parts)
                    self.assertNotIn("__pycache__", parts)
                    self.assertNotIn(".git", parts)
                    self.assertNotIn(".env", parts)
                    self.assertNotIn("auth.json", parts)
                    self.assertNotIn("node_modules", parts)
                    self.assertFalse(any(pattern.search(zipped.read(name)) for pattern in installer.SECRET_PATTERNS))
            checksum = hashlib.sha256(before).hexdigest()
            self.assertIn(checksum + "  " + zip_file.name, (output / "SHA256SUMS").read_text(encoding="utf-8"))
            packager.build(output)
            self.assertEqual(before, zip_file.read_bytes())


if __name__ == "__main__":
    unittest.main()
