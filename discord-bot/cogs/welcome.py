"""
Welcome & goodbye messages, plus verification panel.
"""

import discord
from discord.ext import commands

from database import set_guild_config, get_guild_config
from utils import checks
from utils.embeds import success_embed, base_embed
import config


def _format_message(template: str, member: discord.Member) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{username}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{membercount}", str(member.guild.member_count))
    )


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", emoji="✅", style=discord.ButtonStyle.success, custom_id="atlas:verify")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await get_guild_config(interaction.guild.id)
        if not row or not row["verify_role"]:
            await interaction.response.send_message("Verification isn't configured on this server.", ephemeral=True)
            return
        role = interaction.guild.get_role(row["verify_role"])
        if not role:
            await interaction.response.send_message("The verification role no longer exists.", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Self-verification")
        await interaction.response.send_message("You've been verified! Welcome aboard.", ephemeral=True)


class Welcome(commands.Cog, name="welcome"):
    """Welcome new members and say goodbye to those who leave."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(VerifyView())

    @commands.hybrid_command(help="Set the welcome channel and message ({user}, {server}, {membercount})")
    @checks.can_manage_guild()
    async def setwelcome(self, ctx: commands.Context, channel: discord.TextChannel, *, message: str = "Welcome {user} to {server}! We're now {membercount} members strong."):
        await set_guild_config(ctx.guild.id, welcome_channel=channel.id, welcome_message=message)
        await ctx.send(embed=success_embed(f"Welcome messages will be sent in {channel.mention}."))

    @commands.hybrid_command(help="Set the goodbye channel and message ({user}, {server})")
    @checks.can_manage_guild()
    async def setgoodbye(self, ctx: commands.Context, channel: discord.TextChannel, *, message: str = "{username} has left {server}."):
        await set_guild_config(ctx.guild.id, goodbye_channel=channel.id, goodbye_message=message)
        await ctx.send(embed=success_embed(f"Goodbye messages will be sent in {channel.mention}."))

    @commands.command(help="Preview the configured welcome message")
    async def previewwelcome(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        template = row["welcome_message"] or "Welcome {user} to {server}!"
        embed = base_embed("👋 Welcome!", _format_message(template, ctx.author), config.COLOR_SUCCESS, ctx.prefix, ctx.guild)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(help="Preview a card-style welcome embed")
    async def welcomecard(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        embed = base_embed(f"Welcome to {ctx.guild.name}!", f"{member.mention} just joined.\nMember #{ctx.guild.member_count}", config.COLOR_SUCCESS, ctx.prefix, ctx.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        if ctx.guild.banner:
            embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Post a verification panel with a button")
    @checks.can_manage_guild()
    async def verifypanel(self, ctx: commands.Context):
        embed = base_embed("✅ Verification", "Click the button below to verify and gain access to the server.", config.COLOR_PRIMARY, ctx.prefix, ctx.guild)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=embed, view=VerifyView())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        row = await get_guild_config(member.guild.id)
        if row and row["welcome_channel"]:
            channel = member.guild.get_channel(row["welcome_channel"])
            if channel:
                template = row["welcome_message"] or "Welcome {user} to {server}!"
                embed = base_embed("👋 Welcome!", _format_message(template, member), config.COLOR_SUCCESS, guild=member.guild)
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        row = await get_guild_config(member.guild.id)
        if row and row["goodbye_channel"]:
            channel = member.guild.get_channel(row["goodbye_channel"])
            if channel:
                template = row["goodbye_message"] or "{username} has left {server}."
                embed = base_embed("👋 Goodbye", _format_message(template, member), config.COLOR_ERROR)
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
