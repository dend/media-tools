function Make-PodcastArtifacts {
    Param (
        [string]
        $AudioPath,
        [string]
        $Season,
        [string]
        $Episode,
        [string]
        $FfmpegPath
    )

    Write-Host "[info] Execution context: $ArgumentList"

    # Generate podcast XML blob.
    $Guid = New-Guid | Select -ExpandProperty "Guid"
    $AudioFileLength = [int](Get-Item "$AudioPath" | % {[int]($_.length / 1kb)}) * 1024

    $Shell = New-Object -COMObject Shell.Application
    $Folder = Split-Path $AudioPath
    $File = Split-Path $AudioPath -Leaf
    $ShellFolder = $Shell.Namespace($Folder)
    $ShellFile = $ShellFolder.ParseName($File)

    $UnformattedDuration = $ShellFolder.GetDetailsOf($ShellFile, 27)
    $DurationComponents = $UnformattedDuration -Split ':'
    $TotalDuration = [int]($DurationComponents[0]) * 60 * 60 + [int]($DurationComponents[1]) * 60 + [int]($DurationComponents[2])

    $CurrentDate = Get-Date -Format "ddd, dd MMM yyyy HH:mm:ss 'GMT'"

    $EpisodeXml = @"
    <item>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:episode>${Episode}</itunes:episode>
      <itunes:season>${Season}</itunes:season>
      <title>#TBD - REPLACE_ME</title>
      <itunes:image href="https://cdn.theworkitem.com/art/episode-logos/s${Season}e${Episode}.png" />
      <description>
        REPLACE_ME
      </description>
      <itunes:summary>
        REPLACE_ME
      </itunes:summary>
      <content:encoded>
        <![CDATA[
        ]]>
      </content:encoded>
      <enclosure length=`"${AudioFileLength}`" type=`"audio/mpeg`" url=`"https://cdn.theworkitem.com/audio/the-work-item-S${Season}E${Episode}.mp3`" />
      <guid isPermaLink="false">${Guid}</guid>
      <pubDate>${CurrentDate}</pubDate>
      <itunes:duration>${TotalDuration}</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
    </item>
"@

    Write-Host $EpisodeXml
}

