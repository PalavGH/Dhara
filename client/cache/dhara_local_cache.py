import os
import json
from loguru import logger

class DharaLocalCache:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_full_path(self, filename):
        return os.path.join(self.cache_dir, filename)

    def save_json(self, filename, data):
        full_path = self._get_full_path(filename)
        try:
            with open(full_path, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Successfully saved JSON to {full_path}")
        except Exception as e:
            logger.error(f"Error saving JSON to {full_path}: {e}")

    def load_json(self, filename):
        full_path = self._get_full_path(filename)
        if not os.path.exists(full_path):
            logger.warning(f"JSON file {full_path} does not exist")
            return None
        try:
            with open(full_path, 'r') as f:
                data = json.load(f)
            logger.debug(f"Successfully loaded JSON from {full_path}")
            return data
        except Exception as e:
            logger.error(f"Error loading JSON from {full_path}: {e}")
            return None

    def save_file(self, filename, data):
        full_path = self._get_full_path(filename)
        try:
            with open(full_path, 'wb') as f:
                f.write(data)
            logger.debug(f"Successfully saved file to {full_path}")
        except Exception as e:
            logger.error(f"Error saving file to {full_path}: {e}")

    def load_file(self, filename):
        full_path = self._get_full_path(filename)
        if not os.path.exists(full_path):
            logger.warning(f"File {full_path} does not exist")
            return None
        try:
            with open(full_path, 'rb') as f:
                data = f.read()
            logger.debug(f"Successfully loaded file from {full_path}")
            return data
        except Exception as e:
            logger.error(f"Error loading file from {full_path}: {e}")
            return None
