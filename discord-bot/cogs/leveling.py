"""
XP & leveling system with level roles and a rank card.
"""

import random
import discord
from discord.ext import commands

import config
from database import get_conn, now
from utils import checks
from utils.embeds import base_embed, success_embed, error_embed, progress_bar


def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


class Leveling(commands.Cog, name="leveling"):
    """Earn XP by chatting and level up with configurable role rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _profile(self, guild_id: int, user_id: int):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = await cur.fetchone()
        if not row:
            await conn.execute("INSERT INTO levels (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
            await conn.commit()
            cur = await conn.execute("SELECT * FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            row = await cur.fetchone()
        return row

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        row = await self._profile(message.guild.id, message.author.id)
        if now() - row["last_xp_at"] < config.XP_COOLDOWN_SECONDS:
            return
        gained = random.randint(config.XP_MIN_PER_MESSAGE, config.XP_MAX_PER_MESSAGE)
        new_xp = row["xp"] + gained
        conn = get_conn()
        leveled_up = False
        new_level = row["level"]
        while new_xp >= xp_for_level(new_level):
            new_xp -= xp_for_level(new_level)
            new_level += 1
            leveled_up = True
        await conn.execute(
            "UPDATE levels SET xp = ?, level = ?, last_xp_at = ? WHERE guild_id = ? AND user_id = ?",
            (new_xp, new_level, now(), message.guild.id, message.author.id),
        )
        await conn.commit()
        if leveled_up:
            embed = base_embed("🎉 Level Up!", f"{message.author.mention} reached **level {new_level}**!", config.COLOR_SUCCESS)
            try:
                await message.channel.send(embed=embed)
            except discord.HTTPException:
                pass
            cur = await conn.execute(
                "SELECT role_id FROM level_roles WHERE guild_id = ? AND level = ?", (message.guild.id, new_level)
            )
            role_row = await cur.fetchone()
            if role_row:
                role = message.guild.get_role(role_row["role_id"])
                if role and isinstance(message.author, discord.Member):
                    try:
                        await message.author.add_roles(role, reason="Level role reward")
                    except discord.HTTPException:
                        pass

    @commands.hybrid_command(help="Show your (or another member's) rank and XP")
    async def rank(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        row = await self._profile(ctx.guild.id, member.id)
        needed = xp_for_level(row["level"])
        bar = progress_bar(row["xp"], needed)
        embed = base_embed(
            f"📊 {member.display_name}'s Rank",
            f"**Level:** {row['level']}\n**XP:** {row['xp']} / {needed}\n{bar}",
            config.COLOR_PRIMARY,
            ctx.prefix,
            ctx.guild,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="levelboard", help="Show the server XP leaderboard")
    async def levelboard(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (ctx.guild.id,)
        )
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=error_embed("No leveling data yet."))
            return
        lines = [f"**#{i+1}** <@{r['user_id']}> — Level {r['level']} ({r['xp']} XP)" for i, r in enumerate(rows)]
        embed = base_embed("📈 XP Leaderboard", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix, ctx.guild)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)

    @commands.command(help="Set a member's XP")
    @checks.can_manage_guild()
    async def setxp(self, ctx: commands.Context, member: discord.Member, amount: int):
        await self._profile(ctx.guild.id, member.id)
        conn = get_conn()
        await conn.execute("UPDATE levels SET xp = ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Set **{member}**'s XP to **{amount}**."))

    @commands.command(help="Remove XP from a member")
    @checks.can_manage_guild()
    async def removexp(self, ctx: commands.Context, member: discord.Member, amount: int):
        await self._profile(ctx.guild.id, member.id)
        conn = get_conn()
        await conn.execute("UPDATE levels SET xp = MAX(xp - ?, 0) WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Removed **{amount}** XP from **{member}**."))

    @commands.hybrid_command(help="Set a role reward for reaching a level")
    @checks.can_manage_roles()
    async def levelrole(self, ctx: commands.Context, level: int, role: discord.Role):
        conn = get_conn()
        await conn.execute(
            "INSERT INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id",
            (ctx.guild.id, level, role.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"Members will now receive **{role.name}** at level **{level}**."))

    @commands.command(help="Show your current XP total")
    async def xp(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        row = await self._profile(ctx.guild.id, member.id)
        await ctx.send(embed=base_embed(f"{member.display_name}'s XP", f"{row['xp']} XP at level {row['level']}", config.COLOR_PRIMARY, ctx.prefix))


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
