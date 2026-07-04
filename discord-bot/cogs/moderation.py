"""
Moderation commands: bans, kicks, mutes, warnings, channel locks, purges, and voice actions.

Note: Discord caps global slash commands at 100. The most commonly used moderation
commands are hybrid (slash + prefix); less common ones are prefix-only (still usable
with both configured prefixes, just not as a slash command) to stay under the cap.
"""

import discord
from discord.ext import commands

import config
from database import get_conn, now
from utils import checks
from utils.embeds import mod_embed, error_embed, success_embed
from utils.helpers import parse_duration, human_duration, truncate


class Moderation(commands.Cog, name="moderation"):
    """Keep your server safe with bans, kicks, mutes, warnings, and channel controls."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log(self, ctx: commands.Context, embed: discord.Embed):
        from database import get_guild_config
        row = await get_guild_config(ctx.guild.id)
        if row and row["mod_log_channel"]:
            channel = ctx.guild.get_channel(row["mod_log_channel"])
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    # --- Bans ---
    @commands.hybrid_command(help="Ban a member from the server")
    @checks.can_ban()
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send(embed=error_embed("You can't ban someone with an equal or higher role.", guild=ctx.guild))
            return
        await ctx.guild.ban(member, reason=f"{ctx.author}: {reason}")
        embed = mod_embed("Member Banned", f"**{member}** was banned.\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    @commands.command(help="Unban a user by ID")
    @checks.can_ban()
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except discord.NotFound:
            await ctx.send(embed=error_embed("That user isn't banned or doesn't exist.", guild=ctx.guild))
            return
        embed = mod_embed("Member Unbanned", f"**{user}** was unbanned.\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    @commands.command(help="Temporarily ban a member (e.g. 1d, 2h)")
    @checks.can_ban()
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(embed=error_embed("Invalid duration. Use formats like `10m`, `2h`, `1d`.", guild=ctx.guild))
            return
        await ctx.guild.ban(member, reason=f"{ctx.author}: {reason} (tempban {duration})")
        embed = mod_embed("Member Temp-Banned", f"**{member}** was banned for **{human_duration(seconds)}**.\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

        async def _unban_later():
            import asyncio
            await asyncio.sleep(seconds)
            try:
                await ctx.guild.unban(member, reason="Tempban expired")
            except discord.HTTPException:
                pass

        self.bot.loop.create_task(_unban_later())

    @commands.command(help="Ban then immediately unban a member to clear their messages")
    @checks.can_ban()
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await ctx.guild.ban(member, reason=f"{ctx.author} (softban): {reason}", delete_message_days=1)
        await ctx.guild.unban(member, reason="Softban cleanup")
        embed = mod_embed("Member Softbanned", f"**{member}** was softbanned (messages purged).\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    # --- Kick ---
    @commands.hybrid_command(help="Kick a member from the server")
    @checks.can_kick()
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send(embed=error_embed("You can't kick someone with an equal or higher role.", guild=ctx.guild))
            return
        await ctx.guild.kick(member, reason=f"{ctx.author}: {reason}")
        embed = mod_embed("Member Kicked", f"**{member}** was kicked.\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    # --- Timeouts / mutes ---
    @commands.hybrid_command(help="Timeout (mute) a member, e.g. 10m, 1h")
    @checks.can_moderate()
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(embed=error_embed("Invalid duration. Use formats like `10m`, `2h`, `1d`.", guild=ctx.guild))
            return
        import datetime
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        await member.timeout(until, reason=f"{ctx.author}: {reason}")
        embed = mod_embed("Member Timed Out", f"**{member}** was timed out for **{human_duration(seconds)}**.\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    @commands.hybrid_command(name="removetimeout", aliases=["unmute", "untimeout"], help="Remove a member's timeout")
    @checks.can_moderate()
    @commands.bot_has_permissions(moderate_members=True)
    async def removetimeout(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        embed = mod_embed("Timeout Removed", f"**{member}**'s timeout was removed.", guild=ctx.guild)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    @commands.command(help="Temporarily timeout a member (alias of timeout)")
    @checks.can_moderate()
    @commands.bot_has_permissions(moderate_members=True)
    async def tempmute(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        await self.timeout(ctx, member, duration, reason=reason)

    # --- Warnings ---
    @commands.hybrid_command(help="Warn a member and log it")
    @checks.can_moderate()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        conn = get_conn()
        await conn.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, member.id, ctx.author.id, reason, now()),
        )
        await conn.commit()
        embed = mod_embed("Member Warned", f"**{member}** was warned.\n**Reason:** {truncate(reason, 500)}", guild=ctx.guild)
        await ctx.send(embed=embed)
        await self._log(ctx, embed)

    @commands.command(help="Remove a specific warning by ID")
    @checks.can_moderate()
    async def unwarn(self, ctx: commands.Context, warning_id: int):
        conn = get_conn()
        cur = await conn.execute(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?", (warning_id, ctx.guild.id)
        )
        await conn.commit()
        if cur.rowcount == 0:
            await ctx.send(embed=error_embed("No warning found with that ID.", guild=ctx.guild))
            return
        await ctx.send(embed=success_embed(f"Warning `#{warning_id}` removed.", guild=ctx.guild))

    @commands.hybrid_command(help="List a member's warnings")
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (ctx.guild.id, member.id),
        )
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=mod_embed("Warnings", f"**{member}** has no warnings.", guild=ctx.guild))
            return
        lines = [f"`#{r['id']}` <@{r['moderator_id']}>: {r['reason']}" for r in rows[:15]]
        embed = mod_embed(f"Warnings for {member}", "\n".join(lines), guild=ctx.guild)
        await ctx.send(embed=embed)

    # --- Purge / channel management ---
    @commands.hybrid_command(aliases=["clear"], help="Bulk delete messages in this channel")
    @checks.can_manage_messages()
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int = 10):
        amount = max(1, min(amount, 500))
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount + (1 if not ctx.interaction else 0))
        embed = success_embed(f"Deleted **{len(deleted)}** messages.", guild=ctx.guild)
        msg = await ctx.send(embed=embed)
        await msg.delete(delay=4)

    @commands.hybrid_command(help="Set slowmode delay in seconds (0 to disable)")
    @checks.can_manage_channels()
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int):
        seconds = max(0, min(seconds, 21600))
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(embed=success_embed("Slowmode disabled.", guild=ctx.guild))
        else:
            await ctx.send(embed=success_embed(f"Slowmode set to **{seconds}s**.", guild=ctx.guild))

    @commands.command(help="Delete and recreate this channel (wipes all messages)")
    @checks.can_manage_channels()
    @commands.bot_has_permissions(manage_channels=True)
    async def nuke(self, ctx: commands.Context):
        channel = ctx.channel
        new_channel = await channel.clone(reason=f"Nuked by {ctx.author}")
        await new_channel.edit(position=channel.position)
        await channel.delete(reason=f"Nuked by {ctx.author}")
        embed = mod_embed("Channel Nuked", "This channel has been nuked.", guild=ctx.guild)
        await new_channel.send(embed=embed)

    @commands.hybrid_command(help="Lock this channel for @everyone")
    @checks.can_manage_channels()
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=mod_embed("Channel Locked", f"🔒 {ctx.channel.mention} has been locked.", guild=ctx.guild))

    @commands.hybrid_command(help="Unlock this channel for @everyone")
    @checks.can_manage_channels()
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=mod_embed("Channel Unlocked", f"🔓 {ctx.channel.mention} has been unlocked.", guild=ctx.guild))

    @commands.command(help="Lock every text channel in the server")
    @checks.can_manage_guild()
    @commands.bot_has_permissions(manage_channels=True)
    async def lockdown(self, ctx: commands.Context):
        count = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            try:
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
                count += 1
            except discord.HTTPException:
                continue
        await ctx.send(embed=mod_embed("Server Lockdown", f"🔒 Locked **{count}** channels.", guild=ctx.guild))

    @commands.command(help="Unlock every text channel in the server")
    @checks.can_manage_guild()
    @commands.bot_has_permissions(manage_channels=True)
    async def unlockdown(self, ctx: commands.Context):
        count = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = None
            try:
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
                count += 1
            except discord.HTTPException:
                continue
        await ctx.send(embed=mod_embed("Lockdown Lifted", f"🔓 Unlocked **{count}** channels.", guild=ctx.guild))

    @commands.command(help="Hide this channel from @everyone")
    @checks.can_manage_channels()
    @commands.bot_has_permissions(manage_channels=True)
    async def hide(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=mod_embed("Channel Hidden", f"👻 {ctx.channel.mention} is now hidden.", guild=ctx.guild))

    @commands.command(help="Unhide this channel from @everyone")
    @checks.can_manage_channels()
    @commands.bot_has_permissions(manage_channels=True)
    async def unhide(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=mod_embed("Channel Unhidden", f"👁️ {ctx.channel.mention} is visible again.", guild=ctx.guild))

    # --- Member management ---
    @commands.hybrid_command(help="Change a member's nickname")
    @checks.can_manage_guild()
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, name: str | None = None):
        await member.edit(nick=name, reason=f"Changed by {ctx.author}")
        if name:
            await ctx.send(embed=success_embed(f"**{member}**'s nickname changed to **{name}**.", guild=ctx.guild))
        else:
            await ctx.send(embed=success_embed(f"**{member}**'s nickname reset.", guild=ctx.guild))

    @commands.hybrid_group(help="Manage roles for a member", invoke_without_command=True)
    @checks.can_manage_roles()
    async def role(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        if role in member.roles:
            await member.remove_roles(role, reason=f"By {ctx.author}")
            await ctx.send(embed=success_embed(f"Removed **{role.name}** from **{member}**.", guild=ctx.guild))
        else:
            await member.add_roles(role, reason=f"By {ctx.author}")
            await ctx.send(embed=success_embed(f"Added **{role.name}** to **{member}**.", guild=ctx.guild))

    # --- Voice moderation ---
    @commands.command(help="Disconnect a member from voice")
    @checks.is_owner_or_perm("move_members")
    @commands.bot_has_permissions(move_members=True)
    async def voicekick(self, ctx: commands.Context, member: discord.Member):
        if not member.voice:
            await ctx.send(embed=error_embed(f"**{member}** isn't in a voice channel.", guild=ctx.guild))
            return
        await member.move_to(None, reason=f"Voicekicked by {ctx.author}")
        await ctx.send(embed=success_embed(f"**{member}** was disconnected from voice.", guild=ctx.guild))

    @commands.command(name="disconnect", help="Disconnect a member from voice")
    @checks.is_owner_or_perm("move_members")
    @commands.bot_has_permissions(move_members=True)
    async def disconnect_cmd(self, ctx: commands.Context, member: discord.Member):
        await self.voicekick(ctx, member)

    @commands.command(help="Move a member to another voice channel")
    @checks.is_owner_or_perm("move_members")
    @commands.bot_has_permissions(move_members=True)
    async def move(self, ctx: commands.Context, member: discord.Member, *, channel: discord.VoiceChannel):
        if not member.voice:
            await ctx.send(embed=error_embed(f"**{member}** isn't in a voice channel.", guild=ctx.guild))
            return
        await member.move_to(channel, reason=f"Moved by {ctx.author}")
        await ctx.send(embed=success_embed(f"Moved **{member}** to **{channel.name}**.", guild=ctx.guild))

    @commands.command(help="Server-deafen a member in voice")
    @checks.is_owner_or_perm("deafen_members")
    @commands.bot_has_permissions(deafen_members=True)
    async def deafen(self, ctx: commands.Context, member: discord.Member):
        await member.edit(deafen=True, reason=f"By {ctx.author}")
        await ctx.send(embed=success_embed(f"**{member}** has been server-deafened.", guild=ctx.guild))

    @commands.command(help="Remove server-deafen from a member")
    @checks.is_owner_or_perm("deafen_members")
    @commands.bot_has_permissions(deafen_members=True)
    async def undeafen(self, ctx: commands.Context, member: discord.Member):
        await member.edit(deafen=False, reason=f"By {ctx.author}")
        await ctx.send(embed=success_embed(f"**{member}**'s server-deafen removed.", guild=ctx.guild))


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
