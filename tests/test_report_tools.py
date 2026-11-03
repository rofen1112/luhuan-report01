"""Portable report fixtures; no browser, network, credentials, or client data."""

from __future__ import annotations

import base64
import importlib.util
import re
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "skills" / "luhuan-report01"


def load_tool(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_tool("report_validator_test", "validate_report.py")
BUNDLER = load_tool("report_bundler_test", "bundle_single_html.py")


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


class ReportToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luhuan-report-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report = self.root / "report"
        shutil.copytree(SKILL / "assets" / "html-report-template", self.report)
        self.input_html = self.report / "index.html"
        self.html = re.sub(
            r"\{\{[^{}]+\}\}", "Synthetic fixture; not a project claim",
            self.input_html.read_text(encoding="utf-8"),
        ).replace("</article>", '<a href="evidence.txt">Fixture evidence</a></article>')
        self.input_html.write_text(self.html, encoding="utf-8")
        self.evidence = b"Synthetic fixture only.\nNot a client record.\n"
        (self.report / "evidence.txt").write_bytes(self.evidence)

    def test_complete_template_and_structure(self):
        result = VALIDATOR.validate(self.input_html)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["required_sections"], 14)
        self.assertEqual(result["warnings"], [])
        # Guard the actual HTML/CSS layout compatibility found during real use.
        css = (self.report / "assets" / "report.css").read_text(encoding="utf-8")
        self.assertIn('class="layout"', self.html)
        self.assertIn('class="rail"', self.html)
        self.assertRegex(css, r"\.layout\s*\{[^}]*display:\s*grid")

    def test_evidence_embedding_requires_opt_in(self):
        result = BUNDLER.bundle(self.input_html, self.root / "default.html")
        self.assertEqual(result["unresolved_local_references"], ["evidence.txt"])
        self.assertEqual(result["inlined"]["linked_files"], 0)
        self.assertIn('href="evidence.txt"', (self.root / "default.html").read_text(encoding="utf-8"))

    def test_opt_in_creates_standalone_report_with_exact_evidence(self):
        output = self.root / "single.html"
        result = BUNDLER.bundle(self.input_html, output, embed_linked_files=True)
        self.assertEqual(result["unresolved_local_references"], [])
        self.assertEqual(result["inlined"]["stylesheets"], 1)
        self.assertEqual(result["inlined"]["scripts"], 1)
        self.assertEqual(result["inlined"]["linked_files"], 1)
        parsed = AnchorParser()
        parsed.feed(output.read_text(encoding="utf-8"))
        embedded = [href for href in parsed.hrefs if href.startswith("data:")]
        self.assertEqual(len(embedded), 1)
        self.assertEqual(base64.b64decode(embedded[0].split(",", 1)[1]), self.evidence)
        self.assertTrue(VALIDATOR.validate(output)["valid"])

    def test_local_resources_cannot_escape_report_directory(self):
        (self.root / "outside.txt").write_text("Synthetic boundary fixture", encoding="utf-8")
        self.input_html.write_text(self.html.replace("evidence.txt", "../outside.txt"), encoding="utf-8")
        result = VALIDATOR.validate(self.input_html)
        self.assertFalse(result["valid"])
        self.assertTrue(any("outside report folder" in error for error in result["errors"]))
        with self.assertRaisesRegex(ValueError, "outside the report folder"):
            BUNDLER.bundle(self.input_html, self.root / "escape.html", embed_linked_files=True)

    def test_spaced_attributes_embed_all_resource_types_and_scan_remaining_links(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
        (self.report / "pixel.svg").write_bytes(svg)
        css_path = self.report / "assets" / "report.css"
        css_path.write_text(
            css_path.read_text(encoding="utf-8") + "\n.fixture { background: url( '../pixel.svg' ); }\n",
            encoding="utf-8",
        )
        spaced = self.html.replace('rel="stylesheet"', 'rel \t=  "stylesheet"')
        spaced = spaced.replace('href="assets/report.css"', 'href\t =\t "assets/report.css"')
        spaced = spaced.replace('src="assets/report.js"', 'src \n =\t "assets/report.js"')
        spaced = spaced.replace('href="evidence.txt"', 'href =  "evidence.txt"')
        spaced = spaced.replace(
            "</article>",
            '<img src \t= \'pixel.svg\' alt="Synthetic pixel"><video poster = "pixel.svg"></video></article>',
        )
        self.input_html.write_text(spaced, encoding="utf-8")
        self.assertTrue(VALIDATOR.validate(self.input_html)["valid"])
        # Without opt-in, the whitespace form must still be reported as unresolved.
        default = BUNDLER.bundle(self.input_html, self.root / "spaced-default.html")
        self.assertEqual(default["unresolved_local_references"], ["evidence.txt"])
        output = self.root / "spaced-single.html"
        result = BUNDLER.bundle(self.input_html, output, embed_linked_files=True)
        self.assertEqual(result["unresolved_local_references"], [])
        self.assertEqual(
            result["inlined"],
            {"stylesheets": 1, "scripts": 1, "images": 2, "css_assets": 1, "linked_files": 1},
        )
        rendered = output.read_text(encoding="utf-8")
        embedded_svg = "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
        self.assertEqual(rendered.count(embedded_svg), 3)
        parsed = AnchorParser()
        parsed.feed(rendered)
        embedded = [href for href in parsed.hrefs if href.startswith("data:")]
        self.assertEqual(base64.b64decode(embedded[0].split(",", 1)[1]), self.evidence)
        self.assertTrue(VALIDATOR.validate(output)["valid"])

    def test_external_link_is_preserved_without_local_embedding(self):
        url = "https://example.com/evidence.txt"
        self.input_html.write_text(self.html.replace("evidence.txt", url), encoding="utf-8")
        output = self.root / "external.html"
        result = BUNDLER.bundle(self.input_html, output, embed_linked_files=True)
        self.assertEqual(result["inlined"]["linked_files"], 0)
        self.assertEqual(result["unresolved_local_references"], [])
        self.assertIn(f'href="{url}"', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
