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
ukr = "єїґцукенгшщзхїфівапролджєячсмитьбю"

API_URL = "https://api.openweathermap.org/data/2.5/weather"

def escape_ansi(line):
    ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
    return ansi_escape.sub("", line)


class WeatherMod(loader.Module):
    """Модуль погоди (Weather module in Ukrainian)"""

    strings = {
        "name": "Погода",
        "city_set": "<b>🏙 Ваше поточне місто: <code>{}</code></b>",
        "no_city": "🚫 Місто не встановлено",
        "api_key_missing": "❗ API ключ OpenWeatherMap не встановлено",
        "city_prompt": "❗ Будь ласка, вкажіть місто",
        "weather_info": "<b>Погода в {}: {}</b>",
        "invalid_city": "❗ Місто не знайдено",
        "api_key_set": "🔑 API ключ встановлено!",
    }

    async def client_ready(self, client, db) -> None:
        self.db = db
        self.client = client

    def get_api_key(self) -> str:
        """Retrieve the stored API key."""
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
        """Прогноз погоди для вказаного міста (Current forecast for provided city)"""
        api_key = self.get_api_key()
        if not api_key:
            await utils.answer(message, self.strings["api_key_missing"])
            return

        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, self.strings["city_prompt"])
            return

        lang = "ua" if city[0].lower() in ukr else "en"
        params = {"q": city, "appid": api_key, "units": "metric", "lang": lang}
        response = requests.get(API_URL, params=params)

        if response.status_code != 200:
            await utils.answer(message, self.strings["invalid_city"])
            return

        data = response.json()
        weather_desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        city_name = data["name"]

        await utils.answer(
            message,
            self.strings["weather_info"].format(city_name, f"{temp}°C, {weather_desc}")
        )

    async def weather_inline_handler(self, query: GeekInlineQuery) -> None:
        """Пошук міста (Search city)"""
        api_key = self.get_api_key()
        if not api_key:
            return

        args = query.args or self.db.get(self.strings["name"], "city", "")
        if not args:
            return

        lang = "ua" if args[0].lower() in ukr else "en"
        params = {"q": args, "appid": api_key, "units": "metric", "lang": lang}
        response = requests.get(API_URL, params=params)

        if response.status_code != 200:
            return

        data = response.json()
        weather_desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        city_name = data["name"]

        await query.answer(
            [
                InlineQueryResultArticle(
                    id=rand(20),
                    title=f"Прогноз для {city_name}",
                    description=f"{temp}°C, {weather_desc}",
                    input_message_content=InputTextMessageContent(
                        f"<b>Погода в {city_name}:</b> {temp}°C, {weather_desc}",
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=0,
        )
