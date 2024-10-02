import asyncio
import logging
import os
import tempfile

import speech_recognition as sr
from pydub import AudioSegment
from telethon.tl.types import DocumentAttributeVideo, Message

# Import Vosk for offline recognition
import vosk
import whisper
from langdetect import detect

# For Google Speech Recognition as fallback
import google.cloud.speech as google_speech

from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class VoicyMod(loader.Module):
    """Recognize voice messages, audio, video, and round messages."""

    strings = {
        "name": "Voicy",
        "converting": "<b>🫠 Recognizing voice message...</b>",
        "converted": "<b>🫠 Recognized:</b>\n<i>{}</i>",
        "voice_not_found": "🫠 <b>Voice not found</b>",
        "autovoice_off": "🫠 I will not recognize voice messages in this chat",
        "autovoice_on": "🫠 I will recognize voice messages in this chat",
        "error": "🚫 <b>Recognition error!</b>",
        "too_big": "🫥 <b>Voice message is too big, I can't recognize it...</b>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("language", "en-US", lambda: self.strings["_cfg_lang"]),
            loader.ConfigValue("ignore_users", [], lambda: self.strings["_cfg_ignore_users"]),
            loader.ConfigValue("silent", False, lambda: self.strings["_cfg_silent"]),
            loader.ConfigValue("google_credentials", "", lambda: self.strings["_cfg_google_credentials"]),
        )

        # Initialize Whisper model (you can choose the model size based on accuracy and speed needs)
        self.whisper_model = whisper.load_model("small")

        # Initialize Vosk model (ensure you have the appropriate language model downloaded)
        self.vosk_model = vosk.Model("path_to_vosk_model")

    async def client_ready(self):
        self.v2a = await self.import_lib(
            "https://libs.hikariatama.ru/v2a.py",
            suspend_on_error=True,
        )
        self.chats = self.pointer("chats", [])

    async def download_media_to_temp(self, message, tmpdir):
        """Download and prepare media as a temp file."""
        try:
            file_name = "audio.mp3" if message.audio else "audio.ogg"
            file_path = os.path.join(tmpdir, file_name)

            media_data = await message.download_media(bytes)

            if message.video:
                media_data = await self.v2a.convert(media_data, "audio.ogg")

            with open(file_path, "wb") as f:
                f.write(media_data)

            return file_path
        except Exception as e:
            logger.exception("Error downloading or converting media: %s", e)
            return None

    async def preprocess_audio(self, file_path):
        """Preprocess audio to standardize format for recognition."""
        try:
            audio = AudioSegment.from_file(file_path)
            # Normalize, convert to mono, and resample to 16kHz
            audio = audio.set_frame_rate(16000).set_channels(1)
            processed_file_path = file_path.replace(".ogg", "_processed.wav")
            audio.export(processed_file_path, format="wav")
            return processed_file_path
        except Exception as e:
            logger.exception("Error in preprocessing audio: %s", e)
            return None

    async def recognize_voice_vosk(self, file_path):
        """Recognize voice using Vosk."""
        try:
            rec = vosk.KaldiRecognizer(self.vosk_model, 16000)
            with open(file_path, "rb") as f:
                while True:
                    data = f.read(4000)
                    if len(data) == 0:
                        break
                    if rec.AcceptWaveform(data):
                        break
            result = rec.FinalResult()
            return result["text"] if "text" in result else None
        except Exception as e:
            logger.exception("Error during Vosk recognition: %s", e)
            return None

    async def recognize_voice_whisper(self, file_path):
        """Recognize voice using Whisper."""
        try:
            result = self.whisper_model.transcribe(file_path)
            return result["text"]
        except Exception as e:
            logger.exception("Error during Whisper recognition: %s", e)
            return None

    async def recognize_voice_google(self, file_path):
        """Recognize voice using Google Cloud Speech-to-Text."""
        try:
            client = google_speech.SpeechClient(credentials=self.config["google_credentials"])
            audio = google_speech.RecognitionAudio(uri=file_path)
            config = google_speech.RecognitionConfig(
                encoding=google_speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code="en-US",
            )
            response = client.recognize(config=config, audio=audio)

            return " ".join([result.alternatives[0].transcript for result in response.results])
        except Exception as e:
            logger.exception("Error during Google recognition: %s", e)
            return None

    async def recognize_voice(self, file_path, duration):
        """Select and use the appropriate recognition service."""
        # Preprocess audio
        processed_file_path = await self.preprocess_audio(file_path)

        # Select recognition service based on file duration
        if duration < 10:
            result = await self.recognize_voice_vosk(processed_file_path)
        elif duration < 60:
            result = await self.recognize_voice_whisper(processed_file_path)
        else:
            result = await self.recognize_voice_google(processed_file_path)

        return result

    async def recognize(self, message: Message):
        try:
            m = await utils.answer(message, self.strings["converting"])
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = await self.download_media_to_temp(message, tmpdir)

                if not file_path:
                    if not self.config["silent"]:
                        await utils.answer(m, self.strings["error"])
                    return

                # Detect the duration of the file to determine recognition service
                duration = next(
                    (attr.duration for attr in message.media.document.attributes if isinstance(attr, DocumentAttributeVideo)),
                    0
                ) or getattr(message.audio, "duration", 0)

                recognized_text = await self.recognize_voice(file_path, duration)

                if recognized_text:
                    await utils.answer(
                        m, self.strings["converted"].format(recognized_text)
                    )
                else:
                    if not self.config["silent"]:
                        await utils.answer(m, self.strings["error"])
        except Exception as e:
            logger.exception("Can't recognize: %s", e)
            if not self.config["silent"]:
                await utils.answer(m, self.strings["error"])

    @loader.unrestricted
    async def voicycmd(self, message: Message):
        """Recognize voice message"""
        reply = await message.get_reply_message()

        if not reply or not reply.media:
            await utils.answer(message, self.strings["voice_not_found"])
            return

        try:
            is_voice = (
                reply.video or reply.audio or reply.media.document.attributes[0].voice
            )
        except (AttributeError, IndexError):
            is_voice = False

        if not is_voice:
            await utils.answer(message, self.strings["voice_not_found"])
            return

        if message.out:
            await message.delete()

        await self.recognize(reply)

    @loader.unrestricted
    async def autovoicecmd(self, message: Message):
        """Toggle automatic recognition in current chat"""
        chat_id = utils.get_chat_id(message)

        if chat_id in self.chats:
            self.chats.remove(chat_id)
            await utils.answer(message, self.strings["autovoice_off"])
        else:
            self.chats.append(chat_id)
            await utils.answer(message, self.strings["autovoice_on"])
