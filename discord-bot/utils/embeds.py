"""
Shared embed builders so every command in Atlas looks consistent and polished.

All builders accept an optional `guild` so the server's icon can be woven into
the footer (and, for key commands, the thumbnail) — giving every embed a
branded, server-aware feel instead of a generic look.
"""

import discord
import datetime
import config


def _guild_icon(guild: discord.Guild | None) -> str | None:
    if guild and guild.icon:
        return guild.icon.url
    return None


def _footer(embed: discord.Embed, prefix: str = ",", guild: discord.Guild | None = None) -> discord.Embed:
    icon = _guild_icon(guild)
    if guild:
        embed.set_footer(text=f"{guild.name} • Prefix: {prefix}", icon_url=icon)
    else:
        embed.set_footer(text=f"Atlas • Prefix: {prefix}")
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    return embed


def base_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = config.COLOR_PRIMARY,
    prefix: str = ",",
    guild: discord.Guild | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if guild:
        icon = _guild_icon(guild)
        embed.set_author(name=guild.name, icon_url=icon)
    return _footer(embed, prefix, guild)


def success_embed(description: str, title: str = "Success", prefix: str = ",", guild: discord.Guild | None = None) -> discord.Embed:
    return base_embed(f"{config.EMOJI_SUCCESS} {title}", description, config.COLOR_SUCCESS, prefix, guild)


def error_embed(description: str, title: str = "Error", prefix: str = ",", guild: discord.Guild | None = None) -> discord.Embed:
    return base_embed(f"{config.EMOJI_ERROR} {title}", description, config.COLOR_ERROR, prefix, guild)


def warning_embed(description: str, title: str = "Warning", prefix: str = ",", guild: discord.Guild | None = None) -> discord.Embed:
    return base_embed(f"{config.EMOJI_WARNING} {title}", description, config.COLOR_WARNING, prefix, guild)


def info_embed(description: str, title: str = "Info", prefix: str = ",", guild: discord.Guild | None = None) -> discord.Embed:
    return base_embed(f"{config.EMOJI_INFO} {title}", description, config.COLOR_INFO, prefix, guild)


def mod_embed(title: str, description: str, prefix: str = ",", guild: discord.Guild | None = None) -> discord.Embed:
    return base_embed(f"{config.EMOJI_MOD} {title}", description, config.COLOR_MOD, prefix, guild)


def with_server_icon(embed: discord.Embed, guild: discord.Guild | None, *, as_thumbnail: bool = True) -> discord.Embed:
    """Attach the server icon to an embed — as a thumbnail (default) for feature-focused
    commands like `serverinfo`/`config`/`boosts`, so the server's branding is front and center."""
    icon = _guild_icon(guild)
    if icon and as_thumbnail:
        embed.set_thumbnail(url=icon)
    return embed


def progress_bar(current: int, total: int, length: int = 14) -> str:
    if total <= 0:
        total = 1
    filled = max(0, min(length, int(length * current / total)))
    filled_char, empty_char = "🟪", "⬛"
    return filled_char * filled + empty_char * (length - filled)
