#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

EXECUTABLE_SCRIPT_TYPES = {
    "",
    "module",
    "text/javascript",
    "application/javascript",
    "application/ecmascript",
    "text/ecmascript",
    "importmap",
    "speculationrules",
}
URL_ATTRS = {"href", "src", "action", "formaction", "xlink:href"}
DANGEROUS_JS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("eval()", re.compile(r"\beval\s*\(")),
    ("new Function()", re.compile(r"\bnew\s+Function\s*\(")),
    ("setTimeout(string)", re.compile(r"\bsetTimeout\s*\(\s*['\"]")),
    ("setInterval(string)", re.compile(r"\bsetInterval\s*\(\s*['\"]")),
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    column: int
    code: str
    message: str

    def render(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"{rel}:{self.line}:{self.column}: {self.code}: {self.message}"


class CspHtmlParser(HTMLParser):
    def __init__(self, path: Path, *, check_inline_style: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.check_inline_style = check_inline_style
        self.findings: list[Finding] = []
        self._script_stack: list[tuple[int, int, str | None, str]] = []
        self._style_stack: list[tuple[int, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_tag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "script" and self._script_stack:
            self._script_stack.pop()
        if normalized == "style" and self._style_stack:
            self._style_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._script_stack and data.strip():
            line, column, script_type, nonce = self._script_stack[-1]
            detail = "inline executable <script> block"
            if script_type:
                detail += f" with type={script_type!r}"
            if nonce:
                detail += "; nonce is present but this app CSP does not currently emit nonces"
            self.findings.append(Finding(self.path, line, column, "CSP001", detail))
        if self.check_inline_style and self._style_stack and data.strip():
            line, column = self._style_stack[-1]
            self.findings.append(Finding(self.path, line, column, "CSP004", "inline <style> block violates style-src 'self' without a nonce/hash"))

    def _handle_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attr_map = {name.lower(): (value or "") for name, value in attrs}
        line, column = self.getpos()

        for name, value in attr_map.items():
            if name.startswith("on"):
                self.findings.append(Finding(self.path, line, column, "CSP002", f"inline event handler attribute {name!r}"))
            if name in URL_ATTRS and value.strip().lower().startswith("javascript:"):
                self.findings.append(Finding(self.path, line, column, "CSP003", f"javascript: URL in {name!r}"))
            if name == "srcdoc":
                self.findings.append(Finding(self.path, line, column, "CSP005", "iframe srcdoc embeds inline HTML and can bypass the external-asset-only contract"))
            if self.check_inline_style and name == "style":
                self.findings.append(Finding(self.path, line, column, "CSP006", "inline style attribute violates style-src 'self' without a nonce/hash"))

        if normalized_tag == "script":
            script_type = attr_map.get("type", "").strip().lower()
            has_src = bool(attr_map.get("src", "").strip())
            nonce = attr_map.get("nonce", "").strip()
            if not has_src and _is_executable_script_type(script_type):
                self._script_stack.append((line, column, script_type or None, nonce))
        elif normalized_tag == "style" and self.check_inline_style:
            self._style_stack.append((line, column))


def _is_executable_script_type(script_type: str) -> bool:
    if script_type in EXECUTABLE_SCRIPT_TYPES:
        return True
    # MIME parameters such as "text/javascript; charset=utf-8" still execute.
    return script_type.split(";", 1)[0].strip() in EXECUTABLE_SCRIPT_TYPES


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def html_findings(paths: Iterable[Path], *, check_inline_style: bool) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        parser = CspHtmlParser(path, check_inline_style=check_inline_style)
        parser.feed(_read_text(path))
        parser.close()
        findings.extend(parser.findings)
    return findings


def asset_findings(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        text = _read_text(path)
        for label, pattern in DANGEROUS_JS_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                last_newline = text.rfind("\n", 0, match.start())
                column = match.start() + 1 if last_newline == -1 else match.start() - last_newline
                findings.append(Finding(path, line, column, "CSP007", f"dynamic code execution pattern {label}"))
    return findings


def discover_html_files(root: Path, include_legacy: bool) -> list[Path]:
    candidates = [root / "frontend" / "index.html", root / "public" / "index.html"]
    if include_legacy:
        candidates.extend([root / "frontend" / "legacy.html", root / "public" / "legacy.html"])
    return [path for path in candidates if path.exists()]


def discover_js_assets(root: Path) -> list[Path]:
    assets_dir = root / "public" / "assets"
    if not assets_dir.exists():
        return []
    return sorted(path for path in assets_dir.glob("*.js") if not path.name.endswith(".map"))


def validate_build_contract(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    index_path = root / "public" / "index.html"
    if not index_path.exists():
        return [Finding(index_path, 1, 1, "CSP100", "public/index.html does not exist; run npm run build before CSP validation")]

    html = _read_text(index_path)
    if "/src/" in html:
        line = html[: html.index("/src/")].count("\n") + 1
        findings.append(Finding(index_path, line, 1, "CSP101", "built public/index.html still references frontend source paths"))

    external_scripts = re.findall(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    outlier_scripts = [src for src in external_scripts if "/assets/outlier-" in src and src.endswith(".js")]
    if not outlier_scripts:
        findings.append(Finding(index_path, 1, 1, "CSP102", "built public/index.html does not reference a fingerprinted /assets/outlier-*.js bundle"))

    for src in external_scripts:
        parsed = urlparse(src)
        if parsed.scheme and parsed.scheme not in {"", "http", "https"}:
            findings.append(Finding(index_path, 1, 1, "CSP103", f"unexpected script URL scheme in {src!r}"))
        if src.startswith("http://") or src.startswith("https://") or src.startswith("//"):
            findings.append(Finding(index_path, 1, 1, "CSP104", f"external script {src!r} violates script-src 'self'"))

    return findings


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that the Vite-built frontend can run under the production CSP without unsafe-inline.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root. Defaults to the current working directory.")
    parser.add_argument("--include-legacy", action="store_true", help="Also scan legacy.html templates and built output.")
    parser.add_argument("--check-inline-style", action="store_true", help="Also fail on inline <style> blocks and style attributes.")
    parser.add_argument("--skip-js-dynamic-code-scan", action="store_true", help="Skip checks for eval/new Function/string timers in built JS assets.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()

    findings: list[Finding] = []
    findings.extend(validate_build_contract(root))
    findings.extend(html_findings(discover_html_files(root, args.include_legacy), check_inline_style=args.check_inline_style))
    if not args.skip_js_dynamic_code_scan:
        findings.extend(asset_findings(discover_js_assets(root)))

    if findings:
        print("CSP validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding.render(root)}", file=sys.stderr)
        return 2

    print("CSP validation passed: Vite HTML uses external scripts and built assets avoid dynamic code execution hazards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
