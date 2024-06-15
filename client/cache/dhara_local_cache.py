import os
import json
from loguru import logger
from PIL import Image
from utils.dhara_helper import normalize_name

class DharaLocalCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _get_full_path(self, filename: str, extension: str = "") -> str:
        normalized_filename = normalize_name(filename)
        return os.path.join(self.cache_dir, f"{normalized_filename}{extension}")

    def save_json(self, filename: str, data: dict):
        full_path = self._get_full_path(filename, ".json")
        try:
            with open(full_path, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Successfully saved JSON to {full_path}")
        except Exception as e:
            logger.exception(f"Failed to save JSON to {full_path}: {e}")

    def load_json(self, filename: str) -> dict:
        full_path = self._get_full_path(filename, ".json")
        if not os.path.exists(full_path):
            logger.warning(f"JSON file {full_path} does not exist")
            return None
        try:
            with open(full_path, 'r') as f:
                data = json.load(f)
            logger.debug(f"Successfully loaded JSON from {full_path}")
            return data
        except Exception as e:
            logger.exception(f"Failed to load JSON from {full_path}: {e}")
            return None

    def save_file(self, filename: str, data: bytes):
        full_path = self._get_full_path(filename)
        try:
            with open(full_path, 'wb') as f:
                f.write(data)
            logger.debug(f"Successfully saved file to {full_path}")
        except Exception as e:
            logger.exception(f"Failed to save file to {full_path}: {e}")

    def load_file(self, filename: str) -> bytes:
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
            logger.exception(f"Failed to load file from {full_path}: {e}")
            return None

    def save_image(self, filename: str, image_data: bytes):
        full_path = self._get_full_path(filename, ".png")
        try:
            with open(full_path, 'wb') as f:
                f.write(image_data)
            logger.debug(f"Successfully saved image to {full_path}")
        except Exception as e:
            logger.exception(f"Failed to save image to {full_path}: {e}")

    def load_image(self, filename: str) -> bytes:
        full_path = self._get_full_path(filename, ".png")
        if not os.path.exists(full_path):
            logger.warning(f"Image file {full_path} does not exist")
            return None
        try:
            with open(full_path, 'rb') as f:
                image_data = f.read()
            logger.debug(f"Successfully loaded image from {full_path}")
            return image_data
        except Exception as e:
            logger.exception(f"Failed to load image from {full_path}: {e}")
            return None

    def save_negative_cache(self, plugin_name: str):
        negative_cache_file = self._get_full_path("negative_cache", ".json")
        negative_cache = self.load_json("negative_cache") or {}
        negative_cache[normalize_name(plugin_name)] = True
        self.save_json("negative_cache", negative_cache)
        logger.debug(f"Saved negative cache for {plugin_name}")

    def is_negative_cache(self, plugin_name: str) -> bool:
        negative_cache = self.load_json("negative_cache") or {}
        return negative_cache.get(normalize_name(plugin_name), False)
