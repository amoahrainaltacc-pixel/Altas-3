"""
Ticket system: buttons to open, claim, rename, and close support tickets.
Now with: reason capture via modal, one-open-ticket-per-user limit, a
transcript log channel, and active-ticket / stats overviews.
"""

import io
import discord
from discord.ext import commands

from database import get_conn, now
from utils import checks
from utils.embeds import success_embed, error_embed, base_embed, info_embed
import config


class TicketReasonModal(discord.ui.Modal, title="Open a Support Ticket"):
    reason = discord.ui.TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        placeholder="Briefly describe your issue…",
        max_length=500,
        required=False,
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        cog: Tickets = interaction.client.get_cog("tickets")
        await cog.create_ticket(interaction, str(self.reason) or "No reason provided")


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open a Ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="atlas:open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketReasonModal())


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.secondary, custom_id="atlas:claim_ticket")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("tickets")
        await cog.claim_ticket(interaction)

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="atlas:close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("tickets")
        await cog.close_ticket(interaction)


class Tickets(commands.Cog, name="tickets"):
    """Support ticket system with buttons and transcripts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView())

    async def _config(self, guild_id: int):
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM ticket_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if not row:
            await conn.execute("INSERT INTO ticket_config (guild_id) VALUES (?)", (guild_id,))
            await conn.commit()
            cur = await conn.execute("SELECT * FROM ticket_config WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return row

    @commands.hybrid_command(help="Post the ticket-creation panel in this channel")
    @checks.can_manage_channels()
    async def ticketpanel(self, ctx: commands.Context):
        embed = base_embed(
            "🎫 Support",
            "Click the button below to open a support ticket. You'll be asked what you need help with.",
            config.COLOR_PRIMARY,
            ctx.prefix,
            ctx.guild,
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=embed, view=TicketPanelView())
        conn = get_conn()
        await self._config(ctx.guild.id)
        await conn.execute("UPDATE ticket_config SET panel_channel_id = ? WHERE guild_id = ?", (ctx.channel.id, ctx.guild.id))
        await conn.commit()

    @commands.command(help="Set the category and support role used for tickets")
    @checks.can_manage_guild()
    async def ticketsetup(self, ctx: commands.Context, category: discord.CategoryChannel, support_role: discord.Role):
        await self._config(ctx.guild.id)
        conn = get_conn()
        await conn.execute(
            "UPDATE ticket_config SET category_id = ?, support_role_id = ? WHERE guild_id = ?",
            (category.id, support_role.id, ctx.guild.id),
        )
        await conn.commit()
        await ctx.send(embed=success_embed("Ticket category and support role configured.", guild=ctx.guild))

    @commands.hybrid_command(help="Set the channel where closed-ticket transcripts are logged")
    @checks.can_manage_guild()
    async def ticketlog(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._config(ctx.guild.id)
        conn = get_conn()
        await conn.execute("UPDATE ticket_config SET log_channel_id = ? WHERE guild_id = ?", (channel.id, ctx.guild.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Ticket transcripts will now be logged to {channel.mention}.", guild=ctx.guild))

    async def create_ticket(self, interaction: discord.Interaction, reason: str = "No reason provided"):
        guild = interaction.guild
        conn = get_conn()

        cur = await conn.execute(
            "SELECT channel_id FROM tickets WHERE guild_id = ? AND owner_id = ? AND status = 'open'",
            (guild.id, interaction.user.id),
        )
        existing = await cur.fetchone()
        if existing and guild.get_channel(existing["channel_id"]):
            await interaction.response.send_message(
                embed=error_embed(f"You already have an open ticket: <#{existing['channel_id']}>", guild=guild),
                ephemeral=True,
            )
            return

        cfg = await self._config(guild.id)
        counter = (cfg["counter"] or 0) + 1
        await conn.execute("UPDATE ticket_config SET counter = ? WHERE guild_id = ?", (counter, guild.id))
        await conn.commit()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        if cfg["support_role_id"]:
            role = guild.get_role(cfg["support_role_id"])
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        category = guild.get_channel(cfg["category_id"]) if cfg["category_id"] else None
        channel = await guild.create_text_channel(
            f"ticket-{counter:04d}", category=category, overwrites=overwrites, reason=f"Ticket opened by {interaction.user}"
        )
        await conn.execute(
            "INSERT INTO tickets (guild_id, channel_id, owner_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild.id, channel.id, interaction.user.id, reason, now()),
        )
        await conn.commit()

        embed = base_embed(
            "🎫 New Ticket",
            f"{interaction.user.mention}, support will be with you shortly.\n\n**Reason:** {reason}\n\nUse the buttons below to manage this ticket.",
            config.COLOR_PRIMARY,
            guild=guild,
        )
        support_ping = f"<@&{cfg['support_role_id']}>" if cfg["support_role_id"] else None
        await channel.send(content=support_ping, embed=embed, view=TicketControlView())
        await interaction.response.send_message(embed=success_embed(f"Ticket created: {channel.mention}"), ephemeral=True)

    async def claim_ticket(self, interaction: discord.Interaction):
        conn = get_conn()
        await conn.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (interaction.user.id, interaction.channel.id))
        await conn.commit()
        await interaction.response.send_message(embed=success_embed(f"Ticket claimed by {interaction.user.mention}."))

    async def _build_transcript(self, channel: discord.TextChannel) -> str:
        messages = [msg async for msg in channel.history(limit=500, oldest_first=True)]
        return "\n".join(f"[{m.created_at}] {m.author}: {m.content}" for m in messages)

    async def close_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild
        transcript = await self._build_transcript(channel)
        conn = get_conn()
        cur = await conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel.id,))
        ticket = await cur.fetchone()
        await conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?", (now(), channel.id)
        )
        await conn.commit()
        await interaction.response.send_message(embed=success_embed("Closing ticket… a transcript will be saved."))

        transcript_file_bytes = transcript.encode("utf-8")
        owner = guild.get_member(ticket["owner_id"]) if ticket else None
        summary = base_embed(
            "🔒 Ticket Closed",
            f"**Ticket:** {channel.name}\n**Opened by:** {owner.mention if owner else (ticket['owner_id'] if ticket else 'Unknown')}\n**Closed by:** {interaction.user.mention}\n**Reason:** {ticket['reason'] if ticket and ticket['reason'] else 'N/A'}",
            config.COLOR_MOD,
            guild=guild,
        )

        cfg = await self._config(guild.id)
        if cfg["log_channel_id"]:
            log_channel = guild.get_channel(cfg["log_channel_id"])
            if log_channel:
                try:
                    await log_channel.send(
                        embed=summary,
                        file=discord.File(fp=io.BytesIO(transcript_file_bytes), filename=f"{channel.name}-transcript.txt"),
                    )
                except discord.HTTPException:
                    pass

        try:
            await interaction.user.send(
                embed=base_embed("Ticket Transcript", f"Transcript for {channel.name}", config.COLOR_PRIMARY),
                file=discord.File(fp=io.BytesIO(transcript_file_bytes), filename=f"{channel.name}-transcript.txt"),
            )
        except discord.HTTPException:
            pass
        await channel.delete(reason=f"Ticket closed by {interaction.user}")

    @commands.hybrid_command(help="Open a ticket (alternative to using the panel button)")
    async def ticket(self, ctx: commands.Context):
        if ctx.interaction:
            await ctx.interaction.response.send_modal(TicketReasonModal())
        else:
            await ctx.send(embed=error_embed("Use the ticket panel button, or run this as a slash command."))

    @commands.hybrid_command(help="Close the current ticket")
    async def closeticket(self, ctx: commands.Context):
        if ctx.interaction:
            await self.close_ticket(ctx.interaction)
        else:
            conn = get_conn()
            cur = await conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (ctx.channel.id,))
            row = await cur.fetchone()
            if not row:
                await ctx.send(embed=error_embed("This isn't a ticket channel."))
                return
            await ctx.send(embed=success_embed("Closing this ticket in 5 seconds…"))
            await conn.execute("UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?", (now(), ctx.channel.id))
            await conn.commit()
            await ctx.channel.delete(delay=5, reason=f"Closed by {ctx.author}")

    @commands.command(help="Add a member to this ticket")
    @checks.can_manage_channels()
    async def adduser(self, ctx: commands.Context, member: discord.Member):
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)
        await ctx.send(embed=success_embed(f"Added **{member}** to this ticket."))

    @commands.command(help="Remove a member from this ticket")
    @checks.can_manage_channels()
    async def removeuser(self, ctx: commands.Context, member: discord.Member):
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(embed=success_embed(f"Removed **{member}** from this ticket."))

    @commands.hybrid_command(help="Generate a transcript of this ticket")
    async def transcript(self, ctx: commands.Context):
        transcript = await self._build_transcript(ctx.channel)
        await ctx.send(
            embed=success_embed("Transcript generated."),
            file=discord.File(fp=io.StringIO(transcript), filename=f"{ctx.channel.name}-transcript.txt"),
        )

    @commands.hybrid_command(help="Claim this ticket")
    async def claim(self, ctx: commands.Context):
        conn = get_conn()
        await conn.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (ctx.author.id, ctx.channel.id))
        await conn.commit()
        await ctx.send(embed=success_embed(f"Ticket claimed by {ctx.author.mention}."))

    @commands.command(help="Rename this ticket channel")
    @checks.can_manage_channels()
    async def rename(self, ctx: commands.Context, *, new_name: str):
        await ctx.channel.edit(name=new_name)
        await ctx.send(embed=success_embed(f"Channel renamed to **{new_name}**."))

    @commands.command(help="Open a new ticket (text command form)")
    async def openticket(self, ctx: commands.Context):
        await ctx.send(embed=error_embed("Please use the ticket panel button to open a ticket."))

    @commands.command(help="Delete this ticket immediately")
    @checks.can_manage_channels()
    async def deleteticket(self, ctx: commands.Context):
        conn = get_conn()
        await conn.execute("UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?", (now(), ctx.channel.id))
        await conn.commit()
        await ctx.send(embed=success_embed("Deleting this ticket…"))
        await ctx.channel.delete(reason=f"Deleted by {ctx.author}")

    @commands.hybrid_command(help="List all currently open tickets in this server")
    @checks.can_manage_channels()
    async def activetickets(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND status = 'open' ORDER BY created_at", (ctx.guild.id,)
        )
        rows = await cur.fetchall()
        if not rows:
            await ctx.send(embed=info_embed("There are no open tickets right now.", "Active Tickets", ctx.prefix, ctx.guild))
            return
        lines = []
        for r in rows:
            claimed = f" • claimed by <@{r['claimed_by']}>" if r["claimed_by"] else ""
            lines.append(f"<#{r['channel_id']}> — opened by <@{r['owner_id']}>{claimed}")
        await ctx.send(embed=base_embed(f"🎫 Active Tickets ({len(rows)})", "\n".join(lines), config.COLOR_PRIMARY, ctx.prefix, ctx.guild))

    @commands.hybrid_command(help="Show ticket statistics for this server")
    @checks.can_manage_guild()
    async def ticketstats(self, ctx: commands.Context):
        conn = get_conn()
        cur = await conn.execute("SELECT status, COUNT(*) as c FROM tickets WHERE guild_id = ? GROUP BY status", (ctx.guild.id,))
        rows = await cur.fetchall()
        counts = {r["status"]: r["c"] for r in rows}
        total = sum(counts.values())
        embed = base_embed(
            "📊 Ticket Stats",
            f"**Total tickets:** {total}\n**Open:** {counts.get('open', 0)}\n**Closed:** {counts.get('closed', 0)}",
            config.COLOR_PRIMARY,
            ctx.prefix,
            ctx.guild,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
