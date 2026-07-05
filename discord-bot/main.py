"""
Atlas — Discord moderation & utility bot.
Entry point: loads config, initializes the database, boots all cogs, and starts the bot.
"""

import asyncio
import logging
import os
import sys
import time

import discord
from discord.ext import commands, tasks

import config
from database import init_db, get_prefix_value

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("atlas")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True
INTENTS.presences = False

COG_MODULES = [
    "cogs.help",
    "cogs.moderation",
    "cogs.administration",
    "cogs.utility",
    "cogs.fun",
    "cogs.information",
    "cogs.automod",
    "cogs.logging_cog",
    "cogs.tickets",
    "cogs.giveaways",
    "cogs.welcome",
    "cogs.economy",
    "cogs.leveling",
    "cogs.owner",
    "cogs.servertools",
]


async def get_prefix(bot: "Atlas", message: discord.Message):
    prefixes = list(config.DEFAULT_PREFIXES)
    if message.guild:
        try:
            custom = await get_prefix_value(message.guild.id)
            if custom and custom not in prefixes:
                prefixes = [custom]
        except Exception:
            pass
    return commands.when_mentioned_or(*prefixes)(bot, message)


STATUS_ROTATION = [
    lambda bot: discord.Activity(
        type=discord.ActivityType.watching,
        name=f"Watching over {sum(g.member_count or 0 for g in bot.guilds)} members",
    ),
    lambda bot: discord.Activity(
        type=discord.ActivityType.watching,
        name=f"Watching over {len(bot.guilds)} servers",
    ),
    lambda bot: discord.Game(name="one of Discord's best bots"),
    lambda bot: discord.Activity(type=discord.ActivityType.listening, name=",help | !help"),
    lambda bot: discord.Activity(type=discord.ActivityType.competing, name="keeping your server safe"),
]


class Atlas(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=get_prefix,
            intents=INTENTS,
            help_command=None,
            case_insensitive=True,
        )
        self.start_time = time.time()
        self.blacklisted_users: set[int] = set()
        self._status_index = 0

    @tasks.loop(seconds=20)
    async def rotate_status(self):
        try:
            activity = STATUS_ROTATION[self._status_index % len(STATUS_ROTATION)](self)
            await self.change_presence(activity=activity)
            self._status_index += 1
        except Exception:
            logger.exception("Failed to rotate presence")

    @rotate_status.before_loop
    async def before_rotate_status(self):
        await self.wait_until_ready()

    async def setup_hook(self) -> None:
        await init_db()
        for module in COG_MODULES:
            try:
                await self.load_extension(module)
                logger.info("Loaded extension %s", module)
            except Exception:
                logger.exception("Failed to load extension %s", module)

        try:
            await self.tree.sync()
            logger.info("Synced application (slash) commands")
        except Exception:
            logger.exception("Failed to sync application commands")

    async def on_ready(self):
        logger.info("Atlas is online as %s (ID: %s)", self.user, self.user.id)
        logger.info("Serving %s guild(s)", len(self.guilds))
        if not self.rotate_status.is_running():
            self.rotate_status.start()

    async def on_guild_join(self, guild: discord.Guild):
        from utils.embeds import base_embed

        logger.info("Joined guild %s (ID: %s)", guild.name, guild.id)
        channel = guild.system_channel
        if not channel or not channel.permissions_for(guild.me).send_messages:
            channel = next(
                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                None,
            )
        if not channel:
            return

        embed = base_embed(
            "👋 Thanks for adding Atlas!",
            (
                "I'm **Atlas** — a full moderation & utility bot covering moderation, "
                "administration, tickets, giveaways, leveling, economy, AutoMod, logging, "
                "and a lot more.\n\n"
                "**Getting started:**\n"
                f"• Run `,help` or `/help` to see everything I can do\n"
                f"• My prefixes are `,` and `!` (change with `,prefix <new>`)\n"
                f"• Set up mod-log channels, autorole, and AutoMod with `,config` and `,setup`\n"
                f"• Change the server language anytime with `,language`\n\n"
                "Thanks for choosing Atlas — one of Discord's best bots! 🚀"
            ),
            config.COLOR_PRIMARY,
            ",",
            guild,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Could not send welcome message in guild %s", guild.id)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        from utils.embeds import error_embed, warning_embed

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            await ctx.send(embed=error_embed(f"You need the **{perms}** permission to do that."))
            return
        if isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            await ctx.send(embed=error_embed(f"I need the **{perms}** permission to do that."))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=warning_embed(f"Missing required argument: `{error.param.name}`"))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=warning_embed(str(error) or "Invalid argument provided."))
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=warning_embed(f"Slow down! Try again in {error.retry_after:.1f}s."))
            return
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=error_embed("This command can't be used in DMs."))
            return
        if isinstance(error, commands.NotOwner):
            await ctx.send(embed=error_embed("Only the bot owner can use this command."))
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=error_embed("You can't use this command here."))
            return

        logger.exception("Unhandled command error in %s", ctx.command, exc_info=error)
        await ctx.send(embed=error_embed("Something went wrong running that command."))


async def main():
    if not config.TOKEN:
        logger.error("DISCORD_TOKEN is not set. Add it in Secrets and restart.")
        sys.exit(1)

    bot = Atlas()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
