# Atlas

Atlas is a full-featured Discord moderation & utility bot covering moderation, administration, utility, fun, information, AutoMod, logging, tickets, giveaways, welcome messages, an economy, and leveling — all via prefix (`,` or `!`, per-guild customizable) and slash commands.

## Run & Operate

- **The bot is actually hosted and run on Railway, not in this Replit workspace.** The local "Atlas Bot" workflow (`cd discord-bot && python main.py`) is for reference/editing only — it will fail here with `DISCORD_TOKEN is not set`, and that's expected since Railway holds the real token. Ship changes by pushing/syncing this code to the Railway deployment; don't chase the local workflow's token error.
- Data persists in `discord-bot/data/atlas.db` (SQLite, created automatically on first run) — on Railway this needs a persistent volume or the DB resets on redeploy.
- Cogs are loaded once at process start — the Railway service needs a redeploy/restart after any code change.
- Owner-only commands (`eval`, `sync`, `reload`, `blacklist`, etc.) are restricted to a single hardcoded Discord user ID (`config.OWNER_ID`), not the Discord application's resolved owner. The Owner category is also hidden from `,help`/`/help` for everyone else.

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
- `discord-bot/cogs/` — one file per command category (moderation, administration, utility, fun, information, automod, logging_cog, tickets, giveaways, welcome, economy, leveling, owner, help, servertools)

## Architecture decisions

- **Hybrid command curation for the 100 global slash-command cap.** Discord allows at most 100 global application (slash) commands total, shared across the whole bot — and prefix command names also share one global namespace across all cogs. With 100+ planned commands, only the most commonly-used ~72 are registered as `hybrid_command`/`hybrid_group` (usable as both slash and prefix); the rest are `commands.command` (prefix-only via `,` or `!`, still fully functional, just not in the slash command list).
- Per-guild config (prefix, log channels, automod toggles, welcome/goodbye messages, autorole, etc.) lives in a single `guild_config` table, lazily created on first access.
- Persistent `discord.ui.View`s (ticket panel, ticket controls, giveaway entry, verify button) are re-registered on bot startup via `bot.add_view()` so buttons keep working across restarts.
- Owner-only commands are always plain prefix commands (never slash) to avoid cluttering the public command list and to keep `eval` off of Discord's app command surface.
- Bot presence rotates on a `tasks.loop` (every 20s) through several `discord.Activity`/`discord.Game` statuses with live member/server counts, instead of a single static presence set once in `on_ready`.
- New guild joins trigger an automatic welcome/intro embed via `on_guild_join` in `main.py`, posted to the system channel (falls back to the first channel the bot can post in).
- Per-guild language preference lives as a `language` column on `guild_config` (default `'en'`), set via `,language`. Since the table is created with `CREATE TABLE IF NOT EXISTS`, new columns added later require an `ALTER TABLE ... ADD COLUMN` migration guarded in a try/except inside `init_db()` — existing databases won't pick up new columns otherwise.

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
- **Server Tools** (`cogs/servertools.py`, all prefix-only): channel/category/voice-channel CRUD, role CRUD (color/hoist/mentionable/position), advanced purge filters (by user/bot/human/images/links/embeds/contains-text), warning count & bulk-clear, ban list, snipe/editsnipe (in-memory last deleted/edited message per channel), emoji & sticker & webhook management, invite list, member search, avatar/banner/icon direct URLs, per-channel permission lookup

## User preferences

_None recorded yet._

## Gotchas

- Discord's 100 global slash-command cap applies to the whole application — if you add new hybrid commands, check the running total (see "Architecture decisions") or the bot will fail to start with `CommandLimitReached`. As of the last count: ~76 hybrid (slash+prefix) commands, ~261 total commands (the rest prefix-only) — still headroom before hitting the cap, but check before adding more hybrids.
- Command names (prefix AND slash) share one global namespace across all cogs — reusing a name in a different cog raises `CommandRegistrationError` at startup, even if one version is hybrid and the other is prefix-only. Always grep `cogs/` for a command name before adding it.
- Snipe/editsnipe state (`cogs/servertools.py`) is in-memory only (a dict keyed by channel ID) — it resets on every restart/redeploy and isn't persisted to SQLite, by design (it's meant to be ephemeral, like most bots' snipe features).
- This repo is edited here but actually deployed on Railway (see "Run & Operate") — the local workflow failing on a missing token is expected, not a bug to fix.

## Pointers

- See the `pnpm-workspace` skill for the unrelated Node.js artifacts in this monorepo (API server, mockup sandbox) — the Discord bot is a standalone Python app at the repo root, not a pnpm package.
