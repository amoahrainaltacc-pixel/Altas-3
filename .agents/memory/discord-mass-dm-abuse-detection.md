---
name: Discord mass-DM abuse detection
description: Why a bot's "message all users" / broadcast DM feature can get it blocked from being added to new servers, and how to throttle it safely.
---

Sending DMs to many users quickly (e.g. an owner-only broadcast command that DMs every member across every guild) is not just a normal per-route 429 — `discord.py`'s HTTP client already auto-handles standard rate-limit buckets internally. Users reporting the bot got "canceled" / "can't be added to guilds" after a mass-DM run are describing Discord's Trust & Safety spam/abuse detection kicking in, which can throttle or disable a bot's ability to be invited to new servers.

**Why:** Discord treats fast, unsolicited bulk DMs as spam-like behavior regardless of whether the sender respects individual rate-limit headers. This is a platform-level abuse heuristic, not a bug in the bot's rate-limit handling.

**How to apply:** Any mass-DM/broadcast feature should:
- Send one DM at a time with a real delay (~2-3s) between each, plus a longer periodic breather every ~20 messages.
- Treat repeated 429 responses (e.g. 3 in a row) as a signal to abort the whole run early rather than push through with retries.
- Catch `discord.Forbidden` (closed DMs) separately and skip instantly — don't burn delay time on users who can't be reached anyway.
- Warn the operator in the UI that this is intentionally slow, and that repeated large broadcasts risk the platform-level restriction, not just failed sends.

See Atlas's `discord-bot/cogs/owner.py` (`BroadcastConfirmView._safe_broadcast`) for a reference implementation of this throttling pattern.
