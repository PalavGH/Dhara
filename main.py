import os
import sys
import asyncio
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QLabel, QWidget, QListWidget, QListWidgetItem, QHBoxLayout, QScrollArea, QLineEdit, QMessageBox
from PySide6.QtGui import QPixmap
import qt_material
from qasync import QEventLoop, asyncSlot, QApplication as QAsyncApplication
from utils import (
    init_db,
    load_plugins,
    check_for_updates,
    search_plugin,
    prettify_date,
    download_image,
    scan_folder,
    check_plugins,
    download_plugin,
    get_best_match,
    normalize_name
)
from state import state  # Import state from state.py
from loguru import logger
import json

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paper Server Manager")
        self.setMinimumSize(800, 600)

        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)

        self.plugin_list = QListWidget()
        self.plugin_list.itemClicked.connect(self.display_plugin_info)

        self.check_updates_button = QPushButton("Check for Updates")
        self.check_updates_button.clicked.connect(self.check_updates)

        self.remove_plugin_button = QPushButton("Remove Plugin")
        self.remove_plugin_button.clicked.connect(self.remove_plugin)

        self.search_plugins_button = QPushButton("Search Plugins")
        self.search_plugins_button.clicked.connect(self.search_plugins)

        self.info_box = QScrollArea()
        self.info_box.setWidgetResizable(True)

        self.button_layout = QVBoxLayout()
        self.button_layout.addWidget(self.check_updates_button)
        self.button_layout.addWidget(self.remove_plugin_button)
        self.button_layout.addWidget(self.search_plugins_button)

        self.main_layout = QHBoxLayout()
        self.main_layout.addWidget(self.plugin_list)
        self.main_layout.addLayout(self.button_layout)

        self.layout.addLayout(self.main_layout)
        self.layout.addWidget(self.info_box)

        self.setCentralWidget(self.central_widget)

        # Set plugin folder from config before loading plugins
        state.set_plugin_folder(config['paths']['plugin_folder'])
        logger.info(f"Plugin folder set to: {state.get_plugin_folder()}")

        # Run the plugin loading in the background to ensure GUI loads immediately
        asyncio.run_coroutine_threadsafe(self.load_plugins(), asyncio.get_event_loop())

    async def load_plugins(self):
        try:
            found_plugins, not_found_plugins = await load_plugins()
            self.plugin_list.clear()
            for plugin in found_plugins:
                item = QListWidgetItem(self.plugin_list)
                widget = self.create_plugin_list_item(plugin)
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.UserRole, plugin)
                self.plugin_list.setItemWidget(item, widget)

            for plugin_name, plugin_version in not_found_plugins:
                item = QListWidgetItem(self.plugin_list)
                widget = self.create_not_found_plugin_list_item(plugin_name, plugin_version)
                item.setSizeHint(widget.sizeHint())
                self.plugin_list.setItemWidget(item, widget)
        except Exception as e:
            logger.error(f"Error loading plugins: {e}")

    @asyncSlot()
    async def check_updates(self):
        try:
            updates = await check_for_updates(state.found_plugins)
            for plugin_name, current_version, latest_version, latest_version_date in updates:
                item = QListWidgetItem(
                    f"Update available for {plugin_name}: {current_version} -> {latest_version} ({prettify_date(latest_version_date)})")
                self.plugin_list.addItem(item)
        except Exception as e:
            logger.error(f"Error checking updates: {e}")

    def display_plugin_info(self, item):
        plugin = item.data(Qt.UserRole)
        if plugin:
            plugin_name, date_modified, mod_name, project_id, plugin_data, image_filepath = plugin
            author = plugin_data.get('author', 'Unknown Author')
            description = plugin_data.get('description', 'No description available.')

            info_layout = QHBoxLayout()

            image_label = QLabel()
            if image_filepath and os.path.exists(image_filepath):
                pixmap = QPixmap(image_filepath)
                image_label.setPixmap(pixmap)
                image_label.setFixedSize(128, 128)
                image_label.setScaledContents(True)
            else:
                image_label.setText("No Image")

            text_layout = QVBoxLayout()
            text_title = QLabel(
                f"<h1><a href='{project_id}' style='color: white'>{plugin_name}</a></h1>")
            text_description = QLabel(
                f"<p><strong>Mod Name:</strong> {mod_name}</p><p><strong>Date Modified:</strong> {prettify_date(date_modified)}</p><p><strong>Author:</strong> {author}</p><p><strong>Description:</strong> {description}</p>")

            text_layout.addWidget(text_title)
            text_layout.addWidget(text_description)

            info_layout.addWidget(image_label)
            info_layout.addLayout(text_layout)

            info_widget = QWidget()
            info_widget.setLayout(info_layout)

            self.info_box.setWidget(info_widget)

    def remove_plugin(self):
        selected_items = self.plugin_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            plugin = item.data(Qt.UserRole)
            plugin_name = plugin[0]

            try:
                os.remove(os.path.join(state.get_plugin_folder(), f"{plugin_name}.jar"))
                logger.info(f"Plugin '{plugin_name}' removed successfully")
                self.plugin_list.takeItem(self.plugin_list.row(item))
            except Exception as e:
                logger.error(f"Error removing plugin: {e}")
                self.show_error_message("Error", f"An error occurred while removing plugin '{plugin_name}'")

    def search_plugins(self):
        search_dialog = SearchDialog(self)
        search_dialog.exec_()

    def create_plugin_list_item(self, plugin):
        widget = QWidget()
        layout = QHBoxLayout()

        label_name = QLabel(f"<a href='{plugin[3]}' style='color: white'>{plugin[2]}</a>")
        label_name.setOpenExternalLinks(True)
        label_last_updated = QLabel(f"Date Modified: {prettify_date(plugin[1])}")

        image_label = QLabel()
        image_filepath = plugin[5]
        if image_filepath and os.path.exists(image_filepath):
            pixmap = QPixmap(image_filepath)
            image_label.setPixmap(pixmap)
            image_label.setFixedSize(64, 64)
            image_label.setScaledContents(True)
        else:
            image_label.setText("No Image")

        layout.addWidget(image_label)
        layout.addWidget(label_name)
        layout.addWidget(label_last_updated)
        widget.setLayout(layout)

        return widget

    def create_not_found_plugin_list_item(self, plugin_name, plugin_version):
        widget = QWidget()
        layout = QHBoxLayout()

        label_name = QLabel(f"Name: {plugin_name}")
        label_version = QLabel(f"Version: {plugin_version}")
        label_not_found = QLabel("Not Found")

        layout.addWidget(label_name)
        layout.addWidget(label_version)
        layout.addWidget(label_not_found)
        widget.setLayout(layout)

        return widget

    def show_error_message(self, title, message):
        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Warning)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(message)
        error_dialog.exec_()


