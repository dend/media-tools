#!/usr/bin/env python

import time
import re
from datetime import datetime, timedelta
import os
import platform

projectManager = resolve.GetProjectManager()
project = projectManager.GetCurrentProject()

srt_file_path = "PATH_TO_SRT_FILE"
target_video_track = 2
# I manually set the frame rate here because the API that is commented out
# above returns the wrong value (it rounds down)
frame_rate=29.97
base_rate=29.97
duration_factor = frame_rate / base_rate
template_index = 0
mediaPoolItemsList = []

text_plus_template_search_pattern = re.compile(r'text|title|subtitle', re.IGNORECASE)

def IdentityTemplateInMediaPool():
    mediaPool = project.GetMediaPool()
    folder = mediaPool.GetRootFolder()

    MediaPoolRecursiveSearch(folder, mediaPoolItemsList, text_plus_template_search_pattern)

def MediaPoolRecursiveSearch(folder, mediaPoolItemsList, pattern):
    # Retrieve all clip properties at once.
    items = folder.GetClipList()
    item_properties = [item.GetClipProperty() for item in items]

    # Iterate through item properties to see if they match
    # the search pattern that we've established.
    for item, properties in zip(items, item_properties):
        itemType = properties["Type"]
        if itemType == "Generator":
            itemName = item.GetName()
            clipName = properties["Clip Name"]

            # Check if itemName or clipName contains the search pattern.
            if pattern.search(itemName) or pattern.search(clipName):
                mediaPoolItemsList.append(item)

    # Recursively search subfolders in the media pool.
    subfolders = folder.GetSubFolderList()
    for subfolder in subfolders:
        recursiveSearch(subfolder, mediaPoolItemsList)

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

    # Get current timeline. If no current timeline try to load it from timeline list
    timeline = project.GetCurrentTimeline()
    if not timeline:
        if project.GetTimelineCount() > 0:
            timeline = project.GetTimelineByIndex(1)
            project.SetCurrentTimeline(timeline)
        else:
            print("Current project has no timelines")
            return

    # Read the subtitles (SRT) file.
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("Subtitle file not found.")
        return

    timelineStartFrame = timeline.GetStartFrame()
    #frame_rate = int(timeline.GetSetting("timelineFrameRate"))  # Incorrect framerate

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

    # We take the first template that was registered in the media pool list.
    templateText = mediaPoolItemsList[0]

    if not templateText:
        print("No Text+ found in Media Pool")
        return

    print(f'{templateText.GetClipProperty()["Clip Name"]} selected as template')

    timelineTrack = video_track_index

    # Add template text to timeline (text not set yet)
    for i, (timelinePos, duration, text) in enumerate(subs):
        if i < len(subs) - 1 and subs[i + 1][0] - (timelinePos + duration) < 200:  # if gap between subs is less than 10 frames
            duration = (subs[i + 1][0] - subs[i][0]) - 1  # then set current subtitle to end at start of next subtitle - 1 frame

        print(f"Subtitle: {i} for {timelinePos}, {duration}")

        newClip = {
            "mediaPoolItem": templateText,
            "startFrame": 0,
            "endFrame": duration / duration_factor,
            "trackIndex": timelineTrack,
            "recordFrame": timelinePos
        }

        if (mediaPool.AppendToTimeline([newClip])):
            print(f"Appended to timeline for {timelinePos} with duration of {duration}")

    print("Modifying subtitle text content...")

    # Get list of Text+ in timeline
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
