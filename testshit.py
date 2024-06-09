import asyncio
import json
import os
import logging
from difflib import SequenceMatcher
from urllib.request import urlretrieve

import aiohttp
from aiohttp.client_exceptions import ClientError
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QPushButton, QLabel, QTextBrowser, QDialog, QHeaderView, QLineEdit,
    QMessageBox, QComboBox
)

# Configuration
API_KEY_MODRINTH = "mrp_OAGlIyM8TsArB075q7P9kMxMyFaqJEOqC00PcVWNG2CSZoWe3mhXylH0p4xt"
API_KEY_HANGAR = "c7996b7e-af7e-40e3-a472-c98ca28646d3"
SEARCH_URL_MODRINTH = "https://api.modrinth.com/v2/search"
PROJECT_URL_MODRINTH = "https://api.modrinth.com/v2/project"
VERSION_URL_MODRINTH = "https://api.modrinth.com/v2/version"
AUTH_URL_HANGAR = "https://hangar.papermc.io/api/v1/authenticate"
SEARCH_URL_HANGAR = "https://hangar.papermc.io/api/v1/projects"
CACHE_DIR = "cache"
PLUGIN_FOLDER = "C:\\Custom\\Sandal Wearers\\plugins"
USER_AGENT = "PluginManagerApp/1.0"

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create cache directory if it doesn't exist
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def normalize_name(name):
    return ''.join(e for e in name if e.isalnum()).lower()


def cache_plugin_data(plugin_id, data):
    with open(os.path.join(CACHE_DIR, f"{plugin_id}.json"), "w") as f:
        json.dump(data, f)


def load_cached_plugin_data(plugin_id):
    cache_path = os.path.join(CACHE_DIR, f"{plugin_id}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    return None


def cache_image(url, plugin_id):
    if not url:
        return None
    image_path = os.path.join(CACHE_DIR, f"{plugin_id}.png")
    if not os.path.exists(image_path):
        urlretrieve(url, image_path)
    return image_path


async def fetch(url, session, headers=None, params=None):
    try:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                logging.error(f"Error fetching {url}: {response.status}")
                return None
            return await response.json()
    except ClientError as e:
        logging.error(f"Client error fetching {url}: {e}")
        return None


async def authenticate_hangar():
    async with aiohttp.ClientSession() as session:
        headers = {"User-Agent": USER_AGENT}
        async with session.post(f"{AUTH_URL_HANGAR}?apiKey={API_KEY_HANGAR}", headers=headers) as response:
            if response.status != 200:
                logging.error(f"Error authenticating with Hangar API: {response.status}")
                return None
            data = await response.json()
            if "token" in data:
                return data["token"]
            else:
                logging.error("Failed to authenticate with Hangar API")
                return None


async def search_plugin_modrinth(plugin_name):
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {API_KEY_MODRINTH}",
            "User-Agent": USER_AGENT
        }
        params = {
            "query": plugin_name,
            "limit": 10,
            "facets": "[[\"categories:utility\"]]",
            "sort": "popularity"
        }
        return await fetch(SEARCH_URL_MODRINTH, session, headers=headers, params=params)


async def search_plugin_hangar(plugin_name, token):
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT
        }
        params = {
            "q": plugin_name,
            "limit": 10
        }
        return await fetch(SEARCH_URL_HANGAR, session, headers=headers, params=params)


async def search_plugin(plugin_name):
    modrinth_results = await search_plugin_modrinth(plugin_name)
    if modrinth_results and modrinth_results.get('total_hits', 0) > 0:
        return modrinth_results['hits']

    token = await authenticate_hangar()
    if token:
        hangar_results = await search_plugin_hangar(plugin_name, token)
        if hangar_results and hangar_results.get('pagination', {}).get('count', 0) > 0:
            return hangar_results['result']
    return []


async def fetch_version_details(version_id, session):
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    return await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)


def get_best_match(plugin_name, results):
    best_match = None
    highest_score = 0
    normalized_plugin_name = normalize_name(plugin_name)

    for plugin in results:
        normalized_result_name = normalize_name(plugin['title'])
        score = SequenceMatcher(None, normalized_plugin_name, normalized_result_name).ratio()
        if score > highest_score:
            highest_score = score
            best_match = plugin

    if best_match and highest_score > 0.8:
        return best_match
    else:
        return None


def scan_folder(folder_path):
    plugins = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".jar"):
            plugin_name = os.path.splitext(filename)[0]
            plugins.append((plugin_name, "Unknown Version"))
    return plugins


