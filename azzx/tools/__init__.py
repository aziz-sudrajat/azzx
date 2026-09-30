"""v7 Universal Toolkit — deterministic executors."""
from .filesystem import register_filesystem_tools
from .archive import register_archive_tools
from .hashutil import register_hash_tools
from .jsonutil import register_json_tools
from .network import register_network_tools
from .system import register_system_tools
from .media import register_media_tools


def register_all_toolkit_tools() -> None:
    register_filesystem_tools()
    register_archive_tools()
    register_hash_tools()
    register_json_tools()
    register_network_tools()
    register_system_tools()
    register_media_tools()
