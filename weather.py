import logging
import requests
from telethon.tl.types import Message
from datetime import datetime, time
import asyncio
from time import time as current_time

from .. import loader, utils

logger = logging.getLogger(__name__)

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"
API_URL_YRNO = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
API_URL_OPENMETEO = "https://api.open-meteo.com/v1/forecast"

class WeatherMod(loader.Module):
    """Модуль погоди з кількома постачальниками (OWM, Yr.no, Open-Meteo) та обробкою недоступності сервісів"""

    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено",
        "city_prompt": "❗ Будь ласка, вкажіть місто",
        "weather_info": "<b>Погода в {} (приблизно): {}</b>",
        "weather_details": "🌡 Температура: {}°C\n💨 Вітер: {} м/с\n💧 Вологість: {}%\n🔴 Тиск: {} hPa\n🤧 Відчувається як: {}°C\n☁️ Хмарність: {}%",
        "invalid_city": "❗ Місто не знайдено",
        "api_key_missing": "❗ API ключ не встановлено",
        "api_key_set": "🔑 API ключ встановлено для {}!",
        "service_unavailable": "❗ Сервіс {} тимчасово недоступний. Перехід до наступного...",
        "no_service_available": "❗ Жоден із сервісів погоди недоступний.",
        "provider_set": "✅ Постачальник погоди встановлено на {}",
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
        self.providers = ["owm", "yrno", "openmeteo"]  

    async def client_ready(self, client, db):
        """Ініціалізація після готовності клієнта"""
        self.db = db
        self.client = client

        self.weather_chat_ids = self.db.get(self.strings["name"], "chats", [])
        self.update_frequency = self.db.get(self.strings["name"], "frequency", 60)
        self.silent_mode = self.db.get(self.strings["name"], "silent_mode", True)
        self.city = self.db.get(self.strings["name"], "city", "")
        self.current_provider = self.db.get(self.strings["name"], "provider", "owm")  

        if self.auto_weather_task is None:
            self.auto_weather_task = asyncio.create_task(self.auto_weather_updates())

    def get_api_key(self, provider: str) -> str:
        """Отримати збережений API ключ для обраного постачальника."""
        return self.db.get(self.strings["name"], f"{provider}_api_key", "")

    async def setprovidercmd(self, message: Message) -> None:
        """Встановити постачальника прогнозу погоди"""
        provider = utils.get_args_raw(message).lower()
        if provider not in self.providers:
            await utils.answer(message, f"❗ Невідомий постачальник. Доступні: {', '.join(self.providers)}.")
            return

        self.db.set(self.strings["name"], "provider", provider)
        self.current_provider = provider
        await utils.answer(message, self.strings["provider_set"].format(provider))

    async def weatherkeycmd(self, message: Message) -> None:
        """Встановити API ключ для поточного постачальника"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        provider = self.current_provider
        self.db.set(self.strings["name"], f"{provider}_api_key", args)
        await utils.answer(message, self.strings["api_key_set"].format(provider))

    async def weathercitycmd(self, message: Message) -> None:
        """Встановити місто за замовчуванням (Set default city for forecast)"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "city", args)
            self.city = args

        await utils.answer(message, self.strings["city_set"].format(self.city))
        return

    async def weathercmd(self, message: Message) -> None:
        """Прогноз погоди для вказаного міста (Current weather for the provided city)"""
        city = utils.get_args_raw(message) or self.city
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        weather_info = await self.get_weather_info(city)
        if weather_info:
            await utils.answer(message, weather_info)
        else:
            await utils.answer(message, self.strings["no_service_available"])
        return

    async def get_weather_info(self, city: str) -> str:
        """Отримати та повернути інформацію про погоду від доступного постачальника"""
        results = []
        for provider in self.providers:
            try:
                api_key = self.get_api_key(provider)
                if provider == "owm":
                    result = await self.get_weather_from_owm(city, api_key)
                elif provider == "yrno":
                    result = await self.get_weather_from_yrno(city)
                elif provider == "openmeteo":
                    result = await self.get_weather_from_openmeteo(city)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"{provider} failed: {e}")
                await self.client.send_message(self.client, self.strings["service_unavailable"].format(provider))
                continue

        if not results:
            return None

        avg_temp = sum(r["temp"] for r in results) / len(results)
        avg_wind = sum(r["wind_speed"] for r in results) / len(results)
        avg_humidity = sum(r["humidity"] for r in results) / len(results)
        avg_pressure = sum(r["pressure"] for r in results) / len(results)
        avg_feels_like = sum(r["feels_like"] for r in results) / len(results)
        avg_cloudiness = sum(r["cloudiness"] for r in results) / len(results)

        return self.strings["weather_details"].format(
            round(avg_temp, 1), round(avg_wind, 1), round(avg_humidity, 1),
            round(avg_pressure, 1), round(avg_feels_like, 1), round(avg_cloudiness, 1)
        )

    async def get_weather_from_owm(self, city: str, api_key: str) -> dict:
        """Отримати погоду з OpenWeatherMap"""
        if not api_key:
            raise ValueError("API ключ OWM не встановлено")

        params = {"q": city, "appid": api_key, "units": self.units, "lang": self.lang}
        response = requests.get(API_URL_OWM, params=params)
        response.raise_for_status()
        data = response.json()

        return {
            "temp": data["main"]["temp"],
            "wind_speed": data["wind"]["speed"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "feels_like": data["main"]["feels_like"],
            "cloudiness": data["clouds"]["all"]
        }

    async def get_weather_from_yrno(self, city: str) -> dict:
        """Отримати погоду з Yr.no"""
        location_coords = self.get_city_coordinates(city)
        if not location_coords:
            raise ValueError("Координати міста не знайдено")

        lat, lon = location_coords
        headers = {"User-Agent": "MyWeatherBot/1.0"}
        response = requests.get(f"{API_URL_YRNO}?lat={lat}&lon={lon}", headers=headers)
        response.raise_for_status()
        data = response.json()

        timeseries = data["properties"]["timeseries"][0]["data"]["instant"]["details"]
        return {
            "temp": timeseries["air_temperature"],
            "wind_speed": timeseries["wind_speed"],
            "humidity": timeseries["relative_humidity"],
            "pressure": timeseries["air_pressure_at_sea_level"],
            "feels_like": timeseries["air_temperature"],  
            "cloudiness": timeseries.get("cloud_area_fraction", 0)
        }

    async def get_weather_from_openmeteo(self, city: str) -> dict:
        """Отримати погоду з Open-Meteo (немає потреби в API ключі)"""
        location_coords = self.get_city_coordinates(city)
        if not location_coords:
            raise ValueError("Координати міста не знайдено")

        lat, lon = location_coords
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True
        }
        response = requests.get(API_URL_OPENMETEO, params=params)
        response.raise_for_status()
        data = response.json()

        current_weather = data["current_weather"]
        return {
            "temp": current_weather["temperature"],
            "wind_speed": current_weather["windspeed"],
            "humidity": 0,  
            "pressure": current_weather["pressure"],
            "feels_like": current_weather["temperature"],  
            "cloudiness": 0 
        }

    def get_city_coordinates(self, city: str) -> tuple:
        """Отримати координати міста для сервісів (вигаданий метод для прикладу)"""
        city_coords_map = {
            "kyiv": (50.4501, 30.5234),
            "london": (51.5074, -0.1278),
            "new york": (40.7128, -74.0060)
        }
        return city_coords_map.get(city.lower())

    async def auto_weather_updates(self):
        """Автоматичні оновлення погоди"""
        while True:
            now = datetime.now().time()
            if self.silent_mode and (self.silence_start <= now or now < self.silence_end):
                await asyncio.sleep(self.update_frequency * 60)
                continue

            api_key = self.get_api_key(self.current_provider)
            if not api_key and self.current_provider != "yrno" and self.current_provider != "openmeteo":
                logger.warning(f"API ключ для {self.current_provider} не встановлено")
                await asyncio.sleep(self.update_frequency * 60)
                continue

            city = self.db.get(self.strings["name"], "city", "")
            if city and self.weather_chat_ids:
                weather_info = await self.get_weather_info(city)
                if weather_info:
                    for chat_id in self.weather_chat_ids:
                        await self.client.send_message(chat_id, self.strings["weather_info"].format(city, weather_info))

            await asyncio.sleep(self.update_frequency * 60)
