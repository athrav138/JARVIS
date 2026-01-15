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
    if "open" in command:
        # get the website name from the command
        website = command.split("open ")[1]
        webbrowser.open(f"https://{website}.com")
    elif "weather in" in command:
        # get the city name from the command
        city = command.split("weather in ")[1]
        weather = get_weather(city)
        return weather
    elif "search" in command:
        # get the search query from the command
        query = command.split("search for ")[1]
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"Searching for {query}."
    elif "remind me to" in command:
        # get the reminder and the time from the command
        parts = command.split("remind me to ")[1].split(" in ")
        reminder = parts[0]
        delay = int(parts[1].split(" ")[0])
        set_reminder(reminder, delay)
        return f"I will remind you to {reminder} in {delay} seconds."
    else:
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
        context += f"\nAlex: {string_words}\nJarvis: "
        response = request_gpt(context)
        context += response

    # Convert response to audio
    audio = elevenlabs.generate(
        text=response, voice="Adam", model="eleven_monolingual_v1"
    )
    response_audio_path = "audio/response.wav"
    elevenlabs.save(audio, response_audio_path)

    print(f"\n --- USER: {string_words}\n --- JARVIS: {response}\n")
    return string_words, response, context, response_audio_path


def main():
    """Main entry point for the Jarvis application."""
    print("Jarvis is running...")
    sound = mixer.Sound(RECORDING_PATH)
    sound.play()


if __name__ == "__main__":
    main()
