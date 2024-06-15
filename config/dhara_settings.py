import json
from loguru import logger

def load_config(config_path):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"Loaded config from {config_path}")
        return config
    except Exception as e:
        logger.exception(f"Failed to load config from {config_path}: {e}")
        return {}
