class DharaPluginList:
    def __init__(self):
        self.clear_plugins()

    def clear_plugins(self):
        self.found_plugins = []
        self.not_found_plugins = []

    def add_found_plugin(self, plugin):
        self.found_plugins.append(plugin)

    def add_not_found_plugin(self, plugin):
        self.not_found_plugins.append(plugin)
