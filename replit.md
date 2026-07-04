# Atlas

Atlas is a full-featured Discord moderation & utility bot covering moderation, administration, utility, fun, information, AutoMod, logging, tickets, giveaways, welcome messages, an economy, and leveling — all via prefix (`,` or `!`, per-guild customizable) and slash commands.

## Run & Operate

- The "Atlas Bot" workflow runs `cd discord-bot && python main.py`
- Required secret: `DISCORD_TOKEN` (bot token from the Discord Developer Portal)
- Data persists in `discord-bot/data/atlas.db` (SQLite, created automatically on first run)
- Restart the workflow after any code change (cogs are loaded once at startup)
- Owner-only commands (`eval`, `sync`, `reload`, `blacklist`, etc.) use the Discord application's owner, resolved automatically at runtime — no config needed

## Stack

- Python 3.11, discord.py (hybrid commands: prefix + slash)
- SQLite via `aiosqlite` for all persistence (guild config, warnings, economy, levels, tickets, giveaways, etc.)
- aiohttp for external API calls (memes, jokes, animal pictures)
- Music/Lavalink is explicitly out of scope for this bot.

## Where things live

- `discord-bot/main.py` — bot entry point, cog loader, prefix resolution, global error handler
- `discord-bot/config.py` — non-secret settings (colors, emojis, XP/economy tuning); token read from env
- `discord-bot/database.py` — SQLite schema + connection helpers
- `discord-bot/utils/` — shared helpers: `embeds.py` (embed builders/progress bars), `checks.py` (permission decorators), `pagination.py` (button-based paginator), `helpers.py` (duration parsing, formatting)
- `discord-bot/cogs/` — one file per command category (moderation, administration, utility, fun, information, automod, logging_cog, tickets, giveaways, welcome, economy, leveling, owner, help)

## Architecture decisions

- **Hybrid command curation for the 100 global slash-command cap.** Discord allows at most 100 global application (slash) commands total, shared across the whole bot — and prefix command names also share one global namespace across all cogs. With 100+ planned commands, only the most commonly-used ~72 are registered as `hybrid_command`/`hybrid_group` (usable as both slash and prefix); the rest are `commands.command` (prefix-only via `,` or `!`, still fully functional, just not in the slash command list).
- Per-guild config (prefix, log channels, automod toggles, welcome/goodbye messages, autorole, etc.) lives in a single `guild_config` table, lazily created on first access.
- Persistent `discord.ui.View`s (ticket panel, ticket controls, giveaway entry, verify button) are re-registered on bot startup via `bot.add_view()` so buttons keep working across restarts.
- Owner-only commands are always plain prefix commands (never slash) to avoid cluttering the public command list and to keep `eval` off of Discord's app command surface.

## Product

- **Moderation**: ban/unban/tempban/softban, kick, timeout/mute, warnings, purge, slowmode, channel lock/hide, nuke, nicknames, roles, voice moderation
- **Administration**: prefix/config management, autorole, reaction roles, embeds/announcements, polls, verification, backups, raid whitelist
- **Utility**: user/server/role/channel info, ping/uptime/botinfo, calculator, reminders, personal todo lists, AFK status
- **Fun**: 8-ball, dice, coinflip, roast/ship/hug-style social commands, trivia, memes/jokes/animal pictures
- **Information**: emoji/role listings, boosts, server icon/banner, permissions lookup
- **AutoMod**: configurable anti-spam, anti-link, anti-invite, anti-caps, anti-hoist, anti-bot, anti-nuke, anti-webhook
- **Logging**: per-event-type log channels (mod actions, joins/leaves, messages, voice, roles, nicknames, server events)
- **Tickets**: button-driven ticket panel, claim/close/rename/transcript, per-ticket permissions
- **Giveaways**: button-based entry, auto-conclusion on a timer, reroll/pause/resume
- **Welcome/Goodbye**: templated messages with placeholders, verification panel
- **Economy**: balance, daily/work rewards, rob, bank deposit/withdraw, shop, leaderboard
- **Leveling**: XP-on-message with cooldown, level-up announcements, level-based role rewards, rank card

## User preferences

_None recorded yet._

## Gotchas

- Discord's 100 global slash-command cap applies to the whole application — if you add new hybrid commands, check the running total (see "Architecture decisions") or the bot will fail to start with `CommandLimitReached`.
- Command names (prefix AND slash) share one global namespace across all cogs — reusing a name in a different cog raises `CommandRegistrationError` at startup, even if one version is hybrid and the other is prefix-only.
- Always restart the "Atlas Bot" workflow after editing any cog — cogs are loaded once at process start.

## Pointers

- See the `pnpm-workspace` skill for the unrelated Node.js artifacts in this monorepo (API server, mockup sandbox) — the Discord bot is a standalone Python app at the repo root, not a pnpm package.
