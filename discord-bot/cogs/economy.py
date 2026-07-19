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

LUCK_BOOSTERS = {
    "lucky_charm": {"price": 500, "luck_bonus": 0.03, "desc": "A small trinket. +3% win chance."},
    "four_leaf_clover": {"price": 1500, "luck_bonus": 0.07, "desc": "Genuinely rare. +7% win chance."},
    "rabbits_foot": {"price": 3000, "luck_bonus": 0.12, "desc": "Lucky, if you're not the rabbit. +12% win chance."},
    "vip": {"price": 5000, "luck_bonus": 0.20, "desc": "The best odds money can buy. +20% win chance."},
}

MAX_LUCK_BONUS = 0.35
MAX_PURCHASES_PER_ITEM = 5
WORK_COOLDOWN = 10  # seconds. 10ms is not a cooldown, it's a typo.


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

    async def _ensure_purchase_log_table(self):
        """
        Tracks lifetime purchase counts per item, separate from `quantity` in boosters.
        Selling a booster back reduces quantity but NOT the purchase count — that's the
        whole point of a purchase cap. If it tracked quantity, sell-then-rebuy would be
        an infinite loop around the cap.
        """
        conn = get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_log (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                times_bought INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, item)
            )
            """
        )
        await conn.commit()

    async def _ensure_loans_table(self):
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

    async def _times_bought(self, guild_id: int, user_id: int, item: str) -> int:
        await self._ensure_purchase_log_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT times_bought FROM purchase_log WHERE guild_id = ? AND user_id = ? AND item = ?",
            (guild_id, user_id, item),
        )
        row = await cur.fetchone()
        return row["times_bought"] if row else 0

    async def _record_purchase(self, guild_id: int, user_id: int, item: str):
        conn = get_conn()
        await conn.execute(
            "INSERT INTO purchase_log (guild_id, user_id, item, times_bought) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET times_bought = times_bought + 1",
            (guild_id, user_id, item),
        )
        # commit happens in caller — same transaction as the balance deduction,
        # so a crash mid-purchase can't leave coins spent with no item recorded.

    async def _get_luck_bonus(self, guild_id: int, user_id: int) -> float:
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
        await self._ensure_loans_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM loans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return row is not None

    async def _get_active_loan(self, guild_id: int, user_id: int):
        await self._ensure_loans_table()
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM loans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return await cur.fetchone()

    async def _check_loan_status(self, ctx: commands.Context) -> bool:
        loan = await self._get_active_loan(ctx.guild.id, ctx.author.id)
        if loan:
            time_remaining = loan["due_at"] - now()
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
        if elapsed < WORK_COOLDOWN:
            await ctx.send(embed=error_embed(f"You're tired. Rest for **{human_duration(WORK_COOLDOWN - elapsed)}**."))
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

    @commands.command(help="Deposit all your cash into your bank")
    async def depositall(self, ctx: commands.Context):
        if await self._check_loan_status(ctx):
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        if row["balance"] <= 0:
            await ctx.send(embed=error_embed("You have nothing to deposit."))
            return
        amount = row["balance"]
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = balance - ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?",
            (amount, amount, ctx.guild.id, ctx.author.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"Deposited all **{amount}** coins into your bank."))

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

    @commands.command(help="Withdraw all coins from your bank")
    async def withdrawall(self, ctx: commands.Context):
        if await self._check_loan_status(ctx):
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        if row["bank"] <= 0:
            await ctx.send(embed=error_embed("Your bank is empty."))
            return
        amount = row["bank"]
        conn = get_conn()
        await conn.execute(
            "UPDATE economy SET balance = balance + ?, bank = bank - ? WHERE guild_id = ? AND user_id = ?",
            (amount, amount, ctx.guild.id, ctx.author.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"Withdrew all **{amount}** coins from your bank."))

    @commands.hybrid_command(name="shop", help="View luck boosters for sale")
    async def shop(self, ctx: commands.Context):
        lines = [
            f"**{name.replace('_', ' ')}** — {info['price']} coins (max {MAX_PURCHASES_PER_ITEM}/person)\n> {info['desc']}"
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

        times_bought = await self._times_bought(ctx.guild.id, ctx.author.id, item)
        if times_bought >= MAX_PURCHASES_PER_ITEM:
            await ctx.send(embed=error_embed(
                f"You've hit the purchase limit for **{item.replace('_', ' ')}** "
                f"({MAX_PURCHASES_PER_ITEM}/{MAX_PURCHASES_PER_ITEM}). Selling it back doesn't reset this."
            ))
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
        await self._record_purchase(ctx.guild.id, ctx.author.id, item)
        await conn.commit()

        remaining = MAX_PURCHASES_PER_ITEM - (times_bought + 1)
        await ctx.send(embed=success_embed(
            f"You bought **{item.replace('_', ' ')}** for **{price}** coins! "
            f"(+{LUCK_BOOSTERS[item]['luck_bonus'] * 100:.0f}% win chance)\n"
            f"**{remaining}** purchase{'s' if remaining != 1 else ''} remaining for this item."
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

    @commands.command(help="Bet coins on a slot machine — three matching symbols pays out big")
    async def slots(self, ctx: commands.Context, amount: int):
        if await self._check_loan_status(ctx):
            return
        row = await self._account(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > row["balance"]:
            await ctx.send(embed=error_embed("Invalid bet amount."))
            return

        symbols = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]
        weights = [30, 25, 20, 15, 8, 2]
        luck_bonus = await self._get_luck_bonus(ctx.guild.id, ctx.author.id)

        spin = random.choices(symbols, weights=weights, k=3)

        conn = get_conn()
        if spin[0] == spin[1] == spin[2]:
            multiplier = {"🍒": 3, "🍋": 4, "🍇": 5, "🔔": 8, "💎": 15, "7️⃣": 25}[spin[0]]
            payout = amount * multiplier
            await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (payout, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=success_embed(f"{' '.join(spin)}\nJACKPOT! You won **{payout}** coins!"))
        elif len(set(spin)) == 2 and random.random() < (0.15 + luck_bonus):
            refund = amount // 2
            await conn.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (refund, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=info_embed(f"{' '.join(spin)}\nClose one. Refunded **{refund}** coins."))
        else:
            await conn.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, ctx.author.id))
            await conn.commit()
            await ctx.send(embed=error_embed(f"{' '.join(spin)}\nNo match. Lost **{amount}** coins."))

    @commands.command(help="Take a loan from the bank (must repay within 1 hour)")
    async def bankloan(self, ctx: commands.Context, amount: int):
        if amount <= 0:
            await ctx.send(embed=error_embed("Loan amount must be positive."))
            return
        if amount > 50000:
            await ctx.send(embed=error_embed("Maximum loan amount is **50,000** coins."))
            return

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
        await self._account(ctx.guild.id, ctx.author.id)
        conn = get_conn()

        due_time = now() + 3600
        await conn.execute(
            "INSERT INTO loans (guild_id, user_id, amount, taken_at, due_at) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, ctx.author.id, amount, now(), due_time),
        )
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

    @commands.command(help="Check your active loan status")
    async def loanstatus(self, ctx: commands.Context):
        loan = await self._get_active_loan(ctx.guild.id, ctx.author.id)
        if not loan:
            await ctx.send(embed=info_embed("You don't have an active loan."))
            return
        time_remaining = loan["due_at"] - now()
        status = "OVERDUE" if time_remaining <= 0 else human_duration(time_remaining)
        await ctx.send(embed=base_embed(
            "📋 Loan Status",
            f"**Owed:** {loan['amount']} coins\n**Due in:** {status}",
            config.COLOR_PRIMARY, ctx.prefix, ctx.guild
        ))

    @commands.command(help="Repay your active bank loan")
    async def repayloan(self, ctx: commands.Context, amount: int | None = None):
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

    @commands.command(help="Show what a luck booster does before you buy it")
    async def iteminfo(self, ctx: commands.Context, *, item: str):
        item = item.lower().replace(" ", "_")
        if item not in LUCK_BOOSTERS:
            await ctx.send(embed=error_embed("That item doesn't exist. Check `shop` for options."))
            return
        info = LUCK_BOOSTERS[item]
        times_bought = await self._times_bought(ctx.guild.id, ctx.author.id, item)
        owned = await self._booster_qty(ctx.guild.id, ctx.author.id, item)
        await ctx.send(embed=base_embed(
            f"🍀 {item.replace('_', ' ').title()}",
            f"{info['desc']}\n\n"
            f"**Price:** {info['price']} coins\n"
            f"**Win bonus:** +{info['luck_bonus'] * 100:.0f}%\n"
            f"**You own:** {owned}\n"
            f"**Purchases used:** {times_bought}/{MAX_PURCHASES_PER_ITEM}",
            config.COLOR_PRIMARY, ctx.prefix, ctx.guild
        ))

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

    @commands.command(help="Wipe a member's purchase history so they can buy items again (admin only)")
    @commands.has_permissions(manage_guild=True)
    async def resetpurchases(self, ctx: commands.Context, member: discord.Member, *, item: str | None = None):
        await self._ensure_purchase_log_table()
        conn = get_conn()
        if item:
            item = item.lower().replace(" ", "_")
            if item not in LUCK_BOOSTERS:
                await ctx.send(embed=error_embed("That item doesn't exist."))
                return
            await conn.execute(
                "DELETE FROM purchase_log WHERE guild_id = ? AND user_id = ? AND item = ?",
                (ctx.guild.id, member.id, item),
            )
            await conn.commit()
            await ctx.send(embed=success_embed(f"Reset **{member}**'s purchase count for **{item.replace('_', ' ')}**."))
        else:
            await conn.execute(
                "DELETE FROM purchase_log WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id),
            )
            await conn.commit()
            await ctx.send(embed=success_embed(f"Reset all purchase limits for **{member}**."))

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

    @commands.command(help="Force-clear a member's active loan (admin only)")
    @commands.has_permissions(manage_guild=True)
    async def clearloan(self, ctx: commands.Context, member: discord.Member):
        await self._ensure_loans_table()
        conn = get_conn()
        await conn.execute("DELETE FROM loans WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Cleared **{member}**'s loan."))

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
