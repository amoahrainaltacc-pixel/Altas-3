"""
Owner-only tools: eval, extension management, blacklist, diagnostics, and maintenance mode.
"""

import io
import re
import os
import sys
import contextlib
import textwrap
import traceback
import time
import asyncio
import platform
import subprocess
import discord
from discord.ext import commands

import config
from database import get_conn, set_guild_config
from utils import checks
from utils.embeds import success_embed, error_embed, base_embed
from utils.helpers import human_duration


class BroadcastConfirmView(discord.ui.View):
    """Confirmation view for `message_all` — shows a live preview of the embed
    that will be DMed, and only sends after the owner clicks Send."""

    def __init__(self, owner_id: int, embed: discord.Embed, recipients: list[discord.abc.Snowflake]):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.embed = embed
        self.recipients = recipients
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ Broadcast preview timed out — nothing was sent.", view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, emoji="✅")
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="📤 Sending broadcast… this is intentionally slow to avoid Discord's spam/abuse detection.", embed=self.embed, view=self)

        sent, skipped, aborted = await self._safe_broadcast()

        if aborted:
            note = (
                f"⚠️ Broadcast **stopped early** after repeated rate-limit responses from Discord — "
                f"this usually means it's flagging the volume as suspicious. Delivered to **{sent}**, "
                f"skipped **{skipped}** before stopping. Wait a while before trying again with a smaller audience."
            )
            await interaction.followup.send(embed=error_embed(note, "Broadcast Stopped Early"))
        else:
            await interaction.followup.send(
                embed=success_embed(f"Broadcast finished. Delivered to **{sent}** user(s), skipped **{skipped}** (DMs closed or errored).", "Broadcast Complete")
            )
        self.stop()

    async def _safe_broadcast(self) -> tuple[int, int, bool]:
        """Send DMs one at a time with a conservative pace, a longer breather
        every batch, and a hard stop if Discord starts throttling us hard."""
        sent = 0
        skipped = 0
        consecutive_rate_limits = 0
        BATCH_SIZE = 20
        PER_MESSAGE_DELAY = 2.5
        BATCH_BREAK = 15

        for i, user in enumerate(self.recipients, start=1):
            try:
                await user.send(embed=self.embed)
                sent += 1
                consecutive_rate_limits = 0
            except discord.Forbidden:
                skipped += 1
            except discord.HTTPException as e:
                if e.status == 429:
                    consecutive_rate_limits += 1
                    retry_after = getattr(e, "retry_after", None) or 5
                    await asyncio.sleep(retry_after + 1)
                    if consecutive_rate_limits >= 3:
                        return sent, skipped, True
                else:
                    skipped += 1

            await asyncio.sleep(PER_MESSAGE_DELAY)
            if i % BATCH_SIZE == 0:
                await asyncio.sleep(BATCH_BREAK)

        return sent, skipped, False

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Broadcast cancelled — no messages were sent.", embed=self.embed, view=self)
        self.stop()


