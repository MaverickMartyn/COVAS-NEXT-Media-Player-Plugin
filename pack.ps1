# Delete dist if it already exists
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}

# Create dist
New-Item "dist" -ItemType Directory

# Install dependencies
if (Test-Path "requirements.txt") {
    pip install --target ./deps -r requirements.txt
}

# Remember to add any additional files, and change the name of the plugin
$artifacts = "MediaPlayerPlugin.py", "requirements.txt", "README.md", "manifest.json"

if (Test-Path "deps") {
    $artifacts += "deps"
}

$compress = @{
LiteralPath = $artifacts
CompressionLevel = "Fastest"
DestinationPath = "dist\MediaPlayerPlugin.zip"
}
Compress-Archive @compress
