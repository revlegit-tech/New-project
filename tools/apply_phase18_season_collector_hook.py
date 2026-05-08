from __future__ import annotations

"""Patch season_auto_collector.py to run Phase 18 context fill after playerboard build."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "season_auto_collector.py"

HOOK = """
        try:
            from tools.phase18_fill_missing_context import run_context_fill

            summary["phase18ContextCollector"] = run_context_fill(
                date_label=date_label,
                season=int(date_label[:4]),
                markets=[
                    "batter_hits",
                    "batter_total_bases",
                    "batter_home_runs",
                    "pitcher_strikeouts",
                    "pitcher_hits_allowed",
                    "pitcher_earned_runs",
                ],
                line_source="propline",
                refresh_provider=True,
                write=True,
            )
        except Exception as context_error:
            summary["phase18ContextCollector"] = {
                "error": str(context_error),
                "note": "Phase 18 context collector failed but the main collector continued.",
            }

"""


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if 'summary["phase18ContextCollector"]' in text:
        print({"status": "ok", "changed": False, "reason": "hook already present"})
        return

    marker = '        try:\n            from playerboard_backtest import grade_playerboard\n'
    if marker not in text:
        raise SystemExit("Could not find insertion point before playerboard_backtest block.")

    text = text.replace(marker, HOOK + "\n" + marker, 1)
    TARGET.write_text(text, encoding="utf-8")
    print({"status": "ok", "changed": True, "target": str(TARGET)})


if __name__ == "__main__":
    main()
