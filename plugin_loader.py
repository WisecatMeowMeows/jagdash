import os
import importlib.util
import fnmatch

#PLUGIN_DIR = "plugins"  //this is the default, was fixed directory in the past


def load_plugins(plugin_dir):
    plugins = []

    if not plugin_dir:
        plugin_dir = "plugins"  #set to default. assuming that at minmum the config_plugin will be here
        #a better option is to use a built-in file browser here to force the user to pick a plugin directory

    if not os.path.exists(plugin_dir):
        return plugins

    filename = None

    #find filename that ends in plugin.py
    for folder in os.listdir(plugin_dir):
        #print("folder=", folder)
        for file in os.listdir(os.path.join(plugin_dir, folder)):
            #print("examining filename=", file)
            if fnmatch.fnmatch(file,'*plugin.py'):
                filename = file
                #print("added filename=", filename)
                plugin_path = os.path.join(
                    plugin_dir,
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