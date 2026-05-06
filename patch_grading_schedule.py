from pathlib import Path

path = Path(".github/workflows/daily-playerboard-grading.yml")
text = path.read_text(encoding="utf-8")

old = '''  schedule:
    # GitHub cron is UTC.
    # 08:00 UTC = 4:00 AM ET during daylight time.
    # Runs after late West Coast games should be final.
    - cron: "0 8 * * *"
'''

new = '''  schedule:
    # GitHub cron is UTC.
    # Backup runs are intentional because MLB final data can lag.
    # During US Eastern daylight time:
    # 08:00 UTC = 4:00 AM ET
    # 12:00 UTC = 8:00 AM ET
    # 16:00 UTC = 12:00 PM ET
    - cron: "0 8 * * *"
    - cron: "0 12 * * *"
    - cron: "0 16 * * *"
'''

if old not in text:
    raise SystemExit("Could not find the existing schedule block. Send me the top of daily-playerboard-grading.yml.")

path.write_text(text.replace(old, new), encoding="utf-8")
print("Added backup daily grading schedules.")
