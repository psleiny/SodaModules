# meta developer: @SodaModules

import logging
import aiohttp
import asyncio
import datetime
import random
from aiocache import cached
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_API_URL = "https://nominatim.openstreetmap.org/search"

class WeatherMod(loader.Module):
    """Модуль погоди з використанням Open-Meteo з глобальним охопленням"""

    strings = {"name": "Погода"}

    def __init__(self):
        self.db = None
        self.client = None
        self.last_update_time = {}  # Stores the last update time to avoid spamming

    async def client_ready(self, client, db):
        """Ініціалізація модуля."""
        self.db = db
        self.client = client

        # Schedule weather updates for chats
        chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        for chat_id in chat_rooms:
            asyncio.create_task(self.schedule_weather_updates(chat_id))

        # Schedule daily weather summary at 22:30
        asyncio.create_task(self.schedule_daily_summary())

    @cached(ttl=3600)
    async def fetch_open_meteo_weather(self, latitude: float, longitude: float) -> dict:
        """Отримати погодні дані з Open-Meteo API."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,precipitation,wind_speed_10m",
            "current_weather": "true",
            "timezone": "Europe/Kiev"  # Adjust timezone if needed
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(OPEN_METEO_API_URL, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    logger.error(f"Помилка отримання даних з Open-Meteo: {response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Помилка підключення до Open-Meteo: {e}")
            return None

    async def geocode_city(self, city: str) -> tuple:
        """Геокодування назви міста до широти та довготи за допомогою Nominatim (OpenStreetMap)."""
        params = {"q": city, "format": "json", "limit": 1}
        async with aiohttp.ClientSession() as session:
            async with session.get(NOMINATIM_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return float(data[0]["lat"]), float(data[0]["lon"])
                logger.error(f"Не вдалося геокодувати місто: {response.status}")
        return None, None

    def random_fun_fact(self) -> str:
        """Випадкове повідомлення для розваги."""
        facts = [
            "🌩 Чи знаєте ви, що блискавка може вдарити одне й те саме місце кілька разів?",
            "☀️ Найспекотніша температура на Землі була зафіксована в Долині Смерті, Каліфорнія: 56.7°C!",
            "🌈 Веселка фактично кругла. Але з землі ми бачимо тільки півколо.",
            "❄️ У Південному Полярному колі може бути холодніше, ніж на Північному полюсі!",
            "💨 Вітер з неймовірною швидкістю 484 км/год був зафіксований на австралійському острові Барроу!"
        ]
        return random.choice(facts)

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

        # Отримуємо погодні дані з Open-Meteo
        weather_data = await self.fetch_open_meteo_weather(latitude, longitude)
        if not weather_data:
            await utils.answer(message, f"⚠️ Не вдалося отримати погодні дані для <b>{city}</b> з Open-Meteo.")
            return

        # Витягнути необхідні дані з Open-Meteo
        current_weather = weather_data["current_weather"]
        temp = current_weather["temperature"]
        wind_speed = current_weather["windspeed"]
        short_forecast = "Наразі без опадів" if current_weather["weathercode"] == 0 else "Можливі опади"

        # Збереження щоденних статистичних даних
        self.save_daily_statistics(city, temp, wind_speed)

        # Створення повідомлення
        message_text = (
            f"🌤 <b>Погода для {city} (Open-Meteo):</b>\n"
            f"<b>Температура:</b> {temp}°C\n"
            f"<b>Вітер:</b> {wind_speed} м/с\n"
            f"<b>Прогноз:</b> {short_forecast}\n"
            f"{self.random_fun_fact()}"
        )

        # Відправляємо повідомлення
        await utils.answer(message, message_text)

    def save_daily_statistics(self, city: str, temp: float, wind_speed: float) -> None:
        """Збереження щоденних статистичних даних: макс. температура та середня швидкість вітру."""
        stats = self.db.get(self.strings["name"], f"stats_{city}", {
            "high_temp": -999,
            "low_temp": 999,
            "total_wind_speed": 0,
            "wind_count": 0
        })

        # Оновлюємо статистику
        stats["high_temp"] = max(stats.get("high_temp", -999), temp)
        stats["low_temp"] = min(stats.get("low_temp", 999), temp)
        stats["total_wind_speed"] += wind_speed
        stats["wind_count"] += 1

        self.db.set(self.strings["name"], f"stats_{city}", stats)

    async def addweathercmd(self, message: Message) -> None:
        """Додати чат для отримання погодних оновлень кожну годину."""
        chat_id = str(message.chat_id)

        weather_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        if chat_id not in weather_rooms:
            weather_rooms.append(chat_id)
            self.db.set(self.strings["name"], "weather_rooms", weather_rooms)
            await utils.answer(message, "✅ Цей чат було додано для погодних оновлень.")
            asyncio.create_task(self.schedule_weather_updates(chat_id))
        else:
            await utils.answer(message, "⚠️ Цей чат вже отримує погодні оновлення.")

    async def removeweathercmd(self, message: Message) -> None:
        """Видалити чат з погодних оновлень."""
        chat_id = str(message.chat_id)

        weather_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        if chat_id in weather_rooms:
            weather_rooms.remove(chat_id)
            self.db.set(self.strings["name"], "weather_rooms", weather_rooms)
            await utils.answer(message, "❌ Цей чат було видалено з погодних оновлень.")
        else:
            await utils.answer(message, "⚠️ Цей чат не отримує погодні оновлення.")

    async def schedule_weather_updates(self, chat_id: str) -> None:
        """Запланувати погодні оновлення для чату кожну годину."""
        while True:
            current_time = datetime.datetime.now().time()

            # Не надсилаємо оновлення з 23:00 до 6:00
            if current_time >= datetime.time(23, 0) or current_time < datetime.time(6, 0):
                await asyncio.sleep(3600)
                continue

            city = self.db.get(self.strings["name"], "city", "")
            if not city:
                await asyncio.sleep(3600)
                continue

            latitude, longitude = await self.geocode_city(city)
            if not latitude or not longitude:
                await asyncio.sleep(3600)
                continue

            # Перевіряємо, коли було останнє оновлення (щоб уникнути спаму)
            last_time = self.last_update_time.get(chat_id, datetime.datetime.min)
            if (datetime.datetime.now() - last_time).seconds < 3600:
                await asyncio.sleep(3600)
                continue

            # Отримуємо погодні дані з Open-Meteo
            weather_data = await self.fetch_open_meteo_weather(latitude, longitude)
            if weather_data:
                current_weather = weather_data["current_weather"]
                temp = current_weather["temperature"]
                wind_speed = current_weather["windspeed"]
                short_forecast = "Наразі без опадів" if current_weather["weathercode"] == 0 else "Можливі опади"

                # Відправляємо погодне оновлення в чат
                await self.client.send_message(
                    int(chat_id),
                    f"🌤 <b>Оновлення погоди для {city} (Open-Meteo):</b>\n"
                    f"<b>Температура:</b> {temp}°C\n"
                    f"<b>Вітер:</b> {wind_speed} м/с\n"
                    f"<b>Прогноз:</b> {short_forecast}\n"
                    f"{self.random_fun_fact()}"
                )

                # Зберігаємо час останнього оновлення
                self.last_update_time[chat_id] = datetime.datetime.now()

            await asyncio.sleep(3600)  # Чекаємо 1 годину до наступного оновлення

    async def schedule_daily_summary(self) -> None:
        """Запланувати щоденну статистику на 22:30."""
        while True:
            now = datetime.datetime.now()
            next_run = datetime.datetime.combine(now.date(), datetime.time(22, 30))
            if now > next_run:
                next_run += datetime.timedelta(days=1)

            await asyncio.sleep((next_run - now).total_seconds())

            chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
            city = self.db.get(self.strings["name"], "city", "")

            if city:
                stats = self.db.get(self.strings["name"], f"stats_{city}", None)
                if stats:
                    high_temp = stats.get("high_temp", "N/A")
                    low_temp = stats.get("low_temp", "N/A")
                    avg_wind_speed = stats.get("total_wind_speed", 0) / stats.get("wind_count", 1)

                    summary_message = (
                        f"📊 <b>Щоденна статистика для {city}:</b>\n"
                        f"<b>Макс. температура:</b> {high_temp}°C\n"
                        f"<b>Мін. температура:</b> {low_temp}°C\n"
                        f"<b>Середня швидкість вітру:</b> {avg_wind_speed} м/с"
                    )

                    for chat_id in chat_rooms:
                        await self.client.send_message(int(chat_id), summary_message)

                # Скидаємо статистику після відправки
                self.db.set(self.strings["name"], f"stats_{city}", {
                    "high_temp": -999,
                    "low_temp": 999,
                    "total_wind_speed": 0,
                    "wind_count": 0
                })
