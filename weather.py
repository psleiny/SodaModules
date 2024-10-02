import logging
import re
from urllib.parse import quote_plus
import requests
import xml.etree.ElementTree as ET
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from telethon.tl.types import Message

from .. import loader, utils
from ..inline import GeekInlineQuery, rand

logger = logging.getLogger(__name__)

n = "\n"
rus = "ёйцукенгшщзхъфывапролджэячсмитьбю"
ukr = "єїґцукенгшщзхїфівапролджєячсмитьбю"

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"
API_URL_YR = "https://www.yr.no/place/{}/{}/forecast.xml"

def escape_ansi(line):
    ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
    return ansi_escape.sub("", line)


class WeatherMod(loader.Module):
    """Модуль погоди з розширеними показниками (Advanced Weather Module)"""

    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено",
        "api_key_missing": "❗ API ключ OpenWeatherMap не встановлено",
        "city_prompt": "❗ Будь ласка, вкажіть місто",
        "weather_info": "<b>Погода в {}: {}</b>",
        "weather_details": "🌡 Температура: {}°C\n💨 Вітер: {} м/с\n💧 Вологість: {}%\n🔴 Тиск: {} hPa",
        "invalid_city": "❗ Місто не знайдено",
        "api_key_set": "🔑 API ключ встановлено!",
        "service_switched": "🔄 Сервіс змінено на {}",
        "service_missing": "❗ Сервіс не вибрано",
    }

    async def client_ready(self, client, db) -> None:
        self.db = db
        self.client = client

    def get_api_key(self) -> str:
        """Retrieve the stored OpenWeatherMap API key."""
        return self.db.get(self.strings["name"], "api_key", "")

    def get_weather_service(self) -> str:
        """Retrieve the currently selected weather service."""
        return self.db.get(self.strings["name"], "service", "OpenWeatherMap")

    async def weatherkeycmd(self, message: Message) -> None:
        """Set OpenWeatherMap API key"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "api_key", args)
            await utils.answer(message, self.strings["api_key_set"])
        return

    async def weatherservicecmd(self, message: Message) -> None:
        """Switch between OpenWeatherMap and yr.no"""
        if args := utils.get_args_raw(message):
            service = args.lower()
            if service in ["openweathermap", "yr.no"]:
                self.db.set(self.strings["name"], "service", service.capitalize())
                await utils.answer(message, self.strings["service_switched"].format(service.capitalize()))
        return

    async def weathercitycmd(self, message: Message) -> None:
        """Встановити місто за замовчуванням (Set default city for forecast)"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "city", args)

        city = self.db.get(self.strings["name"], "city", self.strings["no_city"])
        await utils.answer(message, self.strings["city_set"].format(city))
        return

    async def weathercmd(self, message: Message) -> None:
        """Прогноз погоди для вказаного міста (Current forecast for provided city)"""
        service = self.get_weather_service()
        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        if service == "OpenWeatherMap":
            await self.get_openweathermap_forecast(message, city)
        elif service == "Yr.no":
            await self.get_yrno_forecast(message, city)
        else:
            await utils.answer(message, self.strings["service_missing"])
        return

    async def get_openweathermap_forecast(self, message: Message, city: str) -> None:
        """Fetch weather data from OpenWeatherMap"""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        lang = "ua" if city[0].lower() in ukr else "en"
        params = {"q": city, "appid": api_key, "units": "metric", "lang": lang}
        response = requests.get(API_URL_OWM, params=params)

        if response.status_code != 200:
            await utils.answer(message, self.strings["invalid_city"])
            return

        data = response.json()
        weather_desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        city_name = data["name"]

        details = self.strings["weather_details"].format(temp, wind_speed, humidity, pressure)
        await utils.answer(message, self.strings["weather_info"].format(city_name, f"{weather_desc}\n{details}"))

    async def get_yrno_forecast(self, message: Message, city: str) -> None:
        """Fetch weather data from Yr.no"""
        # Yr.no uses a special format of city name and country, so adjustments may be needed
        city_parts = city.split(',')
        if len(city_parts) != 2:
            await utils.answer(message, self.strings["invalid_city"])
            return

        city_name, country = city_parts
        url = API_URL_YR.format(quote_plus(country.strip()), quote_plus(city_name.strip()))
        response = requests.get(url)

        if response.status_code != 200:
            await utils.answer(message, self.strings["invalid_city"])
            return

        # Parsing XML response
        root = ET.fromstring(response.content)
        temp = root.find(".//temperature").attrib["value"]
        wind_speed = root.find(".//windSpeed").attrib["mps"]
        humidity = root.find(".//humidity").attrib["value"]
        pressure = root.find(".//pressure").attrib["value"]
        city_name = root.find(".//location/name").text

        details = self.strings["weather_details"].format(temp, wind_speed, humidity, pressure)
        await utils.answer(message, self.strings["weather_info"].format(city_name, details))

    async def weather_inline_handler(self, query: GeekInlineQuery) -> None:
        """Пошук міста (Search city)"""
        service = self.get_weather_service()
        args = query.args or self.db.get(self.strings["name"], "city", "")
        if not args:
            return

        if service == "OpenWeatherMap":
            await self.get_openweathermap_inline(query, args)
        elif service == "Yr.no":
            await self.get_yrno_inline(query, args)
        return

    async def get_openweathermap_inline(self, query: GeekInlineQuery, city: str) -> None:
        """Inline forecast for OpenWeatherMap"""
        api_key = self.get_api_key()
        if not api_key:
            return

        lang = "ua" if city[0].lower() in ukr else "en"
        params = {"q": city, "appid": api_key, "units": "metric", "lang": lang}
        response = requests.get(API_URL_OWM, params=params)

        if response.status_code != 200:
            return

        data = response.json()
        weather_desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        city_name = data["name"]

        details = f"{temp}°C, {weather_desc}\n💨 {wind_speed} м/с, 💧 {humidity}%, 🔴 {pressure} hPa"
        await query.answer(
            [
                InlineQueryResultArticle(
                    id=rand(20),
                    title=f"Прогноз для {city_name}",
                    description=details,
                    input_message_content=InputTextMessageContent(
                        f"<b>Погода в {city_name}:</b> {details}",
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=0,
        )

    async def get_yrno_inline(self, query: GeekInlineQuery, city: str) -> None:
        """Inline forecast for Yr.no"""
        city_parts = city.split(',')
        if len(city_parts) != 2:
            return

        city_name, country = city_parts
        url = API_URL_YR.format(quote_plus(country.strip()), quote_plus(city_name.strip()))
        response = requests.get(url)

        if response.status_code != 200:
            return

        root = ET.fromstring(response.content)
        temp = root.find(".//temperature").attrib["value"]
        wind_speed = root.find(".//windSpeed").attrib["mps"]
        humidity = root.find(".//humidity").attrib["value"]
        pressure = root.find(".//pressure").attrib["value"]
        city_name = root.find(".//location/name").text

        details = f"{temp}°C, 💨 {wind_speed} м/с, 💧 {humidity}%, 🔴 {pressure} hPa"
        await query.answer(
            [
                InlineQueryResultArticle(
                    id=rand(20),
                    title=f"Прогноз для {city_name}",
                    description=details,
                    input_message_content=InputTextMessageContent(
                        f"<b>Погода в {city_name}:</b> {details}",
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=0,
        )
