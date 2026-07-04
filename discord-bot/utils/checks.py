"""
Permission decorators used across cogs. Kept small and explicit so
every command's requirement is obvious at a glance.
"""

import discord
from discord.ext import commands
import config


class NotWhitelistedOwnerOnly(commands.CheckFailure):
    pass


def is_owner_or_perm(permission_name: str):
    """Allow bot owners to bypass, otherwise require the named guild permission."""

    async def predicate(ctx: commands.Context) -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        perms = ctx.author.guild_permissions
        if getattr(perms, permission_name, False):
            return True
        raise commands.MissingPermissions([permission_name])

    return commands.check(predicate)


def can_moderate():
    return is_owner_or_perm("moderate_members")


def can_manage_messages():
    return is_owner_or_perm("manage_messages")


def can_manage_guild():
    return is_owner_or_perm("manage_guild")


def can_manage_roles():
    return is_owner_or_perm("manage_roles")


def can_manage_channels():
    return is_owner_or_perm("manage_channels")


def can_kick():
    return is_owner_or_perm("kick_members")


def can_ban():
    return is_owner_or_perm("ban_members")


def is_bot_owner():
    async def predicate(ctx: commands.Context) -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        raise commands.NotOwner()

    return commands.check(predicate)
