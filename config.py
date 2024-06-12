import json
from loguru import logger

class Config:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.config = self.load_config()
            self.initialized = True

    def load_config(self):
        try:
            with open('config.json', 'r') as file:
                config = json.load(file)
                logger.info("Configuration loaded")
                return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return {}

config = Config().config
