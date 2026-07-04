---
name: Discord bot command namespace limits
description: Constraints on discord.py hybrid/slash commands that cause startup crashes if ignored — relevant any time a bot has 80+ planned commands across multiple cogs.
---

Discord enforces two constraints that are easy to miss when scaffolding a large multi-cog bot:

1. **100 global slash (application) command cap.** This is a hard limit for the whole bot application, not per guild and not per cog. If the sum of all `commands.hybrid_command`/`hybrid_group` (and any plain slash commands) across every loaded cog exceeds 100, the bot crashes on startup with `discord.app_commands.errors.CommandLimitReached`, and every cog loaded after the one that pushed it over 100 also fails to load (cascading failures that look unrelated).
2. **One shared name namespace for ALL commands, prefix or slash.** `commands.Bot` keeps a single flat command registry. Two different cogs defining a command with the same name — even if one is `commands.command` (prefix-only) and the other is `commands.hybrid_command` — raises `discord.ext.commands.errors.CommandRegistrationError` at cog load time, regardless of the slash-command cap.

**Why:** these failures surface as generic extension-load tracebacks that don't obviously point to "too many hybrid commands" or "duplicate name in a different file," so they're easy to misdiagnose as unrelated bugs.

**How to apply:** when a bot spec calls for 100+ total commands, only promote the most commonly-used subset (roughly 70-75, to leave safe margin) to `hybrid_command`/`hybrid_group`; register the rest as plain `commands.command`/`commands.group` (still fully usable via prefix, just absent from the slash-command list). Before adding a new hybrid command, grep the whole `cogs/` directory for the exact command name to check for collisions across cogs — name collisions are checked against ALL commands, not just hybrid ones.
