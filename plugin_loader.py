import os
import importlib.util
import fnmatch

def load_plugins(plugin_dir):
    plugins = []

    if not plugin_dir:
        plugin_dir = "plugins"

    if not os.path.exists(plugin_dir):
        return plugins

    # Process absolute layout referencing cleanly
    abs_plugin_dir = os.path.abspath(plugin_dir)

    for folder in os.listdir(abs_plugin_dir):
        folder_path = os.path.join(abs_plugin_dir, folder)
        
        # FIX: ONLY look inside if this item is a real directory!
        # This skips requirements.txt, README.md, or hidden root assets safely.
        if os.path.isdir(folder_path) and not folder.startswith((".", "__")):
            
            for file in os.listdir(folder_path):
                if fnmatch.fnmatch(file, '*plugin.py'):
                    plugin_path = os.path.join(folder_path, file)

                    if os.path.exists(plugin_path):
                        try:
                            spec = importlib.util.spec_from_file_location(
                                folder,
                                plugin_path
                            )

                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            plugins.append(module)
                            print(f"  [Suite Loader] Successfully loaded plugin: {folder}")
                        except Exception as e:
                            print(f"  [Suite Loader Error] Failed to compile {folder}: {e}")
                            
    return plugins
