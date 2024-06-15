import asyncio
import aiohttp
import orjson
from loguru import logger
from config.dhara_settings import load_config
from server.cache.dhara_redis_cache import DharaServerRedisCache
from utils.dhara_helper import normalize_name
from rapidfuzz import fuzz, process
import base64

config = load_config('config/server_config.json')
secrets = load_config('config/secrets.json')


def get_best_match(plugin_name, results):
    normalized_plugin_name = normalize_name(plugin_name)
    choices = [(normalize_name(plugin['title'] if plugin.get('title') else plugin['name']), plugin) for plugin in
               results]
    best_matches = process.extract(normalized_plugin_name, [choice[0] for choice in choices], scorer=fuzz.ratio,
                                   limit=3)
    for match, score, index in best_matches:
        if score > 80:  # Threshold of 80% similarity
            return choices[index][1]
    return None


class DharaAPIHandler:
    def __init__(self):
        self.api_keys = secrets['api_keys']
        self.urls = config['urls']
        self.redis_cache = DharaServerRedisCache()
        self.hangar_token = None
        self.session = None

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def authenticate_hangar(self):
        headers = {"accept": "application/json"}
        params = {"apiKey": self.api_keys['hangar']}
        try:
            async with self.session.post(self.urls['auth_hangar'], headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.hangar_token = data['token']
                else:
                    logger.error(f"Hangar authentication error {response.status}: {response.reason}")
        except Exception as e:
            logger.exception(f"Error during Hangar authentication: {e}")

    async def authenticate_modrinth(self):
        try:
            # Modrinth doesn't need authentication in this implementation
            pass
        except Exception as e:
            logger.exception(f"Error during Modrinth authentication: {e}")

    async def fetch_plugin_data(self, plugin_name):
        plugin_name_cleaned = normalize_name(plugin_name)
        try:
            cached_data = await self.redis_cache.get(plugin_name_cleaned)
            if cached_data:
                logger.info(f"Found {plugin_name_cleaned} in cache")
                return cached_data

            if await self.redis_cache.is_negative_cache(plugin_name_cleaned):
                logger.info(f"Found {plugin_name_cleaned} in negative cache")
                return {"error": "Plugin not found"}

            logger.info(f"Searching for plugin: {plugin_name} on Modrinth and Hangar")

            hangar_task = self.fetch_hangar_data(plugin_name_cleaned)
            modrinth_task = self.fetch_modrinth_data(plugin_name_cleaned)

            results = await asyncio.gather(hangar_task, modrinth_task, return_exceptions=True)

            plugins = []
            for source, result in zip(["hangar", "modrinth"], results):
                if isinstance(result, Exception):
                    logger.error(f"Error fetching data from {source}: {result}")
                    continue

                if result:
                    for item in result:
                        normalized_data = await self._normalize_data(item, source)
                        plugins.append(normalized_data)

                    plugin_names = [item['title'] if 'title' in item else item['name'] for item in result]
                    logger.info(f"Results from {source}: {plugin_names} " + " for " + plugin_name)

            best_match = get_best_match(plugin_name, plugins)

            if best_match:
                logger.info(f"{plugin_name} has been matched to {best_match['name']} from {best_match['source']}")
                await self.redis_cache.set(plugin_name_cleaned, best_match, ex=300)  # Cache for 5 minutes
                return best_match

            await self.redis_cache.set_negative_cache(plugin_name_cleaned, ex=300)  # Negative cache for 5 minutes
            return {"error": "Plugin not found"}
        except Exception as e:
            logger.exception(f"Error fetching plugin data for {plugin_name}: {e}")
            return {"error": "Internal server error"}

    async def fetch_hangar_data(self, plugin_name):
        headers = {
            "Authorization": f"HangarAuth {self.hangar_token}",
            "User-Agent": config['user_agent']
        }
        params = {"q": plugin_name, "limit": 3}
        try:
            async with self.session.get(self.urls['search_hangar'], headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data['result'] if data['result'] else []
        except aiohttp.ClientResponseError as e:
            logger.exception(f"Error fetching Hangar data: {e}")
        except Exception as e:
            logger.exception(f"Error fetching Hangar data: {e}")
        return []

    async def fetch_modrinth_data(self, plugin_name):
        headers = {
            "Authorization": f"Bearer {self.api_keys['modrinth']}",
            "User-Agent": config['user_agent']
        }
        params = {"query": plugin_name, "limit": 3}
        try:
            async with self.session.get(self.urls['search_modrinth'], headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data['hits'] if data['hits'] else []
        except aiohttp.ClientResponseError as e:
            logger.error(f"Modrinth HTTP error {e.status}: {e.message}")
        except Exception as e:
            logger.exception(f"Error fetching Modrinth data: {e}")
        return []

    async def fetch_and_cache_image(self, url, plugin_name):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        await self.redis_cache.set(f"{plugin_name}_image", base64.b64encode(image_data).decode(),
                                                   ex=300)
                        return base64.b64encode(image_data).decode()
                    else:
                        logger.error(f"Failed to fetch image from {url}: {response.status}")
        except Exception as e:
            logger.exception(f"Error fetching image from {url}: {e}")
        return None

    async def _normalize_data(self, data, source):
        normalized_data = {}

        try:
            if source == "hangar":
                normalized_data = {
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "author": data["namespace"].get("owner", ""),
                    "downloads": data["stats"].get("downloads", 0),
                    "followers": data["stats"].get("stars", 0),
                    "last_updated": data.get("lastUpdated", ""),
                    "icon_url": data.get("avatarUrl", ""),
                    "url": "https://hangar.papermc.io/" + data["namespace"].get("owner") + "/" + data.get("name"),
                    "source": "hangar"
                }
            elif source == "modrinth":
                normalized_data = {
                    "name": data.get("title", ""),
                    "description": data.get("description", ""),
                    "author": data.get("author", ""),
                    "downloads": data.get("downloads", 0),
                    "followers": data.get("follows", 0),
                    "last_updated": data.get("date_modified", ""),
                    "icon_url": data.get("icon_url", ""),
                    "url": "https://modrinth.com/plugin/" + data.get("project_id"),
                    "source": "modrinth"
                }

            image_data = await self.fetch_and_cache_image(normalized_data.get("icon_url"),
                                                          normalize_name(normalized_data["name"]))
            if image_data:
                normalized_data["icon_data"] = image_data
        except Exception as e:
            logger.exception(f"Error normalizing data from {source}: {e}")

        return normalized_data

    async def close(self):
        if self.session:
            await self.session.close()
