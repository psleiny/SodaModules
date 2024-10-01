import logging
import aiohttp
import asyncio
import datetime
from aiocache import cached
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

# yr.no API
YR_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

# OpenWeatherMap API (requires key)
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

class WeatherMod(loader.Module):
    """Weather forecast module using yr.no and OpenWeatherMap with detailed daily statistics."""

    strings = {"name": "Weather"}

    def __init__(self):
        self.db = None
        self.client = None

    async def client_ready(self, client, db):
        """Module initialization."""
        self.db = db
        self.client = client

        # Load scheduled weather tasks for chat rooms
        chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
        for chat_id in chat_rooms:
            asyncio.create_task(self.schedule_weather_updates(chat_id))

        # Schedule daily weather summary at 22:30
        asyncio.create_task(self.schedule_daily_summary())

    async def fetch_weather(self, latitude: float, longitude: float, service: str = "yr") -> dict:
        """Fetch weather data from the selected service."""
        headers = {"User-Agent": "YourWeatherBot/1.0"}
        
        if service == "yr":
            url = YR_API_URL
            params = {"lat": latitude, "lon": longitude}
        elif service == "openweather":
            api_key = self.db.get(self.strings["name"], "openweather_api_key", "")
            if not api_key:
                logger.error("OpenWeather API key not found.")
                return None
            url = OPENWEATHER_API_URL
            params = {"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"}
        else:
            logger.error(f"Unknown weather service: {service}")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    logger.error(f"Error fetching weather data from {service}: {response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch weather data from {service}: {e}")
            return None

    async def weathercmd(self, message: Message) -> None:
        """Get current weather for the specified or default city."""
        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, "🚫 No city specified or set as default.")
            return

        # Get coordinates for the city
        latitude, longitude = await self.geocode_city(city)
        if not latitude or not longitude:
            await utils.answer(message, f"⚠️ Failed to find coordinates for <b>{city}</b>.")
            return

        # Fetch weather data from the default service (yr)
        service = self.db.get(self.strings["name"], "weather_service", "yr")
        weather_data = await self.fetch_weather(latitude, longitude, service)

        if not weather_data:
            await utils.answer(message, f"⚠️ Failed to retrieve weather data for <b>{city}</b>. Try again later.")
            return

        # Parse and display weather data
        weather_details = self.parse_weather_data(weather_data, service)
        if weather_details:
            self.save_daily_statistics(city, weather_details)
            await utils.answer(
                message,
                (
                    f"🌤 <b>Weather for {city}:</b>\n"
                    f"<b>Temperature:</b> {weather_details['temperature']}°C\n"
                    f"<b>Feels like:</b> {weather_details['dew_point']}°C\n"
                    f"<b>Wind:</b> {weather_details['wind_speed']} m/s (gusts: {weather_details['wind_gust']} m/s)\n"
                    f"<b>Pressure:</b> {weather_details['air_pressure']} hPa\n"
                    f"<b>Humidity:</b> {weather_details['humidity']}%\n"
                    f"<b>Cloudiness:</b> {weather_details['cloud_area_fraction']}%\n"
                    f"<b>Precipitation:</b> {weather_details['precipitation_amount']} mm\n"
                    f"<b>Precipitation probability:</b> {weather_details['precipitation_probability']}%\n"
                    f"<b>UV index:</b> {weather_details['uv_index']}\n"
                    f"<b>Visibility:</b> {weather_details['visibility']} m"
                )
            )
        else:
            await utils.answer(message, f"⚠️ No weather data available for <b>{city}</b>.")

    async def geocode_city(self, city: str) -> tuple:
        """Geocode the city name to latitude and longitude."""
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={utils.escape_html(city)}&format=json&limit=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(geocode_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return float(data[0]["lat"]), float(data[0]["lon"])
        return None, None

    def parse_weather_data(self, weather_data: dict, service: str) -> dict:
        """Parse weather data according to the service."""
        if service == "yr":
            timeseries = weather_data.get("properties", {}).get("timeseries", [])
            if not timeseries:
                return None

            current_weather = timeseries[0]["data"]["instant"]["details"]
            return {
                "temperature": self.to_float(current_weather.get("air_temperature")),
                "dew_point": self.to_float(current_weather.get("dew_point_temperature")),
                "wind_speed": self.to_float(current_weather.get("wind_speed")),
                "wind_gust": self.to_float(current_weather.get("wind_speed_of_gust")),
                "humidity": self.to_float(current_weather.get("relative_humidity")),
                "air_pressure": self.to_float(current_weather.get("air_pressure_at_sea_level")),
                "cloud_area_fraction": self.to_float(current_weather.get("cloud_area_fraction")),
                "precipitation_amount": self.to_float(timeseries[0].get("data", {}).get("next_1_hours", {}).get("details", {}).get("precipitation_amount", 0.0)),
                "precipitation_probability": self.to_float(timeseries[0].get("data", {}).get("next_1_hours", {}).get("details", {}).get("probability_of_precipitation", 0.0)),
                "uv_index": self.to_float(current_weather.get("ultraviolet_index_clear_sky")),
                "visibility": self.to_float(current_weather.get("visibility")),
            }
        elif service == "openweather":
            return {
                "temperature": self.to_float(weather_data["main"].get("temp")),
                "dew_point": 0.0,  # OpenWeatherMap doesn't provide dew point directly
                "wind_speed": self.to_float(weather_data["wind"].get("speed")),
                "wind_gust": self.to_float(weather_data["wind"].get("gust", 0.0)),
                "humidity": self.to_float(weather_data["main"].get("humidity")),
                "air_pressure": self.to_float(weather_data["main"].get("pressure")),
                "cloud_area_fraction": self.to_float(weather_data["clouds"].get("all")),
                "precipitation_amount": self.to_float(weather_data.get("rain", {}).get("1h", 0.0)),
                "precipitation_probability": 0.0,  # Not provided
                "uv_index": 0.0,  # Not provided
                "visibility": self.to_float(weather_data.get("visibility")),
            }

    def to_float(self, value):
        """Convert a value to float, return 0.0 if conversion fails."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def save_daily_statistics(self, city: str, weather_details: dict) -> None:
        """Save weather data for daily statistics."""
        stats = self.db.get(self.strings["name"], f"stats_{city}", {
            "high_temp": -999,
            "low_temp": 999,
            "total_precipitation": 0,
            "average_wind_speed": 0,
            "wind_count": 0,
            "max_uv_index": 0
        })

        # Update daily stats
        stats["high_temp"] = max(stats["high_temp"], weather_details["temperature"])
        stats["low_temp"] = min(stats["low_temp"], weather_details["temperature"])
        stats["total_precipitation"] += weather_details["precipitation_amount"]
        stats["average_wind_speed"] = (stats["average_wind_speed"] * stats["wind_count"] + weather_details["wind_speed"]) / (stats["wind_count"] + 1)
        stats["wind_count"] += 1
        stats["max_uv_index"] = max(stats["max_uv_index"], weather_details["uv_index"])

        self.db.set(self.strings["name"], f"stats_{city}", stats)

    async def schedule_weather_updates(self, chat_id: str) -> None:
        """Schedule hourly weather updates for a chat."""
        while True:
            now = datetime.datetime.now().time()
            if now >= datetime.time(23, 0) or now < datetime.time(6, 0):
                await asyncio.sleep(3600)  # No updates from 23:00 to 6:00
                continue

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
                weather_details = self.parse_weather_data(weather_data, "yr")
                if weather_details:
                    await self.client.send_message(
                        int(chat_id),
                        f"🌤 <b>Current weather for {city}:</b>\n"
                        f"<b>Temperature:</b> {weather_details['temperature']}°C\n"
                        f"<b>Wind:</b> {weather_details['wind_speed']} m/s (gusts: {weather_details['wind_gust']} m/s)\n"
                        f"<b>Humidity:</b> {weather_details['humidity']}%\n"
                        f"<b>Precipitation:</b> {weather_details['precipitation_amount']} mm"
                    )

            await asyncio.sleep(3600)  # Wait 1 hour for the next update

    async def schedule_daily_summary(self) -> None:
        """Schedule a daily summary at 22:30."""
        while True:
            now = datetime.datetime.now()
            next_run = datetime.datetime.combine(now.date(), datetime.time(22, 30))
            if now > next_run:
                next_run += datetime.timedelta(days=1)

            await asyncio.sleep((next_run - now).total_seconds())

            city = self.db.get(self.strings["name"], "city", "")
            if city:
                stats = self.db.get(self.strings["name"], f"stats_{city}", None)
                if stats:
                    summary_message = (
                        f"📊 <b>Daily statistics for {city}:</b>\n"
                        f"<b>Max Temperature:</b> {stats['high_temp']}°C\n"
                        f"<b>Min Temperature:</b> {stats['low_temp']}°C\n"
                        f"<b>Total Precipitation:</b> {stats['total_precipitation']} mm\n"
                        f"<b>Average Wind Speed:</b> {stats['average_wind_speed']} m/s\n"
                        f"<b>Max UV Index:</b> {stats['max_uv_index']}"
                    )

                    # Send summary to all registered chats
                    chat_rooms = self.db.get(self.strings["name"], "weather_rooms", [])
                    for chat_id in chat_rooms:
                        await self.client.send_message(int(chat_id), summary_message)

                # Reset daily stats
                self.db.set(self.strings["name"], f"stats_{city}", {
                    "high_temp": -999,
                    "low_temp": 999,
                    "total_precipitation": 0,
                    "average_wind_speed": 0,
                    "wind_count": 0,
                    "max_uv_index": 0
                })
