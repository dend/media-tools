#!/usr/bin/env python

import time
import re
from datetime import datetime, timedelta
import os
import platform

projectManager = resolve.GetProjectManager()
project = projectManager.GetCurrentProject()

srt_file_path = "soundclip.srt"
target_video_track = 2
mediaPoolItemsList = []

text_plus_template_search_pattern = re.compile(r'text|title|subtitle', re.IGNORECASE)

def IdentityTemplateInMediaPool():
    mediaPool = project.GetMediaPool()
    folder = mediaPool.GetRootFolder()

    MediaPoolRecursiveSearch(folder, mediaPoolItemsList, text_plus_template_search_pattern)

def MediaPoolRecursiveSearch(folder, mediaPoolItemsList, pattern):
    items = folder.GetClipList()
    item_properties = [item.GetClipProperty() for item in items]

    for item, properties in zip(items, item_properties):
        print(properties["Type"])
        itemType = properties["Type"]
        if itemType == "Fusion Title":
            itemName = item.GetName()
            clipName = properties["Clip Name"]

            if pattern.search(itemName) or pattern.search(clipName):
                print(f"Found media item: {item}")
                mediaPoolItemsList.append(item)

    subfolders = folder.GetSubFolderList()
    for subfolder in subfolders:
        MediaPoolRecursiveSearch(subfolder, mediaPoolItemsList, pattern)

def GenerateTextPlusSubtitles(srt_path, video_track_index):
    content = ''
    subs = []

    resolve.OpenPage("edit")
    mediaPool = project.GetMediaPool()
    folder = mediaPool.GetRootFolder()
    items = folder.GetClipList()

    if not project:
        print("No project is loaded")
        return

    timeline = project.GetCurrentTimeline()
    if not timeline:
        if project.GetTimelineCount() > 0:
            timeline = project.GetTimelineByIndex(1)
            project.SetCurrentTimeline(timeline)
        else:
            print("Current project has no timelines")
            return

    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("Subtitle file not found.")
        return

    timelineStartFrame = timeline.GetStartFrame()
    frame_rate = float(timeline.GetSetting("timelineFrameRate"))

    print(f'Operating at the following FPS: {frame_rate}')

    entries = re.split(r"\n{2,}", content.strip())
    time_pattern = re.compile(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)")

    for entry in entries:
        lines = entry.split("\n")
        if len(lines) >= 3:
            times = lines[1].strip()
            text_lines = lines[2:]

            m = time_pattern.match(times)
            t_start = list(map(int, m.groups()[0:4]))
            t_end = list(map(int, m.groups()[4:8]))
            print (f"Time for subtitle: {t_start} and {t_end}")

            posInFrames = int((t_start[0] * 3600 + t_start[1] * 60 + t_start[2] + t_start[3] / 1000) * frame_rate)
            timelinePos = timelineStartFrame + posInFrames

            print(f"Start position for subtitle: POS_IN_FRAMES - {posInFrames}, TIMELINE_POS - {timelinePos}")

            endPosInFrames = int((t_end[0] * 3600 + t_end[1] * 60 + t_end[2] + t_end[3] / 1000) * frame_rate)
            duration = (timelineStartFrame + endPosInFrames) - timelinePos

            print(f"End position for subtitle: END_POS_IN_FRAMES - {endPosInFrames}, DURATION - {duration}")

            text = "\n".join(text_lines).upper()
            subs.append((timelinePos, duration, text))

    print("Found", len(subs), "subtitles in SRT file")

    templateText = mediaPoolItemsList[0]

    if not templateText:
        print("No Text+ found in Media Pool")
        return

    print(f'{templateText.GetClipProperty()["Clip Name"]} selected as template')

    timelineTrack = video_track_index

    for i, (timelinePos, duration, text) in enumerate(subs):
        if i < len(subs) - 1:
            duration = subs[i + 1][0] - timelinePos  # Extend current subtitle to start of next subtitle
        else:
            duration = duration  # Keep the last subtitle's duration as it is

        print(f"Subtitle: {i} for {timelinePos}, {duration}")

        newClip = {
            "mediaPoolItem": templateText,
            "startFrame": 0,
            "endFrame": duration,
            "trackIndex": timelineTrack,
            "recordFrame": timelinePos
        }

        if (mediaPool.AppendToTimeline([newClip])):
            print(f"Appended to timeline for {timelinePos} with duration of {duration}")

    print("Modifying subtitle text content...")

    clipList = timeline.GetItemListInTrack('video', timelineTrack)

    print(f"There are {len(clipList)} clips in the timeline.")

    for i, clip in enumerate(clipList):
        if clip.GetStart() >= subs[0][0]:
            clip.SetClipColor('Orange')
            text = subs[i][2]

            comp = clip.GetFusionCompByIndex(1)
            if comp:
                for tool in comp.GetToolList().values():
                    if tool.GetAttrs()['TOOLS_Name'] == 'Template':
                        tool.SetInput('StyledText', text)
                clip.SetClipColor('Teal')
            if i >= len(subs) - 1:
                print("Updated text for", i + 1, "subtitles")
                break

    print(f"Subtitles added video track {video_track_index}.")

IdentityTemplateInMediaPool()
GenerateTextPlusSubtitles(srt_file_path, target_video_track)
