#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Subs AI Web User Interface (webui)
"""

import importlib
import mimetypes
import os.path
import shutil
import sys
import tempfile
from base64 import b64encode
from pathlib import Path
import time

import pandas as pd
import streamlit as st
from pysubs2.time import ms_to_str, make_time
from streamlit import runtime
from streamlit_player import st_player
from st_aggrid import AgGrid, GridUpdateMode, GridOptionsBuilder, DataReturnMode

from subsai import SubsAI, Tools
from subsai.configs import ADVANCED_TOOLS_CONFIGS
from subsai.utils import (
    available_subs_formats,
    generate_subtitle,
    create_subtitle_entry,
)
from streamlit.web import cli as stcli
from tempfile import NamedTemporaryFile

from subsai.models.whisper_online import (
    FasterWhisperASR,
    OnlineASRProcessor,
    create_tokenizer,
)
import subprocess
import numpy as np
import signal
import debugpy
import multiprocessing
from elasticsearch import Elasticsearch, helpers
import logging
import logging.handlers
import interpreter



__author__ = "abdeladim-s"
__contact__ = "https://github.com/abdeladim-s"
__copyright__ = "Copyright 2023,"
__deprecated__ = False
__license__ = "GPLv3"
__version__ = importlib.metadata.version("subsai")  # type: ignore

subs_ai = SubsAI()
tools = Tools()
es = Elasticsearch([{"host": "elasticsearch", "port": 9200, "scheme": "http"}])


class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return '[%s] %s' % (self.extra['context'], msg), kwargs


def worker_setup(log_queue, context):
    logger = logging.getLogger(__name__)
    logger.addHandler(logging.handlers.QueueHandler(log_queue))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return ContextAdapter(logger, {'context': context})


def setup_logger():
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Prevent log messages from being passed to the root logger
    return logger

logger = setup_logger()

def ensure_index_exists(index_name):
    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name)


def insert_subtitle_to_es(subtitle, index_name):
    
    try:
        es.index(index=index_name, document=subtitle)
    except Exception as e:
        logger.error(e, exc_info=True)
    finally:
        logger.info("Subtitle Inserted !")


def _get_key(model_name: str, config_name: str) -> str:
    """
    a simple helper method to generate unique key for configs UI

    :param model_name: name of the model
    :param config_name: configuration key
    :return: str key
    """
    return model_name + "-" + config_name


def _config_ui(config_name: str, key: str, config: dict):
    """
    helper func that returns the config UI based on the type of the config

    :param config_name: the name of the model
    :param key: the key to set for the config ui
    :param config: configuration object

    :return: config UI streamlit objects
    """
    
    if config["type"] == str:
        return st.text_input(
            config_name, help=config["description"], key=key, value=config["default"]
        )
    elif config["type"] == list:
        return st.selectbox(
            config_name,
            config["options"],
            index=config["options"].index(config["default"]),
            help=config["description"],
            key=key,
        )
    elif config["type"] == float or config["type"] == int:
        if config["default"] is None:
            return st.text_input(
                config_name,
                help=config["description"],
                key=key,
                value=config["default"],
            )
        return st.number_input(
            label=config_name,
            help=config["description"],
            key=key,
            value=config["default"],
        )
    elif config["type"] == bool:
        return st.checkbox(
            label=config_name,
            value=config["default"],
            help=config["description"],
            key=key,
        )
    else:
        logger.info(f"Warning: {config_name} does not have a supported UI")
        pass


def _generate_config_ui(model_name, config_schema):
    """
    Loops through configuration dict object and generates the configuration UIs
    :param model_name:
    :param config_schema:
    :return: Config UIs
    """
    for config_name in config_schema:
        config = config_schema[config_name]
        key = _get_key(model_name, config_name)
        _config_ui(config_name, key, config)


def _get_config_from_session_state(
    model_name: str, config_schema: dict, notification_placeholder
) -> dict:
    """
    Helper function to get configuration dict from the generated config UIs

    :param model_name: name of the model
    :param config_schema: configuration schema
    :param notification_placeholder: notification placeholder streamlit object in case of errors

    :return: dict of configs
    """
    model_config = {}
    for config_name in config_schema:
        key = _get_key(model_name, config_name)
        try:
            value = st.session_state[key]
            if config_schema[config_name]["type"] == str:
                if value == "None" or value == "":
                    value = None
            elif config_schema[config_name]["type"] == float:
                if value == "None" or value == "":
                    value = None
                else:
                    value = float(value)
            elif config_schema[config_name]["type"] == int:
                if value == "None" or value == "":
                    value = None
                else:
                    value = int(value)

            model_config[config_name] = value
        except KeyError as e:
            pass
        except Exception as e:
            notification_placeholder.error(f"Problem parsing configs!! \n {e}")
            return
    return model_config


def _vtt_base64(subs_str: str, mime="application/octet-stream"):
    """
    Helper func to return vtt subs as base64 to load them into the video

    :param subs_str: str of the subtitles
    :param mime: mime type

    :return: base64 data
    """
    data = b64encode(subs_str.encode()).decode()
    return f"data:{mime};base64,{data}"


def _media_file_base64(file_path, mime="video/mp4", start_time=0):
    """
    Helper func that returns base64 of the media file

    :param file_path: path of the file
    :param mime: mime type
    :param start_time: start time

    :return: base64 of the media file
    """
    
    if file_path == "":
        data = ""
        return [{"type": mime, "src": f"data:{mime};base64,{data}#t={start_time}"}]
    with open(file_path, "rb") as media_file:
        data = b64encode(media_file.read()).decode()
        try:
            mime = mimetypes.guess_type(file_path)[0]
        except Exception as e:
            logger.info(f"Unrecognized video type!")
    return [{"type": mime, "src": f"data:{mime};base64,{data}#t={start_time}"}]


@st.cache_resource
def _create_translation_model(model_name: str):
    """
    Returns a translation model and caches it

    :param model_name: name of the model
    :param model_config: configs

    :return: translation model
    """
    translation_model = tools.create_translation_model(model_name)
    return translation_model

@st.cache_data
def _transcribe(file_path, model_name, model_config):
    """
    Returns and caches the generated subtitles

    :param file_path: path of the media file
    :param model_name: name of the model
    :param model_config: configs dict

    :return: `SSAFile` subs
    """
    model = subs_ai.create_model(model_name, model_config=model_config)
    subs = subs_ai.transcribe(media_file=file_path, model=model)
    return subs


def _subs_df(subs):
    """
    helper function that returns a :class:`pandas.DataFrame` from subs object

    :param subs: subtitles

    :return::class:`pandas.DataFrame`
    """
    sub_table = []
    if subs is not None:
        for sub in subs:
            row = [
                ms_to_str(sub.start, fractions=True),
                ms_to_str(sub.end, fractions=True),
                sub.text,
            ]
            sub_table.append(row)

    df = pd.DataFrame(sub_table, columns=["Start time", "End time", "Text"])
    return df


footer = """
<style>
    #page-container {
      position: relative;
    }

    footer{
        visibility:hidden;
    }

    .footer {
    position: relative;
    left: 0;
    top:230px;
    bottom: 0;
    width: 100%;
    background-color: transparent;
    color: #808080; /* theme's text color hex code at 50 percent brightness*/
    text-align: left; /* you can replace 'left' with 'center' or 'right' if you want*/
    }