async def check_plugins(folder_path):
    plugins = scan_folder(folder_path)
    found_plugins = []
    not_found_plugins = []
    api_call_count = 0
    cache_hit_count = 0

    async with aiohttp.ClientSession() as session:
        tasks = []
        for plugin_name, plugin_version in plugins:
            tasks.append(search_plugin(plugin_name))

        results = await asyncio.gather(*tasks)

        for (plugin_name, plugin_version), result in zip(plugins, results):
            best_match = get_best_match(plugin_name, result)
            if best_match:
                plugin_data = load_cached_plugin_data(best_match['project_id'])
                if not plugin_data:
                    api_call_count += 1
                    plugin_data = best_match
                    cache_plugin_data(best_match['project_id'], plugin_data)
                else:
                    cache_hit_count += 1

                # Fetch the version details for each version
                version_details_tasks = [fetch_version_details(version_id, session) for version_id in plugin_data['versions']]
                version_details = await asyncio.gather(*version_details_tasks)

                # Ensure 'date_published' is present and get the latest version based on it
                valid_versions = [v for v in version_details if v and 'date_published' in v]
                latest_version = max(valid_versions, key=lambda x: x['date_published'])[
                    'version_number'] if valid_versions else "Unknown Version"

                found_plugins.append(
                    (plugin_name, latest_version, plugin_data['title'], plugin_data['project_id'], plugin_data))
            else:
                not_found_plugins.append((plugin_name, plugin_version))

    return found_plugins, not_found_plugins, api_call_count, cache_hit_count


async def fetch_versions(project_id):
    url = f"{PROJECT_URL_MODRINTH}/{project_id}/version"
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    async with aiohttp.ClientSession() as session:
        return await fetch(url, session, headers=headers)


async def download_plugin(version_id, destination):
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {API_KEY_MODRINTH}",
            "User-Agent": USER_AGENT
        }
        data = await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)
        if not data or 'files' not in data or not data['files']:
            logging.error(f"Error fetching version data for {version_id}")
            return

        download_url = data['files'][0]['url']
        async with session.get(download_url) as download_response:
            if download_response.status != 200:
                logging.error(f"Error downloading {download_url}: {download_response.status}")
                return
            with open(destination, 'wb') as f:
                while True:
                    chunk = await download_response.content.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)


async def check_for_updates(plugin_name, current_version, project_id):
    async with aiohttp.ClientSession() as session:
        url = f"{PROJECT_URL_MODRINTH}/{project_id}/version"
        headers = {
            "Authorization": f"Bearer {API_KEY_MODRINTH}",
            "User-Agent": USER_AGENT
        }
        data = await fetch(url, session, headers=headers)
        if not data:
            return None

        current_version_date = None
        latest_version = None
        latest_version_date = None

        for version in data:
            if version['version_number'] == current_version:
                current_version_date = version['date_published']
            if latest_version_date is None or version['date_published'] > latest_version_date:
                latest_version_date = version['date_published']
                latest_version = version['version_number']

        if current_version_date and latest_version_date > current_version_date:
            return latest_version
        else:
            return None


class PluginManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plugin Manager")
        self.setGeometry(100, 100, 1200, 800)

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)

        self.create_widgets()
        asyncio.run(self.load_plugins())

    def create_widgets(self):
        self.plugin_frame = QWidget()
        self.plugin_layout = QGridLayout(self.plugin_frame)
        self.plugin_layout.setColumnStretch(0, 1)
        self.plugin_layout.setColumnStretch(1, 1)
        self.plugin_layout.setColumnStretch(2, 1)
        self.plugin_layout.setColumnStretch(3, 1)

        self.plugin_list = QTreeWidget()
        self.plugin_list.setColumnCount(4)
        self.plugin_list.setHeaderLabels(["Name", "Version", "Found Mod", "Categories"])
        self.plugin_list.header().setSectionResizeMode(QHeaderView.Stretch)
        self.plugin_list.itemSelectionChanged.connect(self.show_plugin_info)
        self.plugin_list.setFont(QFont("Segoe UI", 12))
        self.plugin_list.setMinimumHeight(400)
        self.plugin_list.setIconSize(QSize(48, 48))
        self.plugin_list.setIndentation(20)
        self.plugin_layout.addWidget(self.plugin_list, 0, 0, 1, 4)

        self.control_frame = QWidget()
        self.control_layout = QVBoxLayout(self.control_frame)

        self.download_button = QPushButton("Download Plugins")
        self.download_button.setStyleSheet(self.button_style())
        self.download_button.setFont(QFont("Segoe UI", 10))
        self.download_button.clicked.connect(self.open_download_window)
        self.control_layout.addWidget(self.download_button)

        self.update_button = QPushButton("Check for Updates")
        self.update_button.setStyleSheet(self.button_style())
        self.update_button.setFont(QFont("Segoe UI", 10))
        self.update_button.clicked.connect(self.check_updates)
        self.control_layout.addWidget(self.update_button)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setStyleSheet(self.button_style())
        self.remove_button.setFont(QFont("Segoe UI", 10))
        self.remove_button.clicked.connect(self.remove_plugin)
        self.control_layout.addWidget(self.remove_button)

        self.plugin_layout.addWidget(self.control_frame, 0, 4, 1, 1, alignment=Qt.AlignRight)

        self.info_frame = QWidget()
        self.info_layout = QVBoxLayout(self.info_frame)

        self.plugin_image_label = QLabel()
        self.plugin_image_label.setFixedSize(128, 128)
        self.info_layout.addWidget(self.plugin_image_label, alignment=Qt.AlignLeft)

        self.plugin_info = QTextBrowser()
        self.plugin_info.setOpenExternalLinks(True)
        self.plugin_info.setFont(QFont("Segoe UI", 12))
        self.plugin_info.setMinimumHeight(300)
        self.info_layout.addWidget(self.plugin_info)

        self.plugin_layout.addWidget(self.info_frame, 1, 0, 1, 5)

        self.main_layout.addWidget(self.plugin_frame)

    def button_style(self):
        return """
        QPushButton {
            background-color: #0078d7;
            color: white;
            border: none;
            padding: 10px;
            border-radius: 5px;
        }
        QPushButton:hover {
            background-color: #005a9e;
        }
        """

    async def load_plugins(self):
        self.plugin_list.clear()
        found_plugins, not_found_plugins, api_call_count, cache_hit_count = await check_plugins(PLUGIN_FOLDER)
        for plugin_name, plugin_version, mod_name, mod_id, plugin_data in found_plugins:
            categories = ', '.join(plugin_data.get('categories', []))
            item = QTreeWidgetItem([plugin_name, plugin_version, mod_name, categories])
            if 'icon_url' in plugin_data:
                image_path = cache_image(plugin_data['icon_url'], mod_id)
                icon = QPixmap(image_path).scaled(48, 48, Qt.KeepAspectRatio)
                item.setIcon(0, icon)
            self.plugin_list.addTopLevelItem(item)

        for plugin_name, plugin_version in not_found_plugins:
            item = QTreeWidgetItem([plugin_name, plugin_version, "Not Found", ""])
            item.setForeground(1, Qt.red)
            item.setForeground(2, Qt.red)
            self.plugin_list.addTopLevelItem(item)

        logging.info(f"API calls: {api_call_count}")
        logging.info(f"Cache hits: {cache_hit_count}")

    def remove_plugin(self):
        selected_item = self.plugin_list.selectedItems()[0]
        plugin_name = selected_item.text(0)
        confirm = QMessageBox.question(self, "Confirm Remove", f"Are you sure you want to remove {plugin_name}?",
                                       QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            file_path = os.path.join(PLUGIN_FOLDER, f"{plugin_name}.jar")
            os.remove(file_path)
            asyncio.run(self.load_plugins())

    def open_download_window(self):
        self.download_window = QDialog(self)
        self.download_window.setWindowTitle("Download Plugins")
        self.download_window.setGeometry(150, 150, 800, 600)

        layout = QHBoxLayout(self.download_window)

        self.download_list = QTreeWidget()
        self.download_list.setColumnCount(2)
        self.download_list.setHeaderLabels(["Name", "Version"])
        self.download_list.setFont(QFont("Segoe UI", 12))
        self.download_list.setMinimumHeight(300)
        self.download_list.setMaximumWidth(300)
        self.download_list.setIconSize(QSize(48, 48))
        self.download_list.setIndentation(20)
        self.download_list.itemSelectionChanged.connect(self.show_download_info)
        layout.addWidget(self.download_list)

        self.info_frame = QWidget()
        self.info_layout = QVBoxLayout(self.info_frame)

        self.download_search_entry = QLineEdit()
        self.download_search_entry.setFont(QFont("Segoe UI", 12))
        self.info_layout.addWidget(self.download_search_entry)

        self.download_search_button = QPushButton("Search")
        self.download_search_button.setStyleSheet(self.button_style())
        self.download_search_button.clicked.connect(self.search_plugins_download)
        self.info_layout.addWidget(self.download_search_button)

        self.plugin_image_label_download = QLabel()
        self.plugin_image_label_download.setFixedSize(128, 128)
        self.info_layout.addWidget(self.plugin_image_label_download, alignment=Qt.AlignLeft)

        self.plugin_info_download = QTextBrowser()
        self.plugin_info_download.setOpenExternalLinks(True)
        self.plugin_info_download.setFont(QFont("Segoe UI", 12))
        self.plugin_info_download.setMinimumHeight(300)
        self.info_layout.addWidget(self.plugin_info_download)

        self.version_combo_box = QComboBox()
        self.version_combo_box.setFont(QFont("Segoe UI", 12))
        self.info_layout.addWidget(self.version_combo_box)

        self.download_button = QPushButton("Download Selected")
        self.download_button.setStyleSheet(self.button_style())
        self.download_button.clicked.connect(self.download_selected_plugins)
        self.info_layout.addWidget(self.download_button)

        layout.addWidget(self.info_frame)

        self.download_window.exec()

    def show_download_info(self):
        if not self.download_list.selectedItems():
            return
        selected_item = self.download_list.selectedItems()[0]
        plugin_name = selected_item.text(0)
        project_id = selected_item.data(0, Qt.UserRole)

        versions = asyncio.run(fetch_versions(project_id))
        self.version_combo_box.clear()
        for version in versions:
            self.version_combo_box.addItem(f"{version['version_number']} (MC: {', '.join(version['game_versions'])})",
                                           version['id'])

        plugin_data = load_cached_plugin_data(project_id)
        if plugin_data:
            description = plugin_data.get('description', 'No description available.')
            author = plugin_data.get('author', 'Unknown')
            mod_page_url = f"https://modrinth.com/mod/{project_id}"
            mod_page_link = f"<a href='{mod_page_url}'>Mod Page</a>"
            categories = ', '.join(plugin_data.get('categories', []))
            self.plugin_info_download.setHtml(
                f"<h3>{plugin_name}</h3><p>{description}</p><p>Made by: {author}</p><p>Categories: {categories}</p><p>{mod_page_link}</p>")

            if 'icon_url' in plugin_data:
                image_path = cache_image(plugin_data['icon_url'], project_id)
                if image_path:
                    pixmap = QPixmap(image_path).scaled(128, 128, Qt.KeepAspectRatio)
                    self.plugin_image_label_download.setPixmap(pixmap)

    def download_selected_plugins(self):
        selected_items = self.download_list.selectedItems()
        for item in selected_items:
            plugin_name = item.text(0)
            version_id = self.version_combo_box.currentData()
            destination = os.path.join(PLUGIN_FOLDER, f"{plugin_name}.jar")
            asyncio.run(download_plugin(version_id, destination))
        self.download_window.close()
        asyncio.run(self.load_plugins())

    def search_plugins_download(self):
        query = self.download_search_entry.text()
        if query:
            results = asyncio.run(search_plugin(query))
            self.download_list.clear()
            for result in results:
                item = QTreeWidgetItem([result['title'], ""])
                item.setData(0, Qt.UserRole, result['project_id'])
                if 'icon_url' in result:
                    image_path = cache_image(result['icon_url'], result['project_id'])
                    if image_path:
                        icon = QPixmap(image_path).scaled(48, 48, Qt.KeepAspectRatio)
                        item.setIcon(0, icon)
                self.download_list.addTopLevelItem(item)

    def check_updates(self):
        for index in range(self.plugin_list.topLevelItemCount()):
            item = self.plugin_list.topLevelItem(index)
            plugin_name, plugin_version, mod_name = item.text(0), item.text(1), item.text(2)
            if mod_name != "Not Found":
                plugin_data = load_cached_plugin_data(mod_name)
                if plugin_data:
                    project_id = plugin_data['project_id']
                    current_version = plugin_version
                    latest_version = asyncio.run(check_for_updates(plugin_name, current_version, project_id))
                    if latest_version:
                        logging.info(f"Update available for {plugin_name}: {current_version} -> {latest_version}")

    def show_plugin_info(self):
        if not self.plugin_list.selectedItems():
            return
        selected_item = self.plugin_list.selectedItems()[0]
        plugin_name, plugin_version, mod_name, categories = selected_item.text(0), selected_item.text(
            1), selected_item.text(2), selected_item.text(3)
        results = asyncio.run(search_plugin(plugin_name))
        best_match = get_best_match(plugin_name, results)
        if best_match:
            project_id = best_match['project_id']
            plugin_data = load_cached_plugin_data(project_id)
            if not plugin_data:
                plugin_data = best_match
                cache_plugin_data(project_id, plugin_data)

            description = plugin_data.get('description', 'No description available.')
            author = plugin_data.get('author', 'Unknown')
            mod_page_url = f"https://modrinth.com/mod/{project_id}"
            mod_page_link = f"<a href='{mod_page_url}'>Mod Page</a>"
            self.plugin_info.setHtml(
                f"<h3>{mod_name}</h3><p>{description}</p><p>Made by: {author}</p><p>Categories: {categories}</p><p>{mod_page_link}</p>")

            if 'icon_url' in plugin_data:
                image_path = cache_image(plugin_data['icon_url'], project_id)
                if image_path:
                    pixmap = QPixmap(image_path).scaled(128, 128, Qt.KeepAspectRatio)
                    self.plugin_image_label.setPixmap(pixmap)


if __name__ == "__main__":
    app = QApplication([])
    window = PluginManagerApp()
    window.show()
    app.exec()
