from pathlib import Path


def test_phase20_v2_hotfix_script_exists():
    assert Path('tools/apply_phase20_v2_rail_modal_hotfix.py').exists()
