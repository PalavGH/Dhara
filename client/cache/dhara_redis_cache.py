import redis
import json
from loguru import logger
from config.dhara_settings import load_config

config = load_config('config/client_config.json')

class DharaRedisCache:
    def __init__(self):
        redis_config = config['redis']
        self.client = redis.StrictRedis(
            host=redis_config['host'],
            port=redis_config['port'],
            db=redis_config['db']
        )
        logger.info("Connected to Redis")

    async def set(self, key, value, ex=None):
        try:
            value_json = json.dumps(value)
            self.client.set(key, value_json, ex=ex)
            logger.debug(f"Set {key} in Redis with expiration {ex}")
        except Exception as e:
            logger.error(f"Error saving to Redis: {e}")

    async def get(self, key):
        try:
            value = self.client.get(key)
            if value:
                data = json.loads(value)
                logger.debug(f"Retrieved {key} from Redis")
                return data
            logger.warning(f"{key} not found in Redis")
            return None
        except Exception as e:
            logger.error(f"Error retrieving from Redis: {e}")
            return None

    async def set_negative_cache(self, key, ex=300):
        try:
            self.client.set(key, "NEGATIVE_CACHE", ex=ex)
            logger.debug(f"Set negative cache for {key} with expiration {ex}")
        except Exception as e:
            logger.error(f"Error setting negative cache in Redis: {e}")

    async def is_negative_cache(self, key):
        try:
            value = self.client.get(key)
            is_negative = value == b"NEGATIVE_CACHE"
            logger.debug(f"{key} is {'in' if is_negative else 'not in'} negative cache")
            return is_negative
        except Exception as e:
            logger.error(f"Error checking negative cache in Redis: {e}")
            return False
