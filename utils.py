import asyncio
import os
import json
import traceback
from datetime import datetime
from difflib import SequenceMatcher
from contextlib import asynccontextmanager
from loguru import logger
import httpx
from httpx import HTTPStatusError
from state import state  # Import state from state.py
import redis
import flatbuffers
from PluginManager import Plugin

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Initialize Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Load API keys from Redis
API_KEY_MODRINTH = state.get_api_key('modrinth') or os.environ.get(config['api_keys']['modrinth'])
API_KEY_HANGAR = state.get_api_key('hangar') or os.environ.get(config['api_keys']['hangar'])

# Load other configurations
SEARCH_URL_MODRINTH = config['urls']['search_modrinth']
AUTH_URL_HANGAR = config['urls']['auth_hangar']
SEARCH_URL_HANGAR = config['urls']['search_hangar']
CACHE_DIR = config['paths']['cache_dir']
PLUGIN_FOLDER = config['paths']['plugin_folder']
USER_AGENT = config['user_agent']

logger.add("plugin_manager.log", rotation="10 MB")

def normalize_name(name):
    return ''.join(e for e in name if e.isalpha()).lower()

@asynccontextmanager
async def http_session():
    async with httpx.AsyncClient() as session:
        try:
            yield session
        finally:
            await session.aclose()

def init_db():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def serialize_plugin(plugin_data):
    builder = flatbuffers.Builder(1024)

    name = builder.CreateString(plugin_data['name'])
    title = builder.CreateString(plugin_data['title'])
    description = builder.CreateString(plugin_data['description'])
    author = builder.CreateString(plugin_data['author'])
    date_created = builder.CreateString(plugin_data['date_created'])
    date_modified = builder.CreateString(plugin_data['date_modified'])
    icon_url = builder.CreateString(plugin_data['icon_url'])
    category = builder.CreateString(plugin_data['category'])
    url = builder.CreateString(plugin_data['url'])
    source = builder.CreateString(plugin_data['source'])

    Plugin.PluginStart(builder)
    Plugin.PluginAddName(builder, name)
    Plugin.PluginAddTitle(builder, title)
    Plugin.PluginAddDescription(builder, description)
    Plugin.PluginAddAuthor(builder, author)
    Plugin.PluginAddDateCreated(builder, date_created)
    Plugin.PluginAddDateModified(builder, date_modified)
    Plugin.PluginAddIconUrl(builder, icon_url)
    Plugin.PluginAddCategory(builder, category)
    Plugin.PluginAddDownloads(builder, plugin_data['downloads'])
    Plugin.PluginAddFollows(builder, plugin_data['follows'])
    Plugin.PluginAddUrl(builder, url)
    Plugin.PluginAddSource(builder, source)
    plugin = Plugin.PluginEnd(builder)
    builder.Finish(plugin)

    return bytes(builder.Output())

def deserialize_plugin(data):
    plugin = Plugin.Plugin.GetRootAsPlugin(data, 0)
    return {
        "name": plugin.Name().decode('utf-8'),
        "title": plugin.Title().decode('utf-8'),
        "description": plugin.Description().decode('utf-8'),
        "author": plugin.Author().decode('utf-8'),
        "date_created": plugin.DateCreated().decode('utf-8'),
        "date_modified": plugin.DateModified().decode('utf-8'),
        "icon_url": plugin.IconUrl().decode('utf-8'),
        "category": plugin.Category().decode('utf-8'),
        "downloads": plugin.Downloads(),
        "follows": plugin.Follows(),
        "url": plugin.Url().decode('utf-8'),
        "source": plugin.Source().decode('utf-8')
    }

async def insert_or_update_plugin(plugin_data):
    try:
        key = f"plugin:{plugin_data['name']}"
        serialized_data = serialize_plugin(plugin_data)
        redis_client.set(key, serialized_data)
    except Exception as e:
        logger.error(f"Error inserting or updating plugin data: {e}")

