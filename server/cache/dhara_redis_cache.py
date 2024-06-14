import redis.asyncio as aioredis
from loguru import logger
from config.dhara_settings import load_config
import json

config = load_config('config/server_config.json')

class DharaServerRedisCache:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DharaServerRedisCache, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.redis_client = aioredis.from_url(f"redis://{config['redis']['host']}:{config['redis']['port']}/{config['redis']['db']}")
            logger.info("Connected to Redis")
            self.initialized = True

    async def get(self, key):
        try:
            value = await self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Error loading from Redis: {e}")
            return None

    async def set(self, key, value, ex=None):
        try:
            value_json = json.dumps(value)
            await self.redis_client.set(key, value_json, ex=ex)
            logger.debug(f"Set {key} in Redis with expiration {ex}")
        except Exception as e:
            logger.error(f"Error saving to Redis: {e}")

    async def set_negative_cache(self, key, ex=300):
        try:
            await self.redis_client.set(key, "NEGATIVE_CACHE", ex=ex)
            logger.debug(f"Set negative cache for {key} with expiration {ex}")
        except Exception as e:
            logger.error(f"Error setting negative cache in Redis: {e}")

    async def is_negative_cache(self, key):
        try:
            value = await self.redis_client.get(key)
            is_negative = value == b"NEGATIVE_CACHE"
            logger.debug(f"{key} is {'in' if is_negative else 'not in'} negative cache")
            return is_negative
        except Exception as e:
            logger.error(f"Error checking negative cache in Redis: {e}")
            return False
