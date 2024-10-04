# meta developer: @SodaModules

import logging
import requests
from telethon.tl.types import Message
from datetime import datetime, time
import asyncio
from time import time as current_time
from .. import loader, utils

logger = logging.getLogger(__name__)
API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"

class WeatherMod(loader.Module):
    """Модуль погоди з автоматичними оновленнями та пам'яттю налаштувань"""
    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено",
        "city_prompt": "❗ Будь ласка, вкажіть місто",
        "weather_info": "<b>Погода в {}: {}</b>",
        "weather_details": "🌡 Температура: {}°C\n💨 Вітер: {} м/с\n💧 Вологість: {}%\n🔴 Тиск: {} hPa\n🤧 Відчувається як: {}°C\n☁️ Хмарність: {}%",
        "invalid_city": "❗ Місто не знайдено",
        "api_key_missing": "❗ API ключ OpenWeatherMap не встановлено",
        "api_key_set": "🔑 API ключ встановлено!",
        "api_key_invalid": "❗ Невірний API ключ.",
        "api_key_valid": "✅ API ключ дійсний.",
        "chat_added": "✅ Чат <code>{}</code> додано для оновлень погоди.",
        "chat_removed": "❌ Чат <code>{}</code> видалено з оновлень погоди.",
        "chats_list": "📋 Чати для оновлень погоди:\n{}",
        "no_chats": "🚫 Немає чатів для оновлень погоди.",
        "frequency_set": "🔄 Частота оновлень встановлена: кожні {} хвилин.",
        "silent_mode_enabled": "🔕 Режим тиші увімкнено (22:30 - 06:30).",
        "silent_mode_disabled": "🔔 Режим тиші вимкнено.",
    }

    def __init__(self):
        self.units = "metric"
        self.lang = "ua"
        self.cache = {}
        self.cache_timeout = 600
        self.silence_start = time(22, 30)
        self.silence_end = time(6, 30)
        self.auto_weather_task = None

    async def client_ready(self, client, db):
        self.db, self.client = db, client
        self.weather_chat_ids = self.db.get(self.strings["name"], "chats", [])
        self.update_frequency = self.db.get(self.strings["name"], "frequency", 60)
        self.silent_mode = self.db.get(self.strings["name"], "silent_mode", True)
        self.city = self.db.get(self.strings["name"], "city", "")
        if self.auto_weather_task is None:
            self.auto_weather_task = asyncio.create_task(self.auto_weather_updates())

    def get_api_key(self) -> str:
        return self.db.get(self.strings["name"], "api_key", "")

    async def weathercmd(self, message: Message) -> None:
        """Прогноз погоди для вказаного міста"""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return
        city = utils.get_args_raw(message) or self.city
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return
        weather_info = await self.get_weather_info(city, api_key)
        if weather_info:
            animated_emojis = await self.add_animated_emojis()
            await utils.answer(message, self.strings["weather_info"].format(city, weather_info) + f"\n{animated_emojis}")

    async def get_weather_info(self, city: str, api_key: str) -> str:
        if city in self.cache and current_time() - self.cache[city]["time"] < self.cache_timeout:
            return self.cache[city]["data"]

        params = {"q": city, "appid": api_key, "units": self.units, "lang": self.lang}
        try:
            response = requests.get(API_URL_OWM, params=params)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            return self.strings["invalid_city"]

        data = response.json()
        weather_info = self.extract_weather_details(data)
        self.cache[city] = {"data": weather_info, "time": current_time()}
        return weather_info

    def extract_weather_details(self, data: dict) -> str:
        temp, wind_speed, humidity, pressure = data["main"]["temp"], data["wind"]["speed"], data["main"]["humidity"], data["main"]["pressure"]
        feels_like, cloudiness, weather_desc = data["main"]["feels_like"], data["clouds"]["all"], data["weather"][0]["description"]

        return self.strings["weather_details"].format(temp, wind_speed, humidity, pressure, feels_like, cloudiness) + f"\n{weather_desc}"

    async def add_animated_emojis(self) -> str:
        user = await self.client.get_me()
        if user.premium:
            return "🌤⛅️🌦☀️💨"  # Premium animated emojis
        return "🌤⛅️🌦☀️"  # Static emojis for non-premium

    async def auto_weather_updates(self):
        """Автоматичні оновлення погоди"""
        while True:
            now = datetime.now().time()
            if self.silent_mode and (self.silence_start <= now or now < self.silence_end):
                await asyncio.sleep((datetime.combine(datetime.today(), self.silence_end) - datetime.now()).seconds)
                continue

            api_key = self.get_api_key()
            if not api_key:
                logger.warning("API ключ не встановлено")
                await asyncio.sleep(self.update_frequency * 60)
                continue

            if self.city and self.weather_chat_ids:
                weather_info = await self.get_weather_info(self.city, api_key)
                if weather_info:
                    for chat_id in self.weather_chat_ids:
                        await self.client.send_message(chat_id, self.strings["weather_info"].format(self.city, weather_info))

            await asyncio.sleep(self.update_frequency * 60)
