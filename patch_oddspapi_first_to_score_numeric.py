from pathlib import Path

path = Path("oddspapi_team_backfill.py")
text = path.read_text(encoding="utf-8")

old = '''            actual = int(str(score["firstToScore"]).strip().lower() in {"1", "true", "yes", "y"})
            over = actual
            result = "win" if actual else "loss"
'''

new = '''            first_value = score["firstToScore"]
            try:
                actual = int(float(first_value) > 0)
            except Exception:
                actual = int(str(first_value).strip().lower() in {"1", "1.0", "true", "yes", "y"})
            over = actual
            result = "win" if actual else "loss"
'''

if old not in text:
    raise SystemExit("Could not find firstToScore grading line to patch.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("Patched firstToScore grading to handle numeric 1.0 values.")
