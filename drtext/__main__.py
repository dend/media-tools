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

def time_to_seconds(hours, minutes, seconds, milliseconds):
    """Convert time components to exact seconds with high precision"""
    return float(hours * 3600 + minutes * 60 + seconds) + (float(milliseconds) / 1000.0)

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

    print(f'\n=== TIMELINE SETTINGS ===')
    print(f'Operating at FPS: {frame_rate}')
    print(f'Timeline starts at frame: {timelineStartFrame}')
    print(f'Frame precision: {1/frame_rate:.4f} seconds per frame')
    print(f'Minimum readable duration: {max(int(frame_rate * 0.5), 10)} frames')
    print(f'=========================\n')

    entries = re.split(r"\n{2,}", content.strip())
    time_pattern = re.compile(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)")

    for entry in entries:
        lines = entry.split("\n")
        if len(lines) >= 3:
            times = lines[1].strip()
            text_lines = lines[2:]

            m = time_pattern.match(times)
            if not m:
                print(f"Warning: Could not parse time in entry: {entry}")
                continue

            t_start = list(map(int, m.groups()[0:4]))
            t_end = list(map(int, m.groups()[4:8]))
              # Calculate exact time in seconds (floating point precision)
            start_seconds = time_to_seconds(t_start[0], t_start[1], t_start[2], t_start[3])
            end_seconds = time_to_seconds(t_end[0], t_end[1], t_end[2], t_end[3])
            
            # Convert to exact frame positions with high precision
            start_frame_position = start_seconds * frame_rate
            end_frame_position = end_seconds * frame_rate
              # Calculate precise timeline position and duration
            timelinePos = timelineStartFrame + int(round(start_frame_position))
            
            # Use exact duration from SRT - no minimum duration enforcement
            frame_duration = end_frame_position - start_frame_position
            duration = max(int(round(frame_duration)), 1)  # At least 1 frame to avoid zero duration
            
            print(f"Subtitle #{len(subs)+1}: {start_seconds:.3f}s-{end_seconds:.3f}s -> Frame {timelinePos} (duration: {duration})")
            print(f"  Raw frame positions: {start_frame_position:.2f} to {end_frame_position:.2f}")

            text = "\n".join(text_lines).upper()
            subs.append((timelinePos, duration, text))    
    
    print("Found", len(subs), "subtitles in SRT file")
    
    # No timing adjustments - use exact SRT timing
    print("\n=== USING EXACT SRT TIMING ===")
    print("Creating Text+ elements at precise SRT frame positions")
    print("============================\n")

    if not mediaPoolItemsList:
        print("No Text+ templates found in Media Pool")
        return
    
    templateText = mediaPoolItemsList[0]
    print(f'{templateText.GetClipProperty()["Clip Name"]} selected as template')
    
    # Get template clip frame rate to calculate proper duration
    template_fps = float(templateText.GetClipProperty("FPS"))
    timeline_fps = frame_rate
    fps_ratio = template_fps / timeline_fps
    
    print(f"Template FPS: {template_fps}, Timeline FPS: {timeline_fps}, Ratio: {fps_ratio:.4f}")
      # Add all subtitles with improved error handling
    subtitles_added = 0
    failed_subtitles = []
    for i, (timelinePos, duration, text) in enumerate(subs):
        # Adjust duration for frame rate conversion
        # Use rounding instead of truncation for better accuracy
        adjusted_duration = max(1, round(duration * fps_ratio))
        
        print(f"Processing subtitle #{i+1}: Position={timelinePos}, Duration={duration} -> Adjusted={adjusted_duration} (ratio: {fps_ratio:.6f})")
        
        newClip = {
            "mediaPoolItem": templateText,
            "startFrame": 0,
            "endFrame": adjusted_duration - 1,
            "trackIndex": video_track_index,
            "recordFrame": timelinePos
        }

        # Add one clip at a time and force processing
        success = mediaPool.AppendToTimeline([newClip])
        if success:
            print(f"✓ Added subtitle #{i+1} at frame {timelinePos} (duration: {duration} frames)")
            subtitles_added += 1
            
            # Force a small delay to ensure DaVinci processes each clip separately
            time.sleep(0.01)
        else:
            print(f"✗ Failed to add subtitle #{i+1} at frame {timelinePos}")
            failed_subtitles.append((i+1, timelinePos, text[:50] + "..." if len(text) > 50 else text))
    
    print(f"\nSubtitle addition summary:")
    print(f"  Successfully added: {subtitles_added}/{len(subs)} subtitles")
    if failed_subtitles:
        print(f"  Failed subtitles:")
        for sub_num, pos, text_preview in failed_subtitles:
            print(f"    #{sub_num} at frame {pos}: '{text_preview}'")
      # Verify clips were created properly
    print(f"\nVerifying clip creation...")
    clipList = timeline.GetItemListInTrack('video', video_track_index)
    print(f"Created {len(clipList)} clips from {len(subs)} subtitles")
    
    if len(clipList) == len(subs):
        print(f"✅ SUCCESS: All {len(subs)} subtitles created as clips!")
    else:
        print(f"ℹ️  INFO: {len(clipList)} clips created from {len(subs)} subtitles")

    # Update the text content for each subtitle clip with simple 1:1 matching
    print("\nModifying subtitle text content...")
    print(f"Found {len(clipList)} clips in video track {video_track_index}")    # Simple 1:1 matching - each clip should match one subtitle    
    
    clips_modified = 0
    unmatched_clips = []
    tolerance = 5  # Allow 5 frame tolerance for matching
    
    for clip in clipList:
        clip_start = clip.GetStart()
        clip_duration = clip.GetDuration()
        print(f"  Clip at frame {clip_start} (duration: {clip_duration})")
          # Find the subtitle that matches this clip position
        matching_sub = None
        for i, (sub_pos, sub_duration, sub_text) in enumerate(subs):
            if abs(clip_start - sub_pos) <= tolerance:
                matching_sub = (i, sub_text)
                print(f"    → Matched to subtitle #{i+1} (pos diff: {clip_start - sub_pos})")
                break
        
        if matching_sub:
            i, text = matching_sub
            clip.SetClipColor('Orange')  # Mark as being processed
            
            comp = clip.GetFusionCompByIndex(1)
            if comp:
                template_found = False
                for tool in comp.GetToolList().values():
                    if tool.GetAttrs()['TOOLS_Name'] == 'Template':
                        tool.SetInput('StyledText', text)
                        template_found = True
                        clips_modified += 1
                        break
                
                if template_found:
                    clip.SetClipColor('Teal')  # Mark as successfully processed
                else:
                    clip.SetClipColor('Red')   # Mark as failed - no template found
                    print(f"    ✗ No Template tool found in clip at frame {clip_start}")
            else:
                clip.SetClipColor('Red')  # Mark as failed - no comp
                print(f"    ✗ No Fusion comp found for clip at frame {clip_start}")
        else:
            unmatched_clips.append(clip_start)
            clip.SetClipColor('Yellow')  # Mark as unmatched
            print(f"    ✗ No matching subtitle found for clip at frame {clip_start}")
    
    print(f"\nText update summary:")
    print(f"  Updated text for: {clips_modified}/{len(clipList)} clips")
    if unmatched_clips:
        print(f"  Unmatched clips at frames: {unmatched_clips}")
    
    print(f"\nColor coding:")
    print(f"  Teal: Successfully processed")
    print(f"  Orange: Currently being processed") 
    print(f"  Red: Failed (no template/comp found)")
    print(f"  Yellow: No matching subtitle found")
    print(f"Subtitle insertion complete on video track {video_track_index}.")

IdentityTemplateInMediaPool()
GenerateTextPlusSubtitles(srt_file_path, target_video_track)