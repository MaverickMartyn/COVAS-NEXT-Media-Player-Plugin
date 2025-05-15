
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

Unpack the plugin into the `plugins` folder in COVAS, leading to the following folder structure:
* `plugins`
    * `MediaPlayer`
        * `MediaPlayer.py`
        * `requirements.txt`
        * `playlists`
            * `Rock.m3u`
    * `OtherPlugin`

Install the dependencies using `pip`, by running this command in the ´MediaPluigin` folder:
```bash
  pip install -r requirements.txt
```
    
## Acknowledgements

 - [COVAS:NEXT](https://github.com/RatherRude/Elite-Dangerous-AI-Integration)
 - [My other projects](https://github.com/maverickMartyn)

