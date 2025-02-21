import argparse
import whisperx
import torch
import gc
import os
import warnings
from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer

def main():
    parser = argparse.ArgumentParser(description="Wrap WhisperX command with native Python abstractions.")
    parser.add_argument("--speakers", type=int, required=True, help="Number of speakers")
    parser.add_argument("--audio_path", type=str, required=True, help="Path to the audio file")
    parser.add_argument("--hf_token", type=str, required=True, help="Hugging Face token")
    parser.add_argument("--output_file", type=str, required=True, help="Path to the output text file")
    args = parser.parse_args()

    # Suppress warnings
    warnings.filterwarnings("ignore")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    batch_size = 16  # reduce if low on GPU mem
    compute_type = "float16"  # change to "int8" if low on GPU mem (may reduce accuracy)

    # Prepare the raw output file path
    raw_output_file = args.output_file.replace('.txt', '_raw.txt')

    if os.path.exists(raw_output_file):
        use_existing = input(f"{raw_output_file} already exists. Do you want to skip transcript generation and use the existing file for cleanup? (y/n): ").strip().lower()
    else:
        use_existing = 'n'

    if use_existing != 'y':
        # 1. Transcribe with original Whisper (batched)
        print("Loading Whisper model...")
        model = whisperx.load_model("large-v2", device, compute_type=compute_type)

        print("Loading audio file...")
        audio = whisperx.load_audio(args.audio_path)
        print("Transcribing audio...")
        result = model.transcribe(audio, batch_size=batch_size)

        # delete model if low on GPU resources
        gc.collect()
        torch.cuda.empty_cache()
        del model

        # 2. Align Whisper output
        print("Loading alignment model...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
        print("Aligning transcription...")
        result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)

        # delete model if low on GPU resources
        gc.collect()
        torch.cuda.empty_cache()
        del model_a

        # 3. Assign speaker labels
        print("Loading diarization model...")
        diarize_model = whisperx.DiarizationPipeline(use_auth_token=args.hf_token, device=device)

        # add min/max number of speakers if known
        print("Diarizing audio...")
        diarize_segments = diarize_model(audio, min_speakers=args.speakers, max_speakers=args.speakers)

        print("Assigning speaker labels...")
        result = whisperx.assign_word_speakers(diarize_segments, result)

        # Prepare the diarized output for cleaning
        text_segments = []
        current_speaker = None
        current_text = []
        
        for segment in result["segments"]:
            speaker = segment['speaker']
            text = segment['text']
            
            if speaker != current_speaker:
                if current_speaker is not None:
                    text_segments.append(f"{current_speaker}: {' '.join(current_text)}")
                current_speaker = speaker
                current_text = [text]
            else:
                current_text.append(text)

        if current_text:
            text_segments.append(f"{current_speaker}: {' '.join(current_text)}")

        # Save the raw uncleaned output to a text file
        print(f"Saving raw output to {raw_output_file}...")
        with open(raw_output_file, 'w') as f:
            for line in text_segments:
                f.write(f"{line}\n")
    else:
        # Load the raw uncleaned output from the existing file
        print(f"Loading raw output from {raw_output_file}...")
        with open(raw_output_file, 'r') as f:
            text_segments = f.readlines()

    # Initialize the cleanup model and tokenizer
    model_name_or_path = "meta-llama/Meta-Llama-3-8B-Instruct"
    print("Loading cleanup model and tokenizer...")
    model = AutoModelForCausalLM.from_pretrained(model_name_or_path,
                                               device_map="cuda:0",
                                               trust_remote_code=False,
                                               revision="main",
                                               token=args.hf_token)

    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, use_fast=True, token=args.hf_token)

    # Add these lines to set the padding token
    tokenizer.pad_token = tokenizer.eos_token
    model.config.pad_token_id = tokenizer.pad_token_id

    # Process the text segments line-by-line
    cleaned_lines = []
    for idx, line in enumerate(text_segments):
        print(f"Cleaning line {idx + 1}/{len(text_segments)}")
        cleaning_instruction = (
            "Clean up the following text by removing filler words, correcting grammar, "
            "and making the text more readable. Preserve the speaker labels at the beginning of each line.\n\n"
            f"{line}"
        )

        inputs = tokenizer(cleaning_instruction, return_tensors='pt', padding=True, truncation=True)
        input_ids = inputs.input_ids.cuda()
        attention_mask = inputs.attention_mask.cuda()

        output = model.generate(
            inputs=input_ids,
            attention_mask=attention_mask,
            temperature=0.7,
            do_sample=True,
            top_p=0.95,
            top_k=40,
            max_new_tokens=512
        )
        cleaned_text = tokenizer.decode(output[0], skip_special_tokens=True)
        cleaned_lines.append(cleaned_text.strip())

    # Save the cleaned and diarized output to a text file
    print(f"Saving cleaned output to {args.output_file}...")
    with open(args.output_file, 'w') as f:
        for cleaned_line in cleaned_lines:
            f.write(f"{cleaned_line}\n")

    print("Processing complete.")

if __name__ == "__main__":
    main()
