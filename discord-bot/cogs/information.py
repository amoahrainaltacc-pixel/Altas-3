"""
Read-only information lookups about the server, roles, emojis, and members.
"""

import discord
from discord.ext import commands

import config
from utils.embeds import base_embed, error_embed
from utils.pagination import Paginator


class Information(commands.Cog, name="information"):
    """Look up server, role, and member details."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(help="List all custom emojis in the server")
    async def emojis(self, ctx: commands.Context):
        if not ctx.guild.emojis:
            await ctx.send(embed=error_embed("This server has no custom emojis."))
            return
        chunks = [ctx.guild.emojis[i:i + 30] for i in range(0, len(ctx.guild.emojis), 30)]
        embeds = [
            base_embed(f"Emojis ({len(ctx.guild.emojis)})", " ".join(str(e) for e in chunk), config.COLOR_PRIMARY, ctx.prefix)
            for chunk in chunks
        ]
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds, ctx.author.id))

    @commands.hybrid_command(help="List all roles in the server")
    async def roles(self, ctx: commands.Context):
        roles = [r for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
        chunks = [roles[i:i + 20] for i in range(0, len(roles), 20)]
        embeds = [
            base_embed(f"Roles ({len(roles)})", "\n".join(r.mention for r in chunk), config.COLOR_PRIMARY, ctx.prefix)
            for chunk in chunks
        ] or [base_embed("Roles", "No roles found.", config.COLOR_PRIMARY, ctx.prefix)]
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds, ctx.author.id))

    @commands.hybrid_command(help="Show the server's boost status")
    async def boosts(self, ctx: commands.Context):
        guild = ctx.guild
        embed = base_embed(
            "💎 Server Boosts",
            f"**Boosts:** {guild.premium_subscription_count}\n**Tier:** {guild.premium_tier}",
            config.COLOR_PRIMARY,
            ctx.prefix,
            guild,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.with_size(512).url)
        await ctx.send(embed=embed)

    @commands.command(help="List everyone boosting the server")
    async def boostslist(self, ctx: commands.Context):
        boosters = ctx.guild.premium_subscribers
        if not boosters:
            await ctx.send(embed=error_embed("No one is boosting this server yet."))
            return
        await ctx.send(embed=base_embed(f"Boosters ({len(boosters)})", "\n".join(m.mention for m in boosters[:30]), config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Show the server icon")
    async def servericon(self, ctx: commands.Context):
        if not ctx.guild.icon:
            await ctx.send(embed=error_embed("This server has no icon."))
            return
        embed = base_embed(f"🖼️ {ctx.guild.name}'s Icon", color=config.COLOR_PRIMARY, prefix=ctx.prefix, guild=ctx.guild)
        embed.set_image(url=ctx.guild.icon.with_size(1024).url)
        embed.set_thumbnail(url=ctx.guild.icon.with_size(256).url)
        await ctx.send(embed=embed)

    @commands.command(help="Show the server banner")
    async def serverbanner(self, ctx: commands.Context):
        if not ctx.guild.banner:
            await ctx.send(embed=error_embed("This server has no banner."))
            return
        embed = base_embed(f"{ctx.guild.name}'s Banner", color=config.COLOR_PRIMARY, prefix=ctx.prefix)
        embed.set_image(url=ctx.guild.banner.with_size(1024).url)
        await ctx.send(embed=embed)

    @commands.command(help="Show info about an invite code")
    async def inviteinfo(self, ctx: commands.Context, invite: discord.Invite):
        embed = base_embed(
            "Invite Info",
            f"**Server:** {invite.guild.name}\n**Channel:** {invite.channel}\n**Uses:** {invite.uses or 0}\n**Inviter:** {invite.inviter}",
            config.COLOR_PRIMARY,
            ctx.prefix,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="Show your (or another member's) permissions")
    async def permissions(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        perms = [p.replace("_", " ").title() for p, v in member.guild_permissions if v]
        await ctx.send(embed=base_embed(f"{member}'s Permissions", ", ".join(perms) or "None", config.COLOR_PRIMARY, ctx.prefix))

    @commands.hybrid_command(help="Alias for userinfo")
    async def whois(self, ctx: commands.Context, member: discord.Member | None = None):
        utility_cog = self.bot.get_cog("utility")
        if utility_cog:
            await utility_cog.userinfo(ctx, member)

    @commands.command(help="Show the first message ever sent in this channel")
    async def firstmessage(self, ctx: commands.Context):
        async for message in ctx.channel.history(limit=1, oldest_first=True):
            await ctx.send(embed=base_embed("First Message", f"[Jump to message]({message.jump_url})", config.COLOR_PRIMARY, ctx.prefix))
            return
        await ctx.send(embed=error_embed("Couldn't find the first message."))

    @commands.command(help="List all text channels in the server")
    async def channellist(self, ctx: commands.Context):
        channels = [c.mention for c in ctx.guild.text_channels]
        await ctx.send(embed=base_embed(f"Text Channels ({len(channels)})", "\n".join(channels[:40]) or "None", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="List all voice channels in the server")
    async def voicechannellist(self, ctx: commands.Context):
        channels = [c.name for c in ctx.guild.voice_channels]
        await ctx.send(embed=base_embed(f"Voice Channels ({len(channels)})", "\n".join(channels[:40]) or "None", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="List all bots in the server")
    async def botlist(self, ctx: commands.Context):
        bots = [m.mention for m in ctx.guild.members if m.bot]
        if not bots:
            await ctx.send(embed=error_embed("This server has no bots."))
            return
        await ctx.send(embed=base_embed(f"Bots ({len(bots)})", "\n".join(bots[:40]), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the oldest Discord accounts in this server")
    async def oldestaccounts(self, ctx: commands.Context):
        members = sorted((m for m in ctx.guild.members if not m.bot), key=lambda m: m.created_at)[:10]
        lines = [f"**{i+1}.** {m.mention} — {discord.utils.format_dt(m.created_at, 'D')}" for i, m in enumerate(members)]
        await ctx.send(embed=base_embed("👴 Oldest Accounts", "\n".join(lines) or "None", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the newest members to join this server")
    async def newestmembers(self, ctx: commands.Context):
        members = sorted((m for m in ctx.guild.members if not m.bot and m.joined_at), key=lambda m: m.joined_at, reverse=True)[:10]
        lines = [f"**{i+1}.** {m.mention} — joined {discord.utils.format_dt(m.joined_at, 'R')}" for i, m in enumerate(members)]
        await ctx.send(embed=base_embed("🆕 Newest Members", "\n".join(lines) or "None", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Count the number of categories in the server")
    async def categorycount(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("Category Count", str(len(ctx.guild.categories)), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the server's AFK channel/timeout settings")
    async def afkinfo(self, ctx: commands.Context):
        guild = ctx.guild
        channel = guild.afk_channel.mention if guild.afk_channel else "None"
        await ctx.send(embed=base_embed("💤 AFK Settings", f"**Channel:** {channel}\n**Timeout:** {guild.afk_timeout // 60} minutes", config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show a member's join position in the server")
    async def joinposition(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        members = sorted((m for m in ctx.guild.members if m.joined_at), key=lambda m: m.joined_at)
        try:
            position = members.index(member) + 1
        except ValueError:
            position = "Unknown"
        await ctx.send(embed=base_embed(f"{member.display_name}'s Join Position", f"**#{position}** out of {len(members)}", config.COLOR_PRIMARY, ctx.prefix))


async def setup(bot: commands.Bot):
    await bot.add_cog(Information(bot))
