"""
Server logging: configurable channels for joins/leaves, message edits/deletes, roles, and more.
"""

import discord
from discord.ext import commands

from database import set_guild_config, get_guild_config
from utils import checks
from utils.embeds import success_embed, error_embed, base_embed
import config

LOG_COLUMN_MAP = {
    "mod": "mod_log_channel",
    "join": "join_log_channel",
    "message": "message_log_channel",
    "voice": "voice_log_channel",
    "role": "role_log_channel",
    "nick": "nick_log_channel",
    "server": "server_log_channel",
    "delete": "delete_log_channel",
    "edit": "edit_log_channel",
}


class LoggingCog(commands.Cog, name="logging_cog"):
    """Configure logging channels and view moderation history."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(help="Set a logging channel: mod, join, message, voice, role, nick, server, delete, edit")
    @checks.can_manage_guild()
    async def setlog(self, ctx: commands.Context, log_type: str, channel: discord.TextChannel):
        log_type = log_type.lower()
        if log_type not in LOG_COLUMN_MAP:
            await ctx.send(embed=error_embed(f"Unknown log type. Choose from: {', '.join(LOG_COLUMN_MAP)}"))
            return
        await set_guild_config(ctx.guild.id, **{LOG_COLUMN_MAP[log_type]: channel.id})
        await ctx.send(embed=success_embed(f"`{log_type}` logs will now be sent to {channel.mention}."))

    async def _send_log(self, guild: discord.Guild, column: str, embed: discord.Embed):
        row = await get_guild_config(guild.id)
        if row and row[column]:
            channel = guild.get_channel(row[column])
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    @commands.hybrid_command(help="Show all configured logging channels")
    async def modlogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        lines = []
        for label, column in LOG_COLUMN_MAP.items():
            value = f"<#{row[column]}>" if row[column] else "Not configured"
            lines.append(f"**{label.title()}:** {value}")
        await ctx.send(embed=base_embed("Logging Channels", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the join log channel")
    async def joinlogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['join_log_channel']}>" if row["join_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Join Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the message log channel")
    async def messagelogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['message_log_channel']}>" if row["message_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Message Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the voice log channel")
    async def voicelogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['voice_log_channel']}>" if row["voice_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Voice Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the role log channel")
    async def rolelogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['role_log_channel']}>" if row["role_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Role Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the nickname log channel")
    async def nicklogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['nick_log_channel']}>" if row["nick_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Nickname Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the server event log channel")
    async def serverlogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['server_log_channel']}>" if row["server_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Server Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the deleted-message log channel")
    async def deletelogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['delete_log_channel']}>" if row["delete_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Delete Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Show the edited-message log channel")
    async def editlogs(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        channel = f"<#{row['edit_log_channel']}>" if row["edit_log_channel"] else "Not configured"
        await ctx.send(embed=base_embed("Edit Logs Channel", channel, config.COLOR_PRIMARY, ctx.prefix))

    # --- Listeners that actually populate the logs ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = base_embed("Member Joined", f"{member.mention} ({member})\nAccount created {discord.utils.format_dt(member.created_at, 'R')}", config.COLOR_SUCCESS)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "join_log_channel", embed)

        row = await get_guild_config(member.guild.id)
        if row and row["autorole_id"]:
            role = member.guild.get_role(row["autorole_id"])
            if role:
                try:
                    await member.add_roles(role, reason="Autorole")
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = base_embed("Member Left", f"{member} left the server.", config.COLOR_ERROR)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "join_log_channel", embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        embed = base_embed("Message Deleted", f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Content:** {message.content or '*No text content*'}", config.COLOR_ERROR)
        await self._send_log(message.guild, "delete_log_channel", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = base_embed(
            "Message Edited",
            f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n**Before:** {before.content}\n**After:** {after.content}\n[Jump]({after.jump_url})",
            config.COLOR_WARNING,
        )
        await self._send_log(before.guild, "edit_log_channel", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = base_embed("Nickname Changed", f"{after.mention}: `{before.nick}` → `{after.nick}`", config.COLOR_INFO)
            await self._send_log(after.guild, "nick_log_channel", embed)
        if before.roles != after.roles:
            added = set(after.roles) - set(before.roles)
            removed = set(before.roles) - set(after.roles)
            desc = ""
            if added:
                desc += f"**Added:** {', '.join(r.mention for r in added)}\n"
            if removed:
                desc += f"**Removed:** {', '.join(r.mention for r in removed)}"
            if desc:
                await self._send_log(after.guild, "role_log_channel", base_embed(f"Roles Updated for {after}", desc, config.COLOR_INFO))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        if after.channel and not before.channel:
            desc = f"{member.mention} joined **{after.channel.name}**"
        elif before.channel and not after.channel:
            desc = f"{member.mention} left **{before.channel.name}**"
        else:
            desc = f"{member.mention} moved from **{before.channel.name}** to **{after.channel.name}**"
        await self._send_log(member.guild, "voice_log_channel", base_embed("Voice Update", desc, config.COLOR_INFO))


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
