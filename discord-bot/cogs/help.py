"""
Interactive help command with a category select menu and pagination.
"""

import discord
from discord.ext import commands

import config
from utils.embeds import base_embed

CATEGORY_META = {
    "Moderation": ("🛡️", "moderation"),
    "Administration": ("⚙️", "administration"),
    "Utility": ("🧰", "utility"),
    "Fun": ("🎉", "fun"),
    "Information": ("📖", "information"),
    "AutoMod": ("🤖", "automod"),
    "Logging": ("🧾", "logging_cog"),
    "Tickets": ("🎫", "tickets"),
    "Giveaways": ("🎁", "giveaways"),
    "Welcome": ("👋", "welcome"),
    "Economy": ("💰", "economy"),
    "Leveling": ("📈", "leveling"),
    "Owner": ("👑", "owner"),
}


class HelpSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, author_id: int, prefix: str, guild: discord.Guild | None):
        self.bot = bot
        self.author_id = author_id
        self.prefix = prefix
        self.guild = guild
        options = [
            discord.SelectOption(label="Home", emoji="🏠", value="home", description="Back to the overview")
        ]
        for name, (emoji, cog_name) in CATEGORY_META.items():
            cog = bot.get_cog(cog_name)
            if cog and len(cog.get_commands()) > 0:
                options.append(discord.SelectOption(label=name, emoji=emoji, value=cog_name))
        super().__init__(placeholder="Browse a category…", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu isn't for you.", ephemeral=True)
            return
        value = self.values[0]
        if value == "home":
            embed = build_home_embed(self.bot, self.prefix, self.guild)
            await interaction.response.edit_message(embed=embed, view=self.view)
            return
        cog = self.bot.get_cog(value)
        embed = build_category_embed(cog, self.prefix, self.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int, prefix: str, guild: discord.Guild | None = None):
        super().__init__(timeout=120)
        self.add_item(HelpSelect(bot, author_id, prefix, guild))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


def build_home_embed(bot: commands.Bot, prefix: str, guild: discord.Guild | None = None) -> discord.Embed:
    embed = base_embed(
        f"{config.EMOJI_INFO} Atlas Help Menu",
        (
            "Atlas is a full moderation and utility bot with commands across "
            f"**{len(CATEGORY_META)}** categories.\n\n"
            f"Use the dropdown below to browse a category, or run `{prefix}help <command>` "
            "for details on a specific command.\n\n"
            "**Categories**\n"
            + "\n".join(f"{emoji} {name}" for name, (emoji, _) in CATEGORY_META.items())
        ),
        config.COLOR_PRIMARY,
        prefix,
        guild,
    )
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(
        text=f"{guild.name if guild else 'Atlas'} • Prefix: {prefix} • {sum(1 for c in bot.commands)} commands loaded",
        icon_url=guild.icon.url if guild and guild.icon else None,
    )
    return embed


def build_category_embed(cog: commands.Cog, prefix: str, guild: discord.Guild | None = None) -> discord.Embed:
    if cog is None:
        return base_embed("Category not found", "Try another category.", config.COLOR_ERROR, prefix, guild)
    commands_list = sorted(cog.get_commands(), key=lambda c: c.name)
    lines = []
    for cmd in commands_list:
        desc = cmd.short_doc or "No description provided."
        lines.append(f"**`{prefix}{cmd.name}`** — {desc}")
    emoji = next((e for name, (e, cname) in CATEGORY_META.items() if cname == cog.qualified_name), "📁")
    embed = base_embed(
        f"{emoji} {cog.qualified_name.replace('_cog', '').title()} Commands",
        "\n".join(lines) if lines else "No commands in this category yet.",
        config.COLOR_PRIMARY,
        prefix,
        guild,
    )
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


class Help(commands.Cog, name="help"):
    """Interactive help menu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show the interactive help menu")
    async def help(self, ctx: commands.Context, *, command: str | None = None):
        prefix = ctx.prefix if ctx.prefix and not ctx.prefix.startswith("<@") else ","
        if command:
            cmd = self.bot.get_command(command)
            if not cmd:
                await ctx.send(embed=base_embed("Not Found", f"No command called `{command}`.", config.COLOR_ERROR, prefix, ctx.guild))
                return
            embed = base_embed(
                f"{config.EMOJI_INFO} {prefix}{cmd.qualified_name}",
                cmd.help or cmd.short_doc or "No description provided.",
                config.COLOR_PRIMARY,
                prefix,
                ctx.guild,
            )
            usage = f"{prefix}{cmd.qualified_name} {cmd.signature}".strip()
            embed.add_field(name="Usage", value=f"`{usage}`", inline=False)
            if cmd.aliases:
                embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)
            await ctx.send(embed=embed)
            return

        embed = build_home_embed(self.bot, prefix, ctx.guild)
        view = HelpView(self.bot, ctx.author.id, prefix, ctx.guild)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
