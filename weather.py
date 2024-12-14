# meta developer: @lir1mod

import logging
import asyncio
import aiohttp
from datetime import datetime, time
from .. import loader, utils

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

API_URL_OWM = "https://api.openweathermap.org/data/2.5/weather"

@loader.tds
class WeatherMod(loader.Module):
    """Погодник"""

    strings = {
        "name": "Weather",
        "no_args": "<b>Вкажіть параметр:</b> <code>{}</code>",
        "city_added": "✅ Місто <b>{}</b> додано до списку обраних.",
        "city_removed": "❌ Місто <b>{}</b> видалено зі списку обраних.",
        "default_city_set": "🌟 Місто <b>{}</b> встановлено як основне.",
        "default_city_not_set": "❌ Основне місто ще не встановлено.",
        "chat_added": "✅ Чат додано до списку розсилки.",
        "chat_removed": "❌ Чат видалено зі списку розсилки.",
        "list_cities": "📋 Список обраних міст:\n{}",
        "list_chats": "📋 Список чатів для розсилки:\n{}",
        "weather_response": "🌤️ Погода в <b>{}</b>:\n{}",
        "weather_format": (
            "🌡 Температура: {}°C\n"
            "💨 Вітер: {} м/с\n"
            "💧 Вологість: {}%\n"
            "🔴 Тиск: {} hPa\n"
            "🤧 Відчувається як: {}°C\n"
            "☁️ Хмарність: {}%"
        ),
        "update_frequency": "<b>Частота оновлення встановлена:</b> {} хвилин.",
        "silent_mode_enabled": "🔕 <b>Режим тиші увімкнено (22:30 - 06:30).</b>",
        "silent_mode_disabled": "🔔 <b>Режим тиші вимкнено.</b>",
        "weather_no_default": "❌ Основне місто не встановлено. Виберіть місто через конфігурацію або додайте через <code>.addcity</code>.",
        "weather_no_city": "❌ Не вдалося знайти погоду для міста <b>{}</b>. Спробуйте інше місто.",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                None,
                lambda: "API ключ OpenWeatherMap. Отримати: https://home.openweathermap.org/api_keys",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
            loader.ConfigValue(
                "default_city",
                None,
                lambda: "Основне місто для прогнозу погоди. Вкажіть назву міста.",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "cache_timeout",
                600,
                lambda: "Час кешування (секунд)",
                validator=loader.validators.Integer(minimum=60),
            ),
            loader.ConfigValue(
                "update_frequency",
                60,
                lambda: "Частота оновлення (хвилин)",
                validator=loader.validators.Integer(minimum=1),
            ),
            loader.ConfigValue(
                "silent_mode",
                True,
                lambda: "Увімкнути режим тиші (22:30 - 06:30).",
                validator=loader.validators.Boolean(),
            ),
        )
        self.cache = {}

    async def client_ready(self, client, db):
        """Ініціалізація клієнта та бази даних."""
        self.db = db
        self.client = client
        logger.info("Клієнт готовий, запуск модуля Погода.")

    async def addcitycmd(self, message):
        """Додати місто до списку обраних."""
        city = utils.get_args_raw(message)
        if not city:
            return await utils.answer(message, self.strings["no_args"].format("addcity [місто]"))

        cities = self.db.get(self.strings["name"], "cities", [])
        if city not in cities:
            cities.append(city)
            self.db.set(self.strings["name"], "cities", cities)
            await utils.answer(message, self.strings["city_added"].format(city))
        else:
            await utils.answer(message, f"<b>Місто <b>{city}</b> вже додано.</b>")

    async def removecitycmd(self, message):
        """Видалити місто зі списку обраних."""
        city = utils.get_args_raw(message)
        if not city:
            return await utils.answer(message, self.strings["no_args"].format("removecity [місто]"))

        cities = self.db.get(self.strings["name"], "cities", [])
        if city in cities:
            cities.remove(city)
            self.db.set(self.strings["name"], "cities", cities)
            await utils.answer(message, self.strings["city_removed"].format(city))
        else:
            await utils.answer(message, f"<b>Місто <b>{city}</b> не знайдено.</b>")

    async def listcitiescmd(self, message):
        """Показати список обраних міст."""
        cities = self.db.get(self.strings["name"], "cities", [])
        if not cities:
            return await utils.answer(message, "<b>Список обраних міст порожній.</b>")

        cities_list = "\n".join([f"• {city}" for city in cities])
        await utils.answer(message, self.strings["list_cities"].format(cities_list))

    async def weathercmd(self, message):
        """Показати погоду для основного міста."""
        city = self.config["default_city"]
        if not city:
            return await utils.answer(message, self.strings["weather_no_default"])

        await self.get_weather(message, city)

    async def get_weather(self, message, city):
        """Отримати погоду для заданого міста."""
        api_key = self.config["api_key"]
        if not api_key:
            return await utils.answer(message, "❌ API ключ не заданий.")

        params = {"q": city, "appid": api_key, "units": "metric", "lang": "uk"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL_OWM, params=params) as response:
                    if response.status != 200:
                        return await utils.answer(message, self.strings["weather_no_city"].format(city))

                    data = await response.json()
                    weather = self.strings["weather_format"].format(
                        data["main"]["temp"], data["wind"]["speed"],
                        data["main"]["humidity"], data["main"]["pressure"],
                        data["main"]["feels_like"], data["clouds"]["all"]
                    )
                    await utils.answer(message, self.strings["weather_response"].format(city, weather))
        except Exception as e:
            logger.exception(f"Помилка отримання погоди для {city}: {e}")
            await utils.answer(message, "❌ Помилка отримання даних погоди.")
