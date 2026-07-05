"""
Fun & entertainment commands.
"""

import random
import discord
from discord.ext import commands

import config
from utils.embeds import base_embed, info_embed

COMPLIMENTS = [
    "You light up every room you walk into.",
    "Your ideas are genuinely brilliant.",
    "You make hard things look easy.",
    "You have the best laugh in the server.",
    "You're more talented than you realize.",
]

INSULTS_LIGHT = [
    "You have the charisma of a wet sock.",
    "You're about as sharp as a marble.",
    "Even autocorrect gave up on you.",
    "You're proof that evolution can go backwards.",
]

FACTS = [
    "Honey never spoils — archaeologists have found 3000-year-old honey that's still edible.",
    "Bananas are berries, but strawberries aren't.",
    "A day on Venus is longer than a year on Venus.",
    "Octopuses have three hearts.",
    "Sharks existed before trees did.",
    "The Eiffel Tower can grow taller in summer due to heat expansion.",
]

QUOTES = [
    "\"The only way to do great work is to love what you do.\" — Steve Jobs",
    "\"In the middle of difficulty lies opportunity.\" — Albert Einstein",
    "\"It always seems impossible until it's done.\" — Nelson Mandela",
    "\"Success is not final, failure is not fatal.\" — Winston Churchill",
]

PICKUP_LINES = [
    "Are you a parking ticket? Because you've got FINE written all over you.",
    "Do you have a map? I keep getting lost in your eyes.",
    "Is your name Google? Because you have everything I've been searching for.",
]

NEVER_HAVE_I_EVER = [
    "Never have I ever pretended to be sick to skip something.",
    "Never have I ever sent a text to the wrong person.",
    "Never have I ever laughed so hard I cried.",
    "Never have I ever forgotten someone's name right after meeting them.",
]

RIDDLES = [
    ("What has to be broken before you can use it?", "an egg"),
    ("I speak without a mouth and hear without ears. What am I?", "an echo"),
    ("The more you take, the more you leave behind. What am I?", "footsteps"),
]

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

    @commands.command(help="Give a member a genuine compliment")
    async def compliment(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        await ctx.send(embed=base_embed("💖 Compliment", f"{member.mention}, {random.choice(COMPLIMENTS)}", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Playfully insult a member (all in good fun)")
    async def insult(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        await ctx.send(embed=base_embed("😂 Insult", f"{member.mention}, {random.choice(INSULTS_LIGHT)}", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Get a random fun fact")
    async def fact(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("🧠 Fun Fact", random.choice(FACTS), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Get an inspirational quote")
    async def quote(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("💬 Quote", random.choice(QUOTES), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Get a cheesy pickup line")
    async def pickupline(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("😏 Pickup Line", random.choice(PICKUP_LINES), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Get a 'never have I ever' prompt")
    async def neverhaveiever(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("🙊 Never Have I Ever", random.choice(NEVER_HAVE_I_EVER), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Get a random riddle to solve")
    async def riddle(self, ctx: commands.Context):
        question, _ = random.choice(RIDDLES)
        await ctx.send(embed=base_embed("❓ Riddle", question, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Wink at a member")
    async def wink(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "winks at", "😉")

    @commands.command(help="Cuddle a member")
    async def cuddle(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "cuddles", "🥰")

    @commands.command(help="Poke a member")
    async def poke(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "pokes", "👉")

    @commands.command(help="High-five a member")
    async def highfive(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "high-fives", "🙌")

    @commands.command(help="Bonk a member")
    async def bonk(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "bonks", "🔨")

    @commands.command(help="Bite a member")
    async def bite(self, ctx: commands.Context, member: discord.Member):
        await self._action(ctx, member, "bites", "😬")

    @commands.command(help="Flip a table in frustration")
    async def tableflip(self, ctx: commands.Context):
        await ctx.send("(╯°□°）╯︵ ┻━┻")

    @commands.command(help="Put the table back")
    async def unflip(self, ctx: commands.Context):
        await ctx.send("┬─┬ ノ( ゜-゜ノ)")

    @commands.command(help="Shrug")
    async def shrug(self, ctx: commands.Context):
        await ctx.send("¯\\_(ツ)_/¯")

    @commands.command(help="Reverse the given text")
    async def reverse(self, ctx: commands.Context, *, text: str):
        await ctx.send(embed=base_embed("🔁 Reversed", text[::-1], config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Convert text to mOcKiNg SpOnGeBoB case")
    async def mock(self, ctx: commands.Context, *, text: str):
        mocked = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
        await ctx.send(embed=base_embed("🐸 Mock", mocked, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Pick randomly between two or more options, comma-separated")
    async def choose(self, ctx: commands.Context, *, options: str):
        choices = [o.strip() for o in options.split(",") if o.strip()]
        if len(choices) < 2:
            await ctx.send(embed=info_embed("Give me at least two options, separated by commas."))
            return
        await ctx.send(embed=base_embed("🤷 I Choose", f"**{random.choice(choices)}**", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Roll a percentage chance from 0-100")
    async def percent(self, ctx: commands.Context, *, thing: str = "this happening"):
        await ctx.send(embed=base_embed("📊 Percent Chance", f"There's a **{random.randint(0, 100)}%** chance of {thing}.", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Generate a random number between two values")
    async def random(self, ctx: commands.Context, low: int = 1, high: int = 100):
        low, high = min(low, high), max(low, high)
        await ctx.send(embed=base_embed("🎯 Random Number", f"**{random.randint(low, high)}**", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Spin the bottle — picks a random online member")
    async def spinbottle(self, ctx: commands.Context):
        candidates = [m for m in ctx.guild.members if not m.bot]
        if not candidates:
            await ctx.send(embed=info_embed("No one to spin the bottle on."))
            return
        chosen = random.choice(candidates)
        await ctx.send(embed=base_embed("🍾 Spin the Bottle", f"The bottle landed on {chosen.mention}!", config.COLOR_PRIMARY, ctx.prefix))


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
