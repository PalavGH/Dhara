import asyncio
import os

from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger
from client.plugins.dhara_plugin_manager import DharaPluginManager

class DharaWorker(QThread):
    plugin_found = pyqtSignal(tuple)
    finished = pyqtSignal(list, list)

    def __init__(self, plugin_manager: DharaPluginManager, folder_path: str):
        super().__init__()
        self.plugin_manager = plugin_manager
        self.folder_path = folder_path

    def run(self):
        logger.debug("Starting worker thread")
        asyncio.run(self._check_plugins())

    async def _check_plugins(self):
        found_plugins = []
        not_found_plugins = []
        try:
            plugin_files = [f for f in os.listdir(self.folder_path) if f.endswith(".jar")]

            tasks = [self.plugin_manager.search_plugin(f[:-4]) for f in plugin_files]
            results = await asyncio.gather(*tasks)

            for plugin_file, plugin_data in zip(plugin_files, results):
                plugin_name = plugin_file[:-4]
                if plugin_data:
                    found_plugins.append((plugin_name, plugin_data))
                    self.plugin_found.emit((plugin_name, plugin_data))
                else:
                    not_found_plugins.append((plugin_name, "unknown_version"))

        except Exception as e:
            logger.exception(f"Error in worker thread: {e}")

        self.finished.emit(found_plugins, not_found_plugins)
        logger.debug("Worker thread finished")
