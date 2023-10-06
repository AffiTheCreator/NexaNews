import argparse
import requests
import os

def upload_audio(url, audio_file):
    # Create a dictionary for the form data
    files = {
        'audio_file': (os.path.basename(audio_file), open(audio_file, 'rb'), 'audio/mpeg')
    }

    # Make the POST request with the form data
    response = requests.post(url, files=files)

    # Check the response
    if response.status_code == 200:
        print("File uploaded successfully.")
    else:
        print(f"Failed to upload file. Status code: {response.status_code}")

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Upload audio to a server.")
    parser.add_argument("url", help="The URL to the server's endpoint")
    parser.add_argument("audio_file", help="Path to the audio file (m3u8 format)")

    args = parser.parse_args()

    # Check if the provided file exists
    if not os.path.exists(args.audio_file):
        print(f"Error: The file '{args.audio_file}' does not exist.")
        exit(1)

    # Call the upload_audio function with the provided arguments
    upload_audio(args.url, args.audio_file)