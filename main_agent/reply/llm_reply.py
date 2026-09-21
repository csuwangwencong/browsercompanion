from intent.prompts import GENERAL_FALLBACK
from mimo_api import MiMoApiError, MiMoClient


async def general_reply(message: str) -> str:
    try:
        return await MiMoClient().chat(message)
    except MiMoApiError as exc:
        return f"{GENERAL_FALLBACK}\n\nMiMo is not available: {exc}"
