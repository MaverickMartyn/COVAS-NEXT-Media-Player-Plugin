from lib.Logger import log
from .MediaControllerTypes import MediaControllerBase

def get_platform_controller() -> MediaControllerBase:
    import platform
    os_name = platform.system()
    if os_name == "Linux":
        from .MPRISController import MPRISController
        return MPRISController()
    elif os_name == "Windows":
        from .WindowsMediaController import WindowsMediaController
        return WindowsMediaController()
    else:
        log('error', f'Unsupported platform: {os_name}')
        raise NotImplementedError(f'MediaController not implemented for {os_name}')
