"""
Fun & entertainment commands.
"""

import random
import discord
from discord.ext import commands

import config
from utils.embeds import base_embed, info_embed

EIGHT_BALL_RESPONSES = [
    "It is certain.", "Without a doubt.", "Yes, definitely.", "You may rely on it.",
    "As I see it, yes.", "Most likely.", "Outlook good.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Don't count on it.", "My reply is no.",
    "My sources say no.", "Outlook not so good.", "Very doubtful.",
]

ROASTS = [
    "You bring everyone so much joy… when you leave the room.",
    "You're not stupid; you just have bad luck thinking.",
    "I'd explain it to you, but I left my crayons at home.",
    "You're the reason the gene pool needs a lifeguard.",
    "If laughter is the best medicine, your face must be curing the world.",
]

TRIVIA_QUESTIONS = [
    ("What is the capital of France?", "paris"),
    ("How many continents are there?", "7"),
    ("What planet is known as the Red Planet?", "mars"),
    ("What is the largest ocean on Earth?", "pacific"),
    ("How many strings does a standard guitar have?", "6"),
]

WOULD_YOU_RATHER = [
    ("have the ability to fly", "have the ability to be invisible"),
    ("always be 10 minutes late", "always be 20 minutes early"),
    ("give up sweets", "give up all fried food"),
    ("live without music", "live without movies"),
]


