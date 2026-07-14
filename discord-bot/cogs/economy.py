"""
Simple guild-scoped economy: balances, daily/work rewards, a shop, and leaderboards.
"""

import random
import discord
from discord.ext import commands

import config
from database import get_conn, now
from utils.embeds import success_embed, error_embed, base_embed, info_embed
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

    async def _inventory_qty(self, guild_id: int, user_id: int, item: str) -> int:
        conn = get_conn()
        cur = await conn.execute(
            "SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item = ?",
            (guild_id, user_id, item),
        )
        row = await cur.fetchone()
        return row["quantity"] if row else 0

    @commands.hybrid_command(help="Check your (or another member's) balance")
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        row = await self._account(ctx.guild.id, member.id)
        embed = base_embed(f"💰 {member.display_name}'s Wallet", f"💵 **Cash:** {row['balance']}\n🏦 **Bank:** {row['bank']}", config.COLOR_PRIMARY, ctx.prefix, ctx.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
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

    @commands.hybrid_command(help="View your inventory")
    async def inventory(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        conn = get_conn()
        cur = await conn.execute(
            "SELECT item, quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND quantity > 0",
            (ctx.guild.id, member.id),
        )
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=error_embed(f"**{member.display_name}** doesn't own any items."))
            return
        lines = [f"**{r['item'].replace('_', ' ')}** — x{r['quantity']}" for r in rows]
        await ctx.send(embed=base_embed(f"🎒 {member.display_name}'s Inventory", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

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
        await conn.execute(
            "INSERT INTO inventory (guild_id, user_id, item, quantity) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET quantity = quantity + 1",
            (ctx.guild.id, ctx.author.id, item),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"You bought **{item.replace('_', ' ')}** for **{price}** coins!"))

    @commands.command(help="Sell back an item for half its price")
    async def sell(self, ctx: commands.Context, *, item: str):
        item = item.lower().replace(" ", "_")
        if item not in SHOP_ITEMS:
            await ctx.send(embed=error_embed("That item doesn't exist."))
            return

        conn = get_conn()
        qty = await self._inventory_qty(ctx.guild.id, ctx.author.id, item)
        if qty <= 0:
            await ctx.send(embed=error_embed(f"You don't own **{item.replace('_', ' ')}**."))
            return

        refund = SHOP_ITEMS[item] // 2
        await conn.execute(
            "UPDATE inventory SET quantity = quantity - 1 WHERE guild_id = ? AND user_id = ? AND item = ?",
            (ctx.guild.id, ctx.author.id, item),
        )
        await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (refund, ctx.guild.id, ctx.author.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Sold **{item.replace('_', ' ')}** for **{refund}** coins."))

    @commands.command(help="Show your total net worth (cash + bank)")
    async def networth(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        row = await self._account(ctx.guild.id, member.id)
        total = row["balance"] + row["bank"]
        await ctx.send(embed=base_embed(f"💎 {member.display_name}'s Net Worth", f"**Total:** {total} coins", config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

    @commands.command(help="Give coins to another member")
    async def give(self, ctx: commands.Context, member: discord.Member, amount: int):
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed("You can't give coins to yourself."))
            return
        if amount <= 0:
            await ctx.send(embed=error_embed("Amount must be positive."))
            return
        actor = await self._account(ctx.guild.id, ctx.author.id)
        if actor["balance"] < amount:
            await ctx.send(embed=error_embed("You don't have enough coins."))
            return
        await self._account(ctx.guild.id, member.id)
        conn = get_conn()
        await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
        await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"You gave **{amount}** coins to **{member}**."))

    @commands.command(help="Flip a coin and bet coins on the outcome")
    async def coinbet(self, ctx: commands.Context, amount: int, side: str = "heads"):
        side = side.lower()
        if side not in ("heads", "tails"):
            await ctx.send(embed=error_embed("Choose `heads` or `tails`."))
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["balance"]:
            await ctx.send(embed=error_embed("Invalid bet amount."))
            return
        result = random.choice(["heads", "tails"])
        conn = get_conn()
        if result == side:
            await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=success_embed(f"It landed on **{result}**! You won **{amount}** coins."))
        else:
            await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=error_embed(f"It landed on **{result}**. You lost **{amount}** coins."))

    @commands.command(help="Roll dice and bet coins — high roll wins double")
    async def gamble(self, ctx: commands.Context, amount: int):
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["balance"]:
            await ctx.send(embed=error_embed("Invalid bet amount."))
            return
        player_roll = random.randint(1, 6)
        house_roll = random.randint(1, 6)
        conn = get_conn()
        if player_roll > house_roll:
            await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=success_embed(f"You rolled **{player_roll}** vs house's **{house_roll}** — you won **{amount}** coins!"))
        elif player_roll < house_roll:
            await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=error_embed(f"You rolled **{player_roll}** vs house's **{house_roll}** — you lost **{amount}** coins."))
        else:
            await ctx.send(embed=info_embed(f"You both rolled **{player_roll}** — it's a tie, no coins lost."))

    @commands.command(help="Reset a member's balance to the starting amount (admin only)")
    @commands.has_permissions(manage_guild=True)
    async def resetbalance(self, ctx: commands.Context, member: discord.Member):
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = ?, bank = 0 WHERE guild_id = ? AND user_id = ?",
            (config.STARTING_BALANCE, ctx.guild.id, member.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"Reset **{member}**'s balance."))

    @commands.command(help="Add coins to a member's balance (admin only)")
    @commands.has_permissions(manage_guild=True)
    async def addmoney(self, ctx: commands.Context, member: discord.Member, amount: int):
        await self._account(ctx.guild.id, member.id)
        conn = get_conn()
        await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Added **{amount}** coins to **{member}**."))

    @commands.command(help="Remove coins from a member's balance (admin only)")
    @commands.has_permissions(manage_guild=True)
    async def removemoney(self, ctx: commands.Context, member: discord.Member, amount: int):
        await self._account(ctx.guild.id, member.id)
        conn = get_conn()
        await conn.execute("UPDATE economy SET balance = MAX(balance - ?, 0) WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Removed **{amount}** coins from **{member}**."))

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
        embed = base_embed("💰 Wealth Leaderboard", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix, ctx.guild)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
