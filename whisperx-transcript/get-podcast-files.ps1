# Define the URL to the raw XML file in the repository
$xmlUrl = "https://raw.githubusercontent.com/theworkitem/feeds/master/xml/theworkitem-itunes.xml"
$xmlFile = "theworkitem-itunes.xml"

# Download the XML file
Invoke-WebRequest -Uri $xmlUrl -OutFile $xmlFile

# Load the XML file
[xml]$xml = Get-Content $xmlFile

# Extract all URLs from <enclosure> tags
$urls = $xml.rss.channel.item.enclosure | ForEach-Object {
    $_.url
}

# Download and convert each MP3 file to WAV
foreach ($url in $urls) {
    Write-Host "Downloading $url..."
    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($url)
    $mp3File = "$fileName.mp3"
    $wavFile = "$fileName.wav"
    
    # Download the MP3 file
    Invoke-WebRequest -Uri $url -OutFile $mp3File
    
    # Convert MP3 to WAV using ffmpeg
    & ffmpeg -i $mp3File $wavFile
}
