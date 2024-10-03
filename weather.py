import logging
import requests
from telethon.tl.types import Message
from datetime import datetime
from time import time

from .. import loader, utils

logger = logging.getLogger(__name__)

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"
API_URL_ONECALL = "https://api.openweathermap.org/data/2.5/onecall"

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
        "api_key_invalid": "❗ Невірний API ключ.",
        "api_key_valid": "✅ API ключ дійсний.",
        "alerts": "⚠️ Оповіщення про погоду:\n"
    }

    def __init__(self):
        self.units = "metric"  
        self.lang = "ua"       
        self.cache = {}        
        self.cache_timeout = 600  

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

        if city in self.cache and time() - self.cache[city]["time"] < self.cache_timeout:
            weather_info = self.cache[city]["data"]
        else:
            params = {"q": city, "appid": api_key, "units": self.units, "lang": self.lang}
            try:
                response = requests.get(API_URL_OWM, params=params)
                response.raise_for_status()
            except requests.exceptions.RequestException:
                await utils.answer(message, self.strings["invalid_city"])
                return

            data = response.json()
            weather_info = self.extract_weather_details(data)
            self.cache[city] = {"data": weather_info, "time": time()}

        await utils.answer(message, self.strings["weather_info"].format(city, weather_info))

    def extract_weather_details(self, data: dict) -> str:
        """Extract and format weather details from OpenWeatherMap data"""
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

    async def extendedweathercmd(self, message: Message) -> None:
        """Extended forecast (Hourly and Daily weather)"""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        geocoding_url = "http://api.openweathermap.org/geo/1.0/direct"
        geo_params = {"q": city, "limit": 1, "appid": api_key}
        response = requests.get(geocoding_url, params=geo_params)
        location_data = response.json()
        if not location_data:
            await utils.answer(message, self.strings["invalid_city"])
            return

        lat, lon = location_data[0]["lat"], location_data[0]["lon"]
        params = {"lat": lat, "lon": lon, "appid": api_key, "units": self.units, "exclude": "minutely", "lang": self.lang}

        try:
            response = requests.get(API_URL_ONECALL, params=params)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            await utils.answer(message, self.strings["invalid_city"])
            return

        data = response.json()
        forecast_info = self.extract_extended_forecast(data)
        await utils.answer(message, forecast_info)

    def extract_extended_forecast(self, data: dict) -> str:
        """Extract hourly and daily forecast from OneCall API data"""
        hourly = data.get("hourly", [])
        daily = data.get("daily", [])
        alerts = data.get("alerts", [])

        hourly_forecast = "🕐 <b>Hourly Forecast:</b>\n"
        for hour in hourly[:12]:  
            dt = datetime.fromtimestamp(hour["dt"]).strftime("%H:%M")
            temp = hour["temp"]
            desc = hour["weather"][0]["description"]
            hourly_forecast += f"{dt}: {temp}°C, {desc}\n"

        daily_forecast = "\n📅 <b>7-Day Forecast:</b>\n"
        for day in daily:
            dt = datetime.fromtimestamp(day["dt"]).strftime("%d-%m-%Y")
            temp_day = day["temp"]["day"]
            temp_night = day["temp"]["night"]
            desc = day["weather"][0]["description"]
            daily_forecast += f"{dt}: Day {temp_day}°C, Night {temp_night}°C, {desc}\n"
            
        alert_info = ""
        if alerts:
            alert_info = self.strings["alerts"]
            for alert in alerts:
                alert_info += f"{alert['event']}: {alert['description']}\n"

        return hourly_forecast + daily_forecast + alert_info

    async def checkapikeycmd(self, message: Message) -> None:
        """Check if the API key is valid."""
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
