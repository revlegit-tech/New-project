from pathlib import Path

path = Path("oddspapi_team_backfill.py")
text = path.read_text(encoding="utf-8")

old = '''    write_manual_score_template(fixtures, args.from_date, args.to_date)
'''

new = '''    # Only create a blank manual score template when the user is not supplying
    # an existing score file. This prevents grading runs from overwriting filled scores.
    if not args.manual_scores:
        write_manual_score_template(fixtures, args.from_date, args.to_date)
    else:
        score_path = Path(args.manual_scores)
        if score_path.exists():
            print("using manual scores:", score_path)
        else:
            write_manual_score_template(fixtures, args.from_date, args.to_date)
            print("manual scores file missing; created blank template:", score_path)
'''

if old not in text:
    raise SystemExit("Could not find template-write line to patch.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("Patched oddspapi_team_backfill.py to avoid overwriting manual scores during grading.")
