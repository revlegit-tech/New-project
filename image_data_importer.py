from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

import app


TEAM_RE = r"(?:ARI|ATL|BAL|BOS|CHC|CHW|CIN|CLE|COL|DET|HOU|KCR|KC|LAA|LAD|MIA|MIL|MIN|NYM|NYY|ATH|OAK|PHI|PIT|SDP|SD|SEA|SFG|SF|STL|TBR|TB|TEX|TOR|WSN|WSH)"


def ocr_image(path: Path) -> str:
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError as error:
        raise RuntimeError("Install Pillow before reading image files: python -m pip install pillow") from error
    try:
        import pytesseract
    except ImportError as error:
        raise RuntimeError(
            "Install pytesseract and the Tesseract OCR desktop app, or paste OCR text with --text-file."
        ) from error

    image = Image.open(path)
    image = ImageOps.grayscale(image)
    image = ImageEnhance.Contrast(image).enhance(2.2)
    image = image.resize((image.width * 2, image.height * 2))
    return pytesseract.image_to_string(image, config="--psm 6")


def read_input_text(image_paths: list[Path], text_paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in image_paths:
        chunks.append(ocr_image(path))
    for path in text_paths:
        chunks.append(path.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n".join(chunks)


def clean_name(value: str) -> str:
    return app.clean_name(re.sub(r"\s+", " ", value).strip(" -:\t"))


def parse_percent(value: str) -> str:
    text = value.strip().upper()
    return "" if text == "NA" else text


def plus_count_to_line(count: int) -> float:
    return max(count - 0.5, 0.5)


def parse_strikeout_odds_text(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?P<player>[A-Za-z.'\- ]+?)\s+(?P<count>\d{1,2})\+\s+Strikeouts?\s+(?P<odds>[+\-]\d{2,5})",
        re.IGNORECASE,
    )
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for match in pattern.finditer(text.replace("\n", " ")):
        player = clean_name(match.group("player"))
        count = int(match.group("count"))
        odds = int(match.group("odds").replace("+", ""))
        key = (player.lower(), count, odds)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "Market": "Pitcher Strikeouts",
                "Player": player,
                "Team": "",
                "Opponent": "",
                "Line": f"{plus_count_to_line(count):g}",
                "Odds": f"{odds:+d}" if odds > 0 else str(odds),
                "Book": "image",
                "Side": "Over",
                "Source Count": f"{count}+",
            }
        )
    return rows


def parse_daily_strikeouts_text(text: str) -> list[dict[str, Any]]:
    row_pattern = re.compile(
        rf"^(?P<pitcher>.+?)\s+"
        r"(?P<throws>[LR])\s+"
        r"(?P<ip>NA|\d+(?:\.\d+)?)\s+"
        r"(?P<k>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<l15>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<l30>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<k9>NA|\d+(?:\.\d+)?)\s+"
        r"(?P<csw>NA|\d+(?:\.\d+)?%)\s+"
        rf"(?P<opp>{TEAM_RE})\s+"
        r"(?P<oppk>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<oppl15>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<oppl30>NA|\d+(?:\.\d+)?%)$",
        re.IGNORECASE,
    )
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        match = row_pattern.match(line)
        if not match:
            continue
        item = match.groupdict()
        rows.append(
            {
                "Pitcher": clean_name(item["pitcher"]),
                "Throws": item["throws"].upper(),
                "IP": "" if item["ip"].upper() == "NA" else item["ip"],
                "K%": parse_percent(item["k"]),
                "L15 K%": parse_percent(item["l15"]),
                "L30 K%": parse_percent(item["l30"]),
                "K/9": "" if item["k9"].upper() == "NA" else item["k9"],
                "CSW%": parse_percent(item["csw"]),
                "Opponent": app.normalize_team_code(item["opp"]),
                "Opp K%": parse_percent(item["oppk"]),
                "Opp L15 K%": parse_percent(item["oppl15"]),
                "Opp L30 K%": parse_percent(item["oppl30"]),
            }
        )
    return rows


def parse_hr_sheet_text(text: str) -> list[dict[str, Any]]:
    row_pattern = re.compile(
        rf"^(?P<pitcher>.+?)\s+"
        r"(?P<ip>NA|\d+(?:\.\d+)?)\s+"
        r"(?P<hr>NA|\d+)\s+"
        r"(?P<hr9>NA|\d+(?:\.\d+)?)\s+"
        r"(?P<lhh>NA|\d+)\s+"
        r"(?P<rhh>NA|\d+)\s+"
        r"(?P<fb>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<hard>NA|\d+(?:\.\d+)?%)\s+"
        r"(?P<barrel>NA|\d+(?:\.\d+)?%)\s+"
        rf"(?P<opp>{TEAM_RE})$",
        re.IGNORECASE,
    )
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        match = row_pattern.match(line)
        if not match:
            continue
        item = match.groupdict()
        rows.append(
            {
                "Pitcher": clean_name(item["pitcher"]),
                "IP": "" if item["ip"].upper() == "NA" else item["ip"],
                "HR": "" if item["hr"].upper() == "NA" else item["hr"],
                "HR/9": "" if item["hr9"].upper() == "NA" else item["hr9"],
                "HR vs LHH": "" if item["lhh"].upper() == "NA" else item["lhh"],
                "HR vs RHH": "" if item["rhh"].upper() == "NA" else item["rhh"],
                "FB%": parse_percent(item["fb"]),
                "HardHit%": parse_percent(item["hard"]),
                "Barrel%": parse_percent(item["barrel"]),
                "Opponent": app.normalize_team_code(item["opp"]),
            }
        )
    return rows


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert OCR text from MLB prop screenshots into analyzer-ready CSV.")
    parser.add_argument("--type", choices=["strikeout-odds", "daily-strikeouts", "hr-sheet", "raw"], required=True)
    parser.add_argument("--image", action="append", type=Path, default=[], help="PNG/JPG screenshot to OCR.")
    parser.add_argument("--text-file", action="append", type=Path, default=[], help="Text copied from any OCR tool.")
    parser.add_argument("--out", type=Path, required=True, help="CSV or text output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    text = read_input_text(args.image, args.text_file)
    if args.type == "raw":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote OCR text to {args.out}")
        return 0

    parsers = {
        "strikeout-odds": parse_strikeout_odds_text,
        "daily-strikeouts": parse_daily_strikeouts_text,
        "hr-sheet": parse_hr_sheet_text,
    }
    rows = parsers[args.type](text)
    write_rows(args.out, rows)
    print(f"Wrote {len(rows)} row(s) to {args.out}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
