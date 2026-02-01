"""Main file for the Jarvis project"""
import os
from os import PathLike
from time import time
import asyncio
from typing import Union

from dotenv import load_dotenv
import openai
from deepgram import Deepgram
import pygame
from pygame import mixer
import elevenlabs

import webbrowser
from record import speech_to_text
import openmeteo_requests
import requests_cache
import pandas as pd
from geopy.geocoders import Nominatim
from retry_requests import retry
import threading
import time

# System control imports
import subprocess
import shlex
import logging
import json
from pathlib import Path
import getpass
import shutil
from datetime import datetime

# Optional GUI automation (screenshots / typing)
try:
    import pyautogui
    PY_AUTO = True
except Exception:
    PY_AUTO = False

# Optional local TTS fallback (pyttsx3)
try:
    import pyttsx3
    PY_TTS = True
except Exception:
    PY_TTS = False

# Load API keys
load_dotenv()

missing_keys = []

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    missing_keys.append("OPENAI_API_KEY")

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    missing_keys.append("DEEPGRAM_API_KEY")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    missing_keys.append("ELEVENLABS_API_KEY")

if missing_keys:
    print("Error: The following API keys are missing from your .env file:")
    for key in missing_keys:
        print(f"- {key}")
    print("\nPlease add them to your .env file in the root directory of the project.")
    print("Refer to the README.md for more details on how to set up your API keys.")
    exit(1)

# Admin password (optional) and logging/allowlist setup
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Ensure config and log folders exist
Path("config").mkdir(parents=True, exist_ok=True)
Path("logs").mkdir(parents=True, exist_ok=True)

