# meta developer: @SodaModules

import requests
import json
from .. import loader, utils

class ElevenLabsModule(loader.Module):
    """Модуль для синтезу мови з використанням ElevenLabs API"""
    strings = {
        "name": "ElevenLabs",
        "enter_text": "<b>Введіть текст для синтезу!</b>",
        "synthesizing": "<b>Синтезую...</b>",
        "success": "Аудіо успішно синтезовано.",
        "error": "<b>Помилка: {error_code} - {error_message}</b>",
        "voice_set": "<b>Голос змінено на {voice_id}.</b>",
        "invalid_voice": "<b>Невірний ID голосу!</b>"
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "API_KEY", "", "API ключ для ElevenLabs",
            "DEFAULT_VOICE_ID", "Xb7hH8MSUJpSbSDYk0k2", "ID голосу за замовчуванням"
        )
        self.current_voice_id = self.config["DEFAULT_VOICE_ID"]

    async def client_ready(self, client, db):
        self.client = client

    async def ettscmd(self, message):
        """Використовуйте: .elevenv <текст> для синтезу мови"""
        text = utils.get_args_raw(message)
        if not text:
            await message.edit(self.strings("enter_text"))
            return

        await message.edit(self.strings("synthesizing"))

        # Параметри для синтезу мови
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.current_voice_id}/stream"
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.config["API_KEY"]
        }
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.5,
                "style": 0.5,
                "use_speaker_boost": True
            }
        }

        # Запит до API
        response = requests.post(url, headers=headers, json=data, stream=True)

        if response.ok:
            with open("output.ogg", "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)
            # Надсилання голосового повідомлення в чат через send_file
            await self.client.send_file(
                message.chat_id,
                "output.ogg",
                caption=self.strings("success"),
                voice_note=True  # Указываем, что это голосовое сообщение
            )
            await message.delete()
        else:
            await message.edit(self.strings("error").format(error_code=response.status_code, error_message=response.text))

    async def evoicecmd(self, message):
        """Використовуйте: .setvoice <voice_id> для зміни голосу"""
        new_voice_id = utils.get_args_raw(message)
        if not new_voice_id:
            await message.edit(self.strings("invalid_voice"))
            return

        # Змінюємо голос
        self.current_voice_id = new_voice_id
        await message.edit(self.strings("voice_set").format(voice_id=new_voice_id))