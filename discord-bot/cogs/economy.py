"""
Simple guild-scoped economy: balances, daily/work rewards, a shop, and leaderboards.
"""

import random
import discord
from discord.ext import commands

import config
from database import get_conn, now
from utils.embeds import success_embed, error_embed, base_embed
from utils.helpers import human_duration

SHOP_ITEMS = {
    "vip": 5000,
    "color_role": 2000,
    "shoutout": 1000,
    "sticker_pack": 500,
}


class Economy(commands.Cog, name="economy"):
    """A lighthearted virtual economy with daily rewards and a shop."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _account(self, guild_id: int, user_id: int):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = await cur.fetchone()
        if not row:
            await conn.execute(
                "INSERT INTO economy (guild_id, user_id, balance) VALUES (?, ?, ?)",
                (guild_id, user_id, config.STARTING_BALANCE),
            )
            await conn.commit()
            cur = await conn.execute("SELECT * FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            row = await cur.fetchone()
        return row

    @commands.hybrid_command(help="Check your (or another member's) balance")
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        row = await self._account(ctx.guild.id, member.id)
        embed = base_embed(f"{member.display_name}'s Wallet", f"💵 **Cash:** {row['balance']}\n🏦 **Bank:** {row['bank']}", config.COLOR_PRIMARY, ctx.prefix)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Claim your daily reward")
    async def daily(self, ctx: commands.Context):
        row = await self._account(ctx.guild.id, ctx.author.id)
        elapsed = now() - row["last_daily"]
        if elapsed < 86400:
            await ctx.send(embed=error_embed(f"Come back in **{human_duration(86400 - elapsed)}**."))
            return
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = balance + ?, last_daily = ? WHERE guild_id = ? AND user_id = ?",
            (config.DAILY_AMOUNT, now(), ctx.guild.id, ctx.author.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"You claimed your daily reward of **{config.DAILY_AMOUNT}** coins!"))

    @commands.hybrid_command(help="Work for some coins")
    async def work(self, ctx: commands.Context):
        row = await self._account(ctx.guild.id, ctx.author.id)
        elapsed = now() - row["last_work"]
        if elapsed < 3600:
            await ctx.send(embed=error_embed(f"You're tired. Rest for **{human_duration(3600 - elapsed)}**."))
            return
        earnings = random.randint(config.WORK_MIN, config.WORK_MAX)
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = balance + ?, last_work = ? WHERE guild_id = ? AND user_id = ?",
            (earnings, now(), ctx.guild.id, ctx.author.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"You worked hard and earned **{earnings}** coins!"))

    @commands.command(help="Attempt to rob another member")
    async def rob(self, ctx: commands.Context, member: discord.Member):
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You can't rob yourself."))
            return
        actor = await self._account(ctx.guild.id, ctx.author.id)
        elapsed = now() - actor["last_rob"]
        if elapsed < 1800:
            await ctx.send(embed=error_embed(f"Lay low for **{human_duration(1800 - elapsed)}** before robbing again."))
            return
        target = await self._account(ctx.guild.id, member.id)
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET last_rob = ? WHERE guild_id = ? AND user_id = ?", (now(), ctx.guild.id, ctx.author.id)
        )
        if target["balance"] < 50:
            await conn.commit()
            await ctx.send(embed=error_embed(f"**{member}** doesn't have enough cash to rob."))
            return
        if random.random() < 0.5:
            amount = random.randint(10, min(200, target["balance"]))
            await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, member.id))
            await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=success_embed(f"You stole **{amount}** coins from **{member}**!"))
        else:
            fine = random.randint(20, 100)
            await conn.execute("UPDATE economy SET balance = MAX(balance - ?, 0) WHERE guild_id = ? AND user_id = ?", (fine, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=error_embed(f"You got caught and paid a **{fine}** coin fine."))

    @commands.command(help="Deposit coins into your bank")
    async def deposit(self, ctx: commands.Context, amount: int):
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["balance"]:
            await ctx.send(embed=error_embed("Invalid amount."))
            return
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = balance - ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?",
            (amount, amount, ctx.guild.id, ctx.author.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"Deposited **{amount}** coins into your bank."))

    @commands.command(help="Withdraw coins from your bank")
    async def withdraw(self, ctx: commands.Context, amount: int):
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["bank"]:
            await ctx.send(embed=error_embed("Invalid amount."))
            return
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = balance + ?, bank = bank - ? WHERE guild_id = ? AND user_id = ?",
            (amount, amount, ctx.guild.id, ctx.author.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"Withdrew **{amount}** coins from your bank."))

    @commands.hybrid_command(help="View the shop")
    async def shop(self, ctx: commands.Context):
        lines = [f"**{name}** — {price} coins" for name, price in SHOP_ITEMS.items()]
        await ctx.send(embed=base_embed("🛒 Shop", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Buy an item from the shop")
    async def buy(self, ctx: commands.Context, *, item: str):
        item = item.lower().replace(" ", "_")
        if item not in SHOP_ITEMS:
            await ctx.send(embed=error_embed("That item doesn't exist. Check `shop` for options."))
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        price = SHOP_ITEMS[item]
        if row["balance"] < price:
            await ctx.send(embed=error_embed(f"You need **{price}** coins for that."))
            return
        conn = get_conn()
        await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (price, ctx.guild.id, ctx.author.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"You bought **{item.replace('_', ' ')}** for **{price}** coins!"))

    @commands.command(help="Sell back an item for half its price")
    async def sell(self, ctx: commands.Context, *, item: str):
        item = item.lower().replace(" ", "_")
        if item not in SHOP_ITEMS:
            await ctx.send(embed=error_embed("That item doesn't exist."))
            return
        refund = SHOP_ITEMS[item] // 2
        conn = get_conn()
        await self._account(ctx.guild.id, ctx.author.id)
        await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (refund, ctx.guild.id, ctx.author.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Sold **{item.replace('_', ' ')}** for **{refund}** coins."))

    @commands.hybrid_command(help="Show the richest members in this server")
    async def leaderboard(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM economy WHERE guild_id = ? ORDER BY (balance + bank) DESC LIMIT 10", (ctx.guild.id,)
        )
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=error_embed("No economy data yet."))
            return
        lines = [f"**#{i+1}** <@{r['user_id']}> — {r['balance'] + r['bank']} coins" for i, r in enumerate(rows)]
        await ctx.send(embed=base_embed("💰 Wealth Leaderboard", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix))


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
