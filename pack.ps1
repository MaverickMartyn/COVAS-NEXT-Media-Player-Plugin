# Fail fast on errors
$ErrorActionPreference = 'Stop'

# Delete dist if it already exists
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}

# Create dist
New-Item "dist" -ItemType Directory | Out-Null

# Install dependencies using the active Python
if (Test-Path "requirements.txt") {
    & uv pip install --target ./deps -r requirements.txt --upgrade
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

# Remember to add any additional files, and change the name of the plugin
$artifacts =
    "MediaPlayerPlugin.py",
    "MediaControllers.py",
    "MediaControllerTypes.py",
    "MPRISController.py",
    "WindowsMediaController.py",
    "ActionParams",
    "Projections",
    "requirements.txt",
    "README.md",
    "manifest.json",
    "__init__.py"

if (Test-Path "deps") {
    $artifacts += "deps"
}

$compress = @{
LiteralPath = $artifacts
CompressionLevel = "Fastest"
DestinationPath = "dist\MediaPlayerPlugin.zip"
}
Compress-Archive @compress
