#!/bin/bash

# Fail fast on errors, undefined variables, and pipeline failures
set -euo pipefail

# Delete dist if it already exists
if [ -d "dist" ]; then
    rm -rf dist
fi

# Create dist
mkdir dist

# Install dependencies
if [ -f "requirements.txt" ]; then
    # Use the active Python to install into ./deps; with set -e the script will exit
    # if the install command returns a non-zero exit code.
    python -m pip install --target ./deps -r requirements.txt
fi

# Remember to add any additional files, and change the name of the plugin
artifacts=(
    "MediaPlayerPlugin.py"
    "MediaControllers.py"
    "MediaControllerTypes.py"
    "MPRISController.py"
    "WindowsMediaController.py"
    "ActionParams"
    "Projections"
    "requirements.txt"
    "README.md"
    "manifest.json"
    "__init__.py"
)

if [ -d "deps" ]; then
    artifacts+=("deps")
fi

# Create the zip archive
zip -r -9 "dist/MediaPlayerPlugin.zip" "${artifacts[@]}"