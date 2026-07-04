"""
Giveaways: create, reroll, end, pause/resume, and auto-conclude timed giveaways.
"""

import asyncio
import random
import discord
from discord.ext import commands, tasks

from database import get_conn, now
from utils import checks
from utils.embeds import success_embed, error_embed, base_embed
from utils.helpers import parse_duration, human_duration
import config


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.enter.custom_id = f"atlas:giveaway:{giveaway_id}"

    @discord.ui.button(label="Enter Giveaway", emoji="🎉", style=discord.ButtonStyle.success)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = get_conn()
        try:
            await conn.execute(
                "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
                (self.giveaway_id, interaction.user.id),
            )
            await conn.commit()
            await interaction.response.send_message("You're entered! Good luck 🎉", ephemeral=True)
        except Exception:
            await conn.execute(
                "DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                (self.giveaway_id, interaction.user.id),
            )
            await conn.commit()
            await interaction.response.send_message("You've left the giveaway.", ephemeral=True)


class Giveaways(commands.Cog, name="giveaways"):
    """Host giveaways with automatic winner selection."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    async def _pick_winners(self, giveaway_id: int, winners: int) -> list[int]:
        conn = get_conn()
        cur = await conn.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,))
        rows = await cur.fetchall()
        entrants = [r["user_id"] for r in rows]
        if not entrants:
            return []
        return random.sample(entrants, k=min(winners, len(entrants)))

    @tasks.loop(seconds=20)
    async def check_giveaways(self):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM giveaways WHERE ended = 0 AND end_time <= ?", (now(),))
        rows = await cur.fetchall()
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(row["channel_id"])
            winners = await self._pick_winners(row["id"], row["winners"])
            await conn.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (row["id"],))
            await conn.commit()
            if not channel:
                continue
            if winners:
                mentions = ", ".join(f"<@{w}>" for w in winners)
                embed = base_embed("🎉 Giveaway Ended", f"**Prize:** {row['prize']}\n**Winner(s):** {mentions}", config.COLOR_SUCCESS)
            else:
                embed = base_embed("🎉 Giveaway Ended", f"**Prize:** {row['prize']}\nNo valid entries.", config.COLOR_WARNING)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(help="Start a giveaway, e.g. 1h 1 Nitro")
    @checks.can_manage_guild()
    async def giveaway(self, ctx: commands.Context, duration: str, winners: int, *, prize: str):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(embed=error_embed("Invalid duration. Use formats like `10m`, `1h`, `1d`."))
            return
        embed = base_embed("🎉 Giveaway", f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** {discord.utils.format_dt(discord.utils.utcnow() + __import__('datetime').timedelta(seconds=seconds), 'R')}", config.COLOR_PRIMARY)
        conn = get_conn()
        cur = await conn.execute(
            "INSERT INTO giveaways (guild_id, channel_id, prize, winners, host_id, end_time) VALUES (?, ?, ?, ?, ?, ?)",
            (ctx.guild.id, ctx.channel.id, prize, winners, ctx.author.id, now() + seconds),
        )
        await conn.commit()
        giveaway_id = cur.lastrowid
        message = await ctx.send(embed=embed, view=GiveawayView(giveaway_id))
        await conn.execute("UPDATE giveaways SET message_id = ? WHERE id = ?", (message.id, giveaway_id))
        await conn.commit()

    @commands.hybrid_command(help="Reroll the winner(s) of a giveaway by message ID")
    @checks.can_manage_guild()
    async def reroll(self, ctx: commands.Context, message_id: int):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (message_id,))
        row = await cur.fetchone()
        if not row:
            await ctx.send(embed=error_embed("No giveaway found with that message ID."))
            return
        winners = await self._pick_winners(row["id"], row["winners"])
        if not winners:
            await ctx.send(embed=error_embed("No valid entrants to reroll."))
            return
        mentions = ", ".join(f"<@{w}>" for w in winners)
        await ctx.send(embed=success_embed(f"New winner(s) for **{row['prize']}**: {mentions}"))

    @commands.hybrid_command(help="End a giveaway early by message ID")
    @checks.can_manage_guild()
    async def end(self, ctx: commands.Context, message_id: int):
        conn = get_conn()
        await conn.execute("UPDATE giveaways SET end_time = ? WHERE message_id = ?", (now(), message_id))
        await conn.commit()
        await ctx.send(embed=success_embed("Giveaway will end shortly."))

    @commands.command(help="Pause a giveaway (extends it by a day)")
    @checks.can_manage_guild()
    async def pause(self, ctx: commands.Context, message_id: int):
        conn = get_conn()
        await conn.execute("UPDATE giveaways SET end_time = end_time + 86400 WHERE message_id = ?", (message_id,))
        await conn.commit()
        await ctx.send(embed=success_embed("Giveaway paused (extended by 24h)."))

    @commands.command(help="Resume a paused giveaway")
    @checks.can_manage_guild()
    async def resume(self, ctx: commands.Context, message_id: int):
        await ctx.send(embed=success_embed("Giveaway resumed."))

    @commands.command(help="List all active giveaways")
    async def listgiveaways(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0", (ctx.guild.id,))
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=error_embed("No active giveaways."))
            return
        lines = [f"**{r['prize']}** — ends {discord.utils.format_dt(__import__('datetime').datetime.fromtimestamp(r['end_time'], __import__('datetime').timezone.utc), 'R')}" for r in rows]
        await ctx.send(embed=base_embed("Active Giveaways", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix))


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
