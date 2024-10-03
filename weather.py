import logging
import requests
from telethon.tl.types import Message
from datetime import datetime

from .. import loader, utils

logger = logging.getLogger(__name__)

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"

class WeatherMod(loader.Module):
    """Модуль погоди з розширеними показниками (Advanced Weather Module)"""

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
    }

    def __init__(self):
        self.units = "metric"  # Default temperature unit (Celsius)

    async def client_ready(self, client, db) -> None:
        self.db = db
        self.client = client

    def get_api_key(self) -> str:
        """Retrieve the stored OpenWeatherMap API key."""
        return self.db.get(self.strings["name"], "api_key", "")

    async def weatherkeycmd(self, message: Message) -> None:
        """Set OpenWeatherMap API key"""
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

        # OpenWeatherMap API request for current weather
        params = {"q": city, "appid": api_key, "units": self.units}
        try:
            response = requests.get(API_URL_OWM, params=params)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            await utils.answer(message, self.strings["invalid_city"])
            return

        data = response.json()
        weather_info = self.extract_weather_details(data)
        await utils.answer(message, self.strings["weather_info"].format(data["name"], weather_info))

    def extract_weather_details(self, data: dict) -> str:
        """Extract and format weather details from OpenWeatherMap data"""
        temp = data["main"]["temp"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        feels_like = data["main"]["feels_like"]
        cloudiness = data["clouds"]["all"]
        visibility = data.get("visibility", 10000)  # Default visibility is 10,000 meters
        weather_desc = data["weather"][0]["description"]

        return self.strings["weather_details"].format(
            temp, wind_speed, humidity, pressure, feels_like, cloudiness, visibility
        ) + f"\n{weather_desc}"
