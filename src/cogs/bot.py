import discord
from discord.ext import commands
from settings import QUIT_COMMAND, PREFIX, DEFAULT_ACTIVITY
from src.config.versions import BOT_VERSION as _BOT_VERSION

import json
import asyncio

# Default JSON example for activity loop (copy-paste ready)
DEFAULT_ACTIVITY_LOOP_JSON = json.dumps([
    {"type": "playing", "name": "Hello world", "duration": 30},
    {"type": "watching", "name": "the sky", "duration": 45},
    {"type": "listening", "name": "music", "duration": 20}
], indent=2)

def help_one():
    embed = discord.Embed(
        title="<:NexusBotprofilepicture:1419717002414653581> Bot | Help",
        description=f"Manage bot from discord!"
    )
    
    embed.add_field(name=PREFIX+"bot help", value=f"Shows this message!", inline=False)
    embed.add_field(name=PREFIX+"bot quit", value=f"Turns off bot", inline=False)
    embed.add_field(name=PREFIX+"bot ping", value=f"Get bots latency!", inline=False)
    #embed.add_field(name=PREFIX+"", value=f"", inline=False)
    #embed.add_field(name=PREFIX+"", value=f"", inline=False)
    #embed.add_field(name=PREFIX+"", value=f"", inline=False)
    
    embed2 = discord.Embed(
        title="🎮 Activity | Help",
        description=f"Manage activity of bot from discord!"
    )
    
    embed2.add_field(name=PREFIX+"activity help", value=f"Shows this message!", inline=False)
    embed2.add_field(name=PREFIX+"activity set <type> <input>", value=f"Set bot activity or status. Examples: `activity set activity playing Hello world`, `activity set status idle`", inline=False)
    embed2.add_field(name=PREFIX+"activity reset", value=f"Reset bot activity to default from settings!", inline=False)
    embed2.add_field(
        name=PREFIX+"activity loop <json>",
        value=f"Start looping activities via JSON. Example (copy & paste):\n```json\n{DEFAULT_ACTIVITY_LOOP_JSON}\n```\nUse `activity stop` to cancel.",
        inline=False
    )
    
    
    #embed3 = discord.Embed(
    #    title="🔧 Config | Help",
    #    description=f"Manage configuration from discord!"
    #)
    
    return [embed, embed2]

class OwnerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # task to hold background loop if started
        self.activity_loop_task = None

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
    @quiting.error
    async def handle_error_quitting(self, ctx, _error):
        await ctx.send("❌ You are not owner or some error happened!")
    @botgroup.command(name="ping", hidden=True)
    @commands.is_owner()
    async def botping(self, ctx):
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds and round
        
        await ctx.send(f"Pong! Bot latency: `{latency}ms`!")
    
    @botping.error
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
    async def activity_set(self, ctx, _type: str, *, content: str):
        typ = _type.lower()
        if typ == "status":
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
            await self.bot.change_presence(status=state)
            await ctx.send(f"✅ Status set to `{content}`")
            return

        if typ == "activity":
            parts = content.split()
            atype_str = parts[0].lower()
            if atype_str not in ("playing", "listening", "watching", "competing"):
                atype_str = "playing"
                name = content
            else:
                name = " ".join(parts[1:])
            
            atype_map = {
                "playing": discord.ActivityType.playing,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing
            }
            activity = discord.Activity(type=atype_map[atype_str], name=name)
            await self.bot.change_presence(activity=activity)
            await ctx.send(f"✅ Activity set: `{atype_str}` {name}")
            return

        await ctx.send("❌ Unknown type. Use `activity` or `status`.")

    @activity.command(name="reset", hidden=True)
    @commands.is_owner()
    async def activity_reset(self, ctx):
        try:
            # Try to parse DEFAULT_ACTIVITY as JSON if it's a string
            da = json.loads(DEFAULT_ACTIVITY) if isinstance(DEFAULT_ACTIVITY, str) else DEFAULT_ACTIVITY
            
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
            await ctx.send("✅ Activity reset to default from settings.")
        except json.JSONDecodeError:
            await ctx.send("❌ Failed to parse default activity settings.")
        except Exception as e:
            await ctx.send(f"❌ Error resetting activity: {str(e)}")

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

    async def _run_activity_loop(self, activities):
        atype_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing
        }
        
        try:
            while True:
                for item in activities:
                    typ = item.get("type", "playing").lower()
                    name = item.get("name", "")
                    duration = float(item.get("duration", 30))
                    
                    activity = discord.Activity(type=atype_map.get(typ, discord.ActivityType.playing), name=name)
                    await self.bot.change_presence(activity=activity)
                    await asyncio.sleep(duration)
                    
        except asyncio.CancelledError:
            # Reset to default activity
            await self.activity_reset(None)

    @activity.error
    @activity_set.error
    @activity_reset.error
    @activity_loop.error
    @activity_stop.error
    async def activity_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ This command is only for the bot owner.")
        else:
            await ctx.send(f"❌ An error occurred: {str(error)}")

async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))