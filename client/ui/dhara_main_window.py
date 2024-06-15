import base64
import os
import traceback
import asyncio

from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem, QScrollArea, QLabel, QHBoxLayout, QWidget, QMessageBox
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from loguru import logger

from client.plugins.dhara_plugin_manager import DharaPluginManager
from client.plugins.dhara_plugin_list import DharaPluginList
from client.ui.dhara_worker import DharaWorker
from client.ui.components.dhara_search_dialog import DharaSearchDialog
from utils.dhara_helper import prettify_date

class DharaMainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.plugin_manager = DharaPluginManager()
        self.plugin_list = DharaPluginList()
        self.config = config

        self.setWindowTitle("Dhara Plugin Manager")
        self.setMinimumSize(800, 600)

        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)

        self.plugin_list_widget = QListWidget()
        self.plugin_list_widget.itemClicked.connect(self.display_plugin_info)

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
        self.main_layout.addWidget(self.plugin_list_widget)
        self.main_layout.addLayout(self.button_layout)

        self.layout.addLayout(self.main_layout)
        self.layout.addWidget(self.info_box)

        self.setCentralWidget(self.central_widget)

        self.start_loading_plugins()

    def start_loading_plugins(self):
        plugin_folder_path = self.config['paths']['plugin_folder']
        self.thread = DharaWorker(self.plugin_manager, plugin_folder_path)
        self.thread.plugin_found.connect(self.add_plugin_to_list)
        self.thread.finished.connect(self.on_plugins_loaded)
        logger.debug("Starting worker thread for loading plugins")
        self.thread.start()

    def add_plugin_to_list(self, plugin):
        plugin_name, plugin_data = plugin
        item = QListWidgetItem()
        widget = self.create_plugin_list_item(plugin)
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, plugin)
        self.plugin_list_widget.addItem(item)
        self.plugin_list_widget.setItemWidget(item, widget)

    def on_plugins_loaded(self, found_plugins, not_found_plugins):
        logger.debug("Worker thread finished loading plugins")
        try:
            for plugin_name, plugin_version in not_found_plugins:
                item = QListWidgetItem()
                widget = self.create_not_found_plugin_list_item(plugin_name, plugin_version)
                item.setSizeHint(widget.sizeHint())
                self.plugin_list_widget.addItem(item)
                self.plugin_list_widget.setItemWidget(item, widget)
        except Exception as e:
            logger.exception(f"Error loading plugins: {e}")

    def check_updates(self):
        logger.debug("Checking for updates")
        # Implement the logic to check for updates
        pass

    def display_plugin_info(self, item):
        plugin = item.data(Qt.ItemDataRole.UserRole)
        if plugin:
            logger.debug(f"Displaying info for plugin: {plugin}")
            plugin_name, plugin_data = plugin
            title = plugin_data.get('name', 'Unknown Title')
            url = plugin_data.get('url', '#')
            date_modified = plugin_data.get('last_updated', 'Unknown Date')
            author = plugin_data.get('author', 'Unknown Author')
            description = plugin_data.get('description', 'No description available.')
            icon_data = plugin_data.get('icon_data', '')

            info_layout = QHBoxLayout()

            image_label = QLabel()
            if icon_data:
                pixmap = QPixmap()
                pixmap.loadFromData(base64.b64decode(icon_data))
                image_label.setPixmap(pixmap)
                image_label.setFixedSize(128, 128)
                image_label.setScaledContents(True)
            else:
                image_label.setText("No Image")

            text_layout = QVBoxLayout()
            text_title = QLabel(f"<h1><a href='{url}' style='color: black'>{title}</a></h1>")
            text_description = QLabel(f"<p><strong>Date Modified:</strong> {prettify_date(date_modified)}</p><p><strong>Author:</strong> {author}</p><p><strong>Description:</strong> {description}</p>")

            text_layout.addWidget(text_title)
            text_layout.addWidget(text_description)

            info_layout.addWidget(image_label)
            info_layout.addLayout(text_layout)

            info_widget = QWidget()
            info_widget.setLayout(info_layout)

            self.info_box.setWidget(info_widget)

    def remove_plugin(self):
        selected_items = self.plugin_list_widget.selectedItems()
        if selected_items:
            item = selected_items[0]
            plugin = item.data(Qt.ItemDataRole.UserRole)
            plugin_name = plugin[0]

            try:
                os.remove(os.path.join(self.config['paths']['plugin_folder'], f"{plugin_name}.jar"))
                self.plugin_list_widget.takeItem(self.plugin_list_widget.row(item))
                logger.debug(f"Removed plugin {plugin_name}")
            except Exception as e:
                logger.exception(f"Error removing plugin {plugin_name}: {e}")
                self.show_error_message("Error", f"An error occurred while removing plugin '{plugin_name}'")

    def search_plugins(self):
        logger.debug("Opening search dialog")
        search_dialog = DharaSearchDialog(self)
        search_dialog.exec()

    def create_plugin_list_item(self, plugin):
        widget = QWidget()
        layout = QHBoxLayout()
        plugin_name, plugin_data = plugin

        label_name = QLabel(f"<a href='{plugin_data['url']}' style='color: black'>{plugin_data['name']}</a>")
        label_name.setOpenExternalLinks(True)
        label_last_updated = QLabel(f"Date Modified: {prettify_date(plugin_data['last_updated'])}")

        image_label = QLabel()
        icon_data = plugin_data.get('icon_data', None)
        if icon_data:
            pixmap = QPixmap()
            pixmap.loadFromData(base64.b64decode(icon_data))
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
        error_dialog.setIcon(QMessageBox.Icon.Warning)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(message)
        error_dialog.exec()
