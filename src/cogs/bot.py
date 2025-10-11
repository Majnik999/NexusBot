import json
import asyncio
from typing import List, Optional

import discord
from discord.ext import commands

from settings import QUIT_COMMAND, PREFIX, DEFAULT_ACTIVITY
from src.config.versions import BOT_VERSION as _BOT_VERSION

DEFAULT_ACTIVITY_LOOP_JSON = json.dumps([
    {"type": "playing", "name": "Hello world", "status": "online", "duration": 30},
    {"type": "watching", "name": "the sky", "status": "idle", "duration": 45},
    {"type": "listening", "name": "music", "status": "dnd", "duration": 20}
], indent=2)

def help_one() -> List[discord.Embed]:
    """Generate help embeds for bot and activity commands."""
    embed = discord.Embed(
        title="<:NexusBotprofilepicture:1419717002414653581> Bot | Help",
        description="Manage bot from discord!"
    )
    
    embed.add_field(name=f"{PREFIX}bot help", value="Shows this message!", inline=False)
    embed.add_field(name=f"{PREFIX}bot quit", value="Turns off bot", inline=False)
    embed.add_field(name=f"{PREFIX}bot ping", value="Get bots latency!", inline=False)
    
    embed2 = discord.Embed(
        title="🎮 Activity | Help",
        description="Manage activity and status of bot from discord!"
    )
    
    embed2.add_field(name=f"{PREFIX}activity help", value="Shows this message!", inline=False)
    embed2.add_field(
        name=f"{PREFIX}activity set <type> <input>",
        value="Set bot activity or status. Examples:\n`activity set activity playing Hello world`\n`activity set status idle`",
        inline=False
    )
    embed2.add_field(name=f"{PREFIX}activity reset", value="Reset bot activity to default from settings!", inline=False)
    embed2.add_field(name=f"{PREFIX}activity status", value="Shows current activity status and if loop is running", inline=False)
    embed2.add_field(
        name=f"{PREFIX}activity loop <json>",
        value=(
            f"Start looping activities via JSON. Each item can have:\n"
            f"`type`: playing/watching/listening/competing\n"
            f"`name`: The activity text\n"
            f"`status`: online/idle/dnd/invisible\n"
            f"`duration`: Time in seconds\n"
            f"Example:\n```json\n{DEFAULT_ACTIVITY_LOOP_JSON}\n```\n"
            f"Use `activity stop` to cancel."
        ),
        inline=False
    )
    
    return [embed, embed2]

