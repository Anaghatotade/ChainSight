"""Guards for the project rules: no web layer, no deep-learning frameworks, no .sh files, real data, no stale placeholders."""
import re
from pathlib import Path

import config as cfg

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}


def _files(pattern):
    return [p for p in ROOT.rglob(pattern) if not (set(p.parts) & SKIP)]


def test_no_shell_scripts():
    assert _files("*.sh") == []


def test_no_deep_learning_frameworks_in_code_or_requirements():
    banned = re.compile(r"^\\s*(import|from)\\s+(tensorflow|torch|keras)\\b", re.M)
    for f in _files("*.py"):
        assert not banned.search(f.read_text(encoding="utf-8")), f
    lines = (ROOT / "requirements.txt").read_text().lower().splitlines()
    req = "\\n".join(l.split("#")[0] for l in lines)          # ignore comments
    for name in ("tensorflow", "torch", "keras", "flask", "fastapi", "django", "docker"):
        assert name not in req


def test_no_web_layer_left():
    for name in ("frontend", "backend", "docker-compose.yml", "Dockerfile"):
        assert not (ROOT / name).exists()


def test_required_folders_exist():
    for name in ("data/raw", "data/processed", "notebooks", "src", "sql", "outputs", "tests", "docs"):
        assert (ROOT / name).is_dir(), name


def test_synthetic_data_generator_is_gone_and_data_is_not_committed():
    assert not (ROOT / "src" / "datagen.py").exists()
    ignore = (ROOT / ".gitignore").read_text()
    assert "data/raw/*" in ignore and "data/processed/*" in ignore          # Kaggle rules: never commit the M5 files


def test_config_split_fits_inside_the_m5_history():
    assert cfg.TRAIN_WEEKS + cfg.DEV_WEEKS + cfg.TEST_WEEKS <= 273          # 1,913 days = 273 full weeks
    assert cfg.ABC_A_CUTOFF < cfg.ABC_B_CUTOFF <= 1 and cfg.CV_LOW < cfg.CV_HIGH
    assert cfg.MIN_HISTORY <= cfg.TRAIN_WEEKS


def test_generated_docs_have_no_unresolved_placeholders():
    for name in ("README.md", "INTERVIEW_NOTES.md"):
        path = ROOT / name
        if path.exists():
            assert "{{" not in path.read_text(encoding="utf-8"), name


def test_every_source_file_is_free_of_leftover_synthetic_data_terms():
    stale = re.compile(r"datagen|generate_clean|inject_raw_issues|chainsight\\.db|demand_daily|purchase_orders")
    for f in list(_files("*.py")) + list(_files("*.sql")):
        if f.name == "test_project_rules.py":
            continue
        assert not stale.search(f.read_text(encoding="utf-8")), f
