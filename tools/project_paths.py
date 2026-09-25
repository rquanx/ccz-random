from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_DIR = REPO_ROOT / "resources"
APP_RESOURCES_DIR = RESOURCES_DIR / "app"
DATA_DIR = RESOURCES_DIR / "data"
EQUIPMENT_DATA_DIR = DATA_DIR / "equipment"
JOB_DATA_DIR = DATA_DIR / "jobs"
SKILL_DATA_DIR = DATA_DIR / "skills"
LEGACY_RESOURCES_DIR = RESOURCES_DIR / "legacy"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
