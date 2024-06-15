import redis.asyncio as aioredis
import json
from loguru import logger
from config.dhara_settings import load_config
from utils.dhara_helper import normalize_name

config = load_config('config/server_config.json')

class DharaRedisCache:
    def __init__(self):
        redis_config = config['redis']
        self.client = aioredis.from_url(f"redis://{redis_config['host']}:{redis_config['port']}/{redis_config['db']}")
        logger.info("Connected to Redis")

    async def set(self, key, value, ex=None):
        try:
            value_json = json.dumps(value)
            await self.client.set(normalize_name(key), value_json, ex=ex)
            logger.debug(f"Set {key} in Redis with expiration {ex}")
        except Exception as e:
            logger.exception(f"Error setting {key} in Redis: {e}")

    async def get(self, key):
        try:
            value = await self.client.get(normalize_name(key))
            if value:
                data = json.loads(value)
                logger.debug(f"Retrieved {key} from Redis")
                return data
            logger.warning(f"{key} not found in Redis")
            return None
        except Exception as e:
            logger.exception(f"Error retrieving {key} from Redis: {e}")
            return None

    async def set_negative_cache(self, key, ex=300):
        try:
            await self.client.set(normalize_name(key), "NEGATIVE_CACHE", ex=ex)
            logger.debug(f"Set negative cache for {key} with expiration {ex}")
        except Exception as e:
            logger.exception(f"Error setting negative cache for {key} in Redis: {e}")

    async def is_negative_cache(self, key):
        try:
            value = await self.client.get(normalize_name(key))
            is_negative = value == b"NEGATIVE_CACHE"
            logger.debug(f"{key} is {'in' if is_negative else 'not in'} negative cache")
            return is_negative
        except Exception as e:
            logger.exception(f"Error checking negative cache for {key} in Redis: {e}")
            return False
