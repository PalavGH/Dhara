import aiohttp
from loguru import logger
from config.dhara_settings import load_config
from server.cache.dhara_redis_cache import DharaServerRedisCache

config = load_config('config/server_config.json')
secrets = load_config('config/secrets.json')

class DharaAPIHandler:
    def __init__(self):
        self.api_keys = secrets['api_keys']
        self.urls = config['urls']
        self.redis_cache = DharaServerRedisCache()
        self.hangar_token = None

    async def authenticate_hangar(self):
        headers = {
            "accept": "application/json"
        }
        params = {"apiKey": self.api_keys['hangar']}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.urls['auth_hangar'], headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.hangar_token = data['token']
                    logger.info("Hangar authentication successful")
                else:
                    logger.error(f"Hangar authentication error {response.status}: {response.reason}")

    async def authenticate_modrinth(self):
        logger.info("Modrinth authentication successful")  # Assume token is static or handled externally

    async def fetch_plugin_data(self, plugin_name):
        plugin_name_cleaned = ''.join(filter(lambda x: not x.isdigit() and x != '.', plugin_name))
        cached_data = await self.redis_cache.get(plugin_name_cleaned)
        if cached_data:
            logger.info(f"Found {plugin_name_cleaned} in cache")
            return cached_data

        if await self.redis_cache.is_negative_cache(plugin_name_cleaned):
            logger.info(f"Found {plugin_name_cleaned} in negative cache")
            return {"error": "Plugin not found"}

        hangar_data = await self.fetch_hangar_data(plugin_name_cleaned)
        if hangar_data:
            await self.redis_cache.set(plugin_name_cleaned, hangar_data, ex=300)  # Cache for 5 minutes
            return hangar_data

        modrinth_data = await self.fetch_modrinth_data(plugin_name_cleaned)
        if modrinth_data:
            await self.redis_cache.set(plugin_name_cleaned, modrinth_data, ex=300)  # Cache for 5 minutes
            return modrinth_data

        await self.redis_cache.set_negative_cache(plugin_name_cleaned, ex=300)  # Negative cache for 5 minutes
        return {"error": "Plugin not found"}

    async def fetch_hangar_data(self, plugin_name):
        headers = {
            "Authorization": f"HangarAuth {self.hangar_token}",
            "User-Agent": config['user_agent']
        }
        params = {"q": plugin_name, "limit": 1}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.urls['search_hangar'], headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logger.info(f"Hangar response: {data}")
                    if data['result']:
                        return data['result'][0]
            except aiohttp.ClientResponseError as e:
                logger.error(f"Hangar HTTP error {e.status}: {e.message}")
            except Exception as e:
                logger.error(f"Error fetching Hangar data: {e}")
        return None

    async def fetch_modrinth_data(self, plugin_name):
        headers = {
            "Authorization": f"Bearer {self.api_keys['modrinth']}",
            "User-Agent": config['user_agent']
        }
        params = {"query": plugin_name, "limit": 1}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.urls['search_modrinth'], headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logger.info(f"Modrinth response: {data}")
                    if data['hits']:
                        return data['hits'][0]
            except aiohttp.ClientResponseError as e:
                logger.error(f"Modrinth HTTP error {e.status}: {e.message}")
            except Exception as e:
                logger.error(f"Error fetching Modrinth data: {e}")
        return None
