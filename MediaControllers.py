from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, TypedDict, final, override

from lib.Event import Event
from lib.EventManager import Projection
from lib.PluginHelper import PluginHelper
from lib.Logger import log
from .MPRISController import MPRISController
from .WindowsMediaController import WindowsMediaController
from .MacOSMediaController import MacOSMediaController

def get_platform_controller() -> MPRISController | WindowsMediaController | MacOSMediaController:
    import platform
    os_name = platform.system()
    if os_name == "Linux":
        return MPRISController()
    elif os_name == "Windows":
        return WindowsMediaController()
    elif os_name == "Darwin":
        return MacOSMediaController()
    else:
        log('error', f'Unsupported platform: {os_name}')
        raise NotImplementedError(f'MediaController not implemented for {os_name}')
