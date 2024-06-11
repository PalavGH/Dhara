import asyncio
import json
import os
import logging
import sys
from difflib import SequenceMatcher
from contextlib import asynccontextmanager
import httpx
from httpx import HTTPStatusError
from cachetools import TTLCache
import colorlog
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QLabel, QWidget, QListWidget, QListWidgetItem, QHBoxLayout, QTextEdit
from PySide6.QtGui import QPixmap
import qt_material
from datetime import datetime

# Configuration
API_KEY_MODRINTH = os.environ.get('MODAPI')
API_KEY_HANGAR = os.environ.get('HANGERAPI')
SEARCH_URL_MODRINTH = "https://api.modrinth.com/v2/search"
PROJECT_URL_MODRINTH = "https://api.modrinth.com/v2/project"
VERSION_URL_MODRINTH = "https://api.modrinth.com/v2/version"
AUTH_URL_HANGAR = "https://hangar.papermc.io/api/v1/authenticate"
SEARCH_URL_HANGAR = "https://hangar.papermc.io/api/v1/projects"
CACHE_DIR = "cache"
PLUGIN_FOLDER = "C:\\Custom\\Sandal Wearers\\plugins"
USER_AGENT = "PluginManagerApp/1.0"

# Set up logging with colors using colorlog
log_format = "%(log_color)s%(asctime)s - %(levelname)s - %(message)s"
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(log_format))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class State:
    def __init__(self):
        self.found_plugins = []
        self.not_found_plugins = []
        self.loading = False
        self.error_message = ""
        self.update_status = []
        self.api_keys = {
            "modrinth": API_KEY_MODRINTH,
            "hangar": API_KEY_HANGAR
        }
        self.plugin_folder = PLUGIN_FOLDER
        self.selected_plugin = None

    def set_loading(self, is_loading):
        self.loading = is_loading

    def set_error(self, message):
        self.error_message = message

    def clear_error(self):
        self.error_message = ""

    def add_found_plugin(self, plugin, source):
        self.found_plugins.append((plugin, source))

    def add_not_found_plugin(self, plugin):
        self.not_found_plugins.append(plugin)

    def clear_plugins(self):
        self.found_plugins = []
        self.not_found_plugins = []

    def set_update_status(self, updates):
        self.update_status = updates

    def clear_update_status(self):
        self.update_status = []

    def set_api_key(self, platform, key):
        self.api_keys[platform] = key.strip()

    def get_api_key(self, platform):
        return self.api_keys.get(platform)

    def set_plugin_folder(self, folder_path):
        self.plugin_folder = folder_path

    def get_plugin_folder(self):
        return self.plugin_folder

    def set_selected_plugin(self, plugin):
        self.selected_plugin = plugin

    def get_selected_plugin(self):
        return self.selected_plugin


state = State()


def normalize_name(name):
    return ''.join(e for e in name if e.isalnum()).lower()


cache = TTLCache(maxsize=100, ttl=3600)


def cache_plugin_data(plugin_name, data, source):
    cache_key = f"{source}_{plugin_name}"
    cache[cache_key] = data
    cache_filepath = os.path.join(CACHE_DIR, cache_key + '.json')
    with open(cache_filepath, 'w') as f:
        json.dump(data, f)


def load_cached_plugin_data(plugin_name, source):
    cache_key = f"{source}_{plugin_name}"
    cache_filepath = os.path.join(CACHE_DIR, cache_key + '.json')
    if cache_key in cache:
        return cache[cache_key]
    elif os.path.exists(cache_filepath):
        with open(cache_filepath, 'r') as f:
            data = json.load(f)
            cache[cache_key] = data
            return data
    return None


@asynccontextmanager
async def http_session():
    async with httpx.AsyncClient() as session:
        yield session


async def fetch(url, session, headers=None, params=None):
    try:
        logger.debug(f"Fetching URL: {url} with headers: {headers} and params: {params}")
        response = await session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return None


