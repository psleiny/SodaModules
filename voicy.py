import asyncio
import logging
import os
import tempfile
import wave
from vosk import Model, KaldiRecognizer
from pydub import AudioSegment
from telethon.tl.types import DocumentAttributeVideo, Message

from .. import loader, utils

logger = logging.getLogger(__name__)

# Load Vosk model once during initialization
vosk_model = Model("path_to_vosk_model")

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
            loader.ConfigValue("ignore_users", [], lambda: self.strings["_cfg_ignore_users"], validator=loader.validators.Series(validator=loader.validators.TelegramID())),
            loader.ConfigValue("silent", False, lambda: self.strings["_cfg_silent"], validator=loader.validators.Boolean()),
        )

    async def client_ready(self):
        self.chats = self.pointer("chats", [])

    async def download_media_to_temp(self, message, tmpdir):
        """Download and prepare media as a temp file."""
        try:
            file_name = "audio.ogg"
            file_path = os.path.join(tmpdir, file_name)

            media_data = await message.download_media(bytes)
            with open(file_path, "wb") as f:
                f.write(media_data)

            return file_path
        except Exception as e:
            logger.exception("Error downloading or converting media: %s", e)
            return None

    def convert_to_wav(self, file_path):
        """Convert audio file to WAV format required by Vosk."""
        try:
            audio = AudioSegment.from_file(file_path)
            wav_path = file_path.replace(".ogg", ".wav")
            audio.export(wav_path, format="wav")
            return wav_path
        except Exception as e:
            logger.exception("Error converting to WAV: %s", e)
            return None

    def recognize_voice_vosk(self, wav_path):
        """Recognize voice from audio file using Vosk."""
        try:
            with wave.open(wav_path, "rb") as audio_file:
                if audio_file.getnchannels() != 1 or audio_file.getsampwidth() != 2 or audio_file.getframerate() not in [8000, 16000]:
                    logger.error("Unsupported audio format for Vosk")
                    return None

                recognizer = KaldiRecognizer(vosk_model, audio_file.getframerate())
                while True:
                    data = audio_file.readframes(4000)
                    if len(data) == 0:
                        break
                    if recognizer.AcceptWaveform(data):
                        result = recognizer.Result()
                        return result
                final_result = recognizer.FinalResult()
                return final_result
        except Exception as e:
            logger.exception("Error during Vosk recognition: %s", e)
            return None

    async def recognize(self, message: Message):
        try:
            m = await utils.answer(message, self.strings["converting"])
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = await self.download_media_to_temp(message, tmpdir)

                if not file_path:
                    if not self.config["silent"]:
                        await utils.answer(m, self.strings["error"])
                    return

                wav_path = self.convert_to_wav(file_path)

                if not wav_path:
                    if not self.config["silent"]:
                        await utils.answer(m, self.strings["error"])
                    return

                recognized_text = self.recognize_voice_vosk(wav_path)

                if recognized_text:
                    await utils.answer(m, self.strings["converted"].format(recognized_text))
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

    async def watcher(self, message: Message):
        try:
            if (
                utils.get_chat_id(message) not in self.get("chats", [])
                or not message.media
                or not (message.video or message.audio or message.media.document.attributes[0].voice)
                or message.gif
                or message.sticker
            ):
                return
        except (AttributeError, IndexError):
            return

        if message.sender_id in self.config["ignore_users"]:
            return

        try:
            duration = next(
                (attr.duration for attr in message.media.document.attributes if isinstance(attr, DocumentAttributeVideo)),
                0
            ) or getattr(message.audio, "duration", 0)

            if duration > 300 or message.document.size / 1024 / 1024 > 5:
                if not self.config["silent"]:
                    await utils.answer(message, self.strings["too_big"])
                return
        except (AttributeError, IndexError):
            pass

        await self.recognize(message)

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