class OwnerCommands(commands.Cog):
    """Cog for bot owner commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.activity_loop_task: Optional[asyncio.Task] = None
        self._setup_default_activity()
    
    def _setup_default_activity(self) -> None:
        """Set up default activity loop if configured."""
        if not DEFAULT_ACTIVITY:
            return
            
        try:
            da = json.loads(DEFAULT_ACTIVITY) if isinstance(DEFAULT_ACTIVITY, str) else DEFAULT_ACTIVITY
            if "loop" in da:
                self.activity_loop_task = self.bot.loop.create_task(self._run_activity_loop(da["loop"]))
        except Exception:
            pass

    @commands.group(name="bot", invoke_without_command=True, hidden=True)
    @commands.is_owner()
    async def botgroup(self, ctx):
        await ctx.send(embeds=help_one())
    
    # Creating command quit
    @botgroup.command(name="quit", description="Turns off bot.", hidden=True)
    @commands.is_owner()
    async def quiting(self, ctx):
        if not QUIT_COMMAND: return
        await ctx.send("Bot is turning off please wait...")
        await self.bot.close()
    
    @quiting.error
    async def handle_error_quitting(self, ctx, _error):
        await ctx.send("❌ You are not owner or some error happened!")
    @botgroup.command(name="ping", hidden=True)
    @commands.is_owner()
    async def botping(self, ctx):
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds and round
        
        await ctx.send(f"Pong! Bot latency: `{latency}ms`!")
    
    @botping.error
    async def handle_error_botping(self, ctx, _error):
        await ctx.send("❌ You are not owner or some error happened!")
    # Activity management (owner only)
    @commands.group(name="activity", invoke_without_command=True, hidden=True)
    @commands.is_owner()
    async def activity(self, ctx):
        await ctx.send(embed=help_one()[1])

    @activity.command(name="set", hidden=True)
    @commands.is_owner()
    async def activity_set(self, ctx, setting_type: str, *, content: str = None):
        try:
            if setting_type.lower() == "status":
                states = {
                    "online": discord.Status.online,
                    "idle": discord.Status.idle,
                    "dnd": discord.Status.do_not_disturb,
                    "invisible": discord.Status.invisible
                }
                state = states.get(content.lower())
                if state is None:
                    await ctx.send("❌ Unknown status. Use one of: online, idle, dnd, invisible.")
                    return
                # Keep current activity when changing status
                current_activity = self.bot.activity
                await self.bot.change_presence(status=state, activity=current_activity)
                await ctx.send(f"✅ Status set to `{content}`")
                return

            # Handle activity setting
            parts = content.split() if content else []
            atype_str = parts[0].lower() if parts else "playing"
            name = " ".join(parts[1:]) if len(parts) > 1 else " ".join(parts)

            if atype_str not in ("playing", "listening", "watching", "competing"):
                name = content
                atype_str = "playing"

            atype_map = {
                "playing": discord.ActivityType.playing,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing
            }
            
            # Keep current status when changing activity
            current_status = self.bot.status or discord.Status.online
            activity = discord.Activity(type=atype_map[atype_str], name=name)
            await self.bot.change_presence(status=current_status, activity=activity)
            await ctx.send(f"✅ Activity set: `{atype_str}` {name}")

        except Exception as e:
            await ctx.send(f"❌ Error setting activity: {str(e)}")

    @activity.command(name="reset", hidden=True)
    @commands.is_owner()
    async def activity_reset(self, ctx):
        try:
            # Cancel any existing loop
            if self.activity_loop_task and not self.activity_loop_task.done():
                self.activity_loop_task.cancel()
                self.activity_loop_task = None

            if not DEFAULT_ACTIVITY:
                await self.bot.change_presence(activity=None, status=discord.Status.online)
                if ctx:
                    await ctx.send("✅ Activity reset to none.")
                return

            # Handle string or dict/list DEFAULT_ACTIVITY
            da = json.loads(DEFAULT_ACTIVITY) if isinstance(DEFAULT_ACTIVITY, str) else DEFAULT_ACTIVITY

            # Check if default activity includes a loop configuration
            if isinstance(da, dict) and "loop" in da:
                self.activity_loop_task = self.bot.loop.create_task(self._run_activity_loop(da["loop"]))
                if ctx:
                    await ctx.send("✅ Default activity loop started.")
                return

            # Handle list configuration (treat as loop)
            if isinstance(da, list):
                self.activity_loop_task = self.bot.loop.create_task(self._run_activity_loop(da))
                if ctx:
                    await ctx.send("✅ Default activity loop started.")
                return

            # Handle single activity setting
            status_str = da.get("status", "online")
            name = da.get("name", "")
            type_str = da.get("type", "playing")

            status_map = {
                "online": discord.Status.online,
                "idle": discord.Status.idle,
                "dnd": discord.Status.do_not_disturb,
                "invisible": discord.Status.invisible
            }
            atype_map = {
                "playing": discord.ActivityType.playing,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing
            }

            status = status_map.get(status_str.lower(), discord.Status.online)
            atype = atype_map.get(type_str.lower(), discord.ActivityType.playing)
            activity = discord.Activity(type=atype, name=name) if name else None

            await self.bot.change_presence(status=status, activity=activity)
            if ctx:
                await ctx.send("✅ Activity reset to default from settings.")

        except Exception as e:
            if ctx:
                await ctx.send(f"❌ Error resetting activity: {str(e)}")
            else:
                print(f"Error resetting activity: {str(e)}")

    async def _reset_presence(self):
        """Reset presence without requiring context."""
        try:
            await self.bot.change_presence(activity=None, status=discord.Status.online)
        except Exception as e:
            print(f"Error resetting presence: {str(e)}")

    @activity.command(name="loop", hidden=True)
    @commands.is_owner()
    async def activity_loop(self, ctx, *, json_input: str = None):
        try:
            # If no JSON provided, show the default example
            if not json_input:
                await ctx.send(f"Example JSON format:\n```json\n{DEFAULT_ACTIVITY_LOOP_JSON}\n```")
                return
            
            data = json.loads(json_input)
            if not isinstance(data, list) or not data:
                await ctx.send("❌ JSON must be a non-empty list of activity objects.")
                return

            for item in data:
                if not isinstance(item, dict) or "name" not in item or "duration" not in item:
                    await ctx.send("❌ Each item must have 'name' and 'duration' fields.")
                    return

            if self.activity_loop_task and not self.activity_loop_task.done():
                self.activity_loop_task.cancel()
            
            self.activity_loop_task = self.bot.loop.create_task(self._run_activity_loop(data))
            await ctx.send("✅ Activity loop started.")
            
        except json.JSONDecodeError:
            await ctx.send("❌ Invalid JSON format.")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

    @activity.command(name="stop", hidden=True)
    @commands.is_owner()
    async def activity_stop(self, ctx):
        if self.activity_loop_task and not self.activity_loop_task.done():
            self.activity_loop_task.cancel()
            self.activity_loop_task = None
            await ctx.send("✅ Activity loop stopped.")
        else:
            await ctx.send("ℹ️ No active activity loop.")

    @activity.command(name="status", hidden=True)
    @commands.is_owner()
    async def activity_status(self, ctx):
        try:
            current_activity = self.bot.activity
            current_status = self.bot.status or discord.Status.online
            loop_active = self.activity_loop_task and not self.activity_loop_task.done()
            
            status_msg = f"Status: `{current_status}`\n"
            if current_activity:
                status_msg += f"Activity: `{current_activity.type.name}` {current_activity.name}\n"
            else:
                status_msg += "Activity: None\n"
                
            status_msg += f"Loop active: `{'Yes' if loop_active else 'No'}`"
            
            await ctx.send(status_msg)
        except Exception as e:
            await ctx.send(f"❌ Error getting status: {str(e)}")

    async def _run_activity_loop(self, activities: List[dict]) -> None:
        """Run the activity loop with the given activities."""
        atype_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing
        }
        
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.do_not_disturb,
            "invisible": discord.Status.invisible
        }
        
        try:
            while True:
                for item in activities:
                    activity = discord.Activity(
                        type=atype_map.get(item.get("type", "playing").lower(), discord.ActivityType.playing),
                        name=item.get("name", "")
                    )
                    status = status_map.get(item.get("status", "online").lower(), discord.Status.online)
                    await self.bot.change_presence(status=status, activity=activity)
                    await asyncio.sleep(float(item.get("duration", 30)))
                    
        except asyncio.CancelledError:
            await self._reset_presence()

    async def cog_error(self, ctx: commands.Context, error: Exception) -> None:
        """Global error handler for all commands in this cog."""
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ This command is only for the bot owner.")
        else:
            await ctx.send(f"❌ An error occurred: {str(error)}")

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(OwnerCommands(bot))