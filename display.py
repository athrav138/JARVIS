"""Display the conversation in a Taipy app."""

from threading import Thread
import time
from taipy.gui import Gui, State
import elevenlabs
from pygame import mixer
import os

from main import process_audio, play_audio
from record import speech_to_text

conversation = {"Conversation": []}
selected_row = [1]
status = "Idle"
context = "You are Jarvis, Alex's human assistant. You are witty and full of personality. Your answers should be limited to 1-2 short sentences."
RECORDING_PATH = "audio/recording.wav"
audio_path = None
processing = False
gui_instance = None

# Initialize mixer for audio playback
mixer.init()

# Initialize ElevenLabs
elevenlabs.set_api_key(os.getenv("ELEVENLABS_API_KEY"))


def erase_conv(state: State) -> None:
    """
    Erase the conversation and update the conversation table.
    """
    state.conversation = {"Conversation": []}
    global context
    context = "You are Jarvis, Alex's human assistant. You are witty and full of personality. Your answers should be limited to 1-2 short sentences."


def style_conv(state: State, idx: int, row: int) -> str:
    """
    Apply a style to the conversation table depending on the message's author.
    """
    if idx is None:
        return None
    elif idx % 2 == 0:
        return "user_message"
    else:
        return "gpt_message"


page = """
<|layout|columns=300px 1|
<|part|render=True|class_name=sidebar|
# Taipy **Jarvis**{: .color-primary} # {: .logo-text}
<|New Conversation|button|class_name=fullwidth plain|id=reset_app_button|on_action=erase_conv|>
<br/>
<|Record|button|class_name=fullwidth plain|on_action=record_and_process|>
<br/>
<|{status}|text|>
|>

<|part|render=True|class_name=p2 align-item-bottom table|
<|{conversation}|table|row_class_name=style_conv|show_all|width=100%|rebuild|selected={selected_row}|>
|>
|>
"""

def record_and_process(state: State) -> None:
    """
    Record audio, process it and update the conversation.
    """
    global status
    status = "Listening..."
    
    def record_and_process_thread():
        try:
            print("Starting recording...")
            speech_to_text()
            print("Recording complete, processing audio...")
            global context
            string_words, response, context, audio_file_path = process_audio(RECORDING_PATH, context)
            print(f"User said: {string_words}")
            print(f"Jarvis says: {response}")
            
            # Update conversation
            conv = state.conversation
            conv["Conversation"] += [string_words, response]
            state.conversation = conv
            state.audio_path = audio_file_path
            # Only play if a pre-generated audio file exists (ElevenLabs)
            if audio_file_path:
                play_audio(audio_file_path)
            # If audio_file_path is None, process_audio already handled local TTS fallback
            state.status = "Idle"
        except Exception as e:
            print(f"Error in record_and_process: {e}")
            import traceback
            traceback.print_exc()
            state.status = f"Error: {str(e)}"

    state.status = "Listening..."
    Thread(target=record_and_process_thread, daemon=True).start()

gui = Gui(page)
gui.run(debug=True, dark_mode=True)
