from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDGE_SERVICE = ROOT / "mlb_app" / "services" / "edge_board_service.py"

COMPAT_BLOCK = r'''

# Phase 18 v5 compatibility shim: keep game-context joins tolerant of both
# legacy helper calls (_context_team(value)) and row/key calls
# (_context_team(row, "team")). This is intentionally appended so it overrides
# any earlier malformed helper without disturbing the rest of EdgeBoardService.
def _context_team(row, key: str = "") -> str:
    if isinstance(row, dict):
        value = ""
        if key:
            value = row.get(key) or row.get(key.lower()) or row.get(key.upper()) or ""
        if not value:
            value = row.get("team") or row.get("opponent") or row.get("home_team") or row.get("away_team") or ""
    else:
        value = row

    try:
        text = _clean(value).upper()
    except NameError:
        text = str(value or "").strip().upper()

    aliases = {
        "SD": "SDP",
        "SDP": "SDP",
        "SF": "SFG",
        "SFG": "SFG",
        "CWS": "CHW",
        "CHW": "CHW",
        "WSH": "WSN",
        "WSN": "WSN",
        "TB": "TBR",
        "TBR": "TBR",
        "KC": "KCR",
        "KCR": "KCR",
        "OAK": "ATH",
        "ATH": "ATH",
    }
    return aliases.get(text, text)
'''


def main() -> None:
    if not EDGE_SERVICE.exists():
        raise SystemExit(f"missing {EDGE_SERVICE}")

    text = EDGE_SERVICE.read_text(encoding="utf-8")
    backup = EDGE_SERVICE.with_suffix(EDGE_SERVICE.suffix + ".phase18v5_backup")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    marker = "# Phase 18 v5 compatibility shim"
    if marker in text:
        changed = False
    else:
        EDGE_SERVICE.write_text(text.rstrip() + COMPAT_BLOCK + "\n", encoding="utf-8")
        changed = True

    print({
        "status": "ok",
        "changed": changed,
        "path": str(EDGE_SERVICE),
        "backup": str(backup),
    })


if __name__ == "__main__":
    main()
