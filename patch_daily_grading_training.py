from pathlib import Path

path = Path(".github/workflows/daily-playerboard-grading.yml")
text = path.read_text(encoding="utf-8")

# Make sure Python logs stream.
text = text.replace(
    'python season_auto_collector.py snapshot --run-type grading --date "$GRADE_DATE"',
    'python -u season_auto_collector.py snapshot --run-type grading --date "$GRADE_DATE"',
)

# Add compile check for the new trainer.
text = text.replace(
    "python -m py_compile app.py playerboard.py playerboard_backtest.py model_audit.py ml_export.py season_auto_collector.py",
    "python -m py_compile app.py playerboard.py playerboard_backtest.py model_audit.py ml_export.py season_auto_collector.py train_all_supported_markets.py",
)

training_step = '''      - name: Rebuild and train supported market models
        if: always()
        shell: bash
        run: |
          GRADE_DATE="${{ steps.grade_date.outputs.grade_date }}"
          SEASON="${GRADE_DATE:0:4}"
          python -u train_all_supported_markets.py --season "$SEASON"

'''

marker = '''      - name: Commit grading outputs
        if: always()
'''

if training_step not in text:
    if marker not in text:
        raise SystemExit("Could not find Commit grading outputs step.")
    text = text.replace(marker, training_step + marker)

# Commit summaries. The training CSVs and joblib models are ignored by .gitignore,
# so we force-add only lightweight summary JSONs.
old_add = '''          git add data/health || true
'''

new_add = '''          git add data/health || true
          git add -f data/training/train_all_supported_markets_summary_*.json || true
          git add -f data/training/latest_train_all_supported_markets_summary.json || true
'''

if old_add in text and new_add not in text:
    text = text.replace(old_add, new_add)

path.write_text(text, encoding="utf-8")
print("Patched daily-playerboard-grading.yml to train supported markets automatically.")
