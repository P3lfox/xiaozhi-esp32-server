"""Weather through Open-Meteo (free, no API key), defaulting to the configured home city."""

import httpx

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_LOCATION = "San Miguel de Tucumán"
DEFAULT_LATITUDE = -26.8083
DEFAULT_LONGITUDE = -65.2176

# WMO weather interpretation codes.
WEATHER_CODES = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla con escarcha",
    51: "llovizna leve",
    53: "llovizna",
    55: "llovizna intensa",
    56: "llovizna helada",
    57: "llovizna helada intensa",
    61: "lluvia leve",
    63: "lluvia",
    65: "lluvia fuerte",
    66: "lluvia helada",
    67: "lluvia helada fuerte",
    71: "nevada leve",
    73: "nevada",
    75: "nevada fuerte",
    77: "granizo fino",
    80: "chaparrones leves",
    81: "chaparrones",
    82: "chaparrones violentos",
    85: "chaparrones de nieve",
    86: "chaparrones de nieve fuertes",
    95: "tormenta",
    96: "tormenta con granizo",
    99: "tormenta fuerte con granizo",
}

GET_LOCAL_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_local_weather",
        "description": (
            "Get the current weather and the forecast for the next days. "
            "Use it whenever the user asks about weather, temperature, rain or what to wear. "
            "If the user does not name a place, leave location empty to use the home city."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, e.g. 'Córdoba' or 'Buenos Aires'. Empty for the home city.",
                },
            },
            "required": [],
        },
    },
}


def _describe(code):
    return WEATHER_CODES.get(code, "condición desconocida")


async def _resolve(client, location, config):
    if not location:
        return (
            config.get("default_location", DEFAULT_LOCATION),
            config.get("latitude", DEFAULT_LATITUDE),
            config.get("longitude", DEFAULT_LONGITUDE),
        )
    response = await client.get(
        GEOCODING_URL, params={"name": location, "count": 1, "language": "es"}
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None
    place = results[0]
    name = ", ".join(p for p in (place.get("name"), place.get("admin1"), place.get("country")) if p)
    return name, place["latitude"], place["longitude"]


@register_function("get_local_weather", GET_LOCAL_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
async def get_local_weather(conn, location: str = None):
    config = conn.config.get("plugins", {}).get("get_local_weather", {})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            place = await _resolve(client, location, config)
            if place is None:
                return ActionResponse(
                    Action.REQLLM, f"No encontré la ciudad '{location}'. Pedile que la repita.", None
                )
            name, latitude, longitude = place
            response = await client.get(
                FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.bind(tag=TAG).error(f"Weather request failed: {e}")
        return ActionResponse(Action.REQLLM, "No pude consultar el clima ahora.", None)

    current = data["current"]
    daily = data["daily"]
    lines = [
        f"Clima en {name}:",
        f"Ahora: {_describe(current['weather_code'])}, {current['temperature_2m']:.0f} °C "
        f"(sensación {current['apparent_temperature']:.0f} °C), humedad "
        f"{current['relative_humidity_2m']}%, viento {current['wind_speed_10m']:.0f} km/h.",
    ]
    for label, i in (("Hoy", 0), ("Mañana", 1), ("Pasado mañana", 2)):
        if i < len(daily["time"]):
            lines.append(
                f"{label} ({daily['time'][i]}): {_describe(daily['weather_code'][i])}, "
                f"mínima {daily['temperature_2m_min'][i]:.0f} °C, máxima "
                f"{daily['temperature_2m_max'][i]:.0f} °C, probabilidad de lluvia "
                f"{daily['precipitation_probability_max'][i]}%."
            )
    lines.append("Respondé en una o dos frases, solo con lo que el usuario preguntó.")
    return ActionResponse(Action.REQLLM, "\n".join(lines), None)
