"""Latest headlines from Argentine newspapers' RSS feeds (local La Gaceta by default)."""

import asyncio
import unicodedata
import xml.etree.ElementTree as ET

import httpx

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()

MAX_HEADLINES = 8
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) xiaozhi-news/1.0"

# key -> (display name, RSS url). Keys are matched against the user's words.
# Override or extend through plugins.get_news.sources in the config.
DEFAULT_SOURCES = {
    "gaceta": ("La Gaceta (Tucumán)", "https://www.lagaceta.com.ar/rss/"),
    "infobae": ("Infobae", "https://www.infobae.com/arc/outboundfeeds/rss/"),
    "nacion": ("La Nación", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/"),
    "clarin": ("Clarín", "https://www.clarin.com/rss/lo-ultimo/"),
    "ambito": ("Ámbito (economía)", "https://www.ambito.com/rss/pages/home.xml"),
    "perfil": ("Perfil", "https://www.perfil.com/feed"),
    "ole": ("Olé (deportes)", "https://www.ole.com.ar/rss/ultimas-noticias/"),
}
DEFAULT_SOURCE = "gaceta"
NATIONAL_SOURCES = ("infobae", "nacion", "clarin")

GET_NEWS_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_news",
        "description": (
            "Get today's latest headlines from Argentine newspapers. "
            "Use it whenever the user asks for news, what is happening, or today's headlines. "
            "Local Tucumán news by default; national news when the user asks for the country, "
            "or a specific newspaper when the user names one."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "One of: gaceta (local Tucumán, default), infobae, nacion (La Nación), "
                        "clarin, ambito (economy), perfil, ole (sports), "
                        "nacional (mix of Infobae, La Nación and Clarín)."
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "How many headlines to read, 1 to 8. Default 3.",
                },
            },
            "required": [],
        },
    },
}


def _normalize(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return text.lower().strip()


def _load_sources(config):
    sources = dict(DEFAULT_SOURCES)
    for key, value in (config.get("sources") or {}).items():
        if isinstance(value, dict) and value.get("url"):
            sources[_normalize(key)] = (value.get("name", key), value["url"])
    return sources


def _pick_sources(source, sources):
    wanted = _normalize(source)
    if not wanted:
        return [DEFAULT_SOURCE]
    if wanted in ("nacional", "nacionales", "pais", "argentina"):
        return [k for k in NATIONAL_SOURCES if k in sources]
    if wanted in ("local", "tucuman"):
        return [DEFAULT_SOURCE]
    for key, (name, _) in sources.items():
        if key in wanted or wanted in key or wanted in _normalize(name):
            return [key]
    return [DEFAULT_SOURCE]


def _parse_headlines(xml_text, limit):
    root = ET.fromstring(xml_text)
    headlines = []
    for item in root.iter("item"):
        title = " ".join((item.findtext("title") or "").split())
        if title:
            headlines.append(title)
        if len(headlines) >= limit:
            break
    return headlines


async def _fetch(client, name, url, limit):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return name, _parse_headlines(response.text, limit)
    except Exception as e:
        logger.bind(tag=TAG).error(f"News request to {name} failed: {e}")
        return name, []


@register_function("get_news", GET_NEWS_FUNCTION_DESC, ToolType.SYSTEM_CTL)
async def get_news(conn, source: str = None, count: int = 3):
    config = conn.config.get("plugins", {}).get("get_news", {})
    sources = _load_sources(config)
    keys = _pick_sources(source, sources)
    try:
        limit = max(1, min(int(count or 3), MAX_HEADLINES))
    except (TypeError, ValueError):
        limit = 3
    # A national mix reads a couple of headlines from each paper.
    per_source = limit if len(keys) == 1 else max(1, limit // len(keys) + 1)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=3.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        results = await asyncio.gather(
            *(_fetch(client, sources[k][0], sources[k][1], per_source) for k in keys)
        )

    sections = [
        f"{name}:\n" + "\n".join(f"- {h}" for h in headlines)
        for name, headlines in results
        if headlines
    ]
    if not sections:
        return ActionResponse(Action.REQLLM, "No pude traer las noticias ahora.", None)
    return ActionResponse(
        Action.REQLLM,
        "Titulares de hoy.\n"
        + "\n".join(sections)
        + "\nContalos en forma breve y natural, para escuchar, nombrando el diario, "
        "sin leer listas ni símbolos.",
        None,
    )
