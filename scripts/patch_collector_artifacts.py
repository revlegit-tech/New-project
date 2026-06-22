from pathlib import Path

path = Path(".github/workflows/season-collector.yml")
text = path.read_text(encoding="utf-8")

# Add full PropLine market list to workflow env.
old_env = """env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
"""

new_env = """env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
  PHASE18_MARKETS: "pitcher_strikeouts,batter_hits,batter_total_bases,batter_home_runs,batter_rbis,batter_stolen_bases,batter_walks,batter_singles,batter_doubles,batter_runs,batter_2plus_hits,batter_2plus_home_runs,batter_2plus_rbis,batter_3plus_rbis,pitcher_outs,pitcher_hits_allowed,pitcher_earned_runs"
"""

if old_env not in text:
    raise SystemExit("Could not find expected env block.")

text = text.replace(old_env, new_env)

# Replace compact artifact packaging with full raw/warehouse backup.
old_package = """      - name: Package compact data artifact
        if: always()
        shell: bash
        run: |
          mkdir -p workflow-artifacts
          tar -czf "workflow-artifacts/season-collector-${{ github.run_id }}.tgz" \\
            data/cloud data/cache/savant data/cache/odds_movement data/playerboard data/backtests data/audit data/ml data/training \\
            2>/dev/null || true
"""

new_package = """      - name: Package collector data artifact
        if: always()
        shell: bash
        run: |
          mkdir -p workflow-artifacts
          mkdir -p data/odds data/warehouse/odds_snapshots data/warehouse/raw data/warehouse/summaries data/warehouse/logs
          tar -czf "workflow-artifacts/season-collector-${{ github.run_id }}.tgz" \\
            data/cloud \\
            data/cache/savant \\
            data/cache/odds_movement \\
            data/playerboard \\
            data/backtests \\
            data/audit \\
            data/ml \\
            data/training \\
            data/odds \\
            data/warehouse/odds_snapshots \\
            data/warehouse/raw \\
            data/warehouse/summaries \\
            data/warehouse/logs \\
            2>/dev/null || true
"""

if old_package not in text:
    raise SystemExit("Could not find expected package artifact block.")

text = text.replace(old_package, new_package)

# Keep artifacts longer.
text = text.replace("          retention-days: 14", "          retention-days: 90")

path.write_text(text, encoding="utf-8")
print("Patched .github/workflows/season-collector.yml")
