import os
import re
import sys
import copy
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
from datetime import timedelta

import whisper
from whisper.utils import get_writer

# IMPORTANT NOTE! Make sure that ffmpeg is installed on the OS
# or else you will get cryptic errors that have nothing to do
# with this script.

def ensure_directory_exists(file_path):
    """Ensure the directory for the given file path exists."""
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

def ConvertToXmlString(text_lines):
    combined_text = "\n".join(text_lines)
    return saxutils.escape(combined_text)

def TranscribeAudio(path, output):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file '{path}' not found.")
    
    ensure_directory_exists(output)
    print(f"Transcribing {path} to {output}")
    
    model = whisper.load_model("large", device="cuda")  # Change model as needed
    print("Whisper model loaded.")

    result = model.transcribe(audio=path, initial_prompt="prompt", word_timestamps=True)
    
    print("Transcription finished.")

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
        return (int(numerator), int(denominator)) if return_tuple else float(numerator) / float(denominator)
    return float(s.rstrip('s'))

def ConvertTimestampToXml(t, framerate_tuple):
    multiplier, denominator = framerate_tuple
    x = int(t * denominator)
    return f'{x // denominator}s' if x % multiplier == 0 else f'{x}/{denominator}s'

def GenerateFCPXML(data, output, template_path="template.xml", event_name="CC_XML", framerate=29.97):
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template XML file '{template_path}' not found.")
    
    ensure_directory_exists(output)
    xml = ET.parse(template_path)
    root = xml.getroot()
    
    n_resources = root.find('resources')
    xml_framerate = n_resources.find('format').get('frameDuration')
    xml_framerate_fps = 1 / ConvertXmlTimestamp(xml_framerate)
    
    if abs(framerate - xml_framerate_fps) > 0.005:
        raise ValueError(f'Template frame rate {xml_framerate_fps:.2f}fps is inconsistent with specified framerate {framerate:.2f}fps.')
    
    framerate_tuple = ConvertXmlTimestamp(xml_framerate, return_tuple=True)
    
    n_library = root.find('library')
    n_event = n_library.find('event')
    n_event.set('name', event_name)
    n_project = n_event.find('project')
    n_project.set('name', event_name)
    
    n_sequence = n_project.find('sequence')
    n_spine = n_sequence.find('spine')
    title_proto = n_spine.find('title')
    n_spine.append(ET.Element('divider'))
    
    for counter, (t_start, t_end, text) in enumerate(data, start=1):
        if counter == 1 and t_start > 0:
            gap_new = ET.Element('gap', {
                'name': 'Gap',
                'offset': '0s',
                'duration': ConvertTimestampToXml(t_start, framerate_tuple),
                'start': '0s'
            })
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
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"SRT file '{file_path}' not found.")
    
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

if __name__ == "__main__":
    if len(sys.argv) > 2:
        input_path = os.path.normpath(sys.argv[1])
        output_path = os.path.normpath(sys.argv[2])
        
        try:
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"File not found: {input_path}")

            print(f"File exists at: {os.path.abspath(input_path)}")

            result = TranscribeAudio(input_path, output_path)
            print("SRT generated. Creating XML...")
            data = ProcessSRTFile(result)
            xml_output = os.path.join(os.path.dirname(result), "timeline.fcpxml")
            GenerateFCPXML(data, xml_output)
            print(f"FCPXML file saved at {xml_output}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: script.py <input_audio> <output_srt>")
