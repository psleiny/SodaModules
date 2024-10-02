import logging
import re
from urllib.parse import quote_plus

import requests
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from telethon.tl.types import Message

from .. import loader, utils
from ..inline import GeekInlineQuery, rand

logger = logging.getLogger(__name__)

n = "\n"
rus = "ёйцукенгшщзхъфывапролджэячсмитьбю"


def escape_ansi(line):
    ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
    return ansi_escape.sub("", line)


class WeatherMod(loader.Module):
    """Weather module"""

    strings = {"name": "Weather"}

    async def client_ready(self, client, db) -> None:
        self.db = db
        self.client = client
        self.api_key = self.db.get(self.strings["name"], "api_key", "")
        self.default_city = self.db.get(self.strings["name"], "city", "")

    async def apicmd(self, message: Message) -> None:
        """Set API key for OpenWeatherMap"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "api_key", args)
            self.api_key = args
            await utils.answer(message, "<b>✅ API key has been set successfully!</b>")
        else:
            await utils.answer(message, "<b>🚫 Please provide a valid API key.</b>")

    async def weathercitycmd(self, message: Message) -> None:
        """Set default city for forecast"""
        if args := utils.get_args_raw(message):
            self.db.set(self.strings["name"], "city", args)
            self.default_city = args

        await utils.answer(
            message,
            (
                "<b>🏙 Your current city: "
                f"<code>{self.db.get(self.strings['name'], 'city', '🚫 Not specified')}</code></b>"
            ),
        )
        return

    async def get_weather_data(self, city: str, lang: str = "en") -> dict:
        """Fetches weather data from OpenWeatherMap."""
        if not self.api_key:
            logger.error("API key is not set.")
            return {"error": "🚫 API key is not set. Use the .api command to set it."}

        url = (
            f"http://api.openweathermap.org/data/2.5/weather?q={quote_plus(city)}"
            f"&appid={self.api_key}&units=metric&lang={lang}"
        )
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Error fetching weather data: {response.text}")
        return None

    def format_weather(self, data: dict) -> str:
        """Formats the weather data into a user-friendly message."""
        if not data:
            return "🚫 Unable to fetch weather data."

        if "error" in data:
            return data["error"]

        weather = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        city = data["name"]
        country = data["sys"]["country"]

        return (
            f"🌍 {city}, {country}\n"
            f"🌡 Temperature: {temp}°C (Feels like: {feels_like}°C)\n"
            f"🌤 Condition: {weather}"
        )

    async def weathercmd(self, message: Message) -> None:
        """Current forecast for provided city"""
        city = utils.get_args_raw(message) or self.default_city
        if not city:
            await utils.answer(message, "<b>🚫 No city provided. Set a default city using .weathercitycmd</b>")
            return

        lang = "ru" if city and city[0].lower() in rus else "en"
        data = await self.get_weather_data(city, lang)
        weather_message = self.format_weather(data)
        await utils.answer(message, f"<code>{weather_message}</code>")

    async def weather_inline_handler(self, query: GeekInlineQuery) -> None:
        """Search city"""
        args = query.args or self.default_city

        if not args:
            return

        lang = "ru" if args and args[0].lower() in rus else "en"
        data = await self.get_weather_data(args, lang)
        weather_message = self.format_weather(data)

        await query.answer(
            [
                InlineQueryResultArticle(
                    id=rand(20),
                    title=f"Forecast for {args}",
                    description=weather_message,
                    input_message_content=InputTextMessageContent(
                        f'<code>{weather_message}</code>',
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=0,
        )
