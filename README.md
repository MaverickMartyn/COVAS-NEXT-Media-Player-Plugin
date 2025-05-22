
# COVAS:NEXT Media Player Plugin

Integrates the COVAS:NEXT AI assistant with your media player, allowing the assistant to control playback and provide information about currently playing media.


## Features

- Support multiple methods for integrating, in order to support a wide variety of media players.
    - Simulated media key presses (Simplest)
    - Windows Media Session API (Default for Windows. Best general support)
    - More coming later
- Playlists
    * Add `*.m3u` playlist files to the `playlists` folder, to let the assistant start them for you.


## Installation

Download the latest release under the *Releases* section on the right.  
Unpack the plugin into the `plugins` folder in COVAS, leading to the following folder structure:
* `plugins`
    * `MediaPlayer`
        * `MediaPlayerPlugin.py`
        * `requirements.txt`
        * `deps`
        * `__init__.py`
        * etc.
    * `OtherPlugin`

# Development
During development, clone the COVAS:NEXT repository and place your plugin-project in the plugins folder.  
Install the dependencies to your local .venv virtual environment using `pip`, by running this command in the `MediaPlayer` folder:
```bash
  pip install -r requirements.txt
```

# Packaging
Use the `./pack.ps1` or `./pack.sh` scripts to package the plugin and any Python dependencies in the `deps` folder.
    
## Acknowledgements

 - [COVAS:NEXT](https://github.com/RatherRude/Elite-Dangerous-AI-Integration)
 - [My other projects](https://github.com/MaverickMartyn)