</style>

<div id="page-container">
    <div class="footer">
        <p style='font-size: 0.875em;'>
        Made with ❤ by <a style='display: inline; text-align: left;' href="https://github.com/abdeladim-s" target="_blank">abdeladim-s</a></p>
    </div>
</div>
"""


def handle_ffmpeg_stream(data_queue, channel_name, logger_ffmpeg):
    logger = logging.getLogger(__name__)
    # Define FFmpeg command. Replace [...] with your actual FFmpeg command
    m3u8_stream_path = subs_ai.get_channel_info(channel_name)["url"]
    # logger.info("Channel URL : " + m3u8_stream_path)

    cmd = [
        "ffmpeg",
        "-loglevel",
        "quiet",
        "-i",
        m3u8_stream_path,  # Input stream URL
        "-f",
        "wav",  # Format
        "-acodec",
        "pcm_s16le",  # Audio codec
        "-ar",
        "16000",  # Sample rate
        "-ac",
        "1",  # Audio channels
        "-",  # Output to stdout
    ]

    try:
        # Start FFmpeg process
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8
        )

        while True:
            # Read a chunk of raw audio data
            raw_audio = process.stdout.read(16000 * 2)  # 1 second of audio data

            # Check if we got any data
            if not raw_audio:
                break  # Exit the loop if no more data

            # Convert raw audio to numpy array and normalize
            audio_chunk = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
            audio_chunk /= np.iinfo(np.int16).max

            # Place audio_chunk on the queue for the ASR process
            data_queue.put(audio_chunk)
    except Exception as e:
        logger_ffmpeg.error(f"Error in FFmpeg stream: {str(e)}", exc_info=True)
    finally:
        process.terminate()  # Ensure FFmpeg is terminated cleanly


def handle_asr_engine(data_queue, channel_name , logger_asr):
    src_lan = "en"  # source language
    # Initialize ASR engine. Replace [...] with your actual initialization code.
    asr_engine = FasterWhisperASR(lan=src_lan, modelsize="tiny.en")
    tokenizer = create_tokenizer(src_lan)
    online = OnlineASRProcessor(asr_engine, tokenizer)

    try:
        while True:
            # Get a chunk of audio data from the queue
            audio_chunk = data_queue.get()

            # Break if a special "stop" signal is received (you might send a None, for example)
            if audio_chunk is None:
                break

            # Insert audio chunk to Whisper
            online.insert_audio_chunk(audio_chunk)
            # Process and retrieve transcription
            try:
                transcription_full_output = online.transcriptioChuncker()
                if transcription_full_output:
                    subtitle_completed = generate_subtitle(
                        transcription_full_output, channel_name
                    )
                    logger_asr.info("Subtitle: " + subtitle_completed)
                    insert_subtitle_to_es(subtitle_completed, "subtitles")
                    st.session_state["asr_process"] = subtitle_completed  
                    saveSubsToFile(transcription_full_output)
                    # add interpreter code
                # transcription_full_output = online.process_iter()
            except Exception as e:
                logger_asr.error(f"Error during processing: {str(e)}", exc_info=True)
            # Update UI with transcription. Note: you'll need to determine a safe way to do this in your Streamlit app.
    except Exception as e:
        logger_asr.error(f"Error in ASR engine: {str(e)}", exc_info=True)



def saveSubsToFile(data):
    subtitleTupleIndex = 2
    current_time = time.time()
    
    # Arquivo é criado a cada 10 minutos
    interval_seconds = 600
    
    # Calcula o número do arquivo com base no horário atual e no intervalo
    file_number = int(current_time / interval_seconds)
    
    # Define o nome do arquivo com base no número do arquivo
    file_path = f"/home/nexanews/mysubs_{file_number}.txt"
    
    print(f"Saving to file: {file_path}")
    
    # Abre o arquivo em modo de anexação (append) e escreve os dados
    with open(file_path, 'a') as file:
        file.write(str(data[subtitleTupleIndex]))


def listener_process(log_queue):
    try:
        logger = setup_logger()
        logger.info("[Listener Process] Started.")
        while True:
            print("[Listener Process] Waiting for log record...")
            record = log_queue.get()
            print("[Listener Process] Log record received.")
            if record is None:
                logger.info("[Listener Process] Termination signal received.")
                break
            logger.handle(record)
        logger.info("[Listener Process] Terminating.")
    except Exception as e:
        print(f"[Listener Process] Error: {str(e)}")
    finally:
        print("[Listener Process] Ended.")

def start_processes(channel_name):
    data_queue = multiprocessing.Queue()
    log_queue = multiprocessing.Queue()

    print("[Main] Starting listener...")
    listener = multiprocessing.Process(target=listener_process, args=(log_queue,))
    listener.start()

    print("[Main] Starting ffmpeg_process...")
    ffmpeg_process = multiprocessing.Process(target=handle_ffmpeg_stream, args=(data_queue, channel_name, worker_setup(log_queue, 'ffmpeg_process')))
    ffmpeg_process.start()

    print("[Main] Starting asr_process...")
    asr_process = multiprocessing.Process(
        target=handle_asr_engine, args=(data_queue, channel_name, worker_setup(log_queue, 'asr_process'))
    )
    asr_process.start()

    return ffmpeg_process, asr_process, data_queue, listener, log_queue



def stop_processes(ffmpeg_process, asr_process, data_queue, log_queue):
    data_queue.put(None)
    log_queue.put(None)
    ffmpeg_process.terminate()
    asr_process.terminate()
    ffmpeg_process.join()
    asr_process.join()

#     return stt_model_name
def webui() -> None:
    """
    main web UI
    :return: None
    """

    st.set_page_config(
        page_title="NexaNews",
        page_icon="🎞️",
        menu_items={
            "Get Help": "https://github.com/abdeladim-s/subsai",
            "Report a bug": "https://github.com/abdeladim-s/subsai/issues",
            "About": f"### [Subs AI](https://github.com/abdeladim-s/subsai) \nv{__version__} "
            f"\n \nLicense: GPLv3",
        },
        layout="wide",
        initial_sidebar_state="auto",
    )

    st.sidebar.title("Settings")

    if "transcribed_subs" in st.session_state:
        subs = st.session_state["transcribed_subs"]
    else:
        subs = None

    notification_placeholder = st.empty()

    with st.sidebar:
        channel_name = ""
        file_path = ""
        transcribe_button = False
        with st.expander("Media Source", expanded=True):
            file_mode = st.selectbox(
                "Select file mode",
                ["Local path", "Upload", "IPTV"],
                index=2,
                help="Use `Local Path` if you are on a local machine, or use `Upload` to "
                "upload your files if you are using a remote server or IPTV to perform live ASR",
            )
            if file_mode == "Local path":
                file_path = st.text_input(
                    "Media file path", help="Absolute path of the media file"
                )
                transcribe_button = st.button("Transcribe", type="primary")

            elif file_mode == "Upload":
                uploaded_file = st.file_uploader("Choose a media file")
                if uploaded_file is not None:
                    temp_dir = tempfile.TemporaryDirectory()
                    tmp_dir_path = temp_dir.name
                    file_path = os.path.join(tmp_dir_path, uploaded_file.name)
                    file = open(file_path, "wb")
                    file.write(uploaded_file.getbuffer())
                else:
                    file_path = ""

                transcribe_button = st.button("Transcribe", type="primary")

            elif file_mode == "IPTV":
                # channel_list_json = SubsAI.available_channels()
                # stream_url = st.text_input('Stream URL', help='The URL Address for the Live Stream'  )
                channel_name = st.selectbox(
                    "Select Channel",
                    SubsAI.available_channels(),
                    index=1,
                    help="Select a channel to use ",
                )

        if file_mode == "Upload" or file_mode == "Local path":
            stt_model_name = st.selectbox(
                "Select Model",
                SubsAI.available_models(),
                index=0,
                help="Select an AI model to use for transcription",
            )

            with st.expander("Model Description", expanded=True):
                info = SubsAI.model_info(stt_model_name)
                st.info(info["description"] + "\n" + info["url"])

            with st.sidebar.expander("Model Configs", expanded=False):
                config_schema = SubsAI.config_schema(stt_model_name)
                _generate_config_ui(stt_model_name, config_schema)
        transcribe_loading_placeholder = st.empty()
        start_button = st.button("Start Job", type="primary")
        stop_button = st.button("Stop Job", type="primary")

    if transcribe_button:
        config_schema = SubsAI.config_schema(stt_model_name)
        model_config = _get_config_from_session_state(
            stt_model_name, config_schema, notification_placeholder
        )
        subs = _transcribe(file_path, stt_model_name, model_config)
        st.session_state["transcribed_subs"] = subs
        transcribe_loading_placeholder.success("Done!", icon="✅")

    # Persistent state to keep track of processes
    if "ffmpeg_process" not in st.session_state:
        st.session_state["ffmpeg_process"] = None
    if "asr_process" not in st.session_state:
        st.session_state["asr_process"] = None
    # Start processes
    if (
        start_button and st.session_state.ffmpeg_process is None and st.session_state.asr_process is None ):
        # When you want to start the processes:
        # ffmpeg_process, asr_process, data_queue = start_processes(channel_name)
        # And when you want to stop them:
        (
            st.session_state.ffmpeg_process,
            st.session_state.asr_process,
            st.session_state.data_queue,
            st.session_state.listener,
            st.session_state.log_queue,
        ) = start_processes(channel_name)
        st.write("Processes started!")
    # Stop processes
    elif (
        stop_button
        and st.session_state.ffmpeg_process is not None
        and st.session_state.asr_process is not None
    ):
        stop_processes(
            st.session_state.ffmpeg_process,
            st.session_state.asr_process,
            st.session_state.data_queue,
            st.session_state.log_queue,
        )
        st.session_state.ffmpeg_process, st.session_state.asr_process = None, None
        st.write("Processes stopped!")

    with st.expander("Post Processing Tools", expanded=False):
        basic_tool = st.selectbox(
            "Basic tools",
            options=["", "Set time", "Shift"],
            help="Basic tools to modify subtitles",
        )
        if basic_tool == "Set time":
            st.info("Set subtitle time")
            sub_index = st.selectbox("Subtitle index", options=range(len(subs)))
            time_to_change = st.radio(
                "Select what you want to modify", options=["Start time", "End time"]
            )
            h_col, m_col, s_col, ms_col = st.columns([1, 1, 1, 1])
            with h_col:
                h = st.number_input("h")
            with m_col:
                m = st.number_input("m")
            with s_col:
                s = st.number_input("s")
            with ms_col:
                ms = st.number_input("ms")
            submit = st.button("Modify")
            if submit:
                if time_to_change == "Start time":
                    subs[sub_index].start = make_time(h, m, s, ms)
                elif time_to_change == "End time":
                    subs[sub_index].end = make_time(h, m, s, ms)
                st.session_state["transcribed_subs"] = subs

        elif basic_tool == "Shift":
            st.info("Shift all subtitles by constant time amount")
            h_col, m_col, s_col, ms_col, frames_col, fps_col = st.columns(
                [1, 1, 1, 1, 1, 1]
            )
            with h_col:
                h = st.number_input("h", key="h")
            with m_col:
                m = st.number_input("m", key="m")
            with s_col:
                s = st.number_input("s", key="s")
            with ms_col:
                ms = st.number_input("ms", key="ms")
            with frames_col:
                frames = st.number_input("frames")
            with fps_col:
                fps = st.number_input("fps")
            submit = st.button("Shift")
            if submit:
                subs.shift(
                    h,
                    m,
                    s,
                    ms,
                    frames=None if frames == 0 else frames,
                    fps=None if fps == 0 else fps,
                )
                st.session_state["transcribed_subs"] = subs
        advanced_tool = st.selectbox(
            "Advanced tools",
            options=["", *list(ADVANCED_TOOLS_CONFIGS.keys())],
            help="some post processing tools",
        )
        if advanced_tool == "Translation":
            configs = ADVANCED_TOOLS_CONFIGS[advanced_tool]
            description = configs["description"] + "\n\nURL: " + configs["url"]
            config_schema = configs["config_schema"]
            st.info(description)
            _generate_config_ui(advanced_tool, config_schema)
            translation_config = _get_config_from_session_state(
                advanced_tool, config_schema, notification_placeholder
            )
            download_and_create_model = st.checkbox(
                "Download and create the model",
                value=False,
                help="This will download the weights" " and initializes the model",
            )
            if download_and_create_model:
                translation_model = _create_translation_model(
                    translation_config["model"]
                )
                source_language = st.selectbox(
                    "Source language",
                    options=tools.available_translation_languages(translation_model),
                )
                target_language = st.selectbox(
                    "Target language",
                    options=tools.available_translation_languages(translation_model),
                )
                b1, b2 = st.columns([1, 1])
                with b1:
                    submitted = st.button("Translate")
                    if submitted:
                        if "transcribed_subs" not in st.session_state:
                            st.error("No subtitles to translate")
                        else:
                            with st.spinner("Processing (This may take a while) ..."):
                                translated_subs = tools.translate(
                                    subs=subs,
                                    source_language=source_language,
                                    target_language=target_language,
                                    model=translation_model,
                                    translation_configs=translation_config,
                                )
                                st.session_state["original_subs"] = st.session_state[
                                    "transcribed_subs"
                                ]
                                st.session_state["transcribed_subs"] = translated_subs
                            notification_placeholder.success("Success!", icon="✅")
                with b2:
                    reload_transcribed_subs = st.button("Reload Original subtitles")
                    if reload_transcribed_subs:
                        if "original_subs" in st.session_state:
                            st.session_state["transcribed_subs"] = st.session_state[
                                "original_subs"
                            ]
                        else:
                            st.error("Original subs are already loaded")

        if advanced_tool == "ffsubsync":
            configs = ADVANCED_TOOLS_CONFIGS[advanced_tool]
            description = configs["description"] + "\n\nURL: " + configs["url"]
            config_schema = configs["config_schema"]
            st.info(description)
            _generate_config_ui(advanced_tool, config_schema)
            ffsubsync_config = _get_config_from_session_state(
                advanced_tool, config_schema, notification_placeholder
            )
            submitted = st.button("ffsubsync")
            if submitted:
                with st.spinner("Processing (This may take a while) ..."):
                    synced_subs = tools.auto_sync(subs, file_path, **ffsubsync_config)
                    st.session_state["original_subs"] = st.session_state[
                        "transcribed_subs"
                    ]
                    st.session_state["transcribed_subs"] = synced_subs
                notification_placeholder.success("Success!", icon="✅")

    subs_column, video_column = st.columns([4, 3])

    with subs_column:
        
        if "transcribed_subs" in st.session_state:
            df = _subs_df(st.session_state["transcribed_subs"])
        else:
            df = pd.DataFrame()
        gb = GridOptionsBuilder()
        # customize gridOptions
        gb.configure_default_column(
            groupable=False, value=True, enableRowGroup=True, editable=True
        )

        gb.configure_column(
            "Start time",
            type=["customDateTimeFormat"],
            custom_format_string="HH:mm:ss",
            pivot=False,
            editable=False,
        )
        gb.configure_column(
            "End time",
            type=["customDateTimeFormat"],
            custom_format_string="HH:mm:ss",
            pivot=False,
            editable=False,
        )
        gb.configure_column("Text", type=["textColumn"], editable=True)

        gb.configure_grid_options(
            domLayout="normal",
            allowContextMenuWithControlKey=False,
            undoRedoCellEditing=True,
        )
        gb.configure_selection(use_checkbox=False)

        gridOptions = gb.build()

        returned_grid = AgGrid(
            df,
            height=500,
            width="100%",
            fit_columns_on_grid_load=True,
            theme="alpine",
            update_on=["rowValueChanged"],
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            try_to_convert_back_to_original_types=False,
            gridOptions=gridOptions,
        )

        # change subs
        if len(returned_grid["selected_rows"]) != 0:
            st.session_state["selected_row_idx"] = returned_grid.selected_rows[0][
                "_selectedRowNodeInfo"
            ]["nodeRowIndex"]
            try:
                selected_row = returned_grid["selected_rows"][0]
                changed_sub_index = selected_row["_selectedRowNodeInfo"]["nodeRowIndex"]
                changed_sub_text = selected_row["Text"]
                subs = st.session_state["transcribed_subs"]
                subs[changed_sub_index].text = changed_sub_text
                st.session_state["transcribed_subs"] = subs
            except Exception as e:
                logger.error(e , exc_info=True)
                notification_placeholder.error("Error parsing subs!", icon="🚨")

    with video_column:
        if subs is not None:
            subs = st.session_state["transcribed_subs"]
            vtt_subs = _vtt_base64(subs.to_string(format_="vtt"))
        else:
            vtt_subs = ""

        options2 = {
            "playback_rate": 1,
            "playing": True,
            "muted": True,
            "controls": True,
            "config": {
                "file": {
                    "forceHLS": True,  # Might force using HLS for .m3u8 files
                    "attributes": {
                        "crossOrigin": "anonymous",  # Might handle CORS issues
                    },
                }
            },
        }
        options = {
            "playback_rate": 1,
            "config": {
                "file": {
                    "attributes": {"crossOrigin": "true"},
                    "tracks": [
                        {
                            "kind": "subtitles",
                            "src": vtt_subs,
                            "srcLang": "default",
                            "default": "true",
                        },
                    ],
                }
            },
        }

        if "asr_process" in st.session_state or "ffmpeg_process" in st.session_state:
            # event = st_player(subs_ai.get_channel_info(channel_name)["url"], **options, height=500, key="player-live")
            event = st_player(
                url=subs_ai.get_channel_info(channel_name)["url"],
                **options2,
                height=400,
            )
        else:
            event = st_player(
                _media_file_base64(file_path),
                **options,
                height=500,
                key="player-offline",
            )

    with st.expander("Export subtitles file"):
        media_file = Path(file_path)
        export_format = st.radio("Format", available_subs_formats())
        export_filename = st.text_input("Filename", value=media_file.stem)
        if export_format == ".sub":
            fps = st.number_input(
                "Framerate", help="Framerate must be specified when writing MicroDVD"
            )
        else:
            fps = None
        submitted = st.button("Export")
        if submitted:
            subs = st.session_state["transcribed_subs"]
            exported_file = media_file.parent / (export_filename + export_format)
            subs.save(exported_file, fps=fps)
            st.success(f"Exported file to {exported_file}", icon="✅")
            with open(exported_file, "r") as f:
                st.download_button(
                    "Download", f, file_name=export_filename + export_format
                )

    with st.expander("Merge subtitles with video"):
        media_file = Path(file_path)
        subs_lang = st.text_input(
            "Subtitles language", value="English", key="merged_video_subs_lang"
        )
        exported_video_filename = st.text_input(
            "Filename",
            value=f"{media_file.stem}-subs-merged",
            key="merged_video_out_file",
        )
        submitted = st.button("Merge", key="merged_video_export_btn")
        if submitted:
            subs = st.session_state["transcribed_subs"]
            exported_file_path = tools.merge_subs_with_video(
                {subs_lang: subs}, str(media_file.resolve()), exported_video_filename
            )
            st.success(f"Exported file to {exported_file_path}", icon="✅")
            with open(exported_file_path, "rb") as f:
                st.download_button(
                    "Download",
                    f,
                    file_name=f"{exported_video_filename}{media_file.suffix}",
                )

    st.markdown(footer, unsafe_allow_html=True)


def run():
    if runtime.exists():
        webui()
    else:
        debugpy.listen(("0.0.0.0", 5678))
        # debugpy.wait_for_client()
        sys.argv = ["streamlit", "run", __file__, "--theme.base", "dark"] + sys.argv
        sys.exit(stcli.main())

if __name__ == "__main__":
    run()