# Setup basic logging
logging.basicConfig(
    filename=Path("logs") / "jarvis.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Load allowlist if present (fall back to safe defaults)
ALLOWLIST_PATH = Path("config") / "allowlist.json"
if ALLOWLIST_PATH.exists():
    try:
        with open(ALLOWLIST_PATH, "r", encoding="utf-8") as f:
            ALLOWLIST = json.load(f)
    except Exception as e:
        logging.warning(f"Failed to load allowlist: {e}")
        ALLOWLIST = {"programs": [], "allow_delete": False, "dangerous_keywords": []}
else:
    ALLOWLIST = {"programs": [], "allow_delete": False, "dangerous_keywords": []}

# Initialize APIs
gpt_client = openai.Client(api_key=OPENAI_API_KEY)
deepgram = Deepgram(DEEPGRAM_API_KEY)
elevenlabs.set_api_key(ELEVENLABS_API_KEY)

# mixer is a pygame module for playing audio
mixer.init()

# Change the context if you want to change Jarvis' personality
context = "You are Jarvis, Alex's human assistant. You are witty and full of personality. Your answers should be limited to 1-2 short sentences."
conversation = {"Conversation": []}
RECORDING_PATH = "audio/recording.wav"


# --------------------- System control helpers ---------------------
def _safe_log(action: str, info: str = "") -> None:
    logging.info(f"ACTION: {action} | INFO: {info}")


def load_allowlist(path: str = "config/allowlist.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"programs": [], "allow_delete": False, "dangerous_keywords": []}


def is_allowed_program(program: str) -> bool:
    name = Path(program).stem.lower()
    return any(name == p.lower() or p.lower() in name for p in ALLOWLIST.get("programs", []))


def require_admin_confirmation(command: str, reason: str = "requires confirmation") -> bool:
    """Ask for confirmation. If ADMIN_PASSWORD is set, require it; otherwise ask y/n."""
    print(f"Command '{command}' {reason}.")
    if ADMIN_PASSWORD:
        entered = getpass.getpass("Enter admin password: ")
        if entered == ADMIN_PASSWORD:
            _safe_log("admin_confirmed", command)
            return True
        print("Incorrect password.")
        _safe_log("admin_failed", command)
        return False
    else:
        ans = input("Type 'yes' to confirm: ")
        ok = ans.strip().lower() == "yes"
        if ok:
            _safe_log("confirmed", command)
        else:
            _safe_log("confirmation_denied", command)
        return ok


def execute_system_command(command: str) -> str:
    """Execute a system command safely using the allowlist and confirmation steps."""
    try:
        parts = shlex.split(command)
    except Exception:
        parts = command.split()

    if not parts:
        return "No command provided."

    prog = parts[0]

    if is_allowed_program(prog):
        try:
            subprocess.Popen(parts, shell=False)
            _safe_log("execute", command)
            return f"Executed {prog}."
        except Exception as e:
            logging.exception("Execution failed")
            return f"Failed to execute {prog}: {e}"
    else:
        # Not explicitly allowed - require admin approval
        if require_admin_confirmation(command, reason="is not on the allowlist and requires admin approval"):
            try:
                subprocess.Popen(parts, shell=False)
                _safe_log("execute_admin", command)
                return f"Executed {prog} with admin approval."
            except Exception as e:
                logging.exception("Admin execution failed")
                return f"Failed to execute {prog}: {e}"
        return "Command not executed."


def safe_open_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    try:
        os.startfile(str(p))  # Windows specific
        _safe_log("open_file", str(p))
        return f"Opened file {p}"
    except Exception as e:
        logging.exception("Failed to open file")
        return f"Failed to open file: {e}"


def take_screenshot() -> str:
    if not PY_AUTO:
        return "Screenshot functionality is not available (pyautogui not installed)."
    Path("screenshots").mkdir(exist_ok=True)
    filename = Path("screenshots") / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        img = pyautogui.screenshot()
        img.save(str(filename))
        _safe_log("screenshot", str(filename))
        return f"Saved screenshot to {filename}"
    except Exception as e:
        logging.exception("Screenshot failed")
        return f"Failed to take screenshot: {e}"


def type_text(text: str) -> str:
    if not PY_AUTO:
        return "Typing functionality is not available (pyautogui not installed)."
    try:
        pyautogui.write(text)
        _safe_log("type", text)
        return "Typed text."
    except Exception as e:
        logging.exception("Type failed")
        return f"Failed to type text: {e}"

# -----------------------------------------------------------------


def get_weather(city: str) -> str:
    """
    Get the weather for a given city.
    """
    # Setup the Open-Meteo API client with caching and retry logic
    cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # Get latitude and longitude for the city
    geolocator = Nominatim(user_agent="jarvis")
    location = geolocator.geocode(city)
    if not location:
        return f"Sorry, I couldn't find the weather for {city}."

    # Define parameters for the weather request
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "hourly": ["temperature_2m"],
        "timezone": "auto"
    }

    # Make the API call
    responses = openmeteo.get("https://api.open-meteo.com/v1/forecast", params=params)

    # Process the first location's data
    response = responses[0]
    hourly = response.Hourly()
    hourly_data = {"date": pd.to_datetime(hourly.Time(), unit="s"),
                   "temperature_2m": hourly.Variables(0).ValuesAsNumpy()}
    
    hourly_dataframe = pd.DataFrame(data=hourly_data)
    
    return f"The current temperature in {city} is {hourly_dataframe['temperature_2m'][0]} degrees Celsius."


def set_reminder(reminder: str, delay: int) -> None:
    """
    Set a reminder.
    """
    def play_reminder():
        print(f"Reminder: {reminder}")
        # In the future, you can add code to play a sound or send a notification here.

    timer = threading.Timer(delay, play_reminder)
    timer.start()


def request_gpt(prompt: str) -> str:
    """
    Send a prompt to the GPT-3 API and return the response.

    Args:
        - state: The current state of the app.
        - prompt: The prompt to send to the API.

    Returns:
        The response from the API.
    """
    response = gpt_client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f"{prompt}",
            }
        ],
        model="gpt-3.5-turbo",
    )
    return response.choices[0].message.content


async def transcribe(
    file_name: Union[Union[str, bytes, PathLike[str], PathLike[bytes]], int]
):
    """
    Transcribe audio using Deepgram API.

    Args:
        - file_name: The name of the file to transcribe.

    Returns:
        The response from the API.
    """
    with open(file_name, "rb") as audio:
        source = {"buffer": audio, "mimetype": "audio/wav"}
        response = await deepgram.transcription.prerecorded(source)
        return response["results"]["channels"][0]["alternatives"][0]["words"]


