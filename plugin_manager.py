import os
import asyncio
import flatbuffers
import httpx
from contextlib import asynccontextmanager
from loguru import logger
from difflib import SequenceMatcher
from utils import prettify_date, normalize_name, get_best_match, scan_folder, fetch, download_image, http_session
from redis_client import RedisClient
from state_manager import State
from PluginManager import Plugin as FlatbufferPlugin
from config import Config

class PluginManager:
    def __init__(self):
        self.config = Config().config
        logger.info(self.config.get('api_keys'))
        self.redis_client = RedisClient()
        self.state = State()

    def init_db(self):
        cache_dir = self.config.get('paths', {}).get('cache_dir', 'cache')
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            logger.info(f"Cache directory created at {cache_dir}")
        else:
            logger.info(f"Cache directory already exists at {cache_dir}")

    async def insert_or_update_plugin(self, plugin_data):
        try:
            key = f"plugin:{plugin_data['name']}"
            serialized_data = self.serialize_plugin(plugin_data)
            self.redis_client.set(key, serialized_data)
        except Exception as e:
            logger.error(f"Error inserting or updating plugin data: {e}")

    async def get_plugin_from_db(self, plugin_name):
        try:
            key = f"plugin:{plugin_name}"
            plugin_data = self.redis_client.get(key)
            if plugin_data:
                return self.deserialize_plugin(plugin_data)
            return None
        except Exception as e:
            logger.error(f"Error fetching plugin from database: {e}")
            return None

    def serialize_plugin(self, plugin_data):
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

        FlatbufferPlugin.PluginStart(builder)
        FlatbufferPlugin.PluginAddName(builder, name)
        FlatbufferPlugin.PluginAddTitle(builder, title)
        FlatbufferPlugin.PluginAddDescription(builder, description)
        FlatbufferPlugin.PluginAddAuthor(builder, author)
        FlatbufferPlugin.PluginAddDateCreated(builder, date_created)
        FlatbufferPlugin.PluginAddDateModified(builder, date_modified)
        FlatbufferPlugin.PluginAddIconUrl(builder, icon_url)
        FlatbufferPlugin.PluginAddCategory(builder, category)
        FlatbufferPlugin.PluginAddDownloads(builder, plugin_data['downloads'])
        FlatbufferPlugin.PluginAddFollows(builder, plugin_data['follows'])
        FlatbufferPlugin.PluginAddUrl(builder, url)
        FlatbufferPlugin.PluginAddSource(builder, source)
        plugin = FlatbufferPlugin.PluginEnd(builder)
        builder.Finish(plugin)

        return bytes(builder.Output())

    def deserialize_plugin(self, data):
        plugin = FlatbufferPlugin.Plugin.GetRootAsPlugin(data, 0)
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

    async def search_plugin(self, plugin_name, source="both"):
        async with http_session() as session:
            normalized_plugin_name = normalize_name(plugin_name)

            # Check cache (Redis) first
            cached_data = await self.get_plugin_from_db(normalized_plugin_name)
            if cached_data:
                logger.info(f"Found cached data for {plugin_name}")
                return [cached_data], "cache"

            # Search in Hangar
            if source in ("hangar", "both"):
                token = await self.authenticate_hangar()
                if token:
                    hangar_results = await fetch(self.config['urls']['search_hangar'], session, headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": self.config['user_agent']
                    }, params={"q": normalized_plugin_name, "limit": 10})
                    if hangar_results:
                        hangar_plugins = [self.convert_to_unified(plugin, "hangar") for plugin in
                                          hangar_results.get('result', [])]
                        best_match = get_best_match(normalized_plugin_name, hangar_plugins)
                        if best_match:
                            await self.insert_or_update_plugin(best_match)
                            return [best_match], "hangar"

            # If not found in Hangar or no best match, search in Modrinth
            if source in ("modrinth", "both"):
                modrinth_results = await fetch(self.config['urls']['search_modrinth'], session, headers={
                    "Authorization": f"Bearer {self.config['api_keys']['modrinth']}",
                    "User-Agent": self.config['user_agent']
                }, params={
                    "query": plugin_name,
                    "limit": 10,
                    "facets": "[[\"categories:utility\"]]",
                    "sort": "popularity"
                })
                if modrinth_results:
                    modrinth_plugins = [self.convert_to_unified(plugin, "modrinth") for plugin in
                                        modrinth_results.get('hits', [])]
                    best_match = get_best_match(normalized_plugin_name, modrinth_plugins)
                    if best_match:
                        await self.insert_or_update_plugin(best_match)
                        return [best_match], "modrinth"

        return [], None

    async def authenticate_hangar(self):
        try:
            async with httpx.AsyncClient() as session:
                headers = {
                    "User-Agent": self.config['user_agent']
                }
                api_key = self.config['api_keys']['hangar']
                response = await session.post(
                    f"{self.config['urls']['auth_hangar']}?apiKey={api_key}",
                    headers=headers
                )
                response.raise_for_status()

                # Log the raw response for debugging
                logger.info(f"Raw response: {response.text}")

                # Parse the response as JSON and get the token
                data = response.json()
                token = data.get("token")
                if token:
                    logger.info(f"Authenticated with Hangar. Token: {token}")
                    return token
                else:
                    logger.error("Token not found in Hangar API response")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(f"Error authenticating with Hangar API: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Hangar authentication: {e}")
            return None

    def convert_to_unified(self, data, source):
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

    async def check_plugins(self, folder_path):
        plugins = scan_folder(folder_path)
        self.state.clear_plugins()

        try:
            async with http_session() as session:
                tasks = [self.search_plugin(plugin_name) for plugin_name, _ in plugins]
                results_with_sources = await asyncio.gather(*tasks)

                for (plugin_name, plugin_version), (results, source) in zip(plugins, results_with_sources):
                    best_match = get_best_match(plugin_name, results)
                    if best_match:
                        plugin_data = await self.get_plugin_from_db(normalize_name(plugin_name))
                        if not plugin_data:
                            plugin_data = best_match
                            await self.insert_or_update_plugin(plugin_data)

                        image_filepath = None
                        if plugin_data['icon_url']:
                            file_ext = os.path.splitext(plugin_data['icon_url'])[-1].split('?')[0]
                            image_filepath = os.path.join(self.config['paths']['cache_dir'],
                                                          f"{normalize_name(plugin_name)}{file_ext}")
                            if not os.path.exists(image_filepath):
                                await download_image(plugin_data['icon_url'], image_filepath)

                        self.state.add_found_plugin((plugin_name, plugin_data['date_modified'], plugin_data['title'],
                                                     plugin_data['url'], plugin_data, image_filepath))
                    else:
                        self.state.add_not_found_plugin((plugin_name, plugin_version))
        except Exception as e:
            logger.error(f"Error checking plugins: {e}")
            logger.error(traceback.format_exc())

        return self.state.found_plugins, self.state.not_found_plugins

    async def check_for_updates(self, found_plugins):
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

    async def download_plugin(self, url, destination):
        try:
            async with http_session() as session:
                async with session.stream("GET", url) as download_response:
                    download_response.raise_for_status()
                    with open(destination, 'wb') as f:
                        async for chunk in download_response.aiter_bytes():
                            f.write(chunk)
        except Exception as e:
            logger.error(f"Error downloading plugin: {e}")

    async def load_plugins(self):
        self.state.set_loading(True)
        try:
            found_plugins, not_found_plugins = await self.check_plugins(self.state.get_plugin_folder())
            self.state.set_loading(False)
            return found_plugins, not_found_plugins
        except Exception as e:
            logger.error(f"Error loading plugins: {e}")
            self.state.set_loading(False)
            return [], []
