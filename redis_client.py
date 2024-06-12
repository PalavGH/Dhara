import redis
from loguru import logger


class RedisClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, host='localhost', port=6379, db=0):
        if not hasattr(self, 'initialized'):
            self.redis_client = redis.StrictRedis(host=host, port=port, db=db)
            logger.info("Connected to Redis")
            self.initialized = True

    def set(self, key, value):
        try:
            self.redis_client.set(key, value)
        except Exception as e:
            logger.error(f"Error saving to Redis: {e}")

    def get(self, key):
        try:
            value = self.redis_client.get(key)
            return value if value else None
        except Exception as e:
            logger.error(f"Error loading from Redis: {e}")
            return None

    def delete(self, key):
        try:
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"Error deleting from Redis: {e}")

    def clear(self):
        try:
            self.redis_client.flushdb()
        except Exception as e:
            logger.error(f"Error clearing Redis database: {e}")
