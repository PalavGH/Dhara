class State:
    def __init__(self):
        self.found_plugins = []
        self.not_found_plugins = []
        self.loading = False
        self.error_message = ""
        self.update_status = []
        self.api_keys = {}
        self.plugin_folder = ""
        self.selected_plugin = None

    def set_loading(self, is_loading):
        self.loading = is_loading

    def set_error(self, message):
        self.error_message = message

    def clear_error(self):
        self.error_message = ""

    def add_found_plugin(self, plugin):
        self.found_plugins.append(plugin)

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
