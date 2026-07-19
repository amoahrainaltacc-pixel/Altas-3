"""
Simple guild-scoped economy: balances, daily/work rewards, yealuck boosters, and leaderboards.
"""

import random
import discord
from discord.ext import commands

import config
from database import get_conn, now
from utils.embeds import success_embed, error_embed, base_embed, info_embed
from utils.helpers import human_duration

# Luck boosters: replaces the old cosmetic shop.
# "luck_bonus" is added directly to win probability for coinbet/gamble.
# e.g. 0.05 = +5 percentage points of win chance.
LUCK_BOOSTERS = {
    "lucky_charm": {"price": 500, "luck_bonus": 0.03, "desc": "A small trinket. +3% win chance."},
    "four_leaf_clover": {"price": 1500, "luck_bonus": 0.07, "desc": "Genuinely rare. +7% win chance."},
    "rabbits_foot": {"price": 3000, "luck_bonus": 0.12, "desc": "Lucky, if you're not the rabbit. +12% win chance."},
    "vip": {"price": 5000, "luck_bonus": 0.20, "desc": "The best odds money can buy. +20% win chance."},
}

# Safety cap so stacking boosters can't push win chance to something absurd.
MAX_LUCK_BONUS = 0.35


class Economy(commands.Cog, name="economy"):
    """A lighthearted virtual economy with daily rewards, gambling, and luck boosters."""

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

    async def _ensure_boosters_table(self):
        """Create the boosters table if it doesn't exist yet. Safe to call repeatedly."""
        conn = get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS boosters (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, item)
            )
            """
        )
        await conn.commit()

    async def _ensure_loans_table(self):
        """Create the loans table if it doesn't exist yet. Safe to call repeatedly."""
        conn = get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS loans (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                taken_at INTEGER NOT NULL,
                due_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await conn.commit()

    async def _get_luck_bonus(self, guild_id: int, user_id: int) -> float:
        """Sum up luck bonuses from all boosters a user owns, capped at MAX_LUCK_BONUS."""
        await self._ensure_boosters_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT item, quantity FROM boosters WHERE guild_id = ? AND user_id = ? AND quantity > 0",
            (guild_id, user_id),
        )
        rows = await cur.fetchall()
        total = 0.0
        for r in rows:
            info = LUCK_BOOSTERS.get(r["item"])
            if info:
                total += info["luck_bonus"] * r["quantity"]
        return min(total, MAX_LUCK_BONUS)

    async def _booster_qty(self, guild_id: int, user_id: int, item: str) -> int:
        await self._ensure_boosters_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT quantity FROM boosters WHERE guild_id = ? AND user_id = ? AND item = ?",
            (guild_id, user_id, item),
        )
        row = await cur.fetchone()
        return row["quantity"] if row else 0

    async def _has_active_loan(self, guild_id: int, user_id: int) -> bool:
        """Check if a user has an active loan that hasn't been paid off."""
        await self._ensure_loans_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM loans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return row is not None

    async def _get_active_loan(self, guild_id: int, user_id: int):
        """Get the active loan for a user, or None if no active loan."""
        await self._ensure_loans_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM loans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return await cur.fetchone()

    async def _check_loan_status(self, ctx: commands.Context) -> bool:
        """Check if user has an OVERDUE loan. Returns True if overdue (blocked from economy), False otherwise."""
        loan = await self._get_active_loan(ctx.guild.id, ctx.author.id)
        if loan:
            time_remaining = loan["due_at"] - now()
            # Only block if overdue (time_remaining <= 0)
            if time_remaining <= 0:
                await ctx.send(
                    embed=error_embed(
                        f"⚠️ **Your loan is overdue!**\n"
                        f"You owe **{loan['amount']}** coins.\n"
                        f"You cannot use economy commands until you repay your loan with `repayloan`."
                    )
                )
                return True
        return False

    @commands.hybrid_command(help="Check your (or another member's) balance")
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None):
        if await self._check_loan_status(ctx):
            return
        member = member or ctx.author
        row = await self._account(ctx.guild.id, member.id)
        embed = base_embed(f"💰 {member.display_name}'s Wallet", f"💵 **Cash:** {row['balance']}\n🏦 **Bank:** {row['bank']}", config.COLOR_PRIMARY, ctx.prefix, ctx.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Claim your daily reward")
    async def daily(self, ctx: commands.Context):
        if await self._check_loan_status(ctx):
            return
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
        if await self._check_loan_status(ctx):
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        elapsed = now() - row["last_work"]
        if elapsed < 10:
            await ctx.send(embed=error_embed(f"You're tired. Rest for **{human_duration(10 - elapsed)}**."))
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
        if await self._check_loan_status(ctx):
            return
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
        if await self._check_loan_status(ctx):
            return
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
        if await self._check_loan_status(ctx):
            return
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

    @commands.hybrid_command(name="shop", help="View luck boosters for sale")
    async def shop(self, ctx: commands.Context):
        lines = [
            f"**{name.replace('_', ' ')}** — {info['price']} coins\n> {info['desc']}"
            for name, info in LUCK_BOOSTERS.items()
        ]
        embed = base_embed(
            "🍀 Luck Booster Shop",
            "\n\n".join(lines) + f"\n\n*Boosts stack, capped at +{int(MAX_LUCK_BONUS * 100)}% win chance total.*",
            config.COLOR_PRIMARY,
            ctx.prefix,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="View your inventory")
    async def inventory(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        await self._ensure_boosters_table()
        conn = get_conn()

        cur = await conn.execute(
            "SELECT item, quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND quantity > 0",
            (ctx.guild.id, member.id),
        )
        old_rows = await cur.fetchall()

        cur = await conn.execute(
            "SELECT item, quantity FROM boosters WHERE guild_id = ? AND user_id = ? AND quantity > 0",
            (ctx.guild.id, member.id),
        )
        booster_rows = await cur.fetchall()

        if not old_rows and not booster_rows:
            await ctx.send(embed=error_embed(f"**{member.display_name}** doesn't own any items."))
            return

        lines = [f"**{r['item'].replace('_', ' ')}** — x{r['quantity']}" for r in old_rows]
        lines += [f"🍀 **{r['item'].replace('_', ' ')}** — x{r['quantity']}" for r in booster_rows]

        total_luck = await self._get_luck_bonus(ctx.guild.id, member.id)
        desc = "\n".join(lines)
        if total_luck > 0:
            desc += f"\n\n**Total luck bonus:** +{total_luck * 100:.0f}% win chance"

        await ctx.send(embed=base_embed(f"🎒 {member.display_name}'s Inventory", desc, config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

    @commands.hybrid_command(help="Buy a luck booster from the shop")
    async def buy(self, ctx: commands.Context, *, item: str):
        if await self._check_loan_status(ctx):
            return
        item = item.lower().replace(" ", "_")
        if item not in LUCK_BOOSTERS:
            await ctx.send(embed=error_embed("That item doesn't exist. Check `shop` for options."))
            return

        row = await self._account(ctx.guild.id, ctx.author.id)
        price = LUCK_BOOSTERS[item]["price"]
        if row["balance"] < price:
            await ctx.send(embed=error_embed(f"You need **{price}** coins for that."))
            return

        await self._ensure_boosters_table()
        conn = get_conn()
        await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (price, ctx.guild.id, ctx.author.id))
        await conn.execute(
            "INSERT INTO boosters (guild_id, user_id, item, quantity) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET quantity = quantity + 1",
            (ctx.guild.id, ctx.author.id, item),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(
            f"You bought **{item.replace('_', ' ')}** for **{price}** coins! "
            f"(+{LUCK_BOOSTERS[item]['luck_bonus'] * 100:.0f}% win chance)"
        ))

    @commands.command(help="Sell back a luck booster for half its price")
    async def sell(self, ctx: commands.Context, *, item: str):
        if await self._check_loan_status(ctx):
            return
        item = item.lower().replace(" ", "_")
        if item not in LUCK_BOOSTERS:
            await ctx.send(embed=error_embed("That item doesn't exist."))
            return

        qty = await self._booster_qty(ctx.guild.id, ctx.author.id, item)
        if qty <= 0:
            await ctx.send(embed=error_embed(f"You don't own **{item.replace('_', ' ')}**."))
            return

        conn = get_conn()
        refund = LUCK_BOOSTERS[item]["price"] // 2
        await conn.execute(
            "UPDATE boosters SET quantity = quantity - 1 WHERE guild_id = ? AND user_id = ? AND item = ?",
            (ctx.guild.id, ctx.author.id, item),
        )
        await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (refund, ctx.guild.id, ctx.author.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Sold **{item.replace('_', ' ')}** for **{refund}** coins."))

    @commands.command(help="Show your total net worth (cash + bank)")
    async def networth(self, ctx: commands.Context, member: discord.Member | None = None):
        if await self._check_loan_status(ctx):
            return
        member = member or ctx.author
        row = await self._account(ctx.guild.id, member.id)
        total = row["balance"] + row["bank"]
        await ctx.send(embed=base_embed(f"💎 {member.display_name}'s Net Worth", f"**Total:** {total} coins", config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

    @commands.command(help="Give coins to another member")
    async def give(self, ctx: commands.Context, member: discord.Member, amount: int):
        if await self._check_loan_status(ctx):
            return
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
        if await self._check_loan_status(ctx):
            return
        side = side.lower()
        if side not in ("heads", "tails"):
            await ctx.send(embed=error_embed("Choose `heads` or `tails`."))
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["balance"]:
            await ctx.send(embed=error_embed("Invalid bet amount."))
            return

        luck_bonus = await self._get_luck_bonus(ctx.guild.id, ctx.author.id)
        win_chance = 0.5 + luck_bonus
        won = random.random() < win_chance

        conn = get_conn()
        if won:
            result = side
            await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=success_embed(f"It landed on **{result}**! You won **{amount}** coins."))
        else:
            result = "tails" if side == "heads" else "heads"
            await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=error_embed(f"It landed on **{result}**. You lost **{amount}** coins."))

    @commands.command(help="Roll dice and bet coins — high roll wins double")
    async def gamble(self, ctx: commands.Context, amount: int):
        if await self._check_loan_status(ctx):
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["balance"]:
            await ctx.send(embed=error_embed("Invalid bet amount."))
            return

        luck_bonus = await self._get_luck_bonus(ctx.guild.id, ctx.author.id)

        player_roll = random.randint(1, 6)
        house_roll = random.randint(1, 6)

        # Apply luck as a chance to nudge a tie or narrow loss into a win,
        # rather than touching the dice directly (keeps rolls meaningful/visible).
        if player_roll <= house_roll and random.random() < luck_bonus:
            player_roll = house_roll + 1

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

    @commands.command(help="Take a loan from the bank (must repay within 1 hour)")
    async def bankloan(self, ctx: commands.Context, amount: int):
        """
        Borrow coins from the bank. You must repay within 1 hour or you'll be locked out of economy commands.
        Usage: !bankloan 5000
        """
        if amount <= 0:
            await ctx.send(embed=error_embed("Loan amount must be positive."))
            return
        if amount > 50000:
            await ctx.send(embed=error_embed("Maximum loan amount is **50,000** coins."))
            return

        # Check if user already has an active loan
        existing_loan = await self._get_active_loan(ctx.guild.id, ctx.author.id)
        if existing_loan:
            time_remaining = existing_loan["due_at"] - now()
            await ctx.send(
                embed=error_embed(
                    f"You already have an active loan of **{existing_loan['amount']}** coins!\n"
                    f"Due in: **{human_duration(time_remaining)}**\n"
                    f"Repay it first with `repayloan` before taking another."
                )
            )
            return

        await self._ensure_loans_table()
        row = await self._account(ctx.guild.id, ctx.author.id)
        conn = get_conn()

        # Add the loan to the loans table
        due_time = now() + 3600  # 1 hour from now
        await conn.execute(
            "INSERT INTO loans (guild_id, user_id, amount, taken_at, due_at) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, ctx.author.id, amount, now(), due_time),
        )
        # Add the coins to the user's balance
        await conn.execute(
            "UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
            (amount, ctx.guild.id, ctx.author.id),
        )
        await conn.commit()

        await ctx.send(
            embed=success_embed(
                f"💰 **Bank Loan Approved!**\n"
                f"You borrowed **{amount}** coins.\n"
                f"You must repay by **{human_duration(3600)}** or you'll be locked from economy commands.\n"
                f"Use `repayloan` to repay."
            )
        )

    @commands.command(help="Repay your active bank loan")
    async def repayloan(self, ctx: commands.Context, amount: int | None = None):
        """
        Repay your bank loan. If no amount is specified, you repay the full amount.
        Usage: !repayloan (repays full) or !repayloan 5000 (repays 5000)
        """
        await self._ensure_loans_table()
        loan = await self._get_active_loan(ctx.guild.id, ctx.author.id)

        if not loan:
            await ctx.send(embed=error_embed("You don't have an active loan."))
            return

        if amount is None:
            amount = loan["amount"]

        if amount <= 0:
            await ctx.send(embed=error_embed("Repayment amount must be positive."))
            return

        row = await self._account(ctx.guild.id, ctx.author.id)
        if row["balance"] < amount:
            await ctx.send(embed=error_embed(f"You only have **{row['balance']}** coins. You need **{amount}** to repay."))
            return

        conn = get_conn()

        if amount >= loan["amount"]:
            # Full repayment - remove the loan
            await conn.execute(
                "DELETE FROM loans WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, ctx.author.id),
            )
            await conn.execute(
                "UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?",
                (loan["amount"], ctx.guild.id, ctx.author.id),
            )
            await conn.commit()
            await ctx.send(embed=success_embed(f"✅ **Loan Repaid!**\nYou repaid **{loan['amount']}** coins. You're debt-free!"))
        else:
            # Partial repayment - update the loan amount
            new_amount = loan["amount"] - amount
            await conn.execute(
                "UPDATE loans SET amount = ? WHERE guild_id = ? AND user_id = ?",
                (new_amount, ctx.guild.id, ctx.author.id),
            )
            await conn.execute(
                "UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?",
                (amount, ctx.guild.id, ctx.author.id),
            )
            await conn.commit()
            time_remaining = loan["due_at"] - now()
            await ctx.send(
                embed=success_embed(
                    f"💵 **Partial Repayment**\n"
                    f"You repaid **{amount}** coins.\n"
                    f"Remaining balance: **{new_amount}** coins\n"
                    f"Due in: **{human_duration(time_remaining)}**"
                )
            )

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
