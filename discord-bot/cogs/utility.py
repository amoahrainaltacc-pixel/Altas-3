"""
General utility commands: info lookups, ping/stats, reminders, todos, AFK, calculator.
"""

import time
import asyncio
import discord
from discord.ext import commands

import config
from database import get_conn, now
from utils.embeds import base_embed, success_embed, error_embed, info_embed
from utils.helpers import human_duration, safe_send_dm


class Utility(commands.Cog, name="utility"):
    """Everyday utilities: info lookups, reminders, todos, and more."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(help="Show a user's avatar")
    async def avatar(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        embed = base_embed(f"{member.display_name}'s Avatar", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.set_image(url=member.display_avatar.with_size(1024).url)
        await ctx.send(embed=embed)

    @commands.command(help="Show the server banner")
    async def banner(self, ctx: commands.Context):
        guild = await self.bot.fetch_guild(ctx.guild.id)
        if not guild.banner:
            await ctx.send(embed=error_embed("This server has no banner set."))
            return
        embed = base_embed(f"{guild.name}'s Banner", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.set_image(url=guild.banner.with_size(1024).url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Show info about a member")
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        embed = base_embed(f"{member}", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name=f"Roles [{len(roles)}]", value=" ".join(roles[:15]) or "None", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Show info about this server")
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = base_embed(guild.name, color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
        embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (Tier {guild.premium_tier})", inline=True)
        embed.add_field(name="Emojis", value=len(guild.emojis), inline=True)
        embed.add_field(name="Verification Level", value=str(guild.verification_level).title(), inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="Show info about a role")
    async def roleinfo(self, ctx: commands.Context, *, role: discord.Role):
        embed = base_embed(role.name, color=role.color.value or config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="Show info about a channel")
    async def channelinfo(self, ctx: commands.Context, channel: discord.abc.GuildChannel | None = None):
        channel = channel or ctx.channel
        embed = base_embed(channel.name, color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.add_field(name="ID", value=channel.id, inline=True)
        embed.add_field(name="Type", value=str(channel.type).title(), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(channel.created_at, "R"), inline=True)
        embed.add_field(name="Category", value=channel.category.name if channel.category else "None", inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="Show the server member count")
    async def membercount(self, ctx: commands.Context):
        guild = ctx.guild
        humans = sum(1 for m in guild.members if not m.bot)
        bots = guild.member_count - humans
        embed = info_embed(f"**Total:** {guild.member_count}\n**Humans:** {humans}\n**Bots:** {bots}", "Member Count", ctx.prefix)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Show info about Atlas")
    async def botinfo(self, ctx: commands.Context):
        embed = base_embed("Atlas", "A modern moderation & utility bot.", config.COLOR_PRIMARY, ctx.prefix)
        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Users", value=sum(g.member_count for g in self.bot.guilds), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name="Uptime", value=human_duration(time.time() - self.bot.start_time), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Check the bot's latency")
    async def ping(self, ctx: commands.Context):
        start = time.perf_counter()
        message = await ctx.send(embed=info_embed("Pinging…"))
        elapsed = (time.perf_counter() - start) * 1000
        embed = success_embed(f"**Message:** {elapsed:.0f}ms\n**Websocket:** {round(self.bot.latency * 1000)}ms", "Pong! 🏓")
        await message.edit(embed=embed)

    @commands.hybrid_command(help="Show how long Atlas has been running")
    async def uptime(self, ctx: commands.Context):
        await ctx.send(embed=info_embed(human_duration(time.time() - self.bot.start_time), "Uptime"))

    @commands.hybrid_command(help="Get Atlas's invite link")
    async def invite(self, ctx: commands.Context):
        url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(permissions=8))
        await ctx.send(embed=info_embed(f"[Click here to invite Atlas]({url})", "Invite Atlas"))

    @commands.command(help="Get the support server link")
    async def support(self, ctx: commands.Context):
        await ctx.send(embed=info_embed(f"[Join the support server]({config.SUPPORT_URL})", "Support"))

    @commands.command(help="Show bot statistics")
    async def stats(self, ctx: commands.Context):
        embed = base_embed("Atlas Stats", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.add_field(name="Guilds", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Commands", value=len(self.bot.commands), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="Get the project's GitHub link")
    async def github(self, ctx: commands.Context):
        await ctx.send(embed=info_embed(f"[View source on GitHub]({config.GITHUB_URL})"))

    @commands.command(help="Get Atlas's website link")
    async def website(self, ctx: commands.Context):
        await ctx.send(embed=info_embed(f"[Visit the website]({config.WEBSITE_URL})"))

    @commands.hybrid_command(help="Evaluate a basic math expression")
    async def calculator(self, ctx: commands.Context, *, expression: str):
        allowed = set("0123456789.+-*/() ")
        if not set(expression) <= allowed:
            await ctx.send(embed=error_embed("Only numbers and + - * / ( ) are allowed."))
            return
        try:
            result = eval(expression, {"__builtins__": {}}, {})
        except Exception:
            await ctx.send(embed=error_embed("Couldn't evaluate that expression."))
            return
        await ctx.send(embed=success_embed(f"`{expression}` = **{result}**", "Calculator"))

    @commands.hybrid_command(help="Remind yourself of something later, e.g. 10m Take a break")
    async def reminder(self, ctx: commands.Context, duration: str, *, message: str):
        from utils.helpers import parse_duration
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(embed=error_embed("Invalid duration. Use formats like `10m`, `2h`, `1d`."))
            return
        conn = get_conn()
        remind_at = now() + seconds
        await conn.execute(
            "INSERT INTO reminders (user_id, channel_id, message, remind_at) VALUES (?, ?, ?, ?)",
            (ctx.author.id, ctx.channel.id, message, remind_at),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"I'll remind you in **{human_duration(seconds)}**."))

        async def _remind():
            await asyncio.sleep(seconds)
            try:
                await ctx.channel.send(f"{ctx.author.mention} ⏰ Reminder: {message}")
            except discord.HTTPException:
                pass

        self.bot.loop.create_task(_remind())

    @commands.hybrid_group(name="todo", invoke_without_command=True, help="Manage your personal todo list")
    async def todo(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM todos WHERE user_id = ? ORDER BY id", (ctx.author.id,))
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=info_embed("Your todo list is empty.", "Todo List"))
            return
        lines = [f"`#{r['id']}` {r['task']}" for r in rows]
        await ctx.send(embed=info_embed("\n".join(lines), "Your Todo List"))

    @todo.command(name="add", help="Add a todo item")
    async def todo_add(self, ctx: commands.Context, *, task: str):
        conn = get_conn()
        await conn.execute(
            "INSERT INTO todos (user_id, task, created_at) VALUES (?, ?, ?)", (ctx.author.id, task, now())
        )
        await conn.commit()
        await ctx.send(embed=success_embed("Added to your todo list."))

    @todo.command(name="remove", help="Remove a todo item by ID")
    async def todo_remove(self, ctx: commands.Context, todo_id: int):
        conn = get_conn()
        cur = await conn.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, ctx.author.id))
        await conn.commit()
        if cur.rowcount == 0:
            await ctx.send(embed=error_embed("No todo with that ID."))
            return
        await ctx.send(embed=success_embed("Removed."))

    @commands.hybrid_command(help="Set yourself as AFK with an optional reason")
    async def afk(self, ctx: commands.Context, *, reason: str = "AFK"):
        conn = get_conn()
        await conn.execute(
            "INSERT INTO afk (user_id, reason, since) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET reason = excluded.reason, since = excluded.since",
            (ctx.author.id, reason, now()),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"You're now AFK: {reason}"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM afk WHERE user_id = ?", (message.author.id,))
        row = await cur.fetchone()
        if row:
            await conn.execute("DELETE FROM afk WHERE user_id = ?", (message.author.id,))
            await conn.commit()
            try:
                await message.reply(embed=info_embed("Welcome back! I've removed your AFK status."), delete_after=5)
            except discord.HTTPException:
                pass
        if message.mentions:
            for user in message.mentions:
                cur = await conn.execute("SELECT * FROM afk WHERE user_id = ?", (user.id,))
                afk_row = await cur.fetchone()
                if afk_row:
                    try:
                        await message.channel.send(
                            embed=info_embed(f"**{user}** is AFK: {afk_row['reason']}"), delete_after=8
                        )
                    except discord.HTTPException:
                        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
