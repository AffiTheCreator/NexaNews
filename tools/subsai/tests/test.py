import os
import subprocess
import tempfile
import time
import whisper_online

# Configuration
src_lan = "en"
tgt_lan = "en"
m3u8_stream_path = "https://cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8"
ffmpeg_command = [
    "ffmpeg", "-i", m3u8_stream_path, 
    "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", 
    "-f", "wav", "pipe:1"
]
chunk_size = 128000  # For 4s of audio, based on previous calculations

# Initialize whisper_online
asr = whisper_online.FasterWhisperASR(src_lan, "tiny.en")

online = whisper_online.OnlineASRProcessor(tgt_lan, asr)
online.
online.init()

# Create a temporary file
temp_fd, temp_filename = tempfile.mkstemp(suffix=".wav")

try:
    # Start FFmpeg process
    ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**5)
    
    # if not hasattr(asr, 'sep'):
    #     asr.sep = " "

    with open(temp_filename, 'wb') as temp_file:
        while True:  # Main loop
            try:
                # Read and write audio chunk
                audio_chunk = ffmpeg_process.stdout.read(chunk_size)
                if not audio_chunk:
                    print("No more audio chunks. Ending.")
                    break
                temp_file.write(audio_chunk)
                temp_file.flush()
                
                # Process with whisper_online
                print("Inserting audio chunk...")
                result = online.insert_audio_chunk(temp_filename)                
                print("Processing...")
                print("Insert result:", result)
                print("Insert result type:", type(result))
                try:
                    print(type(asr))
                    print(hasattr(asr, 'sep'))
                    partial_output = online.process_iter()
                except AttributeError as e:
                    print("AttributeError during process_iter: ", str(e))
                    print(f"Attribute Error: {str(e)}")
                    print(f"ASR Object Type: {type(asr)}")
                    print(f"ASR has 'sep': {hasattr(asr, 'sep')}")
                    # Additional logging, recovery, or handling code here
                    continue 
                print("Partial output:", partial_output)
                print("Type of partial_output:", type(partial_output))
            except Exception as e:
                print(f"Error during processing: {str(e)}")
                print("Retrying in 1 second...")
                time.sleep(1)  # Wait before retrying
                
            time.sleep(0.1)  # Optional delay
            
finally:
    # Cleanup
    os.close(temp_fd)
    os.remove(temp_filename)
    ffmpeg_process.terminate()
    ffmpeg_process.wait()
    final_output = online.finish()
    print(final_output)
    online.init()
