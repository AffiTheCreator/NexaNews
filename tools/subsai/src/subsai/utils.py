#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utility functions
"""

import os
import torch
from pysubs2.formats import FILE_EXTENSION_TO_FORMAT_IDENTIFIER
import ffmpeg
import time
import datetime
from datetime import timedelta
import json

def _load_config(config_name, model_config, config_schema):
    """
    Helper function to load default values if `config_name` is not specified

    :param config_name: the name of the config
    :param model_config: configuration provided to the model
    :param config_schema: the schema of the configuration

    :return: config value
    """
    if config_name in model_config:
        return model_config[config_name]
    return config_schema[config_name]["default"]

def create_subtitle_entry(start, end, text):
    """
    Converts timestamps and text into a subtitle entry.

    Parameters:
        start (float): The start time in seconds.
        end (float): The end time in seconds.
        text (str): The transcribed text.

    Returns:
        dict: A subtitle entry with formatted timestamps and text.
    """
    start_time = str(timedelta(seconds=start))
    end_time = str(timedelta(seconds=end))
    
    return {
        "start_time": start_time,
        "end_time": end_time,
        "text": text
    }

def generate_subtitle(complete_now_output):
    """
    Generates a subtitle entry from the "COMPLETE NOW" output.

    Parameters:
        complete_now_output (tuple): A tuple (start, end, text).

    Returns:
        str: A JSON-formatted string of the subtitle entry.
    """
    start, end, text = complete_now_output
    
    # If no valid data, return None
    if start is None or end is None or text.strip() == "":
        print("Empty Subtitle")
        return None
    
    subtitle_entry = create_subtitle_entry(start, end, text)
    return json.dumps(subtitle_entry)

def get_available_devices() -> list:
    """
    Get available devices (cpu and gpus)

    :return: list of available devices
    """
    return ["cpu", *[f"cuda:{i}" for i in range(torch.cuda.device_count())]]


def available_translation_models() -> list:
    """
    Returns available translation models
    from (dl-translate)[https://github.com/xhluca/dl-translate]

    :return: list of available models
    """
    models = [
        "facebook/m2m100_418M",
        "facebook/m2m100_1.2B",
        "facebook/mbart-large-50-many-to-many-mmt",
    ]
    return models


def available_subs_formats(include_extensions=True):
    """
    Returns available subtitle formats
    from :attr:`pysubs2.FILE_EXTENSION_TO_FORMAT_IDENTIFIER`

    :param include_extensions: include the dot separator in file extensions

    :return: list of subtitle formats
    """

    extensions = list(FILE_EXTENSION_TO_FORMAT_IDENTIFIER.keys())

    if include_extensions:
        return extensions
    else:
        # remove the '.' separator from extension names
        return [ext.split(".")[1] for ext in extensions]


# def create_unique_file_name_and_folder_structure(output_folder, output_file_name, start_time):
#   """Creates a unique file name and folder structure to save the files.

#   Args:
#     output_folder: The path to the output folder.
#     output_file_name: The name of the output audio file.
#     start_time: The start time of the output audio file.

#   Returns:
#     A tuple containing the full path to the output audio file and the folder structure.
#   """

#   # Convert the start time to a datetime object.
#   start_time_datetime = datetime.datetime.fromtimestamp(start_time)

#   # Create a unique folder name based on the start time.
#   folder_name = start_time_datetime.strftime("%Y-%m-%d/%H-%M-%S")

#   # Create the folder if it doesn't exist.
#   folder_path = os.path.join(output_folder, folder_name)
#   if not os.path.exists(folder_path):
#     os.makedirs(folder_path)

#   # Create a unique file name based on the start time and the output file name.
#   file_name = start_time_datetime.strftime("%Y-%m-%d/%H-%M-%S_%s.mp3" % output_file_name)

#   # Return the full path to the output audio file and the folder structure.
#   return os.path.join(folder_path, file_name), folder_name



# def cut_audio_file( m3u8_stream_path, output_folder, output_file_name, silence_threshold=-70, duration=2):
#     """Cuts a live M3U8 stream into 10-minute increments when there is silence.

#     Args:
#       m3u8_stream_path: The path to the M3U8 stream.
#       output_folder: The path to the output folder.
#       output_file_name: The name of the output audio file.
#       silence_threshold: The threshold in dB for silence detection.
#       duration: The duration in seconds of silence required before the filter marks the audio as silent.
#     """

#     # Create a unique file name and folder structure.
#     output_file_path, folder_name = create_unique_file_name_and_folder_structure(
#         output_folder, output_file_name, start_time=time.time()
#     )

#     # Start recording the live M3U8 stream to the output audio file.
#     ffmpeg_process = (
#         ffmpeg.input(m3u8_stream_path)
#         .output(
#             output_file_path,
#             format="mp4",
#             codec="copy",
#             t=10,
#             filter="silencedetect=silence_threshold={silence_threshold}:duration={duration}".format(
#                 silence_threshold=silence_threshold, duration=duration
#             ),
#         )
#         .run_async(pipe_stdout=True)
#     )

#     # Start a loop to check for silence in the audio stream.
#     while True:
#         # Read a line of output from ffmpeg.
#         line = ffmpeg_process.stdout.readline().decode()

#         # If the line contains the string "silence_end", then silence has been detected.
#         if "silence_end" in line:
#             # Cut the output audio file at the current point.
#             ffmpeg.input(output_file_path).output(
#                 output_file_path, format="mp4", codec="copy", ss=time.time()
#             ).run()

#             # Create a new unique file name and folder structure.
#             (
#                 output_file_path,
#                 folder_name,
#             ) = create_unique_file_name_and_folder_structure(
#                 output_folder, output_file_name, start_time=time.time()
#             )

#             # Start recording a new output audio file.
#             ffmpeg_process = (
#                 ffmpeg.input(m3u8_stream_path)
#                 .output(
#                     output_file_path,
#                     format="mp4",
#                     codec="copy",
#                     t=10,
#                     filter="silencedetect=silence_threshold={silence_threshold}:duration={duration}".format(
#                         silence_threshold=silence_threshold, duration=duration
#                     ),
#                 )
#                 .run_async(pipe_stdout=True)
#             )

#         # If the ffmpeg process has exited, then stop the loop.
#         if ffmpeg_process.poll() is not None:
#             break

#     # Wait for the ffmpeg process to finish.
#     ffmpeg_process.wait()
#     return True