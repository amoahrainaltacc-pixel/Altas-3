"""
Server management toolkit: channel/category/role admin, advanced purge filters,
warning lookups, snipe/editsnipe, emoji & webhook management, and misc lookups.
All prefix-only (never slash) to stay well under Discord's 100 global
slash-command cap while still adding real, working functionality.
"""

import discord
from discord.ext import commands

import config
from database import get_conn
from utils import checks
from utils.embeds import success_embed, error_embed, base_embed, info_embed


class ServerTools(commands.Cog, name="servertools"):
    """Advanced server management and lookup commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_deleted: dict[int, discord.Message] = {}
        self.last_edited: dict[int, tuple[discord.Message, str]] = {}

    # ---------- Channel management ----------

    @commands.command(help="Create a new text channel")
    @checks.can_manage_channels()
    async def channelcreate(self, ctx: commands.Context, *, name: str):
        channel = await ctx.guild.create_text_channel(name, reason=f"Created by {ctx.author}")
        await ctx.send(embed=success_embed(f"Created {channel.mention}."))

    @commands.command(help="Delete a channel")
    @checks.can_manage_channels()
    async def channeldelete(self, ctx: commands.Context, channel: discord.abc.GuildChannel):
        name = channel.name
        await channel.delete(reason=f"Deleted by {ctx.author}")
        if channel.id != ctx.channel.id:
            await ctx.send(embed=success_embed(f"Deleted channel **{name}**."))

    @commands.command(help="Clone a channel (same settings, empty history)")
    @checks.can_manage_channels()
    async def channelclone(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        clone = await channel.clone(reason=f"Cloned by {ctx.author}")
        await ctx.send(embed=success_embed(f"Cloned {channel.mention} as {clone.mention}."))

    @commands.command(help="Rename a channel")
    @checks.can_manage_channels()
    async def channelrename(self, ctx: commands.Context, channel: discord.abc.GuildChannel, *, name: str):
        await channel.edit(name=name, reason=f"Renamed by {ctx.author}")
        await ctx.send(embed=success_embed(f"Renamed channel to **{name}**."))

    @commands.command(help="Set a text channel's topic")
    @checks.can_manage_channels()
    async def channeltopic(self, ctx: commands.Context, channel: discord.TextChannel, *, topic: str):
        await channel.edit(topic=topic, reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"Updated topic for {channel.mention}."))

    @commands.command(help="Toggle a channel's NSFW flag")
    @checks.can_manage_channels()
    async def channelnsfw(self, ctx: commands.Context, channel: discord.TextChannel, enabled: bool):
        await channel.edit(nsfw=enabled, reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"NSFW for {channel.mention} set to **{enabled}**."))

    @commands.command(help="Move a channel into a category")
    @checks.can_manage_channels()
    async def categorymove(self, ctx: commands.Context, channel: discord.abc.GuildChannel, category: discord.CategoryChannel):
        await channel.edit(category=category, reason=f"Moved by {ctx.author}")
        await ctx.send(embed=success_embed(f"Moved {channel.mention} into **{category.name}**."))

    @commands.command(help="Create a new category")
    @checks.can_manage_channels()
    async def categorycreate(self, ctx: commands.Context, *, name: str):
        category = await ctx.guild.create_category(name, reason=f"Created by {ctx.author}")
        await ctx.send(embed=success_embed(f"Created category **{category.name}**."))

    @commands.command(help="Delete a category")
    @checks.can_manage_channels()
    async def categorydelete(self, ctx: commands.Context, *, category: discord.CategoryChannel):
        name = category.name
        await category.delete(reason=f"Deleted by {ctx.author}")
        await ctx.send(embed=success_embed(f"Deleted category **{name}**."))

    @commands.command(help="Create a voice channel")
    @checks.can_manage_channels()
    async def voicechannelcreate(self, ctx: commands.Context, *, name: str):
        channel = await ctx.guild.create_voice_channel(name, reason=f"Created by {ctx.author}")
        await ctx.send(embed=success_embed(f"Created voice channel **{channel.name}**."))

    @commands.command(help="Set a voice channel's user limit (0 for unlimited)")
    @checks.can_manage_channels()
    async def voicechannellimit(self, ctx: commands.Context, channel: discord.VoiceChannel, limit: int):
        await channel.edit(user_limit=limit, reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"Set **{channel.name}**'s user limit to **{limit or 'unlimited'}**."))

    @commands.command(help="Set a voice channel's bitrate in kbps")
    @checks.can_manage_channels()
    async def voicechannelbitrate(self, ctx: commands.Context, channel: discord.VoiceChannel, kbps: int):
        await channel.edit(bitrate=kbps * 1000, reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"Set **{channel.name}**'s bitrate to **{kbps}kbps**."))

    @commands.command(help="Create an instant invite link for a channel")
    @checks.can_manage_channels()
    async def channelinvite(self, ctx: commands.Context, channel: discord.TextChannel | None = None, max_age: int = 86400):
        channel = channel or ctx.channel
        invite = await channel.create_invite(max_age=max_age, reason=f"Created by {ctx.author}")
        await ctx.send(embed=success_embed(f"{invite.url}", "Invite Created"))

    # ---------- Role management ----------

    @commands.command(help="Create a new role")
    @checks.can_manage_roles()
    async def rolecreate(self, ctx: commands.Context, *, name: str):
        role = await ctx.guild.create_role(name=name, reason=f"Created by {ctx.author}")
        await ctx.send(embed=success_embed(f"Created role {role.mention}."))

    @commands.command(help="Delete a role")
    @checks.can_manage_roles()
    async def roledelete(self, ctx: commands.Context, *, role: discord.Role):
        name = role.name
        await role.delete(reason=f"Deleted by {ctx.author}")
        await ctx.send(embed=success_embed(f"Deleted role **{name}**."))

    @commands.command(help="Change a role's color, e.g. #ff0000")
    @checks.can_manage_roles()
    async def rolecolor(self, ctx: commands.Context, role: discord.Role, hex_code: str):
        try:
            value = int(hex_code.lstrip("#"), 16)
        except ValueError:
            await ctx.send(embed=error_embed("Give me a valid hex color, e.g. `#5865F2`."))
            return
        await role.edit(color=discord.Color(value), reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"Updated **{role.name}**'s color."))

    @commands.command(help="Toggle whether a role is displayed separately (hoisted)")
    @checks.can_manage_roles()
    async def rolehoist(self, ctx: commands.Context, role: discord.Role, enabled: bool):
        await role.edit(hoist=enabled, reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"Set **{role.name}**'s hoist to **{enabled}**."))

    @commands.command(help="Toggle whether a role can be mentioned")
    @checks.can_manage_roles()
    async def rolementionable(self, ctx: commands.Context, role: discord.Role, enabled: bool):
        await role.edit(mentionable=enabled, reason=f"Updated by {ctx.author}")
        await ctx.send(embed=success_embed(f"Set **{role.name}**'s mentionable to **{enabled}**."))

    @commands.command(help="Move a role's position in the hierarchy")
    @checks.can_manage_roles()
    async def roleposition(self, ctx: commands.Context, role: discord.Role, position: int):
        try:
            await role.edit(position=position, reason=f"Updated by {ctx.author}")
        except discord.HTTPException as e:
            await ctx.send(embed=error_embed(f"Couldn't move that role: {e}"))
            return
        await ctx.send(embed=success_embed(f"Moved **{role.name}** to position **{position}**."))

    @commands.command(help="List all members that have a role")
    async def rolemembers(self, ctx: commands.Context, *, role: discord.Role):
        members = role.members
        if not members:
            await ctx.send(embed=error_embed(f"No one has the **{role.name}** role."))
            return
        lines = [m.mention for m in members[:40]]
        await ctx.send(embed=base_embed(f"{role.name} Members ({len(members)})", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix))

    # ---------- Advanced purge filters ----------

    @commands.command(help="Delete recent messages from a specific member")
    @checks.can_manage_messages()
    async def purgeuser(self, ctx: commands.Context, member: discord.Member, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: m.author.id == member.id)
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** message(s) from **{member}**."), delete_after=5)

    @commands.command(help="Delete recent messages sent by bots")
    @checks.can_manage_messages()
    async def purgebots(self, ctx: commands.Context, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: m.author.bot)
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** bot message(s)."), delete_after=5)

    @commands.command(help="Delete recent messages sent by humans")
    @checks.can_manage_messages()
    async def purgehuman(self, ctx: commands.Context, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: not m.author.bot)
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** human message(s)."), delete_after=5)

    @commands.command(help="Delete recent messages containing images/attachments")
    @checks.can_manage_messages()
    async def purgeimages(self, ctx: commands.Context, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: bool(m.attachments))
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** message(s) with attachments."), delete_after=5)

    @commands.command(help="Delete recent messages containing links")
    @checks.can_manage_messages()
    async def purgelinks(self, ctx: commands.Context, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: "http://" in m.content or "https://" in m.content)
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** message(s) with links."), delete_after=5)

    @commands.command(help="Delete recent messages containing embeds")
    @checks.can_manage_messages()
    async def purgeembeds(self, ctx: commands.Context, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: bool(m.embeds))
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** message(s) with embeds."), delete_after=5)

    @commands.command(help="Delete recent messages containing specific text")
    @checks.can_manage_messages()
    async def purgecontains(self, ctx: commands.Context, text: str, limit: int = 50):
        deleted = await ctx.channel.purge(limit=min(limit, 200), check=lambda m: text.lower() in m.content.lower())
        await ctx.send(embed=success_embed(f"Deleted **{len(deleted)}** message(s) containing `{text}`."), delete_after=5)

    # ---------- Warning lookups ----------

    @commands.command(help="Show how many warnings a member has")
    @checks.can_moderate()
    async def warncount(self, ctx: commands.Context, member: discord.Member):
        conn = get_conn()
        cur = await conn.execute("SELECT COUNT(*) as c FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        row = await cur.fetchone()
        await ctx.send(embed=info_embed(f"**{member}** has **{row['c']}** warning(s).", "Warning Count", ctx.prefix, ctx.guild))

    @commands.command(help="Clear all warnings for a member")
    @checks.can_manage_guild()
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        conn = get_conn()
        await conn.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Cleared all warnings for **{member}**."))

    @commands.command(help="List all banned users in this server")
    @checks.can_ban()
    async def banlist(self, ctx: commands.Context):
        bans = [entry async for entry in ctx.guild.bans(limit=50)]
        if not bans:
            await ctx.send(embed=error_embed("No one is banned in this server."))
            return
        lines = [f"**{b.user}** — {b.reason or 'No reason'}" for b in bans]
        await ctx.send(embed=base_embed(f"Banned Users ({len(bans)})", "\n".join(lines[:30]), config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

    # ---------- Snipe ----------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild and not message.author.bot:
            self.last_deleted[message.channel.id] = message

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild and not before.author.bot and before.content != after.content:
            self.last_edited[before.channel.id] = (before, after.content)

    @commands.command(help="Show the last deleted message in this channel")
    @checks.can_manage_messages()
    async def snipe(self, ctx: commands.Context):
        message = self.last_deleted.get(ctx.channel.id)
        if not message:
            await ctx.send(embed=error_embed("There's nothing to snipe here."))
            return
        embed = base_embed("🔎 Sniped Message", message.content or "*[no text content]*", config.COLOR_PRIMARY, ctx.prefix)
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.timestamp = message.created_at
        await ctx.send(embed=embed)

    @commands.command(help="Show the last edited message in this channel")
    @checks.can_manage_messages()
    async def editsnipe(self, ctx: commands.Context):
        pair = self.last_edited.get(ctx.channel.id)
        if not pair:
            await ctx.send(embed=error_embed("There's nothing to editsnipe here."))
            return
        before, after_content = pair
        embed = base_embed("✏️ Edited Message", f"**Before:** {before.content}\n**After:** {after_content}", config.COLOR_PRIMARY, ctx.prefix)
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        await ctx.send(embed=embed)

    # ---------- Emoji / sticker / webhook management ----------

    @commands.command(help="Add a custom emoji to this server from an image URL")
    @checks.can_manage_guild()
    async def emojiadd(self, ctx: commands.Context, name: str, url: str):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.read()
        except Exception:
            await ctx.send(embed=error_embed("Couldn't download an image from that URL."))
            return
        try:
            emoji = await ctx.guild.create_custom_emoji(name=name, image=data, reason=f"Added by {ctx.author}")
        except discord.HTTPException as e:
            await ctx.send(embed=error_embed(f"Couldn't create the emoji: {e}"))
            return
        await ctx.send(embed=success_embed(f"Added emoji {emoji}."))

    @commands.command(help="Delete a custom emoji from this server")
    @checks.can_manage_guild()
    async def emojidelete(self, ctx: commands.Context, emoji: discord.Emoji):
        name = emoji.name
        await emoji.delete(reason=f"Deleted by {ctx.author}")
        await ctx.send(embed=success_embed(f"Deleted emoji **{name}**."))

    @commands.command(help="Rename a custom emoji")
    @checks.can_manage_guild()
    async def emojirename(self, ctx: commands.Context, emoji: discord.Emoji, *, new_name: str):
        await emoji.edit(name=new_name, reason=f"Renamed by {ctx.author}")
        await ctx.send(embed=success_embed(f"Renamed emoji to **{new_name}**."))

    @commands.command(help="List all stickers in this server")
    async def stickerlist(self, ctx: commands.Context):
        stickers = ctx.guild.stickers
        if not stickers:
            await ctx.send(embed=error_embed("This server has no custom stickers."))
            return
        await ctx.send(embed=base_embed(f"Stickers ({len(stickers)})", "\n".join(s.name for s in stickers[:40]), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="Create a webhook in a channel")
    @checks.can_manage_guild()
    async def webhookcreate(self, ctx: commands.Context, channel: discord.TextChannel, *, name: str = "Atlas Webhook"):
        webhook = await channel.create_webhook(name=name, reason=f"Created by {ctx.author}")
        await ctx.send(embed=success_embed(f"Created webhook **{webhook.name}** in {channel.mention}.\n{webhook.url}"))

    @commands.command(help="List webhooks in a channel")
    @checks.can_manage_guild()
    async def webhooklist(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        channel = channel or ctx.channel
        webhooks = await channel.webhooks()
        if not webhooks:
            await ctx.send(embed=error_embed(f"No webhooks found in {channel.mention}."))
            return
        await ctx.send(embed=base_embed(f"Webhooks in #{channel.name}", "\n".join(w.name for w in webhooks), config.COLOR_PRIMARY, ctx.prefix))

    # ---------- Misc lookups ----------

    @commands.command(help="Search for members by name or nickname")
    async def membersearch(self, ctx: commands.Context, *, query: str):
        query = query.lower()
        matches = [m for m in ctx.guild.members if query in m.name.lower() or (m.nick and query in m.nick.lower())][:20]
        if not matches:
            await ctx.send(embed=error_embed("No members matched that search."))
            return
        await ctx.send(embed=base_embed(f"Search Results ({len(matches)})", "\n".join(m.mention for m in matches), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="List active invite links for this server")
    @checks.can_manage_guild()
    async def invitelist(self, ctx: commands.Context):
        invites = await ctx.guild.invites()
        if not invites:
            await ctx.send(embed=error_embed("This server has no active invites."))
            return
        lines = [f"`{i.code}` — {i.uses or 0} uses, by {i.inviter}" for i in invites[:20]]
        await ctx.send(embed=base_embed(f"Active Invites ({len(invites)})", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix))

    @commands.command(help="List special features this server has enabled")
    async def serverfeatures(self, ctx: commands.Context):
        features = ctx.guild.features
        if not features:
            await ctx.send(embed=info_embed("This server has no special features enabled."))
            return
        pretty = [f.replace("_", " ").title() for f in features]
        await ctx.send(embed=base_embed("Server Features", "\n".join(pretty), config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

    @commands.command(help="Get the direct URL to a member's avatar")
    async def avatarurl(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        await ctx.send(embed=info_embed(member.display_avatar.with_size(1024).url, "Avatar URL"))

    @commands.command(help="Get the direct URL to a member's profile banner")
    async def bannerurl(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)
        if not user.banner:
            await ctx.send(embed=error_embed(f"**{member}** has no profile banner set."))
            return
        await ctx.send(embed=info_embed(user.banner.with_size(1024).url, "Banner URL"))

    @commands.command(help="Get the direct URL to the server icon")
    async def servericonurl(self, ctx: commands.Context):
        if not ctx.guild.icon:
            await ctx.send(embed=error_embed("This server has no icon."))
            return
        await ctx.send(embed=info_embed(ctx.guild.icon.with_size(1024).url, "Server Icon URL"))

    @commands.command(help="Check a member's permissions in a specific channel")
    async def channelpermissionsfor(self, ctx: commands.Context, member: discord.Member, channel: discord.abc.GuildChannel | None = None):
        channel = channel or ctx.channel
        perms = channel.permissions_for(member)
        allowed = [p.replace("_", " ").title() for p, v in perms if v]
        await ctx.send(embed=base_embed(f"{member}'s Permissions in #{channel.name}", ", ".join(allowed) or "None", config.COLOR_PRIMARY, ctx.prefix))


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerTools(bot))
