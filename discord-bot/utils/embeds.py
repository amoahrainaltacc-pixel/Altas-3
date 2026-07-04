"""
Shared embed builders so every command in Atlas looks consistent.
"""

import discord
import datetime
import config


def _footer(embed: discord.Embed, prefix: str = ",") -> discord.Embed:
    embed.set_footer(text=f"Atlas • Prefix: {prefix}")
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def base_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = config.COLOR_PRIMARY,
    prefix: str = ",",
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    return _footer(embed, prefix)


def success_embed(description: str, title: str = "Success", prefix: str = ",") -> discord.Embed:
    return base_embed(f"{config.EMOJI_SUCCESS} {title}", description, config.COLOR_SUCCESS, prefix)


def error_embed(description: str, title: str = "Error", prefix: str = ",") -> discord.Embed:
    return base_embed(f"{config.EMOJI_ERROR} {title}", description, config.COLOR_ERROR, prefix)


def warning_embed(description: str, title: str = "Warning", prefix: str = ",") -> discord.Embed:
    return base_embed(f"{config.EMOJI_WARNING} {title}", description, config.COLOR_WARNING, prefix)


def info_embed(description: str, title: str = "Info", prefix: str = ",") -> discord.Embed:
    return base_embed(f"{config.EMOJI_INFO} {title}", description, config.COLOR_INFO, prefix)


def mod_embed(title: str, description: str, prefix: str = ",") -> discord.Embed:
    return base_embed(f"{config.EMOJI_MOD} {title}", description, config.COLOR_MOD, prefix)


def progress_bar(current: int, total: int, length: int = 14) -> str:
    if total <= 0:
        total = 1
    filled = max(0, min(length, int(length * current / total)))
    return "█" * filled + "░" * (length - filled)
