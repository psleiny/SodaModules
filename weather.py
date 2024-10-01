import logging
import aiohttp
import asyncio
import datetime
from aiocache import cached
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

API_URLS = [
    "https://api.met.no/weatherapi/locationforecast/2.0/compact",  # Primary API
    "https://wttr.in",  # Free weather service without API key
]

class WeatherMod(loader.Module):
    """Розширений модуль прогнозу погоди з використанням API yr.no та інших відкритих сервісів"""

    strings = {"name": "Погода"}

    def __init__(self):
        self.db = None
        self.client = None

    async def client_ready(self, client, db):
        """Ініціалізація модуля."""
        self.db = db
        self.client = client

        chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        for chat_id in chat_rooms:
            asyncio.create_task(self.schedule_weather_updates(chat_id))

        asyncio.create_task(self.schedule_daily_summary())

    async def fetch_weather(self, latitude: float, longitude: float) -> dict:
        """Отримання даних про погоду з декількох API."""
        headers = {"User-Agent": "YourWeatherBot/1.0"}

        for api_url in API_URLS:
            try:
                if "wttr.in" in api_url:
                    # wttr.in requires parameters differently
                    api_url = f"{api_url}/{latitude},{longitude}?format=j1"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, headers=headers) as response:
                            if response.status == 200:
                                return await response.json()
                            logger.error(f"Помилка отримання даних про погоду з {api_url}: {response.status}")
                else:
                    # Default API structure (like met.no)
                    params = {"lat": latitude, "lon": longitude}
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, params=params, headers=headers) as response:
                            if response.status == 200:
                                return await response.json()
                            logger.error(f"Помилка отримання даних про погоду з {api_url}: {response.status}")
            except aiohttp.ClientError as e:
                logger.error(f"Помилка доступу до {api_url}: {e}")
        
        return None

    async def weathercitycmd(self, message: Message) -> None:
        """Команда для встановлення або відображення міста за замовчуванням."""
        city = utils.get_args_raw(message)
        if city:
            self.db.set(self.strings["name"], "city", city)
            await utils.answer(message, f"🏙 Місто за замовчуванням встановлено: <b>{city}</b>")
        else:
            current_city = self.db.get(self.strings["name"], "city", "🚫 Не вказано")
            await utils.answer(message, f"🏙 Поточне місто за замовчуванням: <b>{current_city}</b>")

    async def weathercmd(self, message: Message) -> None:
        """Отримати поточну погоду для вказаного або міста за замовчуванням."""
        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, "🚫 Місто не вказане або не встановлене за замовчуванням.")
            return

        latitude, longitude = await self.geocode_city(city)
        if not latitude or not longitude:
            await utils.answer(message, f"⚠️ Не вдалося знайти координати для <b>{city}</b>.")
            return

        weather_data = await self.fetch_weather(latitude, longitude)
        if not weather_data:
            await utils.answer(message, f"⚠️ Не вдалося отримати дані про погоду для <b>{city}</b>. Спробуйте пізніше.")
            return

        timeseries = self.extract_timeseries(weather_data)

        if not timeseries:
            await utils.answer(message, f"⚠️ Немає доступних даних про погоду для <b>{city}</b>.")
            return

        current_weather = timeseries[0]["data"]["instant"]["details"]

        weather_details = self.extract_weather_details(current_weather, timeseries)

        self.save_daily_statistics(city, weather_details)

        await utils.answer(
            message,
            (
                f"🌤 <b>Погода для {city}:</b>\n"
                f"<b>Температура:</b> {weather_details['temperature']}°C\n"
                f"<b>Відчувається як:</b> {weather_details['dew_point']}°C\n"
                f"<b>Вітер:</b> {weather_details['wind_speed']} м/с (пориви: {weather_details['wind_gust']} м/с)\n"
                f"<b>Тиск:</b> {weather_details['air_pressure']} гПа\n"
                f"<b>Вологість:</b> {weather_details['humidity']}%\n"
                f"<b>Хмарність:</b> {weather_details['cloud_area_fraction']}%\n"
                f"<b>Туман:</b> {weather_details['fog_area_fraction']}%\n"
                f"<b>Опади за годину:</b> {weather_details['precipitation_amount']} мм\n"
                f"<b>Ймовірність опадів:</b> {weather_details['precipitation_probability']}%\n"
                f"<b>УФ-індекс:</b> {weather_details['uv_index']}\n"
                f"<b>Видимість:</b> {weather_details['visibility']} м"
            )
        )

    async def geocode_city(self, city: str) -> tuple:
        """Геокодування назви міста до широти та довготи з використанням OpenStreetMap."""
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={utils.escape_html(city)}&format=json&limit=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(geocode_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return float(data[0]["lat"]), float(data[0]["lon"])
        return None, None

    def extract_timeseries(self, weather_data: dict) -> list:
        """Extract timeseries for weather data."""
        if "wttr.in" in weather_data.get("url", ""):
            # Custom extraction for wttr.in API format
            return [{
                "data": {
                    "instant": {
                        "details": {
                            "air_temperature": weather_data['current_condition']['temp_C'],
                            "wind_speed": weather_data['current_condition']['windspeedKmph'],
                            "dew_point_temperature": weather_data['current_condition']['FeelsLikeC'],
                            "relative_humidity": weather_data['current_condition']['humidity'],
                            "wind_speed_of_gust": weather_data['current_condition']['windspeedKmph'],
                            "visibility": weather_data['current_condition']['visibility']
                        }
                    },
                    "next_1_hours": {
                        "details": {
                            "precipitation_amount": weather_data['weather'][0]['hourly'][0]['precipMM'],
                            "probability_of_precipitation": weather_data['weather'][0]['hourly'][0]['chanceofrain']
                        }
                    }
                }
            }]
        # Default API structure
        return weather_data.get("properties", {}).get("timeseries", [])

    def extract_weather_details(self, current_weather: dict, timeseries: list) -> dict:
        """Екстракція погодних деталей."""
        return {
            "temperature": self.to_float(current_weather.get("air_temperature", "N/A")),
            "dew_point": self.to_float(current_weather.get("dew_point_temperature", "N/A")),
            "wind_speed": self.to_float(current_weather.get("wind_speed", "N/A")),
            "wind_direction": self.to_float(current_weather.get("wind_from_direction", "N/A")),
            "wind_gust": self.to_float(current_weather.get("wind_speed_of_gust", "N/A")),
            "humidity": self.to_float(current_weather.get("relative_humidity", "N/A")),
            "air_pressure": self.to_float(current_weather.get("air_pressure_at_sea_level", "N/A")),
            "cloud_area_fraction": self.to_float(current_weather.get("cloud_area_fraction", "N/A")),
            "fog_area_fraction": self.to_float(current_weather.get("fog_area_fraction", "N/A")),
            "precipitation_amount": self.to_float(timeseries[0].get("data", {}).get("next_1_hours", {}).get("details", {}).get("precipitation_amount", "N/A")),
            "precipitation_probability": self.to_float(timeseries[0].get("data", {}).get("next_1_hours", {}).get("details", {}).get("probability_of_precipitation", "N/A")),
            "uv_index": self.to_float(current_weather.get("ultraviolet_index_clear_sky", "N/A")),
            "visibility": self.to_float(current_weather.get("visibility", "N/A"))
        }

    def to_float(self, value):
        """Converts a value to float, returns 0 if conversion fails."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def save_daily_statistics(self, city: str, weather_details: dict) -> None:
        """Збереження всіх параметрів для щоденної статистики."""
        stats = self.db.get(self.strings["name"], f"stats_{city}", {
            "high_temp": -999,
            "low_temp": 999,
            "total_precipitation": 0,
            "average_wind_speed": 0,
            "wind_count": 0,
            "max_uv_index": 0
        })

        temperature = weather_details['temperature']
        wind_speed = weather_details['wind_speed']
        precipitation = weather_details['precipitation_amount']
        uv_index = weather_details['uv_index']

        stats["high_temp"] = max(stats.get("high_temp", -999), temperature)
        stats["low_temp"] = min(stats.get("low_temp", 999), temperature)
        stats["total_precipitation"] += precipitation
        stats["average_wind_speed"] = (stats["average_wind_speed"] * stats["wind_count"] + wind_speed) / (stats["wind_count"] + 1)
        stats["wind_count"] += 1
        stats["max_uv_index"] = max(stats.get("max_uv_index", 0), uv_index)

        self.db.set(self.strings["name"], f"stats_{city}", stats)
