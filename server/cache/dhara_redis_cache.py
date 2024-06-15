import redis.asyncio as aioredis
from loguru import logger
from config.dhara_settings import load_config
import orjson
from utils.dhara_helper import normalize_name

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
            normalized_key = normalize_name(key)
            value = await self.redis_client.get(normalized_key)
            if value:
                logger.debug(f"Retrieved {normalized_key} from Redis")
                if value == b"NEGATIVE_CACHE":
                    logger.debug(f"{normalized_key} is in negative cache")
                    return "NEGATIVE_CACHE"
                return orjson.loads(value)
            logger.warning(f"{normalized_key} not found in Redis")
            return None
        except orjson.JSONDecodeError as e:
            logger.exception(f"JSON decode error loading {normalized_key} from Redis: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error loading {normalized_key} from Redis: {e}")
            return None

    async def set(self, key, value, ex=None):
        try:
            normalized_key = normalize_name(key)
            value_json = orjson.dumps(value)
            await self.redis_client.set(normalized_key, value_json, ex=ex)
            logger.debug(f"Set {normalized_key} in Redis with expiration {ex}")
        except Exception as e:
            logger.exception(f"Error saving {normalized_key} to Redis: {e}")

    async def set_negative_cache(self, key, ex=300):
        try:
            normalized_key = normalize_name(key)
            await self.redis_client.set(normalized_key, "NEGATIVE_CACHE", ex=ex)
            logger.debug(f"Set negative cache for {normalized_key} with expiration {ex}")
        except Exception as e:
            logger.exception(f"Error setting negative cache for {normalized_key} in Redis: {e}")

    async def is_negative_cache(self, key):
        try:
            normalized_key = normalize_name(key)
            value = await self.redis_client.get(normalized_key)
            is_negative = value == b"NEGATIVE_CACHE"
            logger.debug(f"{normalized_key} is {'in' if is_negative else 'not in'} negative cache")
            return is_negative
        except Exception as e:
            logger.exception(f"Error checking negative cache for {normalized_key} in Redis: {e}")
            return False
