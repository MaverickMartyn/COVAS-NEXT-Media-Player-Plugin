# If dist does not exist, create it
if (!(Test-Path "dist")) {
    mkdir dist
}

$compress = @{
LiteralPath= "MediaPlayerPlugin.py", "requirements.txt", "playlists", "README.md"
CompressionLevel = "Fastest"
DestinationPath = "dist\MediaPlayerPlugin.zip"
}
Compress-Archive @compress