class Owner(commands.Cog, name="owner"):
    """Bot-owner-only administrative commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- eval / debugging ----------

    @commands.command(help="Evaluate a Python expression (owner only)")
    @checks.is_bot_owner()
    async def eval(self, ctx: commands.Context, *, code: str):
        code = code.strip("` ")
        if code.startswith("py"):
            code = code[2:]
        env = {
            "bot": self.bot, "ctx": ctx, "discord": discord,
            "guild": ctx.guild, "channel": ctx.channel, "author": ctx.author,
        }
        stdout = io.StringIO()
        wrapped = f"async def __eval():\n{textwrap.indent(code, '    ')}"
        try:
            exec(wrapped, env)
            with contextlib.redirect_stdout(stdout):
                result = await env["__eval"]()
        except Exception as e:
            tb = traceback.format_exc(limit=3)
            await ctx.send(embed=error_embed(f"```py\n{tb[-1900:]}\n```"))
            return
        output = stdout.getvalue()
        if result is not None:
            output += repr(result)
        output = output or "No output."
        await ctx.send(embed=success_embed(f"```py\n{output[:1900]}\n```", "Eval Result"))

    @commands.command(help="Run a shell command on the host (owner only)")
    @checks.is_bot_owner()
    async def shell(self, ctx: commands.Context, *, command: str):
        command = command.strip("` ")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            await ctx.send(embed=error_embed("Command timed out after **30s**."))
            return
        output = stdout.decode(errors="replace") or "No output."
        await ctx.send(embed=base_embed("💻 Shell", f"```\n{output[:1900]}\n```", config.COLOR_PRIMARY, ctx.prefix))

    # ---------- extension / process management ----------

    @commands.command(help="Reload a specific cog (owner only)")
    @checks.is_bot_owner()
    async def reload(self, ctx: commands.Context, extension: str):
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
        except Exception as e:
            await ctx.send(embed=error_embed(f"Failed to reload `{extension}`: {e}"))
            return
        await ctx.send(embed=success_embed(f"Reloaded `{extension}`."))

    @commands.command(help="Reload all cogs (owner only)")
    @checks.is_bot_owner()
    async def reloadall(self, ctx: commands.Context):
        from main import COG_MODULES
        failures = []
        for module in COG_MODULES:
            try:
                await self.bot.reload_extension(module)
            except Exception:
                failures.append(module)
        if failures:
            await ctx.send(embed=error_embed(f"Failed to reload: {', '.join(failures)}"))
        else:
            await ctx.send(embed=success_embed("All extensions reloaded."))

    @commands.command(help="Load a cog that isn't currently loaded (owner only)")
    @checks.is_bot_owner()
    async def load(self, ctx: commands.Context, extension: str):
        try:
            await self.bot.load_extension(f"cogs.{extension}")
        except Exception as e:
            await ctx.send(embed=error_embed(f"Failed to load `{extension}`: {e}"))
            return
        await ctx.send(embed=success_embed(f"Loaded `{extension}`."))

    @commands.command(help="Unload a currently loaded cog (owner only)")
    @checks.is_bot_owner()
    async def unload(self, ctx: commands.Context, extension: str):
        if extension == "owner":
            await ctx.send(embed=error_embed("Can't unload the owner cog from itself — that's how you get locked out."))
            return
        try:
            await self.bot.unload_extension(f"cogs.{extension}")
        except Exception as e:
            await ctx.send(embed=error_embed(f"Failed to unload `{extension}`: {e}"))
            return
        await ctx.send(embed=success_embed(f"Unloaded `{extension}`."))

    @commands.command(help="Sync slash commands (owner only)")
    @checks.is_bot_owner()
    async def sync(self, ctx: commands.Context):
        synced = await self.bot.tree.sync()
        await ctx.send(embed=success_embed(f"Synced **{len(synced)}** application commands."))

    @commands.command(help="Restart the bot process (owner only)")
    @checks.is_bot_owner()
    async def restart(self, ctx: commands.Context):
        await ctx.send(embed=success_embed("Restarting…"))
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @commands.command(help="Shut down the bot (owner only)")
    @checks.is_bot_owner()
    async def shutdown(self, ctx: commands.Context):
        await ctx.send(embed=success_embed("Shutting down…"))
        await self.bot.close()

    # ---------- blacklist ----------

    @commands.command(help="Blacklist a user from using the bot (owner only)")
    @checks.is_bot_owner()
    async def blacklist(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason"):
        conn = get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO blacklist (user_id, reason) VALUES (?, ?)", (user.id, reason)
        )
        await conn.commit()
        self.bot.blacklisted_users.add(user.id)
        await ctx.send(embed=success_embed(f"**{user}** has been blacklisted. Reason: {reason}"))

    @commands.command(name="unblacklist", help="Remove a user from the blacklist (owner only)")
    @checks.is_bot_owner()
    async def owner_whitelist(self, ctx: commands.Context, user: discord.User):
        conn = get_conn()
        await conn.execute("DELETE FROM blacklist WHERE user_id = ?", (user.id,))
        await conn.commit()
        self.bot.blacklisted_users.discard(user.id)
        await ctx.send(embed=success_embed(f"**{user}** has been removed from the blacklist."))

    @commands.command(help="List every blacklisted user (owner only)")
    @checks.is_bot_owner()
    async def blacklisted(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute("SELECT user_id, reason FROM blacklist")
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=success_embed("Blacklist is empty."))
            return
        lines = [f"<@{r['user_id']}> — {r['reason']}" for r in rows]
        await ctx.send(embed=base_embed("🚫 Blacklisted Users", "\n".join(lines)[:4000], config.COLOR_PRIMARY, ctx.prefix))

    # ---------- diagnostics ----------

    @commands.command(help="Show bot diagnostics (owner only)")
    @checks.is_bot_owner()
    async def diagnostics(self, ctx: commands.Context):
        process_mem = ""
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            process_mem = f"**Memory:** {proc.memory_info().rss / 1024 / 1024:.1f} MB\n"
        except ImportError:
            pass
        embed = base_embed(
            "🔧 Diagnostics",
            (
                f"**Guilds:** {len(self.bot.guilds)}\n"
                f"**Users:** {sum(g.member_count or 0 for g in self.bot.guilds)}\n"
                f"**Latency:** {round(self.bot.latency * 1000)}ms\n"
                f"**Uptime:** {human_duration(time.time() - self.bot.start_time)}\n"
                f"**Cogs Loaded:** {len(self.bot.cogs)}\n"
                f"**Commands:** {len(self.bot.commands)}\n"
                f"{process_mem}"
                f"**Python:** {platform.python_version()}\n"
                f"**discord.py:** {discord.__version__}"
            ),
            config.COLOR_PRIMARY,
            ctx.prefix,
        )
        await ctx.send(embed=embed)

    @commands.command(help="List every guild Atlas is in (owner only)")
    @checks.is_bot_owner()
    async def guildlist(self, ctx: commands.Context):
        lines = [f"**{g.name}** — `{g.id}` — {g.member_count or 0} members" for g in self.bot.guilds]
        chunk = "\n".join(lines)[:4000]
        await ctx.send(embed=base_embed(f"🌐 Guilds ({len(self.bot.guilds)})", chunk, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show detailed info for one guild by ID (owner only)")
    @checks.is_bot_owner()
    async def guildinfo(self, ctx: commands.Context, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send(embed=error_embed(f"Atlas isn't in a guild with ID `{guild_id}`."))
            return
        embed = base_embed(
            f"🌐 {guild.name}",
            (
                f"**ID:** {guild.id}\n"
                f"**Owner:** {guild.owner}\n"
                f"**Members:** {guild.member_count}\n"
                f"**Channels:** {len(guild.channels)}\n"
                f"**Roles:** {len(guild.roles)}\n"
                f"**Created:** {discord.utils.format_dt(guild.created_at, 'R')}"
            ),
            config.COLOR_PRIMARY, ctx.prefix,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @commands.command(help="Make Atlas leave a guild by ID (owner only)")
    @checks.is_bot_owner()
    async def leaveguild(self, ctx: commands.Context, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send(embed=error_embed(f"Atlas isn't in a guild with ID `{guild_id}`."))
            return
        name = guild.name
        await guild.leave()
        await ctx.send(embed=success_embed(f"Left **{name}** (`{guild_id}`)."))

    @commands.command(help="Generate an invite link for a guild Atlas is already in (owner only)")
    @checks.is_bot_owner()
    async def forceinvite(self, ctx: commands.Context, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send(embed=error_embed(f"Atlas isn't in a guild with ID `{guild_id}`."))
            return
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).create_instant_invite:
                invite = await channel.create_invite(max_age=3600, max_uses=1, reason="Owner forceinvite")
                await ctx.send(embed=success_embed(f"{invite.url}\nExpires in 1 hour, single use."))
                return
        await ctx.send(embed=error_embed(f"No channel in **{guild.name}** where Atlas can create an invite."))

    # ---------- maintenance / config ----------

    @commands.command(help="Toggle maintenance mode for this server (owner only)")
    @checks.is_bot_owner()
    async def maintenance(self, ctx: commands.Context, enabled: bool):
        await set_guild_config(ctx.guild.id, maintenance=1 if enabled else 0)
        await ctx.send(embed=success_embed(f"Maintenance mode {'enabled' if enabled else 'disabled'}."))

    @commands.command(help="Change the bot's playing/watching status (owner only)")
    @checks.is_bot_owner()
    async def setstatus(self, ctx: commands.Context, activity_type: str, *, text: str):
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing,
        }
        if activity_type.lower() not in types:
            await ctx.send(embed=error_embed("Type must be one of: playing, watching, listening, competing."))
            return
        await self.bot.change_presence(activity=discord.Activity(type=types[activity_type.lower()], name=text))
        await ctx.send(embed=success_embed(f"Status set to **{activity_type} {text}**."))

    @commands.command(help="Change the bot's username (owner only)")
    @checks.is_bot_owner()
    async def setname(self, ctx: commands.Context, *, name: str):
        try:
            await self.bot.user.edit(username=name)
        except discord.HTTPException as e:
            await ctx.send(embed=error_embed(f"Failed to change name: {e}"))
            return
        await ctx.send(embed=success_embed(f"Username changed to **{name}**."))

    @commands.command(help="Change the bot's avatar from an attached image or URL (owner only)")
    @checks.is_bot_owner()
    async def setavatar(self, ctx: commands.Context, url: str | None = None):
        if ctx.message.attachments:
            data = await ctx.message.attachments[0].read()
        elif url:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await ctx.send(embed=error_embed("Couldn't fetch that URL."))
                        return
                    data = await resp.read()
        else:
            await ctx.send(embed=error_embed("Attach an image or provide a URL."))
            return
        try:
            await self.bot.user.edit(avatar=data)
        except discord.HTTPException as e:
            await ctx.send(embed=error_embed(f"Failed to change avatar: {e}"))
            return
        await ctx.send(embed=success_embed("Avatar updated."))

    # ---------- messaging ----------

    @commands.command(
        name="say",
        help="Make Atlas say something in this channel. Add 'exclude=123456789012345678' to skip sending if this server's ID matches (owner only)",
    )
    @checks.is_bot_owner()
    async def say(self, ctx: commands.Context, *, message: str):
        excluded_guild_id = None
        match = re.match(r"^\s*exclude\s*[:=]\s*(\d+)\s+(.*)$", message, re.DOTALL)
        if match:
            excluded_guild_id = int(match.group(1))
            message = match.group(2)

        if not message.strip():
            await ctx.send(embed=error_embed("You need to include a message, e.g. `,say Hello!` or `,say exclude=123456789012345678 Hello!`"))
            return

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if excluded_guild_id is not None and ctx.guild and ctx.guild.id == excluded_guild_id:
            return

        await ctx.send(message)

    @commands.command(help="Make Atlas send a message to a specific channel by ID (owner only)")
    @checks.is_bot_owner()
    async def sayto(self, ctx: commands.Context, channel_id: int, *, message: str):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send(embed=error_embed(f"No channel found with ID `{channel_id}`."))
            return
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        try:
            await channel.send(message)
        except discord.HTTPException as e:
            await ctx.send(embed=error_embed(f"Failed to send: {e}"), delete_after=10)
            return

    @commands.command(
        name="message_all",
        aliases=["messageall", "dmall", "broadcast"],
        help="DM users Atlas can see with an embed message. Optionally cap how many with 'limit=N' at the start — shows a preview with Send/Cancel first (owner only)",
    )
    @checks.is_bot_owner()
    async def message_all(self, ctx: commands.Context, *, message: str):
        limit = None
        match = re.match(r"^\s*limit\s*[:=]\s*(\d+)\s+(.*)$", message, re.DOTALL)
        if match:
            limit = int(match.group(1))
            message = match.group(2)
            if limit <= 0:
                await ctx.send(embed=error_embed("Limit must be a positive number."))
                return

        if not message.strip():
            await ctx.send(embed=error_embed("You need to include a message to send, e.g. `,message_all limit=50 Hello everyone!`"))
            return

        recipients = {}
        for guild in self.bot.guilds:
            for member in guild.members:
                if not member.bot:
                    recipients[member.id] = member
        recipients = list(recipients.values())
        total_available = len(recipients)

        if not recipients:
            await ctx.send(embed=error_embed("There's no one to message — Atlas can't see any non-bot members."))
            return

        if limit is not None:
            recipients = recipients[:limit]

        embed = base_embed("📢 Announcement", message, config.COLOR_PRIMARY)
        embed.set_footer(text="Sent by the Atlas team")

        view = BroadcastConfirmView(ctx.author.id, embed, recipients)
        limit_note = f" (capped from **{total_available}** available)" if limit is not None else ""
        note = (
            f"**Preview** — this is exactly what will be DMed.\n"
            f"Recipients: **{len(recipients)}** unique member(s){limit_note} across **{len(self.bot.guilds)}** server(s).\n\n"
            f"Tip: start your message with `limit=50` to cap how many people it sends to, e.g. `,message_all limit=50 Hello!`\n\n"
            f"Click **Send** to broadcast, or **Cancel** to abort."
        )
        view.message = await ctx.send(content=note, embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