async def authenticate_hangar():
    async with http_session() as session:
        headers = {"User-Agent": USER_AGENT}
        api_key = state.get_api_key("hangar")
        try:
            response = await session.post(f"{AUTH_URL_HANGAR}?apiKey={api_key}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("token")
        except HTTPStatusError as e:
            logger.error(f"Error authenticating with Hangar API: {e.response.status_code} - {e.response.text}")
            return None


async def search_plugin_modrinth(plugin_name):
    async with http_session() as session:
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
    async with http_session() as session:
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
    logger.info(f"Modrinth results: {modrinth_results}")
    if modrinth_results and modrinth_results.get('total_hits', 0) > 0:
        return modrinth_results['hits'], "modrinth"

    token = await authenticate_hangar()
    if token:
        hangar_results = await search_plugin_hangar(plugin_name, token)
        logger.info(f"Hangar results: {hangar_results}")
        if hangar_results and hangar_results.get('pagination', {}).get('count', 0) > 0:
            return hangar_results['result'], "hangar"
    return [], None


async def fetch_version_details(version_id, session):
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    return await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)


async def download_image(url, filepath):
    async with http_session() as session:
        async with session.stream("GET", url) as response:
            response.raise_for_status()
            with open(filepath, 'wb') as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)


def get_best_match(plugin_name, results, source):
    best_match = None
    highest_score = 0
    normalized_plugin_name = normalize_name(plugin_name)

    for plugin in results:
        if source == "modrinth":
            normalized_result_name = normalize_name(plugin['title'])
        elif source == "hangar":
            normalized_result_name = normalize_name(plugin['name'])

        score = SequenceMatcher(None, normalized_plugin_name, normalized_result_name).ratio()
        if score > highest_score:
            highest_score = score
            best_match = plugin

    return best_match if highest_score > 0.8 else None


def scan_folder(folder_path):
    plugins = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".jar"):
            plugin_name = os.path.splitext(filename)[0]
            plugins.append((plugin_name, "Unknown Version"))
    return plugins


async def check_plugins(folder_path):
    plugins = scan_folder(folder_path)
    state.clear_plugins()

    async with http_session() as session:
        tasks = [search_plugin(plugin_name) for plugin_name, _ in plugins]
        results_with_sources = await asyncio.gather(*tasks)

        for (plugin_name, plugin_version), (result, source) in zip(plugins, results_with_sources):
            best_match = get_best_match(plugin_name, result, source)
            if best_match:
                plugin_data = load_cached_plugin_data(plugin_name, source)
                if not plugin_data:
                    plugin_data = best_match
                    cache_plugin_data(plugin_name, plugin_data, source)

                if source == "modrinth":
                    if 'versions' in plugin_data:
                        valid_versions = plugin_data['versions']
                    else:
                        version_details_tasks = [fetch_version_details(version_id, session) for version_id in
                                                 plugin_data['versions']]
                        version_details = await asyncio.gather(*version_details_tasks)
                        valid_versions = [v['version_number'] for v in version_details if v and 'version_number' in v]

                        plugin_data['versions'] = valid_versions
                        cache_plugin_data(plugin_name, plugin_data, source)
                    date_modified = plugin_data['date_modified'] if 'date_modified' in plugin_data else "Unknown Date"
                    icon_url = plugin_data.get('icon_url', None)
                else:
                    date_modified = best_match.get('lastUpdated', "Unknown Date")
                    icon_url = best_match.get('avatarUrl', None)

                if icon_url:
                    file_ext = os.path.splitext(icon_url)[-1].split('?')[0]
                    image_filepath = os.path.join(CACHE_DIR, f"{plugin_name}{file_ext}")
                    if not os.path.exists(image_filepath):
                        await download_image(icon_url, image_filepath)
                else:
                    image_filepath = None

                state.add_found_plugin((plugin_name, date_modified,
                                        plugin_data['title'] if source == "modrinth" else plugin_data['name'],
                                        plugin_data['project_id'] if source == "modrinth" else plugin_data['namespace'][
                                            'slug'], plugin_data, image_filepath), source)
            else:
                state.add_not_found_plugin((plugin_name, plugin_version))

    return state.found_plugins, state.not_found_plugins


async def fetch_versions(project_id):
    url = f"{PROJECT_URL_MODRINTH}/{project_id}/version"
    headers = {
        "Authorization": f"Bearer {API_KEY_MODRINTH}",
        "User-Agent": USER_AGENT
    }
    async with http_session() as session:
        return await fetch(url, session, headers=headers)


async def download_plugin(version_id, destination):
    async with http_session() as session:
        headers = {
            "Authorization": f"Bearer {API_KEY_MODRINTH}",
            "User-Agent": USER_AGENT
        }
        data = await fetch(f"{VERSION_URL_MODRINTH}/{version_id}", session, headers=headers)
        if not data or 'files' not in data or not data['files']:
            logger.error(f"Error fetching version data for {version_id}")
            return

        download_url = data['files'][0]['url']
        async with session.stream("GET", download_url) as download_response:
            download_response.raise_for_status()
            with open(destination, 'wb') as f:
                async for chunk in download_response.aiter_bytes():
                    f.write(chunk)


