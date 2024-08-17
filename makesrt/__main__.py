import os
import re
import sys
import copy
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from datetime import timedelta

import whisper
from whisper.utils import get_writer

def ConvertToXmlString(text_lines):
    combined_text = "\n".join(text_lines)
    xml_compatible_string = saxutils.escape(combined_text)
    return xml_compatible_string

def TranscribeAudio(path, output):
    print(f"Transcribing {path} to {output}")

    model = whisper.load_model("large", device="cuda") # Change this to your desired model
    print("Whisper model loaded.")
    result = model.transcribe(audio=path, initial_prompt="prompt", word_timestamps=True)
    
    word_options = {
        "highlight_words": False,
        "max_line_count": 2,
        "max_line_width": 15
    }

    srt_writer = get_writer("srt", os.path.dirname(output))
    srt_writer(result, os.path.basename(output), word_options)

    return output

def ConvertXmlTimestamp(s, return_tuple=False):
    if '/' in s:
        numerator, denominator = map(lambda x: x.rstrip('s'), s.split('/'))
        if return_tuple:
            return int(numerator), int(denominator)
        return float(numerator) / float(denominator)
    return float(s.rstrip('s'))

def ConvertTimestampToXml(t, framerate_tuple):
    multiplier, denominator = framerate_tuple
    x = int(t * denominator)
    if x % multiplier == 0:
        return f'{x // denominator}s'
    return f'{x}/{denominator}s'

def GenerateFCPXML(data, output, template_path="template.xml", event_name="CC_XML", framerate=29.97):
    xml = ET.parse(template_path)
    root = xml.getroot()

    n_resources = root.find('resources')
    xml_framerate = n_resources.find('format').get('frameDuration')
    xml_framerate_fps = 1 / ConvertXmlTimestamp(xml_framerate)

    if abs(framerate - xml_framerate_fps) > 0.005:
        raise Exception(f'Template frame rate {xml_framerate_fps:.2f}fps is inconsistent with specified framerate {framerate:.2f}fps.')

    framerate_tuple = ConvertXmlTimestamp(xml_framerate, return_tuple=True)

    n_library = root.find('library')
    n_event = n_library.find('event')
    n_event.set('name', 'CC_XML')
    n_project = n_event.find('project')
    n_project.set('name', event_name)

    n_sequence = n_project.find('sequence')
    n_spine = n_sequence.find('spine')

    title_proto = n_spine.find('title')
    n_spine.append(ET.Element('divider'))

    for counter, line in enumerate(data, start=1):
        t_start, t_end, text = line

        if counter == 1 and t_start > 0:
            gap_new = ET.Element('gap')
            gap_new.set('name', 'Gap')
            gap_new.set('offset', '0s')
            gap_new.set('duration', ConvertTimestampToXml(t_start, framerate_tuple))
            gap_new.set('start', '0s')
            n_spine.append(gap_new)

        title_new = copy.deepcopy(title_proto)
        offset = ConvertTimestampToXml(t_start, framerate_tuple)
        duration = ConvertTimestampToXml(t_end - t_start, framerate_tuple)
        output_text = ConvertToXmlString(text)
        
        title_new.set('name', f'{{{counter}}} {output_text}')
        title_new.set('offset', offset)
        title_new.set('duration', duration)
        title_new.set('start', offset)

        title_text = title_new.find('text')
        title_text[0].text = output_text
        title_text[0].set('ref', f'ts{counter}')
        title_new.find('text-style-def').set('id', f'ts{counter}')

        n_spine.append(title_new)
    
    while n_spine[0].tag != 'divider':
        n_spine.remove(n_spine[0])
    n_spine.remove(n_spine[0])

    with open(output, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE fcpxml>\n\n')
        f.write(ET.tostring(root, encoding='UTF-8', xml_declaration=False).decode('utf-8'))

def ConvertSRTTimestamp(arr):
    hours, minutes, seconds, milliseconds = map(float, arr)
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

def ProcessSRTFile(file_path):
    data = []

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = re.split(r'\n{2,}', content.strip())

    for entry in entries:
        lines = entry.split('\n')
        if len(lines) < 3:
            continue

        index, times, *text_lines = lines

        m = re.match(r'(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)', times)
        if m:
            t_start = ConvertSRTTimestamp(m.groups()[:4])
            t_end = ConvertSRTTimestamp(m.groups()[4:])

            data.append((t_start, t_end, text_lines))

    return data

if len(sys.argv) > 2:
    input_path = sys.argv[1]
    output_path = sys.argv[2]

    event_name = ''

    result = TranscribeAudio(input_path, output_path)
    if result:
        print("SRT generated. Trying to create XML...")
        data = ProcessSRTFile(result)
        event_name = result[:-4]

        GenerateFCPXML(data, os.path.join(os.path.dirname(result), "timeline.fcpxml"))
else:
    print("No arguments were passed.")

