"""
Central configuration for Atlas.
Non-secret settings live here. The Discord token is read from the environment.
"""

import os

# --- Core ---
TOKEN = os.environ.get("DISCORD_TOKEN", "")
BOT_NAME = "Atlas"
DEFAULT_PREFIXES = [",", "!"]
OWNER_IDS: list[int] = []  # populated at runtime from application.owner if empty

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "atlas.db")

# --- Embed colors (Discord-native palette) ---
COLOR_PRIMARY = 0x5865F2   # blurple
COLOR_SUCCESS = 0x57F287   # green
COLOR_ERROR = 0xED4245     # red
COLOR_WARNING = 0xFEE75C   # yellow
COLOR_INFO = 0x5865F2
COLOR_MOD = 0xEB459E       # fuchsia

# --- Emojis (rounded / clean style) ---
EMOJI_SUCCESS = "✅"
EMOJI_ERROR = "❌"
EMOJI_WARNING = "⚠️"
EMOJI_INFO = "ℹ️"
EMOJI_LOADING = "⏳"
EMOJI_MOD = "🛡️"
EMOJI_ARROW = "➜"
EMOJI_BULLET = "▸"

# --- Misc ---
SUPPORT_URL = "https://discord.com"
GITHUB_URL = "https://github.com"
WEBSITE_URL = "https://discord.com"

# XP / Leveling
XP_MIN_PER_MESSAGE = 15
XP_MAX_PER_MESSAGE = 25
XP_COOLDOWN_SECONDS = 60

# Economy
DAILY_AMOUNT = 250
WORK_MIN = 50
WORK_MAX = 200
STARTING_BALANCE = 500
