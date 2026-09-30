"""v9 Local plugin system with manifest + permission validation."""
from .loader import (
    PluginManager,
    install_plugin,
    list_plugins,
    load_enabled_plugins,
    validate_manifest,
    register_plugin_tools,
)

__all__ = [
    "PluginManager",
    "install_plugin",
    "list_plugins",
    "load_enabled_plugins",
    "validate_manifest",
    "register_plugin_tools",
]
