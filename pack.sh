#!/bin/bash

# Delete dist if it already exists
if [ -d "dist" ]; then
    rm -rf dist
fi

# Create dist
mkdir dist

# Install dependencies
if [ -f "requirements.txt" ]; then
    pip install --target ./deps -r requirements.txt
fi

# Remember to add any additional files, and change the name of the plugin
artifacts=("MediaPlayerPlugin.py", "MediaControllers.py", "MediaControllerTypes.py", "MPRISController.py", "WindowsMediaController.py", "requirements.txt", "README.md" "manifest.json", "__init__.py")

if [ -d "deps" ]; then
    artifacts+=("deps")
fi

# Create the zip archive
zip -r -9 "dist/MediaPlayerPlugin.zip" "${artifacts[@]}"