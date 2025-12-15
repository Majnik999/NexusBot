import discord
import psutil
import time
from discord.ext import commands
from main import PREFIX, logger
from settings import INVITE_LINK, BOT_PROFILE_PICTURE_EMOJI

# ===== HELP DATA =====
HELP_DATA = {
    "fun": {
        "description": "🎲 Fun commands like **MUSIC**, jokes and memes",
        "commands": {
            PREFIX + "joke help": "Tells a random joke",
            PREFIX + "meme <count> <subreddit>": "Sends a random meme",
            PREFIX + "8ball <question>": "Ask the magic 8ball",
            PREFIX + "sudo help": "Play with sudo commands",
            PREFIX + "wordle help": "Play wordle",
            PREFIX + "maze help": "Play maze",
            PREFIX + "eco help": "Economy system",
            PREFIX + "music help": "Music commands",
        }
    },
    "moderation": {
        "description": "🛡️ Kick, ban, mute, etc.",
        "commands": {
            PREFIX + "clear <amount>": "Clear messages",
            PREFIX + "kick <@user>": "Kick a user",
            PREFIX + "ban <@user> <reason>": "Ban a user",
            PREFIX + "mute <@user> <time>": "Mute a user",
            PREFIX + "unmute <@user>": "Unmute a user",
            PREFIX + "unban <@user>": "Unban a user"
        }
    },
    "utility": {
        "description": "🔧 Helpful tools",
        "commands": {
            PREFIX + "profile": "Get profile info",
            PREFIX + "profile pic": "Get profile picture",
            PREFIX + "embed help": "Embed builder help",
            PREFIX + "steam help": "Steam commands",
            PREFIX + "ai help": "AI commands",
        }
    }
}

# ===== HELPERS =====
def format_uptime(seconds: int) -> str:
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")

    return " ".join(parts) or "Just started"

# ===== SELECT MENU =====
class HelpSelect(discord.ui.Select):
    def __init__(self, show_back: bool = False):
        options = []

        if show_back:
            options.append(
                discord.SelectOption(
                    label="⬅️ Go back",
                    description="Return to the main help menu",
                    value="__back"
                )
            )

        options.extend([
            discord.SelectOption(
                label=category.capitalize(),
                description=data["description"],
                value=category
            )
            for category, data in HELP_DATA.items()
        ])

        super().__init__(
            placeholder="📂 Select a help category",
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]

        # ⬅️ BACK TO MAIN MENU
        if value == "__back":
            process = psutil.Process()
            cpu_usage = psutil.cpu_percent(interval=0.3)
            ram_used = process.memory_info().rss / 1024 / 1024
            uptime_seconds = int(time.time() - interaction.client.start_time)

            shard_id = (
                str(interaction.guild.shard_id)
                if interaction.guild and interaction.guild.shard_id is not None
                else "No sharding"
            )

            categories_text = "\n".join(
                f"• **{cat.capitalize()}** – {data['description']}"
                for cat, data in HELP_DATA.items()
            )

            embed = discord.Embed(
                title=f"{BOT_PROFILE_PICTURE_EMOJI} Help Menu",
                description=(
                    "Use the **dropdown menu** below to select a category.\n\n"
                    f"{categories_text}"
                ),
                color=discord.Color.blue()
            )

            embed.add_field(
                name="📊 Runtime Info",
                value=(
                    f"🧠 **CPU:** `{cpu_usage:.1f}%`\n"
                    f"💾 **RAM Used:** `{ram_used:.1f} MB`\n"
                    f"⏱️ **Uptime:** `{format_uptime(uptime_seconds)}`\n"
                    f"🧩 **Shard:** `{shard_id}`"
                ),
                inline=False
            )

            await interaction.response.edit_message(
                embed=embed,
                view=HelpView(show_back=False)
            )
            return

        # 📂 CATEGORY VIEW
        data = HELP_DATA[value]
        commands_text = "\n".join(
            f"`{cmd}` — {desc}"
            for cmd, desc in data["commands"].items()
        )

        embed = discord.Embed(
            title=f"{BOT_PROFILE_PICTURE_EMOJI} {value.capitalize()} Commands",
            description=f"**{data['description']}**\n\n{commands_text}",
            color=discord.Color.green()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=HelpView(show_back=True)
        )

# ===== VIEW =====
class HelpView(discord.ui.View):
    def __init__(self, show_back: bool = False):
        super().__init__(timeout=None)

        self.add_item(HelpSelect(show_back=show_back))

        self.add_item(discord.ui.Button(
            label="Invite Nexus Bot",
            url=INVITE_LINK,
            style=discord.ButtonStyle.link,
            row=1
        ))

        self.add_item(discord.ui.Button(
            label="Website",
            url="https://3002r.vapp.uk/?v=0",
            style=discord.ButtonStyle.link,
            row=1
        ))

        self.add_item(discord.ui.Button(
            label="Support Server",
            url="https://discord.gg/G57EwMhuMR",
            style=discord.ButtonStyle.link,
            row=1
        ))

# ===== COG =====
class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        process = psutil.Process()
        cpu_usage = psutil.cpu_percent(interval=0.3)
        ram_used = process.memory_info().rss / 1024 / 1024
        uptime_seconds = int(time.time() - self.bot.start_time)

        shard_id = (
            str(ctx.guild.shard_id)
            if ctx.guild and ctx.guild.shard_id is not None
            else "No sharding"
        )

        categories_text = "\n".join(
            f"• **{cat.capitalize()}** – {data['description']}"
            for cat, data in HELP_DATA.items()
        )

        embed = discord.Embed(
            title=f"{BOT_PROFILE_PICTURE_EMOJI} Help Menu",
            description=(
                "Use the **dropdown menu** below to select a category.\n\n"
                ""
            ),
            color=discord.Color.blue()
        )

        embed.add_field(
            name=":open_file_folder: Categories",
            value=categories_text,
            inline=False
        )

        embed.add_field(
            name="📊 Runtime Info",
            value=(
                f"🧠 **CPU:** `{cpu_usage:.1f}%`\n"
                f"💾 **RAM Used:** `{ram_used:.1f} MB`\n"
                f"⏱️ **Uptime:** `{format_uptime(uptime_seconds)}`\n"
                f"🧩 **Shard:** `{shard_id}`"
            ),
            inline=False
        )

        await ctx.send(embed=embed, view=HelpView(show_back=False))

# ===== SETUP =====
async def setup(bot):
    await bot.add_cog(HelpCog(bot))