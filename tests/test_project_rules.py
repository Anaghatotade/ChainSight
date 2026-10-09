"""Guards for the project rules: no web layer, no deep-learning frameworks, no .sh files, reproducible data."""
import re
from pathlib import Path

import datagen

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}


def _files(pattern):
    return [p for p in ROOT.rglob(pattern) if not (set(p.parts) & SKIP)]


def test_no_shell_scripts():
    assert _files("*.sh") == []


def test_no_deep_learning_frameworks_in_code_or_requirements():
    banned = re.compile(r"^\s*(import|from)\s+(tensorflow|torch|keras)\b", re.M)
    for f in _files("*.py"):
        assert not banned.search(f.read_text(encoding="utf-8")), f
    lines = (ROOT / "requirements.txt").read_text().lower().splitlines()
    req = "\n".join(l.split("#")[0] for l in lines)          # ignore comments
    for name in ("tensorflow", "torch", "keras", "flask", "fastapi", "django", "docker"):
        assert name not in req


def test_no_web_layer_left():
    for name in ("frontend", "backend", "docker-compose.yml", "Dockerfile"):
        assert not (ROOT / name).exists()


def test_required_folders_exist():
    for name in ("data/raw", "data/processed", "notebooks", "src", "sql", "outputs", "tests", "docs"):
        assert (ROOT / name).is_dir(), name


def test_generator_is_reproducible():
    a = datagen.generate_clean(seed=3, n_skus=4, n_suppliers=6, n_days=70)
    b = datagen.generate_clean(seed=3, n_skus=4, n_suppliers=6, n_days=70)
    for name in a:
        assert a[name].equals(b[name]), name


def test_hidden_simulation_parameters_are_not_exported(small_clean):
    for df in small_clean.values():
        assert not any(c.startswith("_") for c in df.columns)