async def get_plugin_from_db(plugin_name):
    try:
        key = f"plugin:{plugin_name}"
        plugin_data = redis_client.get(key)
        if plugin_data:
            return deserialize_plugin(plugin_data)
        return None
    except Exception as e:
        logger.error(f"Error fetching plugin from database: {e}")
        return None

async def fetch(url, session, headers=None, params=None):
    try:
        logger.debug(f"Fetching URL: {url} with headers: {headers} and params: {params}")
        response = await session.get(url, headers=headers, params=params)
        response.raise_for_status()
        json_response = response.json()
        if isinstance(json_response, dict):
            return json_response
        else:
            logger.error(f"Unexpected response format: {json_response}")
            return None
    except HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code} - {e.response.text}")
        logger.error(traceback.format_exc())
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        logger.error(traceback.format_exc())
        return None

async def authenticate_hangar():
    try:
        async with http_session() as session:
            headers = {"User-Agent": USER_AGENT}
            response = await session.post(f"{AUTH_URL_HANGAR}?apiKey={API_KEY_HANGAR}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("token")
    except HTTPStatusError as e:
        logger.error(f"Error authenticating with Hangar API: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Hangar authentication: {e}")
        return None

async def search_plugin(plugin_name, source="both"):
    async with http_session() as session:
        normalized_plugin_name = normalize_name(plugin_name)

        # Check cache (Redis) first
        cached_data = await get_plugin_from_db(normalized_plugin_name)
        if cached_data:
            logger.info(f"Found cached data for {plugin_name}")
            return [cached_data], "cache"

        # Search in Hangar
        if source in ("hangar", "both"):
            token = await authenticate_hangar()
            if token:
                hangar_results = await fetch(SEARCH_URL_HANGAR, session, headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": USER_AGENT
                }, params={"q": normalized_plugin_name, "limit": 10})
                if hangar_results:
                    hangar_plugins = [convert_to_unified(plugin, "hangar") for plugin in
                                      hangar_results.get('result', [])]
                    best_match = get_best_match(normalized_plugin_name, hangar_plugins)
                    if best_match:
                        await insert_or_update_plugin(best_match)
                        return [best_match], "hangar"

        # If not found in Hangar or no best match, search in Modrinth
        if source in ("modrinth", "both"):
            modrinth_results = await fetch(SEARCH_URL_MODRINTH, session, headers={
                "Authorization": f"Bearer {API_KEY_MODRINTH}",
                "User-Agent": USER_AGENT
            }, params={
                "query": plugin_name,
                "limit": 10,
                "facets": "[[\"categories:utility\"]]",
                "sort": "popularity"
            })
            if modrinth_results:
                modrinth_plugins = [convert_to_unified(plugin, "modrinth") for plugin in
                                    modrinth_results.get('hits', [])]
                best_match = get_best_match(normalized_plugin_name, modrinth_plugins)
                if best_match:
                    await insert_or_update_plugin(best_match)
                    return [best_match], "modrinth"

    return [], None

def convert_to_unified(data, source):
    if source == "modrinth":
        return {
            "name": normalize_name(data.get("title", "")),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "author": data.get("author", "Unknown Author"),
            "date_created": data.get("date_created", ""),
            "date_modified": data.get("date_modified", ""),
            "icon_url": data.get("icon_url", ""),
            "category": data.get("categories", [""])[0],
            "downloads": data.get("downloads", 0),
            "follows": data.get("follows", 0),
            "url": f"https://modrinth.com/mod/{data.get('slug', '')}",
            "source": source
        }
    elif source == "hangar":
        return {
            "name": normalize_name(data.get("name", "")),
            "title": data.get("name", ""),
            "description": data.get("description", ""),
            "author": data.get("namespace", {}).get("owner", "Unknown Author"),
            "date_created": data.get("createdAt", ""),
            "date_modified": data.get("lastUpdated", ""),
            "icon_url": data.get("avatarUrl", ""),
            "category": data.get("category", ""),
            "downloads": data.get("stats", {}).get("downloads", 0),
            "follows": data.get("stats", {}).get("stars", 0),
            "url": f"https://hangar.papermc.io/{data.get('namespace', {}).get('owner', '')}/{data.get('namespace', {}).get('slug', '')}",
            "source": source
        }

