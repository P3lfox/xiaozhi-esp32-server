"""Argentine dollar quotes (oficial, blue, MEP, CCL, cripto...) and other currencies via dolarapi.com."""

import asyncio

import httpx

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()

DOLLARS_URL = "https://dolarapi.com/v1/dolares"
OTHER_CURRENCIES_URL = "https://dolarapi.com/v1/cotizaciones"

GET_EXCHANGE_RATES_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_exchange_rates",
        "description": (
            "Get today's Argentine peso exchange rates: dollar oficial, blue, MEP (bolsa), "
            "contado con liquidación, mayorista, cripto and tarjeta, plus euro, real and others. "
            "Use it whenever the user asks how much the dollar or another currency is."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": (
                        "Which quote: 'dolar' (all dollar types, default), 'euro', 'real', "
                        "'peso chileno', 'peso uruguayo', or 'todas'."
                    ),
                },
            },
            "required": [],
        },
    },
}


def _price(value):
    if not isinstance(value, (int, float)):
        return "sin dato"
    if value < 100:
        return f"{value:.2f}".replace(".", ",")
    return f"{value:,.0f}".replace(",", ".")


def _line(quote):
    return (
        f"- {quote.get('nombre', quote.get('casa'))} ({quote.get('moneda')}): "
        f"compra {_price(quote.get('compra'))}, venta {_price(quote.get('venta'))} pesos"
    )


@register_function("get_exchange_rates", GET_EXCHANGE_RATES_FUNCTION_DESC, ToolType.WAIT)
async def get_exchange_rates(currency: str = None):
    wanted = (currency or "dolar").lower()
    want_dollars = "dol" in wanted or "usd" in wanted or "toda" in wanted
    want_others = not want_dollars or "toda" in wanted
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            urls = ([DOLLARS_URL] if want_dollars else []) + (
                [OTHER_CURRENCIES_URL] if want_others else []
            )
            responses = await asyncio.gather(*(client.get(u) for u in urls))
            for response in responses:
                response.raise_for_status()
            quotes = [q for response in responses for q in response.json()]
    except Exception as e:
        logger.bind(tag=TAG).error(f"Exchange rate request failed: {e}")
        return ActionResponse(Action.REQLLM, "No pude consultar las cotizaciones ahora.", None)

    if want_others and not want_dollars:
        # Keep only the currency asked for, when it is recognizable.
        matches = [q for q in quotes if wanted[:4] in (q.get("nombre") or "").lower()]
        quotes = matches or [q for q in quotes if q.get("moneda") != "USD"]
    elif want_others:
        quotes = [q for q in quotes if not (q.get("moneda") == "USD" and q.get("casa") == "oficial"
                                             and q.get("nombre") == "Dólar")]

    if not quotes:
        return ActionResponse(Action.REQLLM, "No encontré esa cotización.", None)
    return ActionResponse(
        Action.REQLLM,
        "Cotizaciones de hoy en Argentina (pesos por unidad):\n"
        + "\n".join(_line(q) for q in quotes)
        + "\nRespondé solo lo que preguntó, en una o dos frases. Si pregunta 'el dólar' sin "
        "aclarar, decí el oficial y el blue (precio de venta).",
        None,
    )
