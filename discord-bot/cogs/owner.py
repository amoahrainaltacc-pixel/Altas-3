"""
Owner-only tools: eval, extension management, blacklist, diagnostics, and maintenance mode.
"""

import io
import contextlib
import textwrap
import time
import asyncio
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
        await interaction.response.edit_message(content="📤 Sending broadcast… this may take a moment.", embed=self.embed, view=self)

        sent, failed = 0, 0
        for user in self.recipients:
            try:
                await user.send(embed=self.embed)
                sent += 1
            except discord.HTTPException:
                failed += 1
            await asyncio.sleep(1)

        await interaction.followup.send(
            embed=success_embed(f"Broadcast finished. Delivered to **{sent}** user(s), failed for **{failed}**.", "Broadcast Complete")
        )
        self.stop()

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

    @commands.command(help="Evaluate a Python expression (owner only)")
    @checks.is_bot_owner()
    async def eval(self, ctx: commands.Context, *, code: str):
        code = code.strip("` ")
        if code.startswith("py"):
            code = code[2:]
        env = {"bot": self.bot, "ctx": ctx, "discord": discord}
        stdout = io.StringIO()
        wrapped = f"async def __eval():\n{textwrap.indent(code, '    ')}"
        try:
            exec(wrapped, env)
            with contextlib.redirect_stdout(stdout):
                result = await env["__eval"]()
        except Exception as e:
            await ctx.send(embed=error_embed(f"```py\n{e}\n```"))
            return
        output = stdout.getvalue()
        if result is not None:
            output += repr(result)
        output = output or "No output."
        await ctx.send(embed=success_embed(f"```py\n{output[:1900]}\n```", "Eval Result"))

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

    @commands.command(help="Shut down the bot (owner only)")
    @checks.is_bot_owner()
    async def shutdown(self, ctx: commands.Context):
        await ctx.send(embed=success_embed("Shutting down…"))
        await self.bot.close()

    @commands.command(help="Blacklist a user from using the bot (owner only)")
    @checks.is_bot_owner()
    async def blacklist(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason"):
        conn = get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO blacklist (user_id, reason) VALUES (?, ?)", (user.id, reason)
        )
        await conn.commit()
        self.bot.blacklisted_users.add(user.id)
        await ctx.send(embed=success_embed(f"**{user}** has been blacklisted."))

    @commands.command(name="unblacklist", help="Remove a user from the blacklist (owner only)")
    @checks.is_bot_owner()
    async def owner_whitelist(self, ctx: commands.Context, user: discord.User):
        conn = get_conn()
        await conn.execute("DELETE FROM blacklist WHERE user_id = ?", (user.id,))
        await conn.commit()
        self.bot.blacklisted_users.discard(user.id)
        await ctx.send(embed=success_embed(f"**{user}** has been removed from the blacklist."))

    @commands.command(help="Show bot diagnostics (owner only)")
    @checks.is_bot_owner()
    async def diagnostics(self, ctx: commands.Context):
        embed = base_embed(
            "🔧 Diagnostics",
            (
                f"**Guilds:** {len(self.bot.guilds)}\n"
                f"**Latency:** {round(self.bot.latency * 1000)}ms\n"
                f"**Uptime:** {human_duration(time.time() - self.bot.start_time)}\n"
                f"**Cogs Loaded:** {len(self.bot.cogs)}\n"
                f"**Commands:** {len(self.bot.commands)}"
            ),
            config.COLOR_PRIMARY,
            ctx.prefix,
        )
        await ctx.send(embed=embed)

    @commands.command(help="Toggle maintenance mode for this server (owner only)")
    @checks.is_bot_owner()
    async def maintenance(self, ctx: commands.Context, enabled: bool):
        await set_guild_config(ctx.guild.id, maintenance=1 if enabled else 0)
        await ctx.send(embed=success_embed(f"Maintenance mode {'enabled' if enabled else 'disabled'}."))

    @commands.command(
        name="message_all",
        aliases=["messageall", "dmall", "broadcast"],
        help="DM every user Atlas can see with an embed message — shows a preview with Send/Cancel first (owner only)",
    )
    @checks.is_bot_owner()
    async def message_all(self, ctx: commands.Context, *, message: str):
        recipients = {}
        for guild in self.bot.guilds:
            for member in guild.members:
                if not member.bot:
                    recipients[member.id] = member
        recipients = list(recipients.values())

        embed = base_embed("📢 Announcement", message, config.COLOR_PRIMARY)
        embed.set_footer(text="Sent by the Atlas team")

        if not recipients:
            await ctx.send(embed=error_embed("There's no one to message — Atlas can't see any non-bot members."))
            return

        view = BroadcastConfirmView(ctx.author.id, embed, recipients)
        note = (
            f"**Preview** — this is exactly what will be DMed.\n"
            f"Recipients: **{len(recipients)}** unique member(s) across **{len(self.bot.guilds)}** server(s).\n\n"
            f"Click **Send** to broadcast, or **Cancel** to abort."
        )
        view.message = await ctx.send(content=note, embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
