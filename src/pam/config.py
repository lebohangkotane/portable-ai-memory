"""Global configuration for PAM."""

from pathlib import Path

import platformdirs


APP_NAME = "pam"
APP_AUTHOR = "pam"

# Default directories
DATA_DIR = Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))
CONFIG_DIR = Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))

# Vault defaults
DEFAULT_VAULT_PATH = DATA_DIR / "vault.db"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# Token budget defaults (conservative — works with all models)
DEFAULT_TOKEN_BUDGET = 4000
MAX_MEMORIES_PER_QUERY = 50
