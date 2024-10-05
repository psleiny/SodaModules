# meta developer: @SodaModules

import logging
import aiohttp
from datetime import datetime, time, timedelta
import asyncio
from time import time as current_time

from .. import loader, utils

logger = logging.getLogger(__name__)

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"
API_LIMIT = 50000  

class WeatherMod(loader.Module):
    """Модуль погоди з автоматичними оновленнями та пам'яттю налаштувань."""

    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено.",
        "city_prompt": "❗ Будь ласка, вкажіть місто.",
        "weather_info": "<b>Погода в {}: {}</b>",
        "weather_details": "🌡 Температура: {}°C\n💨 Вітер: {} м/с\n💧 Вологість: {}%\n🔴 Тиск: {} hPa\n🤧 Відчувається як: {}°C\n☁️ Хмарність: {}%\n🌞 УФ-індекс: {}\n👁 Видимість: {} м",
        "invalid_city": "❗ Місто не знайдено.",
        "api_key_missing": "❗ API ключ OpenWeatherMap не встановлено.",
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
        "api_limit_exceeded": "❗ Ліміт запитів на сьогодні перевищено.",
    }

    def __init__(self):
        self.units = "metric"  
        self.lang = "ua"  
        self.cache = {}  
        self.cache_timeout = 600  
        self.silence_start = time(22, 30)  
        self.silence_end = time(6, 30)  
        self.auto_weather_task = None  
        self.api_requests_today = 0  

    async def client_ready(self, client, db):
        """Ініціалізація після готовності клієнта."""
        self.db = db
        self.client = client

        self.weather_chat_ids = self.db.get(self.strings["name"], "chats", [])
        self.update_frequency = self.db.get(self.strings["name"], "frequency", 60)
        self.silent_mode = self.db.get(self.strings["name"], "silent_mode", True)
        self.city = self.db.get(self.strings["name"], "city", "")
        self.api_requests_today = self.db.get(self.strings["name"], "api_requests_today", 0)
        self.last_reset = self.db.get(self.strings["name"], "last_reset", datetime.now())

        if datetime.now().date() != self.last_reset.date():
            self.api_requests_today = 0
            self.db.set(self.strings["name"], "api_requests_today", 0)
            self.db.set(self.strings["name"], "last_reset", datetime.now())

        if self.auto_weather_task is None:
            self.auto_weather_task = asyncio.create_task(self.auto_weather_updates())

    def get_api_key(self) -> str:
        """Отримати збережений API ключ OpenWeatherMap."""
        return self.db.get(self.strings["name"], "api_key", "")

    def is_silent_period(self, now=None) -> bool:
        """Перевірити, чи зараз режим тиші."""
        now = now or datetime.now().time()
        return self.silent_mode and (self.silence_start <= now or now < self.silence_end)

    async def weatherkeycmd(self, message) -> None:
        """Встановити API ключ OpenWeatherMap."""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "api_key", args)
            await utils.answer(message, self.strings["api_key_set"])
        return

    async def weathercitycmd(self, message) -> None:
        """Встановити місто за замовчуванням."""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "city", args)
            self.city = args

        await utils.answer(message, self.strings["city_set"].format(self.city))
        return

    async def weathercmd(self, message) -> None:
        """Отримати прогноз погоди для вказаного міста."""
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
            await utils.answer(message, self.strings["weather_info"].format(city, weather_info))
        return

    async def get_weather_info(self, city: str, api_key: str) -> str:
        """Отримати та повернути інформацію про погоду з OpenWeatherMap."""
        if self.api_requests_today >= API_LIMIT:
            logger.warning("Ліміт запитів на сьогодні перевищено.")
            return self.strings["api_limit_exceeded"]

        if city in self.cache and current_time() - self.cache[city]["time"] < self.cache_timeout:
            return self.cache[city]["data"]

        params = {"q": city, "appid": api_key, "units": self.units, "lang": self.lang}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL_OWM, params=params) as response:
                    if response.status == 404:
                        return self.strings["invalid_city"]
                    elif response.status == 401:
                        return self.strings["api_key_invalid"]
                    elif response.status != 200:
                        logger.error(f"Помилка під час отримання даних: {response.status}")
                        return self.strings["invalid_city"]

                    data = await response.json()
                    self.api_requests_today += 1  
                    self.db.set(self.strings["name"], "api_requests_today", self.api_requests_today)

        except aiohttp.ClientError as e:
            logger.error(f"Помилка API запиту: {str(e)}")
            return self.strings["invalid_city"]

        weather_info = self.extract_weather_details(data)
        self.cache[city] = {"data": weather_info, "time": current_time()}
        return weather_info

    def extract_weather_details(self, data: dict) -> str:
        """Витягти та форматувати деталі погоди з OpenWeatherMap."""
        temp = data["main"]["temp"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        feels_like = data["main"]["feels_like"]
        cloudiness = data["clouds"]["all"]
        visibility = data.get("visibility", 0)  
        uv_index = data.get("uvi", "Н/Д")  
        weather_desc = data["weather"][0]["description"]

        weather_emoji = self.get_weather_emoji(weather_desc)
        return self.strings["weather_details"].format(
            temp, wind_speed, humidity, pressure, feels_like, cloudiness, uv_index, visibility
        ) + f"\n{weather_emoji} {weather_desc}"

    def get_weather_emoji(self, description: str) -> str:
        """Повернути відповідний емодзі залежно від опису погоди."""
        if "дощ" in description.lower():
            return "🌧️"
        elif "ясно" in description.lower():
            return "☀️"
        elif "хмара" in description.lower():
            return "☁️"
        elif "сніг" in description.lower():
            return "❄️"
        return "🌡"

    async def checkapikeycmd(self, message) -> None:
        """Перевірити, чи дійсний API ключ."""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL_OWM, params={"q": "London", "appid": api_key, "units": self.units}) as response:
                    if response.status == 200:
                        await utils.answer(message, self.strings["api_key_valid"])
                    else:
                        await utils.answer(message, self.strings["api_key_invalid"])
        except aiohttp.ClientError:
            await utils.answer(message, self.strings["api_key_invalid"])

    async def setchatcmd(self, message) -> None:
        """Встановити чат для автоматичних оновлень погоди."""
        chat_id = utils.get_chat_id(message)
        if chat_id not in self.weather_chat_ids:
            self.weather_chat_ids.append(chat_id)
            self.db.set(self.strings["name"], "chats", self.weather_chat_ids)
            await utils.answer(message, self.strings["chat_added"].format(chat_id))
        else:
            await utils.answer(message, f"Чат <code>{chat_id}</code> вже додано.")
        return

    async def removechatcmd(self, message) -> None:
        """Видалити чат з автоматичних оновлень погоди."""
        chat_id = utils.get_chat_id(message)
        if chat_id in self.weather_chat_ids:
            self.weather_chat_ids.remove(chat_id)
            self.db.set(self.strings["name"], "chats", self.weather_chat_ids)
            await utils.answer(message, self.strings["chat_removed"].format(chat_id))
        else:
            await utils.answer(message, f"Чат <code>{chat_id}</code> не знайдено.")
        return

    async def listchatscmd(self, message) -> None:
        """Переглянути список чатів для автоматичних оновлень погоди."""
        if self.weather_chat_ids:
            chats = "\n".join([f"• {chat_id}" for chat_id in self.weather_chat_ids])
            await utils.answer(message, self.strings["chats_list"].format(chats))
        else:
            await utils.answer(message, self.strings["no_chats"])
        return

    async def setfrequencycmd(self, message) -> None:
        """Встановити частоту оновлень погоди (в хвилинах)."""
        args = utils.get_args_raw(message)
        try:
            frequency = int(args)
            if frequency < 1:
                raise ValueError("Частота повинна бути більше 0.")
            self.update_frequency = frequency
            self.db.set(self.strings["name"], "frequency", frequency)
            await utils.answer(message, self.strings["frequency_set"].format(frequency))
        except (ValueError, TypeError):
            await utils.answer(message, "❗ Вкажіть правильну кількість хвилин (позитивне ціле число).")
        return

    async def toggle_silentcmd(self, message) -> None:
        """Увімкнути або вимкнути режим тиші (22:30 - 06:30)."""
        self.silent_mode = not self.silent_mode
        self.db.set(self.strings["name"], "silent_mode", self.silent_mode)
        if self.silent_mode:
            await utils.answer(message, self.strings["silent_mode_enabled"])
        else:
            await utils.answer(message, self.strings["silent_mode_disabled"])
        return

    async def auto_weather_updates(self):
        """Автоматичні оновлення погоди."""
        while True:
            if self.is_silent_period():
                await asyncio.sleep(self.update_frequency * 60)
                continue

            api_key = self.get_api_key()
            if not api_key:
                logger.warning("API ключ не встановлено")
                await asyncio.sleep(self.update_frequency * 60)
                continue

            city = self.db.get(self.strings["name"], "city", "")
            if city and self.weather_chat_ids:
                weather_info = await self.get_weather_info(city, api_key)
                if weather_info:
                    await asyncio.gather(*(self.client.send_message(chat_id, self.strings["weather_info"].format(city, weather_info)) for chat_id in self.weather_chat_ids))

            await asyncio.sleep(self.update_frequency * 60)