class Fun(commands.Cog, name="fun"):
    """Games, jokes, and lighthearted commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(aliases=["8ball"], help="Ask the magic 8-ball a question")
    async def eightball(self, ctx: commands.Context, *, question: str):
        await ctx.send(embed=base_embed("🎱 8-Ball", f"**Q:** {question}\n**A:** {random.choice(EIGHT_BALL_RESPONSES)}", config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Flip a coin")
    async def coinflip(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("🪙 Coin Flip", random.choice(["Heads!", "Tails!"]), config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Roll a dice, e.g. 2d6")
    async def dice(self, ctx: commands.Context, spec: str = "1d6"):
        try:
            count, sides = spec.lower().split("d")
            count, sides = int(count), int(sides)
            count = max(1, min(count, 20))
            sides = max(2, min(sides, 1000))
        except ValueError:
            await ctx.send(embed=info_embed("Use the format `NdM`, e.g. `2d6`."))
            return
        rolls = [random.randint(1, sides) for _ in range(count)]
        await ctx.send(embed=base_embed("🎲 Dice Roll", f"Rolls: {', '.join(map(str, rolls))}\n**Total:** {sum(rolls)}", config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Rate anything out of 10")
    async def rate(self, ctx: commands.Context, *, thing: str):
        score = random.randint(0, 10)
        await ctx.send(embed=base_embed("⭐ Rating", f"I'd rate **{thing}** a **{score}/10**.", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Roast a member (all in good fun)")
    async def roast(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        await ctx.send(embed=base_embed("🔥 Roasted", f"{member.mention} {random.choice(ROASTS)}", config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Ship two members together")
    async def ship(self, ctx: commands.Context, member1: discord.Member, member2: discord.Member | None = None):
        member2 = member2 or ctx.author
        score = random.randint(0, 100)
        name = member1.display_name[: len(member1.display_name) // 2] + member2.display_name[len(member2.display_name) // 2:]
        await ctx.send(embed=base_embed("💞 Ship", f"**{member1.display_name}** + **{member2.display_name}** = **{name}**\nCompatibility: **{score}%**", config.COLOR_PRIMARY, ctx.prefix))

    async def _action(self, ctx: commands.Context, member: discord.Member, verb: str, emoji: str):
        actor = ctx.author
        target = member or actor
        await ctx.send(embed=base_embed(f"{emoji} {verb.title()}", f"**{actor.display_name}** {verb} **{target.display_name}**!", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Hug a member")
    async def hug(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "hugs", "🤗")

    @commands.command(help="Slap a member")
    async def slap(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "slaps", "👋")

    @commands.command(help="Kiss a member")
    async def kiss(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "kisses", "😘")

    @commands.command(help="Pat a member")
    async def pat(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "pats", "✋")

    @commands.command(help="Dance!")
    async def dance(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("💃 Dance", f"{ctx.author.mention} is dancing! 🕺", config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Answer a random trivia question")
    async def trivia(self, ctx: commands.Context):
        question, answer = random.choice(TRIVIA_QUESTIONS)
        await ctx.send(embed=base_embed("🧠 Trivia", question, config.COLOR_PRIMARY, ctx.prefix))

        def check(m: discord.Message):
            return m.channel == ctx.channel and m.author == ctx.author

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=20)
        except Exception:
            await ctx.send(embed=info_embed(f"Time's up! The answer was **{answer}**."))
            return
        if reply.content.strip().lower() == answer:
            await ctx.send(embed=base_embed("✅ Correct!", "Nice job!", config.COLOR_SUCCESS, ctx.prefix))
        else:
            await ctx.send(embed=base_embed("❌ Wrong", f"The answer was **{answer}**.", config.COLOR_ERROR, ctx.prefix))

    @commands.command(help="Get a random 'would you rather' question")
    async def wouldyourather(self, ctx: commands.Context):
        a, b = random.choice(WOULD_YOU_RATHER)
        await ctx.send(embed=base_embed("🤔 Would You Rather", f"Would you rather **{a}** or **{b}**?", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Convert text to ASCII-style spaced letters")
    async def ascii(self, ctx: commands.Context, *, text: str):
        spaced = " ".join(text.upper())
        await ctx.send(embed=base_embed("🔤 ASCII", f"```{spaced}```", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Emojify text into regional indicator letters")
    async def emojify(self, ctx: commands.Context, *, text: str):
        result = []
        for ch in text.lower():
            if ch.isalpha():
                result.append(f":regional_indicator_{ch}: ")
            elif ch == " ":
                result.append("   ")
            else:
                result.append(ch + " ")
        content = "".join(result)
        if len(content) > 2000:
            content = content[:1990] + "…"
        await ctx.send(content)

    @commands.hybrid_command(help="Get a random meme")
    async def meme(self, ctx: commands.Context):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://meme-api.com/gimme", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
            embed = base_embed(data.get("title", "Meme"), color=config.COLOR_PRIMARY, prefix=ctx.prefix)
            embed.set_image(url=data["url"])
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=info_embed("Couldn't fetch a meme right now, try again later."))

    @commands.hybrid_command(help="Get a random joke")
    async def joke(self, ctx: commands.Context):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Accept": "application/json"}
                async with session.get("https://icanhazdadjoke.com/", headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
            await ctx.send(embed=base_embed("😄 Joke", data["joke"], config.COLOR_PRIMARY, ctx.prefix))
        except Exception:
            await ctx.send(embed=info_embed("Couldn't fetch a joke right now, try again later."))

    async def _animal(self, ctx: commands.Context, animal: str):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                if animal == "cat":
                    embed = base_embed("🐱 Cat", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
                    embed.set_image(url=f"https://cataas.com/cat?{random.randint(1, 999999)}")
                elif animal == "dog":
                    async with session.get("https://random.dog/woof.json", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        data = await resp.json()
                    embed = base_embed("🐶 Dog", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
                    embed.set_image(url=data["url"])
                else:
                    async with session.get("https://randomfox.ca/floof/", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        data = await resp.json()
                    embed = base_embed("🦊 Fox", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
                    embed.set_image(url=data["image"])
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=info_embed(f"Couldn't fetch a {animal} picture right now."))

    @commands.hybrid_command(help="Get a random cat picture")
    async def cat(self, ctx: commands.Context):
        await self._animal(ctx, "cat")

    @commands.hybrid_command(help="Get a random dog picture")
    async def dog(self, ctx: commands.Context):
        await self._animal(ctx, "dog")

    @commands.command(help="Get a random fox picture")
    async def fox(self, ctx: commands.Context):
        await self._animal(ctx, "fox")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
