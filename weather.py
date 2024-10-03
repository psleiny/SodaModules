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
    """Модуль погоди з автоматичними оновленнями щогодини"""

    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено",
        "city_prompt": "❗ Будь ласка, вкажіть місто",
        "weather_info": "<b>Погода в {}: {}</b>",
        "weather_details": "🌡 Температура: {}°C\n💨 Вітер: {} м/с\n💧 Вологість: {}%\n🔴 Тиск: {} hPa\n🤧 Відчувається як: {}°C\n☁️ Хмарність: {}%\n👁️ Видимість: {} м",
        "invalid_city": "❗ Місто не знайдено",
        "api_key_missing": "❗ API ключ OpenWeatherMap не встановлено",
        "api_key_set": "🔑 API ключ встановлено!",
        "api_key_invalid": "❗ Невірний API ключ.",
        "api_key_valid": "✅ API ключ дійсний.",
    }

    def __init__(self):
        self.units = "metric" 
        self.lang = "ua"  
        self.cache = {}  
        self.cache_timeout = 600  
        self.silence_start = time(22, 30)  
        self.silence_end = time(6, 30)  
        self.weather_chat_id = None  
        self.auto_weather_task = None 

    async def client_ready(self, client, db) -> None:
        self.db = db
        self.client = client

        if self.auto_weather_task is None:
            self.auto_weather_task = asyncio.create_task(self.auto_weather_updates())

    def get_api_key(self) -> str:
        """Отримати збережений API ключ OpenWeatherMap."""
        return self.db.get(self.strings["name"], "api_key", "")

    async def weatherkeycmd(self, message: Message) -> None:
        """Встановити API ключ OpenWeatherMap"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "api_key", args)
            await utils.answer(message, self.strings["api_key_set"])
        return

    async def weathercitycmd(self, message: Message) -> None:
        """Встановити місто за замовчуванням (Set default city for forecast)"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "city", args)

        city = self.db.get(self.strings["name"], "city", self.strings["no_city"])
        await utils.answer(message, self.strings["city_set"].format(city))
        return

    async def weathercmd(self, message: Message) -> None:
        """Прогноз погоди для вказаного міста (Current weather for the provided city)"""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        weather_info = await self.get_weather_info(city, api_key)
        if weather_info:
            await utils.answer(message, self.strings["weather_info"].format(city, weather_info))
        return

    async def get_weather_info(self, city: str, api_key: str) -> str:
        """Отримати та повернути інформацію про погоду"""

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
        """Витягти та форматувати деталі погоди з даних OpenWeatherMap"""
        temp = data["main"]["temp"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        feels_like = data["main"]["feels_like"]
        cloudiness = data["clouds"]["all"]
        visibility = data.get("visibility", 10000)  
        weather_desc = data["weather"][0]["description"]

        return self.strings["weather_details"].format(
            temp, wind_speed, humidity, pressure, feels_like, cloudiness, visibility
        ) + f"\n{weather_desc}"

    async def checkapikeycmd(self, message: Message) -> None:
        """Перевірити, чи дійсний API ключ."""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        try:
            response = requests.get(API_URL_OWM, params={"q": "London", "appid": api_key, "units": self.units})
            response.raise_for_status()
            await utils.answer(message, self.strings["api_key_valid"])
        except requests.exceptions.HTTPError:
            await utils.answer(message, self.strings["api_key_invalid"])

    async def setchatcmd(self, message: Message) -> None:
        """Встановити чат для автоматичних оновлень погоди"""
        chat_id = utils.get_chat_id(message)
        self.weather_chat_id = chat_id
        await utils.answer(message, f"Чат для оновлень погоди встановлено: {chat_id}")
        return

    async def auto_weather_updates(self):
        """Автоматичні щогодинні оновлення погоди"""
        while True:
            now = datetime.now().time()
            if self.silence_start <= now or now < self.silence_end:

                await asyncio.sleep(3600)
                continue

            if self.weather_chat_id:
                api_key = self.get_api_key()
                if not api_key:
                    logger.warning("API ключ не встановлено")
                    await asyncio.sleep(3600)
                    continue

                city = self.db.get(self.strings["name"], "city", "")
                if city:
                    weather_info = await self.get_weather_info(city, api_key)
                    if weather_info:
                        await self.client.send_message(self.weather_chat_id, self.strings["weather_info"].format(city, weather_info))

            await asyncio.sleep(3600)
