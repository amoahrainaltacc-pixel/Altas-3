"""
Small shared helpers used across multiple cogs.
"""

import re
import discord

DURATION_RE = re.compile(r"^(\d+)([smhdw])$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> int | None:
    """Parse strings like '10m', '2h', '1d' into seconds."""
    match = DURATION_RE.match(text.strip().lower())
    if not match:
        return None
    amount, unit = match.groups()
    return int(amount) * UNIT_SECONDS[unit]


def human_duration(seconds: int) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def truncate(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


async def safe_send_dm(user: discord.abc.User, *args, **kwargs) -> bool:
    try:
        await user.send(*args, **kwargs)
        return True
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return False
