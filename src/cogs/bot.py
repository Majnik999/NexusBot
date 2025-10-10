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
        """
        Shows all servers the bot is on in pages of 10. Owner-only.
        """
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        if not guilds:
            await ctx.send("ℹ️ Bot is not in any servers.")
            return

        # gather info (attempt to build invite for each guild if possible)
        entries = []
        for g in guilds:
            info = {
                "name": g.name,
                "id": g.id,
                "members": g.member_count,
                "owner_id": getattr(g.owner_id, "__int__", lambda: g.owner_id)() if hasattr(g, "owner_id") else None,
                "invite": "No invite / missing perms"
            }
            # try to find a text channel where bot can create invites
            try:
                ch = next((c for c in g.text_channels if c.permissions_for(g.me).create_instant_invite), None)
                if ch:
                    inv = await ch.create_invite(max_age=0, max_uses=0, unique=False)
                    info["invite"] = str(inv)
            except Exception:
                # keep default "No invite / missing perms"
                pass
            entries.append(info)

        # pagination
        per_page = 10
        pages = [entries[i:i+per_page] for i in range(0, len(entries), per_page)]
        current = 0

        def make_embed(page_index: int):
            emb = discord.Embed(
                title=f"Servers ({len(entries)})",
                description=f"Page {page_index+1}/{len(pages)} — Showing {len(pages[page_index])} server(s)",
                color=discord.Color.blurple()
            )
            for idx, e in enumerate(pages[page_index], start=1 + page_index*per_page):
                name_line = f"{idx}. {e['name']}"
                value = f"ID: `{e['id']}`\nMembers: `{e['members']}`\nOwner ID: `{e.get('owner_id')}`\nInvite: {e['invite']}"
                emb.add_field(name=name_line, value=value, inline=False)
            emb.set_footer(text=f"Requested by {ctx.author} • Use ◀️ ▶️ to navigate, ⏹️ to stop")
            return emb

        # create view-based pager with buttons
        class ServerListView(discord.ui.View):
            def __init__(self, author_id, pages, make_embed, timeout=120.0):
                super().__init__(timeout=timeout)
                self.author_id = author_id
                self.pages = pages
                self.make_embed = make_embed
                self.current = 0
                self.message = None

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("❌ You are not allowed to use these controls.", ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
            @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
            async def previous(self, _button: discord.ui.Button, interaction: discord.Interaction):
                self.current = (self.current - 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.make_embed(self.current), view=self)
            @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
            @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
            async def next(self, _button: discord.ui.Button, interaction: discord.Interaction):
                self.current = (self.current + 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.make_embed(self.current), view=self)
            @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger)
            @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger)
            async def stop(self, _button: discord.ui.Button, interaction: discord.Interaction):
                for child in self.children:
                    child.disabled = True
                try:
                    await interaction.response.edit_message(view=self)
                except Exception:
                    pass
                self.stop()
            @discord.ui.button(label="Why are you sometimes dum", style=discord.ButtonStyle.primary)
            @discord.ui.button(label="Why are you sometimes dum", style=discord.ButtonStyle.primary)
            async def why(self, _button: discord.ui.Button, interaction: discord.Interaction):
                # playful owner-only explanation; ephemeral so only owner sees it
                await interaction.response.send_message("I'm a bot — sometimes I do weird things due to rate limits, missing intents/permissions, or edge cases in code. If something's broken, please report with logs.", ephemeral=True)
            async def on_timeout(self):
                # disable buttons on timeout and update message embed footer
                for child in self.children:
                    child.disabled = True
                try:
                    emb = self.make_embed(self.current)
                    emb.set_footer(text="Session timed out")
                    if self.message:
                        await self.message.edit(embed=emb, view=self)
                except Exception:
                    pass

        view = ServerListView(ctx.author.id, pages, make_embed)
        msg = await ctx.send(embed=make_embed(current), view=view)
        view.message = msg

async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))