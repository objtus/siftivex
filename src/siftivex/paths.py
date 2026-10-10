from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"

DEFAULT_DB_PATH = DATA_DIR / "siftivex.db"
DEFAULT_LANCE_PATH = DATA_DIR / "lance"
DEFAULT_THUMBNAILS_DIR = DATA_DIR / "thumbnails"
PHASE0_MANIFEST = DATA_DIR / "phase0" / "manifest.json"
PHASE0_CONFIG = CONFIG_DIR / "phase0.yaml"
PHASE0_RESULTS = DATA_DIR / "phase0" / "results"
PHASE0_REVIEW = DATA_DIR / "phase0" / "review"
PHASE0_GOLD = DATA_DIR / "phase0" / "gold"
PILOT_MODEL_CACHE = DATA_DIR / "pilot_models"
TAG_VOCABULARY_PATH = CONFIG_DIR / "tag_vocabulary.yaml"
FOLDER_RULES_PATH = CONFIG_DIR / "folder_rules.yaml"