def handle_command(command: str):
    """
    Handle the user's command.
    """
    cmd = command.strip()
    cmd_lower = cmd.lower()

    # Run a program (allowlist checked)
    if cmd_lower.startswith("run "):
        program = cmd.split("run ", 1)[1]
        return execute_system_command(program)

    # Open a file with default application
    if cmd_lower.startswith("open file "):
        path = cmd.split("open file ", 1)[1].strip().strip('"')
        return safe_open_file(path)

    # Delete a file or folder (requires allowlist permission or admin approval)
    if cmd_lower.startswith("delete file "):
        path = cmd.split("delete file ", 1)[1].strip().strip('"')
        if not ALLOWLIST.get("allow_delete", False):
            if not require_admin_confirmation(f"delete {path}", reason="is a delete operation and requires admin approval"):
                return "Delete cancelled."
        try:
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            _safe_log("delete", str(p))
            return f"Deleted {p}"
        except Exception as e:
            logging.exception("Delete failed")
            return f"Failed to delete: {e}"

    # Screenshots
    if "screenshot" in cmd_lower:
        return take_screenshot()

    # Type text using GUI automation
    if cmd_lower.startswith("type "):
        text = cmd.split("type ", 1)[1]
        return type_text(text)

    # Shutdown or restart
    if "shutdown" in cmd_lower or "restart" in cmd_lower:
        if not require_admin_confirmation(command, reason="is a system power operation"):
            return "Cancelled."
        if "shutdown" in cmd_lower:
            subprocess.Popen(["shutdown", "/s", "/t", "10"], shell=False)
            _safe_log("shutdown", command)
            return "Shutting down in 10 seconds."
        else:
            subprocess.Popen(["shutdown", "/r", "/t", "10"], shell=False)
            _safe_log("restart", command)
            return "Restarting in 10 seconds."

    # Fallback to previous behaviors
    if "open " in cmd_lower:
        # get the website name from the command
        website = cmd.split("open ", 1)[1]
        webbrowser.open(f"https://{website}.com")
        return f"Opening {website}"

    if "weather in" in cmd_lower:
        # get the city name from the command
        city = cmd.split("weather in ", 1)[1]
        weather = get_weather(city)
        return weather

    if "search for" in cmd_lower:
        # get the search query from the command
        query = cmd.split("search for ", 1)[1]
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"Searching for {query}."

    if "remind me to" in cmd_lower:
        # get the reminder and the time from the command
        parts = cmd.split("remind me to ", 1)[1].split(" in ")
        reminder = parts[0]
        delay = int(parts[1].split(" ")[0])
        set_reminder(reminder, delay)
        return f"I will remind you to {reminder} in {delay} seconds."

    return None

def process_audio(file_path: str, context: str):
    """
    Process the audio file at the given path.
    """
    # Transcribe audio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    words = loop.run_until_complete(transcribe(file_path))
    string_words = " ".join(
        word_dict.get("word") for word_dict in words if "word" in word_dict
    )

    # Handle command
    response = handle_command(string_words)

    # Get response from GPT-3
    if response is None:
        context += f"Alex: {string_words}nJarvis: "
        response = request_gpt(context)
        context += response

    # Convert response to audio (try ElevenLabs, fallback to local TTS)
    response_audio_path = "audio/response.wav"
    try:
        audio = elevenlabs.generate(
            text=response, voice="Adam", model="eleven_monolingual_v1"
        )
        elevenlabs.save(audio, response_audio_path)
    except Exception as e:
        logging.exception("ElevenLabs TTS failed")
        _safe_log("tts_fallback", str(e))

        # Local TTS fallback
        if PY_TTS:
            try:
                engine = pyttsx3.init()
                engine.say(response)
                engine.runAndWait()
                _safe_log("local_tts_spoken", response)
                # No audio file to return — playback handled directly
                response_audio_path = None
            except Exception as e:
                logging.exception("Local TTS failed")
                response_audio_path = None
        else:
            response_audio_path = None

    print(f"n --- USER: {string_words}n --- JARVIS: {response}n")
    return string_words, response, context, response_audio_path


def play_audio(file_path: str):
    """
    Play the audio file at the given path.
    """
    mixer.music.load(file_path)
    mixer.music.play()


def main():
    """Main entry point for the Jarvis application."""
    print("Jarvis is running...")
    sound = mixer.Sound(RECORDING_PATH)
    sound.play()


if __name__ == "__main__":
    main()
