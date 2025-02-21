param(
    [string]$FolderPath = "."
)

# Function to extract duration of the MP3 file in ISO8601 format
function Get-MP3DurationISO8601 {
    param(
        [string]$Url
    )
    try {
        Write-Warning "Downloading ${Url}..."
        $tempFile = "$env:TEMP\audio.mp3"
        Invoke-WebRequest -Uri $Url -OutFile $tempFile -ErrorAction Stop

        $shell = New-Object -ComObject Shell.Application
        $folder = $shell.Namespace((Get-Item $tempFile).DirectoryName)
        $item = $folder.ParseName((Get-Item $tempFile).Name)

        $duration = $folder.GetDetailsOf($item, 27)  # Duration is typically at index 27
        if ($duration) {
            $parts = $duration -split ":", 3
            $hours = if ($parts.Length -eq 3) { $parts[0] } else { "0" }
            $minutes = if ($parts.Length -eq 3) { $parts[1] } else { $parts[0] }
            $seconds = if ($parts.Length -eq 3) { $parts[2] } else { $parts[1] }

            $iso8601 = "PT" + $hours + "H" + $minutes + "M" + $seconds + "S"
            return $iso8601
        }
    } catch {
        Write-Warning "Failed to get duration for `$Url. Error: $($_.Exception.Message)"
    } finally {
        Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
    }
    return $null
}

# Function to generate the missing properties
function Get-MissingProperties {
    param(
        [hashtable]$properties,
        [string]$content
    )

    $missingProps = @{}

    if (-not $properties.ContainsKey("audioURL")) {
        if ($content -match '<audio[^>]*>\s*<source[^>]*src="([^"]+)"[^>]*\/>\s*<\/audio>') {
            $missingProps["audioURL"] = $matches[1]
        }
    }

    if (-not $properties.ContainsKey("duration") -and $missingProps.ContainsKey("audioURL")) {
        $missingProps["duration"] = Get-MP3DurationISO8601 -Url $missingProps["audioURL"]
    }

    if (-not $properties.ContainsKey("season") -and $missingProps.ContainsKey("audioURL")) {
        if ($missingProps["audioURL"] -match "S(\d{2})") {
            $missingProps["season"] = [int]$matches[1]
        }
    }

    if (-not $properties.ContainsKey("episodeNumber") -and $properties.ContainsKey("title")) {
        if ($properties["title"] -match "#(\d+)") {
            $missingProps["episodeNumber"] = [int]$matches[1]
        }
    }

    return $missingProps
}

# Process Markdown files in the folder
Get-ChildItem -Path $FolderPath -Filter "*.md" | ForEach-Object {
    $filePath = $_.FullName
    $content = Get-Content -Path $filePath -Raw

    # Extract front-matter block using a more robust regex
    if ($content -match "(?s)^---\s*(.*?)\s*---") {
        $frontMatter = $matches[1]
        $properties = @{}
        $missingProps = @{}

        # Parse front-matter properties
        foreach ($line in $frontMatter -split "`n") {
            if ($line -match "^(.+?):\s*(.+)") {
                $properties[$matches[1].Trim()] = $matches[2].Trim()
            }
        }

        # Get missing properties
        $missingProps = Get-MissingProperties -properties $properties -content $content

        # If there are missing properties, append them before the closing ---
        if ($missingProps.Count -gt 0) {
            $newFrontMatter = "---`n$frontMatter`n"
            foreach ($key in $missingProps.Keys) {
                $newFrontMatter += "${key}: $($missingProps[$key])`n"
            }
            $newFrontMatter += "---`n`n"  # Adding an extra new line after the final ---

            # Replace the old front-matter with the new one
            $newContent = $newFrontMatter + ($content -replace "(?s)^---\s*\n.*?\n---\s*", "")
            Set-Content -Path $filePath -Value $newContent -Force
        }
    } else {
        Write-Warning "No front-matter found in $filePath"
    }
}
