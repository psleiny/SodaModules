import logging
import re
from urllib.parse import quote_plus
import requests
import xml.etree.ElementTree as ET
from telethon.tl.types import Message
from datetime import datetime, timedelta

from .. import loader, utils

logger = logging.getLogger(__name__)

n = "\n"
rus = "ёйцукенгшщзхъфывапролджэячсмитьбю"
ukr = "єїґцукенгшщзхїфівапролджєячсмитьбю"

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"
API_URL_OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"
API_URL_YR = "https://www.yr.no/place/{}/{}/forecast.xml"

class WeatherMod(loader.Module):
    """Модуль погоди з розширеними показниками (Advanced Weather Module)"""

    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено",
        "city_added": "✅ Місто <code>{}</code> додано до списку!",
        "city_removed": "❌ Місто <code>{}</code> видалено зі списку!",
        "api_key_missing": "❗ API ключ OpenWeatherMap не встановлено",
        "city_prompt": "❗ Будь ласка, вкажіть місто",
        "weather_info": "<b>Погода в {}: {}</b>",
        "weather_details": "🌡 Температура: {}°C\n💨 Вітер: {} м/с\n💧 Вологість: {}%\n🔴 Тиск: {} hPa",
        "forecast_info": "<b>Прогноз на {} днів у {}: {}</b>",
        "invalid_city": "❗ Місто не знайдено",
        "api_key_set": "🔑 API ключ встановлено!",
        "service_switched": "🔄 Сервіс змінено на {}",
        "unsupported_service": "❗ Непідтримуваний сервіс. Підтримуються: OpenWeatherMap, Yr.no",
        "service_missing": "❗ Сервіс не вибрано",
        "services_list": "Підтримувані сервіси: OpenWeatherMap, Yr.no",
        "city_list": "🏙 <b>Ваші міста:</b>\n{}",
        "no_cities": "❗ Ви не додали жодного міста",
        "units_set": "🌡 Одиниці вимірювання змінено на {}.",
        "daily_update_set": "🕒 Щоденне оновлення погоди налаштоване на {} для міста {}.",
    }

    def __init__(self):
        self.weather_cache = {}  # Cache for storing weather data temporarily
        self.units = "metric"  # Default temperature unit (Celsius)

    async def client_ready(self, client, db) -> None:
        self.db = db
        self.client = client

    def get_api_key(self) -> str:
        """Retrieve the stored OpenWeatherMap API key."""
        return self.db.get(self.strings["name"], "api_key", "")

    def get_weather_service(self) -> str:
        """Retrieve the currently selected weather service."""
        return self.db.get(self.strings["name"], "service", "OpenWeatherMap")

    def get_city_list(self) -> list:
        """Retrieve the list of stored cities."""
        return self.db.get(self.strings["name"], "cities", [])

    async def weatherkeycmd(self, message: Message) -> None:
        """Set OpenWeatherMap API key"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "api_key", args)
            await utils.answer(message, self.strings["api_key_set"])
        return

    async def weatherservicecmd(self, message: Message) -> None:
        """Switch between OpenWeatherMap and Yr.no"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["service_missing"])
            return

        service = args.strip().lower()
        if service in ["openweathermap", "owm"]:
            service_name = "OpenWeatherMap"
        elif service in ["yr.no", "yrno"]:
            service_name = "Yr.no"
        else:
            await utils.answer(message, self.strings["unsupported_service"])
            return

        self.db.set(self.strings["name"], "service", service_name)
        await utils.answer(message, self.strings["service_switched"].format(service_name))
        return

    async def setunitscmd(self, message: Message) -> None:
        """Set temperature units (metric or imperial)"""
        args = utils.get_args_raw(message)
        if args in ["metric", "imperial"]:
            self.units = args
            unit_name = "Цельсій" if args == "metric" else "Фаренгейт"
            await utils.answer(message, self.strings["units_set"].format(unit_name))
        else:
            await utils.answer(message, "❗ Неправильні одиниці. Використовуйте 'metric' або 'imperial'.")
    
    async def scheduleweathercmd(self, message: Message) -> None:
        """Schedule daily weather updates"""
        args = utils.get_args_raw(message).split()
        if len(args) != 2:
            await utils.answer(message, "❗ Невірний формат. Використовуйте: .scheduleweather <час у форматі HH:MM> <місто>")
            return
        
        time, city = args
        try:
            update_time = datetime.strptime(time, "%H:%M").time()
        except ValueError:
            await utils.answer(message, "❗ Неправильний формат часу. Використовуйте HH:MM.")
            return
        
        self.db.set(self.strings["name"], "update_time", update_time.strftime("%H:%M"))
        self.db.set(self.strings["name"], "update_city", city)
        await utils.answer(message, self.strings["daily_update_set"].format(update_time, city))

    async def weathercitycmd(self, message: Message) -> None:
        """Встановити місто за замовчуванням (Set default city for forecast)"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "city", args)

        city = self.db.get(self.strings["name"], "city", self.strings["no_city"])
        await utils.answer(message, self.strings["city_set"].format(city))
        return

    async def addcitycmd(self, message: Message) -> None:
        """Додати місто до списку (Add city to the city list)"""
        city = utils.get_args_raw(message)
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        cities = self.get_city_list()
        if city not in cities:
            cities.append(city)
            self.db.set(self.strings["name"], "cities", cities)
            await utils.answer(message, self.strings["city_added"].format(city))
        else:
            await utils.answer(message, f"Місто <code>{city}</code> вже є в списку.")

    async def delcitycmd(self, message: Message) -> None:
        """Видалити місто зі списку (Remove city from the city list)"""
        city = utils.get_args_raw(message)
        cities = self.get_city_list()

        if city not in cities:
            await utils.answer(message, self.strings["invalid_city"])
            return

        cities.remove(city)
        self.db.set(self.strings["name"], "cities", cities)

        await utils.answer(message, self.strings["city_removed"].format(city))

    async def listcitiescmd(self, message: Message) -> None:
        """Показати список міст (Show list of stored cities)"""
        cities = self.get_city_list()
        if not cities:
            await utils.answer(message, self.strings["no_cities"])
            return

        city_list = "\n".join([f"• {city}" for city in cities])
        await utils.answer(message, self.strings["city_list"].format(city_list))

    async def weathercmd(self, message: Message) -> None:
        """Прогноз погоди для вказаного міста (Current forecast for provided city)"""
        service = self.get_weather_service()
        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        try:
            if service == "OpenWeatherMap":
                await self.get_openweathermap_forecast(message, city)
            elif service == "Yr.no":
                await self.get_yrno_forecast(message, city)
            else:
                await utils.answer(message, self.strings["service_missing"])
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            await utils.answer(message, "❗ Виникла помилка під час отримання даних про погоду.")
        return

    async def forecastcmd(self, message: Message) -> None:
        """Прогноз на 3 дні для вказаного міста (3-day weather forecast)"""
        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        # Check cache first
        if city in self.weather_cache and self.weather_cache[city]["timestamp"] > datetime.now() - timedelta(minutes=10):
            forecast_data = self.weather_cache[city]["forecast"]
        else:
            params = {"q": city, "appid": api_key, "units": self.units, "cnt": 3}
            response = requests.get(API_URL_OWM_FORECAST, params=params)
            if response.status_code != 200:
                await utils.answer(message, self.strings["invalid_city"])
                return
            forecast_data = response.json()
            self.weather_cache[city] = {"forecast": forecast_data, "timestamp": datetime.now()}  # Cache the response

        forecast_text = ""
        for forecast in forecast_data["list"][:3]:
            date = datetime.utcfromtimestamp(forecast["dt"]).strftime("%Y-%m-%d")
            temp = forecast["main"]["temp"]
            description = forecast["weather"][0]["description"]
            forecast_text += f"{date}: {temp}°C, {description}\n"

        await utils.answer(message, self.strings["forecast_info"].format(3, city, forecast_text))

    async def get_openweathermap_forecast(self, message: Message, city: str) -> None:
        """Fetch weather data from OpenWeatherMap"""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        lang = "ua" if city[0].lower() in ukr else "en"
        params = {"q": city, "appid": api_key, "units": self.units, "lang": lang}
        try:
            response = requests.get(API_URL_OWM, params=params)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            await utils.answer(message, self.strings["invalid_city"])
            return

        data = response.json()
        weather_info = self.extract_weather_details(data)
        await utils.answer(message, self.strings["weather_info"].format(data["name"], weather_info))

    async def get_yrno_forecast(self, message: Message, city: str) -> None:
        """Fetch weather data from Yr.no"""
        city_parts = city.split(',')
        if len(city_parts) != 2:
            await utils.answer(message, self.strings["invalid_city"])
            return

        city_name, country = city_parts
        url = API_URL_YR.format(quote_plus(country.strip()), quote_plus(city_name.strip()))
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            await utils.answer(message, self.strings["invalid_city"])
            return

        root = ET.fromstring(response.content)
        weather_info = self.extract_weather_details_yrno(root)
        await utils.answer(message, self.strings["weather_info"].format(city_name, weather_info))

    def extract_weather_details(self, data: dict) -> str:
        """Extract and format weather details from OpenWeatherMap data"""
        temp = data["main"]["temp"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        weather_desc = data["weather"][0]["description"]
        return self.strings["weather_details"].format(temp, wind_speed, humidity, pressure) + f"\n{weather_desc}"

    def extract_weather_details_yrno(self, root: ET.Element) -> str:
        """Extract and format weather details from Yr.no XML data"""
        temp = root.find(".//temperature").attrib["value"]
        wind_speed = root.find(".//windSpeed").attrib["mps"]
        humidity = root.find(".//humidity").attrib["value"]
        pressure = root.find(".//pressure").attrib["value"]
        return self.strings["weather_details"].format(temp, wind_speed, humidity, pressure)
