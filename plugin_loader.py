import os
import importlib.util
import fnmatch

PLUGIN_DIR = "plugins"


def load_plugins():
    plugins = []

    if not os.path.exists(PLUGIN_DIR):
        return plugins

    filename = None

    #find filename that ends in plugin.py
    for folder in os.listdir(PLUGIN_DIR):
        #print("folder=", folder)
        for file in os.listdir(os.path.join(PLUGIN_DIR, folder)):
            #print("examining filename=", file)
            if fnmatch.fnmatch(file,'*plugin.py'):
                filename = file
                #print("added filename=", filename)
                plugin_path = os.path.join(
                    PLUGIN_DIR,
                    folder,
                    filename
                )
                #break

                if os.path.exists(plugin_path):
                    spec = importlib.util.spec_from_file_location(
                        folder,
                        plugin_path
                    )

                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    plugins.append(module)

    return plugins