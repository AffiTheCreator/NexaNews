import subprocess
import librosa
import numpy as np
from whisper_online import FasterWhisperASR, OnlineASRProcessor , create_tokenizer

# Initialize ASR
asr = FasterWhisperASR(lan='en', modelsize='tiny.en')
tokenizer = create_tokenizer('en')
online = OnlineASRProcessor(asr, tokenizer)

# HLS stream URL
stream_url = "https://cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8"

# FFmpeg command to capture and convert audio data
cmd = [
    'ffmpeg',
    '-i', stream_url,  # Input stream URL
    '-f', 'wav',       # Format
    '-acodec', 'pcm_s16le',  # Audio codec
    '-ar', '16000',    # Sample rate
    '-ac', '1',        # Audio channels
    '-',               # Output to stdout
]

# Start FFmpeg process
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)

# Processing loop
try:
    while True:
        # Read a chunk of data
        raw_audio = process.stdout.read(16000*2)  # 1 second of audio data
        
        if not raw_audio:
            break

        # Convert raw audio to numpy array
        audio_chunk = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
        
        # Normalize audio data
        audio_chunk /= np.iinfo(np.int16).max
        
        # Insert audio chunk to Whisper
        online.insert_audio_chunk(audio_chunk)

        # Process and retrieve transcription
        try:
            partial_output = online.process_iter()
            print(partial_output)
        except Exception as e:
            print(f"Error during processing: {str(e)}")
finally:
    # Cleanup
    process.kill()
