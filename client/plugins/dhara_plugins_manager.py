import os
import json
import aiohttp
from loguru import logger
from client.cache.dhara_local_cache import DharaLocalCache
from client.cache.dhara_redis_cache import DharaRedisCache
from utils.dhara_helper import normalize_name
from config.dhara_settings import load_config

config = load_config('config/client_config.json')

class DharaPluginManager:
    def __init__(self):
        self.local_cache = DharaLocalCache(config['paths']['cache_dir'])
        self.redis_cache = DharaRedisCache()
        self.server_url = f"http://{config['server']['host']}:{config['server']['port']}"
        self.plugin_folder = config['paths']['plugin_folder']
        self.server_healthy = False

    async def health_check(self):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.server_url}/health") as response:
                    if response.status == 200:
                        logger.info("Server health check passed")
                        self.server_healthy = True
                        return True
                    else:
                        logger.error(f"Server health check failed with status code {response.status}")
                        self.server_healthy = False
                        return False
            except Exception as e:
                logger.error(f"Server health check failed: {e}")
                self.server_healthy = False
                return False

    async def get_plugin_from_cache(self, plugin_name):
        if await self.redis_cache.is_negative_cache(plugin_name):
            logger.info(f"{plugin_name} is in negative cache")
            return None

        cached_data = self.local_cache.load_json(f"{plugin_name}.json")
        if cached_data:
            logger.info(f"Loaded {plugin_name} data from local cache")
            return cached_data

        redis_data = await self.redis_cache.get(plugin_name)
        if redis_data:
            self.local_cache.save_json(f"{plugin_name}.json", redis_data)
            logger.info(f"Loaded {plugin_name} data from Redis and cached locally")
            return redis_data

        logger.info(f"{plugin_name} data not found in local cache or Redis")
        return None

    async def request_server_fetch(self, plugin_name):
        url = f"{self.server_url}/fetch_plugin"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={"plugin_name": plugin_name}) as response:
                    if response.status == 200:
                        data = await response.json()
                        await self.redis_cache.set(plugin_name, json.dumps(data), ex=300)  # Cache for 5 minutes
                        self.local_cache.save_json(f"{plugin_name}.json", data)
                        logger.info(f"Fetched {plugin_name} data from server and updated caches")
                        return data
                    else:
                        logger.error(f"Failed to fetch {plugin_name} data from server: {response.status}")
            except Exception as e:
                logger.error(f"Error fetching {plugin_name} data from server: {e}")
        return None

    async def search_plugin(self, plugin_name):
        logger.info(f"Searching for plugin: {plugin_name}")
        try:
            if not self.server_healthy:
                if not await self.health_check():
                    return None

            normalized_plugin_name = normalize_name(plugin_name)
            cached_data = await self.get_plugin_from_cache(normalized_plugin_name)
            if cached_data:
                return cached_data

            plugin_data = await self.request_server_fetch(normalized_plugin_name)
            if plugin_data:
                return plugin_data
            else:
                await self.redis_cache.set_negative_cache(normalized_plugin_name)
                logger.info(f"Set negative cache for {normalized_plugin_name}")

        except Exception as e:
            logger.error(f"Error searching for plugin: {e}")
        return None

    async def check_plugins(self, folder_path):
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            logger.info(f"Created plugins directory: {folder_path}")

        found_plugins = []
        not_found_plugins = []
        for filename in os.listdir(folder_path):
            if filename.endswith(".jar"):
                plugin_name = filename[:-4]
                plugin_data = await self.search_plugin(plugin_name)
                if plugin_data:
                    found_plugins.append((plugin_name, plugin_data))
                else:
                    not_found_plugins.append((plugin_name, "unknown_version"))
        return found_plugins, not_found_plugins
