import redis
import json
from loguru import logger

# Initialize Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

class State:
    def __init__(self):
        self.found_plugins = []
        self.not_found_plugins = []
        self.loading = False
        self.error_message = ""
        self.update_status = []
        self.api_keys = {}
        self.plugin_folder = ""
        self.selected_plugin = None

    def set_loading(self, is_loading):
        self.loading = is_loading
        self._save_to_redis('loading', is_loading)

    def set_error(self, message):
        self.error_message = message
        self._save_to_redis('error_message', message)

    def clear_error(self):
        self.error_message = ""
        self._save_to_redis('error_message', "")

    def add_found_plugin(self, plugin):
        self.found_plugins.append(plugin)
        self._save_to_redis('found_plugins', self.found_plugins)

    def add_not_found_plugin(self, plugin):
        self.not_found_plugins.append(plugin)
        self._save_to_redis('not_found_plugins', self.not_found_plugins)

    def clear_plugins(self):
        self.found_plugins = []
        self.not_found_plugins = []
        self._save_to_redis('found_plugins', self.found_plugins)
        self._save_to_redis('not_found_plugins', self.not_found_plugins)

    def set_update_status(self, updates):
        self.update_status = updates
        self._save_to_redis('update_status', updates)

    def clear_update_status(self):
        self.update_status = []
        self._save_to_redis('update_status', [])

    def set_api_key(self, platform, key):
        self.api_keys[platform] = key.strip()
        self._save_to_redis('api_keys', self.api_keys)

    def get_api_key(self, platform):
        return self.api_keys.get(platform)

    def set_plugin_folder(self, folder_path):
        self.plugin_folder = folder_path
        self._save_to_redis('plugin_folder', folder_path)

    def get_plugin_folder(self):
        return self.plugin_folder

    def set_selected_plugin(self, plugin):
        self.selected_plugin = plugin
        self._save_to_redis('selected_plugin', plugin)

    def get_selected_plugin(self):
        return self.selected_plugin

    def _save_to_redis(self, key, value):
        try:
            redis_client.set(key, json.dumps(value))
        except Exception as e:
            logger.error(f"Error saving to Redis: {e}")

    def _load_from_redis(self, key):
        try:
            value = redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error loading from Redis: {e}")
            return None

    def load_state(self):
        self.found_plugins = self._load_from_redis('found_plugins') or []
        self.not_found_plugins = self._load_from_redis('not_found_plugins') or []
        self.loading = self._load_from_redis('loading') or False
        self.error_message = self._load_from_redis('error_message') or ""
        self.update_status = self._load_from_redis('update_status') or []
        self.api_keys = self._load_from_redis('api_keys') or {}
        self.plugin_folder = self._load_from_redis('plugin_folder') or ""
        self.selected_plugin = self._load_from_redis('selected_plugin') or None


state = State()
state.load_state()
