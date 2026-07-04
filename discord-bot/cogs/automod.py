"""
AutoMod: configurable protections against spam, links, invites, caps, hoisted names, and more.
"""

import re
import time
import discord
from discord.ext import commands

from database import get_guild_config, set_guild_config
from utils import checks
from utils.embeds import success_embed, base_embed
import config

INVITE_RE = re.compile(r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/\S+", re.IGNORECASE)
LINK_RE = re.compile(r"https?://\S+", re.IGNORECASE)
HOIST_CHARS = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")

TOGGLES = {
    "automod": "automod_enabled",
    "antispam": "antispam",
    "antilink": "antilink",
    "antiinvite": "antiinvite",
    "antiemoji": "antiemoji",
    "anticaps": "anticaps",
    "antihoist": "antihoist",
    "antibot": "antibot",
    "antinuke": "antinuke",
    "antiwebhook": "antiwebhook",
}


class AutoMod(commands.Cog, name="automod"):
    """Automatic protection against spam, malicious links, and raid behavior."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._spam_tracker: dict[int, list[float]] = {}

    async def _toggle(self, ctx: commands.Context, key: str, enabled: bool | None):
        row = await get_guild_config(ctx.guild.id)
        column = TOGGLES[key]
        if enabled is None:
            enabled = not bool(row[column])
        await set_guild_config(ctx.guild.id, **{column: 1 if enabled else 0})
        await ctx.send(embed=success_embed(f"`{key}` is now **{'enabled' if enabled else 'disabled'}**."))

    @commands.hybrid_command(help="Toggle all automod protections on/off")
    @checks.can_manage_guild()
    async def automod(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "automod", enabled)

    @commands.hybrid_command(help="Toggle anti-spam protection")
    @checks.can_manage_guild()
    async def antispam(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antispam", enabled)

    @commands.hybrid_command(help="Toggle blocking of links")
    @checks.can_manage_guild()
    async def antilink(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antilink", enabled)

    @commands.hybrid_command(help="Toggle blocking of Discord invite links")
    @checks.can_manage_guild()
    async def antiinvite(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antiinvite", enabled)

    @commands.command(help="Toggle blocking of excessive emoji spam")
    @checks.can_manage_guild()
    async def antiemoji(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antiemoji", enabled)

    @commands.command(help="Toggle blocking of excessive caps")
    @checks.can_manage_guild()
    async def anticaps(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "anticaps", enabled)

    @commands.command(help="Toggle blocking hoisted (symbol-prefixed) nicknames")
    @checks.can_manage_guild()
    async def antihoist(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antihoist", enabled)

    @commands.command(help="Toggle auto-kicking unauthorized bots on join")
    @checks.can_manage_guild()
    async def antibot(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antibot", enabled)

    @commands.command(help="Toggle anti-nuke protections (mass channel/role deletion)")
    @checks.can_manage_guild()
    async def antinuke(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antinuke", enabled)

    @commands.command(help="Toggle blocking of new webhook creation")
    @checks.can_manage_guild()
    async def antiwebhook(self, ctx: commands.Context, enabled: bool | None = None):
        await self._toggle(ctx, "antiwebhook", enabled)

    async def _delete_and_warn(self, message: discord.Message, reason: str):
        try:
            await message.delete()
            warn = await message.channel.send(
                embed=base_embed(f"{config.EMOJI_WARNING} AutoMod", f"{message.author.mention} {reason}", config.COLOR_WARNING)
            )
            await warn.delete(delay=6)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return

        row = await get_guild_config(message.guild.id)
        if not row or not row["automod_enabled"]:
            return

        content = message.content

        if row["antiinvite"] and INVITE_RE.search(content):
            await self._delete_and_warn(message, "Discord invites aren't allowed here.")
            return

        if row["antilink"] and LINK_RE.search(content):
            await self._delete_and_warn(message, "Links aren't allowed here.")
            return

        if row["anticaps"] and len(content) >= 10:
            letters = [c for c in content if c.isalpha()]
            if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
                await self._delete_and_warn(message, "Please avoid excessive caps.")
                return

        if row["antiemoji"]:
            custom_emoji_count = len(re.findall(r"<a?:\w+:\d+>", content))
            unicode_emoji_count = len(re.findall(r"[\U0001F300-\U0001FAFF]", content))
            if custom_emoji_count + unicode_emoji_count > 10:
                await self._delete_and_warn(message, "Please avoid excessive emoji spam.")
                return

        if row["antispam"]:
            key = message.author.id
            history = self._spam_tracker.setdefault(key, [])
            now_ts = time.time()
            history.append(now_ts)
            self._spam_tracker[key] = [t for t in history if now_ts - t < 6]
            if len(self._spam_tracker[key]) > 6:
                await self._delete_and_warn(message, "Please slow down — you're sending messages too fast.")
                self._spam_tracker[key] = []
                return

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        row = await get_guild_config(after.guild.id)
        if not row or not row["antihoist"]:
            return
        name = after.display_name
        if name and name[0] in HOIST_CHARS:
            try:
                await after.edit(nick="Member", reason="Antihoist: hoisted nickname")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        row = await get_guild_config(member.guild.id)
        if row and row["antibot"] and member.bot:
            try:
                await member.kick(reason="Antibot: unauthorized bot join")
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