def get_best_match(plugin_name, results):
    best_match = None
    highest_score = 0
    normalized_plugin_name = normalize_name(plugin_name)

    for plugin in results:
        normalized_result_name = normalize_name(plugin['title'] if plugin.get('title') else plugin['name'])
        score = SequenceMatcher(None, normalized_plugin_name, normalized_result_name).ratio()
        if score > highest_score:
            highest_score = score
            best_match = plugin

    return best_match if highest_score > 0.8 else None

def scan_folder(folder_path):
    return [(os.path.splitext(filename)[0], "Unknown Version") for filename in os.listdir(folder_path) if
            filename.endswith(".jar")]

async def check_plugins(folder_path):
    plugins = scan_folder(folder_path)
    state.clear_plugins()

    try:
        async with http_session() as session:
            tasks = [search_plugin(plugin_name) for plugin_name, _ in plugins]
            results_with_sources = await asyncio.gather(*tasks)

            for (plugin_name, plugin_version), (results, source) in zip(plugins, results_with_sources):
                best_match = get_best_match(plugin_name, results)
                if best_match:
                    plugin_data = await get_plugin_from_db(normalize_name(plugin_name))
                    if not plugin_data:
                        plugin_data = best_match
                        await insert_or_update_plugin(plugin_data)

                    image_filepath = None
                    if plugin_data['icon_url']:
                        file_ext = os.path.splitext(plugin_data['icon_url'])[-1].split('?')[0]
                        image_filepath = os.path.join(CACHE_DIR, f"{normalize_name(plugin_name)}{file_ext}")
                        if not os.path.exists(image_filepath):
                            await download_image(plugin_data['icon_url'], image_filepath)

                    state.add_found_plugin((plugin_name, plugin_data['date_modified'], plugin_data['title'],
                                            plugin_data['url'], plugin_data, image_filepath))
                else:
                    state.add_not_found_plugin((plugin_name, plugin_version))
    except Exception as e:
        logger.error(f"Error checking plugins: {e}")
        logger.error(traceback.format_exc())

    return state.found_plugins, state.not_found_plugins

async def download_image(url, filepath):
    try:
        async with http_session() as session:
            async with session.stream("GET", url) as response:
                response.raise_for_status()
                with open(filepath, 'wb') as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
    except Exception as e:
        logger.error(f"Error downloading image: {e}")

async def check_for_updates(found_plugins):
    updates = []
    try:
        for plugin in found_plugins:
            plugin_name, current_version, mod_name, project_id, plugin_data, _ = plugin
            latest_version = plugin_data.get('latest_version', "Unknown Date")
            if latest_version != current_version:
                updates.append((plugin_name, current_version, latest_version, latest_version))

        return updates
    except Exception as e:
        logger.error(f"Error checking updates: {e}")
        return updates

async def download_plugin(url, destination):
    try:
        async with http_session() as session:
            async with session.stream("GET", url) as download_response:
                download_response.raise_for_status()
                with open(destination, 'wb') as f:
                    async for chunk in download_response.aiter_bytes():
                        f.write(chunk)
    except Exception as e:
        logger.error(f"Error downloading plugin: {e}")

def prettify_date(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except ValueError:
        return date_str

async def load_plugins():
    state.set_loading(True)
    try:
        found_plugins, not_found_plugins = await check_plugins(state.get_plugin_folder())
        state.set_loading(False)
        return found_plugins, not_found_plugins
    except Exception as e:
        logger.error(f"Error loading plugins: {e}")
        state.set_loading(False)
        return [], []
