import logging
import aiohttp
import asyncio
import datetime
from aiocache import cached
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

class WeatherMod(loader.Module):
    """Розширений модуль прогнозу погоди з використанням API yr.no з докладною статистикою за день"""

    strings = {"name": "Погода"}

    def __init__(self):
        self.db = None
        self.client = None

    async def client_ready(self, client, db):
        """Ініціалізація модуля."""
        self.db = db
        self.client = client

        # Load scheduled weather tasks for chat rooms
        chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        for chat_id in chat_rooms:
            asyncio.create_task(self.schedule_weather_updates(chat_id))

        # Schedule the daily weather summary at 22:30
        asyncio.create_task(self.schedule_daily_summary())

    @cached(ttl=3600)
    async def fetch_weather(self, latitude: float, longitude: float) -> dict:
        """Отримання даних про погоду з API yr.no."""
        headers = {"User-Agent": "YourWeatherBot/1.0"}
        params = {"lat": latitude, "lon": longitude}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    logger.error(f"Помилка отримання даних про погоду: {response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Не вдалося отримати дані про погоду: {e}")
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

        # Отримуємо координати для міста
        latitude, longitude = await self.geocode_city(city)
        if not latitude or not longitude:
            await utils.answer(message, f"⚠️ Не вдалося знайти координати для <b>{city}</b>.")
            return

        # Отримуємо дані про погоду з yr.no
        weather_data = await self.fetch_weather(latitude, longitude)
        if not weather_data:
            await utils.answer(message, f"⚠️ Не вдалося отримати дані про погоду для <b>{city}</b>. Спробуйте пізніше.")
            return

        # Отримуємо інформацію про поточну погоду
        timeseries = weather_data.get("properties", {}).get("timeseries", [])
        if not timeseries:
            await utils.answer(message, f"⚠️ Немає доступних даних про погоду для <b>{city}</b>.")
            return

        # Інформація про поточну погоду
        current_weather = timeseries[0]["data"]["instant"]["details"]

        # Отримуємо всі доступні параметри
        weather_details = {
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

        # Збереження погодних даних для статистики
        self.save_daily_statistics(city, weather_details)

        # Виводимо детальні дані про погоду
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
        """Геокодування назви міста до широти та довготи з використанням зовнішнього сервісу."""
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={utils.escape_html(city)}&format=json&limit=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(geocode_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return float(data[0]["lat"]), float(data[0]["lon"])
        return None, None

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
            "max_uv_index": 0  # Ensure max_uv_index exists
        })

        # Оновлення статистики
        temperature = weather_details['temperature']
        wind_speed = weather_details['wind_speed']
        precipitation = weather_details['precipitation_amount']
        uv_index = weather_details['uv_index']

        stats["high_temp"] = max(stats.get("high_temp", -999), temperature)
        stats["low_temp"] = min(stats.get("low_temp", 999), temperature)
        stats["total_precipitation"] += precipitation
        stats["average_wind_speed"] = (stats["average_wind_speed"] * stats["wind_count"] + wind_speed) / (stats["wind_count"] + 1)
        stats["wind_count"] += 1
        stats["max_uv_index"] = max(stats.get("max_uv_index", 0), uv_index)  # Use .get() to avoid KeyError

        self.db.set(self.strings["name"], f"stats_{city}", stats)

    async def addweathercmd(self, message: Message) -> None:
        """Додати чат для отримання погодних оновлень кожну годину."""
        chat_id = str(message.chat_id)

        weather_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        if chat_id not in weather_rooms:
            weather_rooms.append(chat_id)
            self.db.set(self.strings["name"], "weather_rooms", weather_rooms)
            await utils.answer(message, "✅ Цей чат додано для погодних оновлень.")
            asyncio.create_task(self.schedule_weather_updates(chat_id))
        else:
            await utils.answer(message, "⚠️ Цей чат вже отримує погодні оновлення.")

    async def removeweathercmd(self, message: Message) -> None:
        """Видалити чат з оновлень погоди."""
        chat_id = str(message.chat_id)

        weather_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        if chat_id in weather_rooms:
            weather_rooms.remove(chat_id)
            self.db.set(self.strings["name"], "weather_rooms", weather_rooms)
            await utils.answer(message, "❌ Цей чат було видалено з погодних оновлень.")
        else:
            await utils.answer(message, "⚠️ Цей чат не отримує погодні оновлення.")

    async def schedule_weather_updates(self, chat_id: str) -> None:
        """Плануємо погодні оновлення для чату кожну годину."""
        while True:
            # Поточний час
            current_time = datetime.datetime.now().time()

            # Якщо поточний час з 23:00 до 6:00, не надсилаємо оновлення
            if current_time >= datetime.time(23, 0) or current_time < datetime.time(6, 0):
                await asyncio.sleep(3600)
                continue

            # Використовуємо останнє збережене місто для отримання погоди
            city = self.db.get(self.strings["name"], "city", "")
            if not city:
                await asyncio.sleep(3600)
                continue

            latitude, longitude = await self.geocode_city(city)
            if not latitude or not longitude:
                await asyncio.sleep(3600)
                continue

            weather_data = await self.fetch_weather(latitude, longitude)
            if weather_data:
                timeseries = weather_data.get("properties", {}).get("timeseries", [])
                if timeseries:
                    current_weather = timeseries[0]["data"]["instant"]["details"]
                    temperature = current_weather.get("air_temperature", "N/A")
                    wind_speed = current_weather.get("wind_speed", "N/A")
                    wind_gust = current_weather.get("wind_speed_of_gust", "N/A")
                    humidity = current_weather.get("relative_humidity", "N/A")
                    precipitation = timeseries[0].get("data", {}).get("next_1_hours", {}).get("details", {}).get("precipitation_amount", "N/A")

                    await self.client.send_message(
                        int(chat_id),
                        f"🌤 <b>Поточна погода для {city}:</b>\n"
                        f"<b>Температура:</b> {temperature}°C\n"
                        f"<b>Вітер:</b> {wind_speed} м/с (пориви: {wind_gust} м/с)\n"
                        f"<b>Вологість:</b> {humidity}%\n"
                        f"<b>Опади за годину:</b> {precipitation} мм"
                    )

            await asyncio.sleep(3600)  # Чекаємо 1 годину до наступного оновлення

    async def schedule_daily_summary(self) -> None:
        """Запланувати щоденну статистику на 22:30."""
        while True:
            now = datetime.datetime.now()
            next_run = datetime.datetime.combine(now.date(), datetime.time(22, 30))
            if now > next_run:
                next_run += datetime.timedelta(days=1)

            # Чекаємо до 22:30
            await asyncio.sleep((next_run - now).total_seconds())

            # Отримуємо дані для щоденної статистики
            chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
            city = self.db.get(self.strings["name"], "city", "")

            if city:
                stats = self.db.get(self.strings["name"], f"stats_{city}", None)
                if stats:
                    high_temp = stats.get("high_temp", "N/A")
                    low_temp = stats.get("low_temp", "N/A")
                    total_precipitation = stats.get("total_precipitation", "N/A")
                    average_wind_speed = stats.get("average_wind_speed", "N/A")
                    max_uv_index = stats.get("max_uv_index", "N/A")

                    summary_message = (
                        f"📊 <b>Щоденна статистика для {city}:</b>\n"
                        f"<b>Макс. температура:</b> {high_temp}°C\n"
                        f"<b>Мін. температура:</b> {low_temp}°C\n"
                        f"<b>Загальні опади:</b> {total_precipitation} мм\n"
                        f"<b>Середня швидкість вітру:</b> {average_wind_speed} м/с\n"
                        f"<b>Макс. УФ-індекс:</b> {max_uv_index}"
                    )

                    # Надсилаємо статистику до кожного чату
                    for chat_id in chat_rooms:
                        await self.client.send_message(int(chat_id), summary_message)

                # Скидаємо статистику після надсилання
                self.db.set(self.strings["name"], f"stats_{city}", {
                    "high_temp": -999,
                    "low_temp": 999,
                    "total_precipitation": 0,
                    "average_wind_speed": 0,
                    "wind_count": 0,
                    "max_uv_index": 0
                })            
