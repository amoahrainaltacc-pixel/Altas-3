"""
Server administration: prefix, config, autorole, reaction roles, embeds, polls, backups.

Note: some less-common commands are prefix-only (see moderation.py note on the 100
global slash command cap).
"""

import json
import discord
from discord.ext import commands

import config
from database import get_conn, get_guild_config, set_guild_config
from utils import checks
from utils.embeds import success_embed, error_embed, info_embed, base_embed


class Administration(commands.Cog, name="administration"):
    """Configure Atlas for your server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(help="Change the command prefix for this server")
    @checks.can_manage_guild()
    async def prefix(self, ctx: commands.Context, new_prefix: str | None = None):
        if not new_prefix:
            row = await get_guild_config(ctx.guild.id)
            await ctx.send(embed=info_embed(f"Current prefix: `{row['prefix']}`"))
            return
        if len(new_prefix) > 5:
            await ctx.send(embed=error_embed("Prefix must be 5 characters or fewer."))
            return
        await set_guild_config(ctx.guild.id, prefix=new_prefix)
        await ctx.send(embed=success_embed(f"Prefix updated to `{new_prefix}`.", prefix=new_prefix))

    @commands.command(help="Run a quick guided setup for common settings")
    @checks.can_manage_guild()
    async def setup(self, ctx: commands.Context):
        embed = info_embed(
            "Use these commands to configure Atlas:\n\n"
            f"`{ctx.prefix}setlog <type> <channel>` — set a logging channel\n"
            f"`{ctx.prefix}autorole <role>` — auto-assign a role on join\n"
            f"`{ctx.prefix}setwelcome <channel> <message>` — welcome messages\n"
            f"`{ctx.prefix}automod` — toggle automod protections\n"
            f"`{ctx.prefix}ticketpanel` — post a ticket creation panel",
            "Atlas Setup",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(help="View the current server configuration")
    @checks.can_manage_guild()
    async def config(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        embed = base_embed("⚙️ Server Configuration", color=config.COLOR_PRIMARY, prefix=row["prefix"], guild=ctx.guild)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.with_size(512).url)
        embed.add_field(name="Prefix", value=f"`{row['prefix']}`", inline=True)
        embed.add_field(name="Autorole", value=f"<@&{row['autorole_id']}>" if row["autorole_id"] else "Not set", inline=True)
        embed.add_field(name="Mod Log", value=f"<#{row['mod_log_channel']}>" if row["mod_log_channel"] else "Not set", inline=True)
        embed.add_field(name="Welcome Channel", value=f"<#{row['welcome_channel']}>" if row["welcome_channel"] else "Not set", inline=True)
        embed.add_field(name="AutoMod", value="Enabled" if row["automod_enabled"] else "Disabled", inline=True)
        embed.add_field(name="Server Locked", value="Yes" if row["server_locked"] else "No", inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="Alias for config")
    @checks.can_manage_guild()
    async def settings(self, ctx: commands.Context):
        await self.config(ctx)

    @commands.hybrid_command(help="Set the role automatically given to new members")
    @checks.can_manage_roles()
    async def autorole(self, ctx: commands.Context, role: discord.Role | None = None):
        if role is None:
            await set_guild_config(ctx.guild.id, autorole_id=None)
            await ctx.send(embed=success_embed("Autorole disabled."))
            return
        await set_guild_config(ctx.guild.id, autorole_id=role.id)
        await ctx.send(embed=success_embed(f"New members will now receive **{role.name}**."))

    @commands.command(help="Create a reaction role on a message")
    @checks.can_manage_roles()
    async def reactionrole(self, ctx: commands.Context, message_id: int, emoji: str, role: discord.Role):
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(embed=error_embed("Message not found in this channel."))
            return
        conn = get_conn()
        await conn.execute(
            "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
            (ctx.guild.id, message_id, emoji, role.id),
        )
        await conn.commit()
        await message.add_reaction(emoji)
        await ctx.send(embed=success_embed(f"Reacting with {emoji} on that message now grants **{role.name}**."))

    @commands.hybrid_command(help="Post a custom embed to a channel (JSON title/description)")
    @checks.can_manage_guild()
    async def embed(self, ctx: commands.Context, channel: discord.TextChannel, *, content: str):
        title, _, description = content.partition("|")
        embed = base_embed(title.strip() or None, description.strip() or None, config.COLOR_PRIMARY, ctx.prefix)
        await channel.send(embed=embed)
        await ctx.send(embed=success_embed(f"Embed sent to {channel.mention}."))

    @commands.hybrid_command(help="Announce a message to a channel with an announcement embed")
    @checks.can_manage_guild()
    async def announce(self, ctx: commands.Context, channel: discord.TextChannel, *, message: str):
        embed = base_embed("📢 Announcement", message, config.COLOR_PRIMARY, ctx.prefix)
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        await channel.send(embed=embed)
        await ctx.send(embed=success_embed(f"Announcement sent to {channel.mention}."))

    @commands.hybrid_command(help="Create a quick reaction poll")
    async def poll(self, ctx: commands.Context, *, question: str):
        embed = base_embed("🗳️ Poll", question, config.COLOR_PRIMARY, ctx.prefix)
        embed.set_footer(text=f"Started by {ctx.author} • Atlas")
        message = await ctx.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("👎")

    @commands.hybrid_command(help="Set up a member verification role/channel")
    @checks.can_manage_guild()
    async def verify(self, ctx: commands.Context, channel: discord.TextChannel, role: discord.Role):
        await set_guild_config(ctx.guild.id, verify_channel=channel.id, verify_role=role.id)
        await ctx.send(embed=success_embed(f"Verification set up in {channel.mention} granting **{role.name}**."))

    @commands.command(help="Export a JSON backup of server config")
    @checks.can_manage_guild()
    async def backup(self, ctx: commands.Context):
        row = await get_guild_config(ctx.guild.id)
        data = dict(row)
        content = json.dumps(data, indent=2)
        await ctx.send(
            embed=success_embed("Backup generated. See the attached file."),
            file=discord.File(fp=__import__("io").StringIO(content), filename=f"atlas_backup_{ctx.guild.id}.json"),
        )

    @commands.command(help="Reset server configuration to defaults")
    @checks.can_manage_guild()
    async def resetconfig(self, ctx: commands.Context):
        conn = get_conn()
        await conn.execute("DELETE FROM guild_config WHERE guild_id = ?", (ctx.guild.id,))
        await conn.commit()
        await ctx.send(embed=success_embed("Configuration reset to defaults."))

    @commands.command(help="Restore config from a backup (placeholder acknowledgement)")
    @checks.can_manage_guild()
    async def restore(self, ctx: commands.Context):
        await ctx.send(embed=info_embed("Attach a backup JSON file and re-run this command with it as context to restore settings."))

    @commands.command(help="Set the channel used for member suggestions")
    @checks.can_manage_guild()
    async def suggestion(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_guild_config(ctx.guild.id, suggestion_channel=channel.id)
        await ctx.send(embed=success_embed(f"Suggestions will now be posted in {channel.mention}."))

    @commands.command(help="Lock the entire server to a specific role")
    @checks.can_manage_guild()
    async def serverlock(self, ctx: commands.Context, enabled: bool):
        await set_guild_config(ctx.guild.id, server_locked=1 if enabled else 0)
        await ctx.send(embed=success_embed(f"Server lock {'enabled' if enabled else 'disabled'}."))

    @commands.command(help="Toggle anti-raid protection (blocks rapid joins)")
    @checks.can_manage_guild()
    async def antiraid(self, ctx: commands.Context, enabled: bool):
        await set_guild_config(ctx.guild.id, antiraid=1 if enabled else 0)
        await ctx.send(embed=success_embed(f"Anti-raid {'enabled' if enabled else 'disabled'}."))

    @commands.hybrid_command(help="Add a member to the raid-protection whitelist")
    @checks.can_manage_guild()
    async def whitelist(self, ctx: commands.Context, member: discord.Member):
        conn = get_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO whitelist (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, member.id)
        )
        await conn.commit()
        await ctx.send(embed=success_embed(f"**{member}** added to the whitelist."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Administration(bot))
