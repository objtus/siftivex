from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"

DEFAULT_DB_PATH = DATA_DIR / "siftivex.db"
DEFAULT_LANCE_PATH = DATA_DIR / "lance"
PHASE0_MANIFEST = DATA_DIR / "phase0" / "manifest.json"
PHASE0_CONFIG = CONFIG_DIR / "phase0.yaml"
PHASE0_RESULTS = DATA_DIR / "phase0" / "results"
PHASE0_REVIEW = DATA_DIR / "phase0" / "review"
TAG_VOCABULARY_PATH = CONFIG_DIR / "tag_vocabulary.yaml"