class SearchDialog(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Plugins")
        self.setMinimumSize(400, 200)

        central_widget = QWidget()
        layout = QVBoxLayout()

        self.search_field = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search)

        layout.addWidget(self.search_field)
        layout.addWidget(self.search_button)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    @asyncSlot()
    async def search(self):
        plugin_name = self.search_field.text()
        if plugin_name:
            results, _ = await search_plugin(plugin_name)
            if results:
                self.show_plugin_results(results)
            else:
                self.show_error_message("Error", f"No results found for '{plugin_name}'")

    def show_plugin_results(self, results):
        results_dialog = PluginResultsDialog(results, self)
        results_dialog.exec_()

    def show_error_message(self, title, message):
        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Warning)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(message)
        error_dialog.exec_()


class PluginResultsDialog(QMainWindow):
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Results")
        self.setMinimumSize(600, 400)

        central_widget = QWidget()
        layout = QVBoxLayout()

        self.plugin_list = QListWidget()
        self.plugin_list.itemDoubleClicked.connect(self.select_plugin)

        layout.addWidget(self.plugin_list)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.populate_results(results)

    def populate_results(self, results):
        for plugin in results:
            item = QListWidgetItem(plugin.get('title', plugin.get('name')))
            item.setData(Qt.UserRole, plugin)
            self.plugin_list.addItem(item)

    def select_plugin(self, item):
        plugin = item.data(Qt.UserRole)
        if plugin:
            state.set_selected_plugin(plugin)
            self.close()


if __name__ == "__main__":
    app = QAsyncApplication(sys.argv)
    qt_material.apply_stylesheet(app, theme='dark_lightgreen.xml')
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    init_db()
    main_window = MainWindow()
    main_window.show()

    with loop:
        loop.run_forever()
