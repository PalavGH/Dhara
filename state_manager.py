import os
from loguru import logger
from redis_client import RedisClient
from config import Config

class State:
    def __init__(self):
        self.redis_client = RedisClient()
        self.config = Config().config
        self.plugin_folder = self.config.get('paths', {}).get('plugin_folder', 'plugins')
        self.loading = False
        self.found_plugins = []
        self.not_found_plugins = []

    def set_plugin_folder(self, folder_path):
        self.plugin_folder = folder_path

    def get_plugin_folder(self):
        return self.plugin_folder

    def set_loading(self, loading):
        self.loading = loading

    def clear_plugins(self):
        self.found_plugins = []
        self.not_found_plugins = []

    def add_found_plugin(self, plugin):
        self.found_plugins.append(plugin)

    def add_not_found_plugin(self, plugin):
        self.not_found_plugins.append(plugin)

    def load_state(self):
        try:
            self.plugin_folder = self.redis_client.get('plugin_folder') or self.plugin_folder
            logger.info(f"State loaded. Plugin folder: {self.plugin_folder}")
        except Exception as e:
            logger.error(f"Error loading state: {e}")

    def save_state(self):
        try:
            self.redis_client.set('plugin_folder', self.plugin_folder)
            logger.info("State saved.")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
