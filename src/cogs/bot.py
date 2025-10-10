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
        # show activity help embed (second embed from help_one)
        await ctx.send(embed=help_one()[1])

    @activity.command(name="set", hidden=True)
    @commands.is_owner()
    async def activity_set(self, ctx, _type: str, *, content: str):
        """
        Usage examples:
            activity set status idle
            activity set activity playing Hello world
            activity set activity listening Music
        """
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
            atype_str = parts[0].lower() if parts and parts[0].lower() in ("playing","listening","watching","competing") else "playing"
            name = " ".join(parts[1:]) if atype_str != "playing" and len(parts) > 1 else content
            atype_map = {
                "playing": discord.ActivityType.playing,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing
            }
            atype = atype_map.get(atype_str, discord.ActivityType.playing)
            activity = discord.Activity(type=atype, name=name)
            await self.bot.change_presence(activity=activity)
            await ctx.send(f"✅ Activity set: `{atype_str}` {name}")
            return

        await ctx.send("❌ Unknown type. Use `activity` or `status`.")

    @activity.command(name="reset", hidden=True)
    @commands.is_owner()
    async def activity_reset(self, ctx):
        # DEFAULT_ACTIVITY expected to be a dict like:
        # {"type": "playing", "name": "Hello", "status": "online"}
        da = DEFAULT_ACTIVITY if isinstance(DEFAULT_ACTIVITY, dict) else {}
        status_str = da.get("status", "online")
        name = da.get("name", "")
        type_str = da.get("type", "playing")
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.do_not_disturb,
            "invisible": discord.Status.invisible
        }
        status = status_map.get(status_str.lower(), discord.Status.online)
        atype_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing
        }
        atype = atype_map.get(type_str.lower(), discord.ActivityType.playing)
        activity = discord.Activity(type=atype, name=name) if name else None
        await self.bot.change_presence(status=status, activity=activity)
        await ctx.send("✅ Activity reset to default from settings.")

    @activity.command(name="loop", hidden=True)
    @commands.is_owner()
    async def activity_loop(self, ctx, *, json_input: str):
        """
        Starts looping activities. json_input should be a JSON array of items:
        [{"type":"playing","name":"Hello","duration":30}, ...]
        Supported types: playing, listening, watching, competing
        Duration in seconds required for each item.
        """
        try:
            data = json.loads(json_input)
            if not isinstance(data, list) or not data:
                await ctx.send("❌ JSON must be a non-empty list of activity objects.")
                return
            # validate entries
            for item in data:
                if not isinstance(item, dict) or "name" not in item or "duration" not in item:
                    await ctx.send("❌ Each item must be an object with at least 'name' and 'duration' fields.")
                    return
        except Exception as e:
            await ctx.send(f"❌ Failed to parse JSON: {e}")
            return

        # cancel existing task if running
        # cancel existing task if running
        if self.activity_loop_task and not self.activity_loop_task.done():
            self.activity_loop_task.cancel()
            try:
                await self.activity_loop_task
            except:
                pass

        self.activity_loop_task = asyncio.create_task(self._run_activity_loop(data))
        await ctx.send("✅ Activity loop started.")
    @activity.command(name="stop", hidden=True)
    @commands.is_owner()
    async def activity_stop(self, ctx):
        if self.activity_loop_task and not self.activity_loop_task.done():
            self.activity_loop_task.cancel()
            try:
                await self.activity_loop_task
            except:
                pass
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
                        atype = atype_map.get(typ, discord.ActivityType.playing)
                        activity = discord.Activity(type=atype, name=name) if name else None
                        await self.bot.change_presence(activity=activity)
                        await asyncio.sleep(max(1.0, duration))
            except asyncio.CancelledError:
                # optionally reset to default on cancellation
                da = DEFAULT_ACTIVITY if isinstance(DEFAULT_ACTIVITY, dict) else {}
                status_str = da.get("status", "online")
                name = da.get("name", "")
                type_str = da.get("type", "playing")
                status_map = {
                    "online": discord.Status.online,
                    "idle": discord.Status.idle,
                    "dnd": discord.Status.do_not_disturb,
                    "invisible": discord.Status.invisible
                }
                status = status_map.get(status_str.lower(), discord.Status.online)
                atype_map = {
                    "playing": discord.ActivityType.playing,
                    "listening": discord.ActivityType.listening,
                    "watching": discord.ActivityType.watching,
                    "competing": discord.ActivityType.competing
                }
                atype = atype_map.get(type_str.lower(), discord.ActivityType.playing)
                activity = discord.Activity(type=atype, name=name) if name else None
                await self.bot.change_presence(status=status, activity=activity)
                return
    @activity_set.error
    @activity_set.error
    @activity_reset.error
    @activity_loop.error
    @activity_stop.error
    async def activity_error(self, ctx, _error):
        await ctx.send("❌ You are not owner or some error happened!")
    # add servers listing (owner-only)
    @botgroup.command(name="servers", hidden=True)
    @commands.is_owner()
    async def servers(self, ctx):
        """Shows all servers the bot is in with pagination and invite links"""
        # Sort guilds by member count
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        if not guilds:
            await ctx.send("Bot is not in any servers.")
            return

        # Create entries list
        entries = []
        for guild in guilds:
            invite_url = "No invite available"
            # Try to create invite from text channels
            for channel in guild.text_channels:
                try:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        invite = await channel.create_invite(max_age=0)
                        invite_url = invite.url
                        break
                except:
                    continue

            entry = {
                "name": guild.name,
                "id": guild.id, 
                "members": guild.member_count,
                "owner_id": guild.owner_id,
                "invite": invite_url
            }
            entries.append(entry)

        # Pagination setup
        per_page = 10
        pages = [entries[i:i+per_page] for i in range(0, len(entries), per_page)]

        # Create embed
        def create_embed(page_num):
            embed = discord.Embed(
                title=f"Servers ({len(entries)} total)",
                description=f"Page {page_num+1}/{len(pages)}",
                color=discord.Color.blue()
            )
            
            for i, guild in enumerate(pages[page_num], start=1 + page_num*per_page):
                embed.add_field(
                    name=f"{i}. {guild['name']}", 
                    value=f"ID: `{guild['id']}`\nMembers: `{guild['members']}`\nOwner ID: `{guild['owner_id']}`\nInvite: {guild['invite']}",
                    inline=False
                )
            return embed

        # Create view with buttons
        class Buttons(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.page = 0

            @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
            async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != ctx.author:
                    return
                self.page = (self.page - 1) % len(pages)
                await interaction.response.edit_message(embed=create_embed(self.page))

            @discord.ui.button(label="▶", style=discord.ButtonStyle.primary) 
            async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != ctx.author:
                    return
                self.page = (self.page + 1) % len(pages)
                await interaction.response.edit_message(embed=create_embed(self.page))

            @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
            async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != ctx.author:
                    return
                await interaction.message.delete()

        view = Buttons()
        await ctx.send(embed=create_embed(0), view=view)

async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))