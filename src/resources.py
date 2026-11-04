"""Local plugin budget; explicitly adjustable without changing OS policy."""
import os


def plugin_memory_bytes():
    value=os.environ.get("ARRANGER_PLUGIN_MEMORY_MIB","2048")
    if not value.isascii() or not value.isdigit() or not 128<=int(value)<=8192:
        raise ValueError("ARRANGER_PLUGIN_MEMORY_MIB must be128 to8192")
    return int(value)*1024**2


def command_memory_bytes():
    value=os.environ.get('ARRANGER_COMMAND_MEMORY_MIB','8192')
    if not value.isascii() or not value.isdigit() or not 512<=int(value)<=16384:
        raise ValueError('ARRANGER_COMMAND_MEMORY_MIB must be512 to16384')
    return int(value)*1024**2
