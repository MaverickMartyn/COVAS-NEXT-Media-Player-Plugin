# If dist does not exist, create it
if (!(Test-Path "dist")) {
    mkdir dist
}

# Delete dist if it already exists
if (Test-Path "dist\MediaPlayerPlugin.zip") {
    Remove-Item "dist\MediaPlayerPlugin.zip"
}

$compress = @{
LiteralPath= "MediaPlayerPlugin.py", "requirements.txt", "playlists", "README.md"
CompressionLevel = "Fastest"
DestinationPath = "dist\MediaPlayerPlugin.zip"
}
Compress-Archive @compress