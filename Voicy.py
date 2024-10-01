import asyncio
import logging
import os
import tempfile

import speech_recognition as sr
from pydub import AudioSegment
from telethon.tl.types import DocumentAttributeVideo, Message

# Import Azure Speech SDK
import azure.cognitiveservices.speech as speechsdk

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
            loader.ConfigValue(
                "language", 
                "en-US", 
                lambda: self.strings["_cfg_lang"], 
                validator=loader.validators.RegExp(r"^[a-z]{2}-[A-Z]{2}$"),
            ),
            loader.ConfigValue(
                "ignore_users", 
                [], 
                lambda: self.strings["_cfg_ignore_users"], 
                validator=loader.validators.Series(
                    validator=loader.validators.TelegramID()
                ),
            ),
            loader.ConfigValue(
                "silent", 
                False, 
                lambda: self.strings["_cfg_silent"], 
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "azure_key", 
                "", 
                lambda: self.strings["_cfg_azure_key"], 
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "azure_region", 
                "", 
                lambda: self.strings["_cfg_azure_region"], 
                validator=loader.validators.String(),
            ),
        )

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

    async def recognize_voice(self, file_path):
        """Recognize voice from audio file using Azure Speech Service."""
        try:
            # Set up Azure Speech configuration
            speech_config = speechsdk.SpeechConfig(
                subscription=self.config["azure_key"],
                region=self.config["azure_region"]
            )
            audio_input = speechsdk.AudioConfig(filename=file_path)
            recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

            # Start recognition
            result = recognizer.recognize_once_async().get()

            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                return result.text
            elif result.reason == speechsdk.ResultReason.NoMatch:
                logger.error("No speech could be recognized.")
                return None
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logger.error("Recognition canceled: %s", cancellation_details.reason)
                return None

        except Exception as e:
            logger.exception("Error during recognition: %s", e)
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

                recognized_text = await self.recognize_voice(file_path)

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

    async def watcher(self, message: Message):
        try:
            # Ensure that the message has media and voice attributes, and is in monitored chats
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

        # Ensure media isn't too big or long
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