async def check_for_updates(found_plugins):
    updates = []
    for (plugin_name, current_version, mod_name, project_id, plugin_data, _), source in found_plugins:
        if source == "modrinth":
            if 'versions' not in plugin_data or not plugin_data['versions']:
                continue

            current_version_date = None
            latest_version = None
            latest_version_date = None

            for version in plugin_data['versions']:
                if version == current_version:
                    current_version_date = version['date_published']
                if latest_version_date is None or version['date_published'] > latest_version_date:
                    latest_version_date = version['date_published']
                    latest_version = version

            if current_version_date and latest_version_date > current_version_date:
                updates.append((plugin_name, current_version, latest_version['version_number'], latest_version_date))
        else:
            latest_version = plugin_data.get('lastUpdated', "Unknown Date")
            if latest_version != current_version:
                updates.append((plugin_name, current_version, latest_version, latest_version))

    return updates


async def load_plugins():
    state.set_loading(True)
    found_plugins, not_found_plugins = await check_plugins(state.get_plugin_folder())
    state.set_loading(False)
    return found_plugins, not_found_plugins


def update_plugin(plugin):
    logger.info(f"Updating plugin: {plugin.get('title', plugin.get('name'))}")
    asyncio.create_task(download_plugin(plugin['versions'][0], f"{state.get_plugin_folder()}/{plugin['title']}.jar"))


def create_plugin_list_item(plugin, source):
    widget = QWidget()
    layout = QHBoxLayout()

    label_name = QLabel(f"<a href='https://modrinth.com/plugin/{plugin[3]}' style='color: white'>{plugin[2]}</a>")
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


def create_not_found_plugin_list_item(plugin_name, plugin_version):
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


def prettify_date(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except ValueError:
        return date_str


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

        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)

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

        asyncio.run(self.load_plugins())

    async def load_plugins(self):
        found_plugins, not_found_plugins = await load_plugins()
        self.plugin_list.clear()
        for plugin, source in found_plugins:
            item = QListWidgetItem(self.plugin_list)
            widget = create_plugin_list_item(plugin, source)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, plugin)
            self.plugin_list.setItemWidget(item, widget)

        for plugin_name, plugin_version in not_found_plugins:
            item = QListWidgetItem(self.plugin_list)
            widget = create_not_found_plugin_list_item(plugin_name, plugin_version)
            item.setSizeHint(widget.sizeHint())
            self.plugin_list.setItemWidget(item, widget)

    def display_plugin_info(self, item):
        plugin = item.data(Qt.UserRole)
        if plugin:
            plugin_name, date_modified, mod_name, project_id, plugin_data, image_filepath = plugin
            author = plugin_data.get('author', 'Unknown Author')
            description = plugin_data.get('description', 'No description available.')

            info_text = (
                f"<div style='color: white; display: flex; align-items: flex-start;'>"
                f"<img src='{image_filepath}' width='128' style='margin-right: 20px;'>"
                f"<div>"
                f"<h1><a href='https://modrinth.com/plugin/{project_id}' style='color: white'>{plugin_name}</a></h1>"
                f"<p><strong>Mod Name:</strong> {mod_name}</p>"
                f"<p><strong>Date Modified:</strong> {prettify_date(date_modified)}</p>"
                f"<p><strong>Author:</strong> {author}</p>"
                f"<p><strong>Description:</strong> {description}</p>"
                f"</div>"
                f"</div>"
            )

            self.info_box.setHtml(info_text)

    def check_updates(self):
        async def check():
            updates = await check_for_updates(state.found_plugins)
            for plugin_name, current_version, latest_version, latest_version_date in updates:
                item = QListWidgetItem(f"Update available for {plugin_name}: {current_version} -> {latest_version} ({prettify_date(latest_version_date)})")
                self.plugin_list.addItem(item)

        asyncio.run(check())

    def remove_plugin(self):
        # Implement plugin removal logic
        pass

    def search_plugins(self):
        # Implement plugin search logic
        pass


def main():
    app = QApplication(sys.argv)
    qt_material.apply_stylesheet(app, theme='dark_teal.xml')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
