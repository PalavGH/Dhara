import asyncio
from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger
from client.plugins.dhara_plugin_manager import DharaPluginManager

class DharaWorker(QThread):
    finished = pyqtSignal(list, list)

    def __init__(self, plugin_manager: DharaPluginManager, folder_path: str):
        super().__init__()
        self.plugin_manager = plugin_manager
        self.folder_path = folder_path

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            found_plugins, not_found_plugins = loop.run_until_complete(self.plugin_manager.check_plugins(self.folder_path))
            self.finished.emit(found_plugins, not_found_plugins)
        except Exception as e:
            logger.error(f"Error in worker thread: {e}")
            self.finished.emit([], [])
        finally:
            loop.close()
