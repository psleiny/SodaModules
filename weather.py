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
    """Unified Weather forecast module using yr.no and OpenWeatherMap with periodic updates."""

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
            asyncio.create_task(self.schedule_weather_updates(chat_id, 7200))  # 2-hour interval

    # --- Weather Fetching Functions ---
    @cached(ttl=3600)
    async def fetch_weather(self, latitude: float, longitude: float, service: str) -> dict:
        """Fetch weather data from yr.no or OpenWeatherMap."""
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
        """Get current weather for the specified or default city, combined from yr.no and OpenWeatherMap."""
        city = utils.get_args_raw(message) or self.db.get(self.strings["name"], "city", "")
        if not city:
            await utils.answer(message, "🚫 No city specified or set as default.")
            return

        # Get coordinates for the city
        latitude, longitude = await self.geocode_city(city)
        if not latitude or not longitude:
            await utils.answer(message, f"⚠️ Failed to find coordinates for <b>{city}</b>.")
            return

        # Fetch weather data from yr.no and OpenWeatherMap
        yr_weather = await self.fetch_weather(latitude, longitude, "yr")
        openweather_weather = await self.fetch_weather(latitude, longitude, "openweather")

        # Combine and display weather data
        weather_details = self.combine_weather_data(yr_weather, openweather_weather)

        if weather_details:
            await utils.answer(
                message,
                (
                    f"🌤 <b>Unified Weather Report for {city}:</b>\n"
                    f"<b>Temperature:</b> {weather_details['temperature']}°C\n"
                    f"<b>Feels like:</b> {weather_details['feels_like']}°C\n"
                    f"<b>Wind Speed:</b> {weather_details['wind_speed']} m/s\n"
                    f"<b>Humidity:</b> {weather_details['humidity']}%\n"
                    f"<b>Precipitation:</b> {weather_details['precipitation']} mm\n"
                    f"<b>Cloud Coverage:</b> {weather_details['cloud_coverage']}%\n"
                )
            )
        else:
            await utils.answer(message, f"⚠️ No weather data available for <b>{city}</b>.")

    # --- Weather Data Parsing and Combining ---
    def combine_weather_data(self, yr_data: dict, ow_data: dict) -> dict:
        """Combine weather data from yr.no and OpenWeatherMap into a single set of details."""
        if not yr_data and not ow_data:
            return None

        yr_details = self.parse_yr_data(yr_data) if yr_data else {}
        ow_details = self.parse_openweather_data(ow_data) if ow_data else {}

        return {
            "temperature": yr_details.get("temperature", ow_details.get("temperature")),
            "feels_like": ow_details.get("feels_like", yr_details.get("dew_point")),
            "wind_speed": yr_details.get("wind_speed", ow_details.get("wind_speed")),
            "humidity": yr_details.get("humidity", ow_details.get("humidity")),
            "precipitation": yr_details.get("precipitation", ow_details.get("precipitation")),
            "cloud_coverage": yr_details.get("cloud_coverage", ow_details.get("cloud_coverage")),
        }

    def parse_yr_data(self, weather_data: dict) -> dict:
        """Extract weather data from yr.no API response."""
        timeseries = weather_data.get("properties", {}).get("timeseries", [])
        if not timeseries:
            return {}

        current_weather = timeseries[0]["data"]["instant"]["details"]
        return {
            "temperature": self.to_float(current_weather.get("air_temperature")),
            "dew_point": self.to_float(current_weather.get("dew_point_temperature")),
            "wind_speed": self.to_float(current_weather.get("wind_speed")),
            "humidity": self.to_float(current_weather.get("relative_humidity")),
            "precipitation": self.to_float(timeseries[0].get("data", {}).get("next_1_hours", {}).get("details", {}).get("precipitation_amount", 0.0)),
            "cloud_coverage": self.to_float(current_weather.get("cloud_area_fraction")),
        }

    def parse_openweather_data(self, weather_data: dict) -> dict:
        """Extract weather data from OpenWeatherMap API response."""
        return {
            "temperature": self.to_float(weather_data["main"].get("temp")),
            "feels_like": self.to_float(weather_data["main"].get("feels_like")),
            "wind_speed": self.to_float(weather_data["wind"].get("speed")),
            "humidity": self.to_float(weather_data["main"].get("humidity")),
            "precipitation": self.to_float(weather_data.get("rain", {}).get("1h", 0.0)),
            "cloud_coverage": self.to_float(weather_data["clouds"].get("all")),
        }

    # --- Utility Functions ---
    def to_float(self, value):
        """Convert a value to float, return 0.0 if conversion fails."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

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

    # --- Periodic Weather Updates ---
    async def schedule_weather_updates(self, chat_id: str, interval: int = 7200) -> None:
        """Schedule weather updates for a chat every 2 hours."""
        while True:
            city = self.db.get(self.strings["name"], "city", "")
            if city:
                latitude, longitude = await self.geocode_city(city)
                if latitude and longitude:
                    yr_weather = await self.fetch_weather(latitude, longitude, "yr")
                    openweather_weather = await self.fetch_weather(latitude, longitude, "openweather")
                    weather_details = self.combine_weather_data(yr_weather, openweather_weather)
                    if weather_details:
                        await self.client.send_message(
                            int(chat_id),
                            (
                                f"🌤 <b>Weather Update for {city}:</b>\n"
                                f"<b>Temperature:</b> {weather_details['temperature']}°C\n"
                                f"<b>Feels like:</b> {weather_details['feels_like']}°C\n"
                                f"<b>Wind Speed:</b> {weather_details['wind_speed']} m/s\n"
                                f"<b>Humidity:</b> {weather_details['humidity']}%\n"
                                f"<b>Precipitation:</b> {weather_details['precipitation']} mm\n"
                                f"<b>Cloud Coverage:</b> {weather_details['cloud_coverage']}%\n"
                            )
                        )
            await asyncio.sleep(interval)  # Wait for the specified interval before sending the next update

    # --- Commands for Managing API Keys ---
    async def apikeycmd(self, message: Message) -> None:
        """Set or display the OpenWeatherMap API key."""
        args = utils.get_args_raw(message)
        if not args:
            current_key = self.db.get(self.strings["name"], "openweather_api_key", "🚫 No API key set.")
            await utils.answer(message, f"🔑 Current OpenWeatherMap API key: <code>{current_key}</code>")
        else:
            self.db.set(self.strings["name"], "openweather_api_key", args)
            await utils.answer(message, "✅ OpenWeatherMap API key has been updated.")
