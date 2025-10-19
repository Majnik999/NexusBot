import discord
from discord import app_commands
from discord.ext import commands, tasks
import wavelink
import typing
from main import logger 
from settings import LAVALINK_URI, LAVALINK_PASSWORD, PREFIX
import asyncio
import time
import re
import urllib.parse as _urlparse

# --- 1. Custom Player Class ---
class CustomPlayer(wavelink.Player):
    """A custom Wavelink Player that tracks the control panel message, queue, and repeat state."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text_channel: typing.Optional[discord.TextChannel] = None
        self.panel_message: typing.Optional[discord.Message] = None
        self.repeat_track: bool = False 


# --- Helper Select Menu for Volume ---
class VolumeSelect(discord.ui.Select):
    """Dropdown menu for volume control (5% to 100%)."""
    def __init__(self, cog: 'Music'):
        self.cog = cog
        
        options = [
            discord.SelectOption(label=f"{i}%", value=str(i)) 
            for i in range(5, 101, 5)
        ]

        super().__init__(
            placeholder="Select Volume",
            options=options,
            custom_id="music:volume_select"
        )

    async def callback(self, interaction: discord.Interaction):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return await interaction.response.defer() 
        
        try:
            new_volume = int(self.values[0])
            await vc.set_volume(new_volume)
            # Use the interaction to immediately update the view
            await self.cog.update_panel_message(vc, interaction=interaction)
            
        except wavelink.LavalinkException:
            # Stop the player and notify the user if Lavalink connection is lost
            try:
                await vc.stop()
                await vc.disconnect()
                if vc.panel_message:
                    try: await vc.panel_message.delete()
                    except: pass
                    vc.panel_message = None
                await interaction.response.send_message("Lost connection to music server. Stopping playback.", ephemeral=True)
            except Exception:
                await interaction.response.send_message("An error occurred with the music player.", ephemeral=True)
            return
            
        except ValueError:
            await interaction.response.send_message("Invalid volume selection.", ephemeral=True)
            
        if not interaction.response.is_done():
            await interaction.response.defer() 

# --- 2. Panel Buttons (View) ---
class MusicPanel(discord.ui.View):
    """The persistent view for the music control panel."""
    def __init__(self, cog: 'Music'):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(VolumeSelect(cog))

    async def _update_panel(self, interaction: discord.Interaction, vc: 'CustomPlayer'):
        """Helper to update the panel after any button interaction."""
        await self.cog.update_panel_message(vc, interaction=interaction)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.red, custom_id='music:stop_disconnect', row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.disconnect_logic(interaction)

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.secondary, custom_id='music:skip', row=1)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return 
        
        await interaction.response.defer() 
        await self.cog.skip_logic(interaction)

    @discord.ui.button(label='Pause/Resume', style=discord.ButtonStyle.green, custom_id='music:pause_resume', row=1)
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return
        
        await self.cog.pause_resume_logic(interaction) 
        await self._update_panel(interaction, vc) 
        
    @discord.ui.button(label='Repeat', style=discord.ButtonStyle.gray, custom_id='music:repeat_toggle', row=1)
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return
        
        vc.repeat_track = not vc.repeat_track
        button.style = discord.ButtonStyle.green if vc.repeat_track else discord.ButtonStyle.gray
        await self._update_panel(interaction, vc) 

    @discord.ui.button(label='Refresh 🔄', style=discord.ButtonStyle.grey, custom_id='music:refresh_panel', row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return
        
        await self._update_panel(interaction, vc)


# --- 3. Main Music Cog ---
class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.panel_view = MusicPanel(self) # This is the single, persistent instance!
        # Lavalink monitor state
        self._lavalink_online: bool = True
        self._last_notify: dict[int, float] = {}  # guild_id -> last notification timestamp
        self._lavalink_host: typing.Optional[str] = None
        self._lavalink_port: typing.Optional[int] = None
        self._original_nicknames = {}  # Store original nicknames per guild

    async def connect_to_nodes(self):
        """Connects to the Lavalink node using the correct wavelink.Pool syntax."""
        await self.bot.wait_until_ready()

        try:
            node = wavelink.Node(
                uri=LAVALINK_URI, 
                password=LAVALINK_PASSWORD
            )
            
            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            # parse host/port once for monitoring
            parsed = _urlparse.urlparse(LAVALINK_URI)
            self._lavalink_host = parsed.hostname
            self._lavalink_port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            # start monitor loop (safe to call start multiple times; will raise if already running)
            try:
                self.lavalink_monitor.start()
            except RuntimeError:
                # already running
                pass
            
            self._lavalink_online = True
            logger.info("Connected to Lavalink node and started monitor.")
            
        except Exception as e:
            # 🎯 UPDATED LOGGING HERE (General error, no specific guild context yet)
            logger.exception("Failed to connect Lavalink node during startup.")
            # leave monitor running even if initial connect failed so it can detect recovery
            parsed = _urlparse.urlparse(LAVALINK_URI)
            self._lavalink_host = parsed.hostname
            self._lavalink_port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            try:
                self.lavalink_monitor.start()
            except RuntimeError:
                pass

    # --- Helper Functions ---
    async def get_player_and_validate(self, interaction_or_ctx):
        if isinstance(interaction_or_ctx, discord.Interaction):
            guild = interaction_or_ctx.guild
            user_voice = interaction_or_ctx.user.voice
            async def reply(msg):
                if interaction_or_ctx.response.is_done():
                    return await interaction_or_ctx.followup.send(msg)
                else:
                    return await interaction_or_ctx.response.send_message(msg, ephemeral=True)
        else:
            guild = interaction_or_ctx.guild
            user_voice = interaction_or_ctx.author.voice
            reply = interaction_or_ctx.send

        vc: CustomPlayer = guild.voice_client

        if not vc:
            await reply("I'm not connected to a voice channel! Use `!music play` first.")
            return None, None
        if not user_voice or user_voice.channel != vc.channel:
            await reply("You must be in the bot's voice channel to use the controls! 🛑")
            return None, None

        return vc, reply
        
    async def update_panel_message(self, vc: CustomPlayer, interaction: typing.Optional[discord.Interaction] = None):
        """Builds the embed and edits the panel message, ensuring view state is correct."""
        if not vc.panel_message: return

        new_embed = await self.build_embed(vc)
        
        view_to_send = self.panel_view
        
        for item in view_to_send.children:
            if isinstance(item, VolumeSelect):
                # Update placeholder to show current volume
                item.placeholder = f"Select Volume (Current: {vc.volume}%)"
                # Set the current volume as the default selected option
                for option in item.options:
                    option.default = (option.value == str(vc.volume))
            elif item.custom_id == 'music:repeat_toggle' and isinstance(item, discord.ui.Button):
                # Ensure the repeat button color is correct
                item.style = discord.ButtonStyle.green if vc.repeat_track else discord.ButtonStyle.gray
                
        # --- SEND/EDIT LOGIC ---
        if interaction and not interaction.response.is_done():
            try:
                await interaction.response.edit_message(embed=new_embed, view=view_to_send)
            except Exception as e:
                # Short, single-line log; avoid full tracebacks
                logger.warning(f"[{vc.guild.id if vc.guild else 'N/A'}] Failed to edit interaction message: {e}")
        else:
            try:
                await vc.panel_message.edit(embed=new_embed, view=view_to_send)
            except discord.HTTPException as e:
                # Keep logs short; only note important cases
                if getattr(e, "status", None) == 404:
                    vc.panel_message = None 
                    logger.info(f"[{vc.guild.id if vc.guild else 'N/A'}] Panel message not found; cleared reference.")
                else:
                    logger.warning(f"[{vc.guild.id if vc.guild else 'N/A'}] Failed editing panel message: {e}")
            except Exception as e:
                logger.warning(f"[{vc.guild.id if vc.guild else 'N/A'}] Unexpected error updating panel: {e}")
        
    async def build_embed(self, vc: CustomPlayer) -> discord.Embed:
        def format_time(ms):
            seconds = int(ms / 1000)
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                return f"{hours}:{minutes:02}:{seconds:02}"
            return f"{minutes:02}:{seconds:02}"
            
        def create_progress_bar(position, length, bar_length=15):
            """Creates a progress bar string using the current position and total length."""
            if length == 0: return ""
            
            percent = position / length
            filled_blocks = int(percent * bar_length)
            empty_blocks = bar_length - filled_blocks

            filled = "▬" * filled_blocks
            empty = "—" * empty_blocks
            
            return f"{filled}🔘{empty}"

        if vc and vc.playing:
            track = vc.current
            time_string = f"{format_time(vc.position)} / {format_time(track.length)}"
            progress_bar = create_progress_bar(vc.position, track.length)
            
            status_emoji = "⏸️ Paused" if vc.paused else "▶️ Playing"
            repeat_status = "✅ On" if vc.repeat_track else "❌ Off"

            embed = discord.Embed(
                title=f"{status_emoji} | {track.title}",
                url=track.uri,
                color=discord.Color.blue()
            )
            embed.set_author(name="Music Control Panel")
            embed.add_field(name="Queue Size", value=f"{len(vc.queue)} tracks", inline=True)
            embed.add_field(name="Volume", value=f"{vc.volume}%", inline=True)
            embed.add_field(name="Repeat", value=repeat_status, inline=True) 
            
            embed.add_field(name="Progress", value=f"`{time_string}`\n{progress_bar}", inline=False) 
            embed.set_thumbnail(url=getattr(track, "thumbnail", None))
        else:
            embed = discord.Embed(
                title="Nothing is currently playing. 🎵",
                description=f"Use `{PREFIX}music play <song>` to start the music!",
                color=discord.Color.red()
            )
        return embed

    # --- Wavelink Listeners ---
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        # 🎯 UPDATED LOGGING HERE
        logger.info(f"Lavalink Node '{payload.node.identifier}' ready at {payload.node.uri}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        """Log succinctly when a track actually starts playing and update nickname."""
        player: CustomPlayer = payload.player
        track = payload.track
        guild_name = player.guild.name if player.guild else "Unknown"
        guild_id = player.guild.id if player.guild else "N/A"
        requester = getattr(track, "requester", None)
        
        # Update nickname
        if player.guild:
            await self._update_bot_nickname(player.guild, track)

        if requester:
            logger.info(f"[{guild_name} ({guild_id})] Now playing: {track.title} (requested by {requester})")
        else:
            logger.info(f"[{guild_name} ({guild_id})] Now playing: {track.title}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: CustomPlayer = payload.player
        if not player:
            return
            
        current_track = payload.track
        guild_name = player.guild.name if player.guild else "Unknown Guild"
        guild_id = player.guild.id if player.guild else "N/A"
        
        if player.repeat_track and current_track:
            await player.play(current_track, start=0) 
            if player.panel_message:
                await self.update_panel_message(player)
            return

        if player.queue.is_empty:
            # Reset nickname when queue is empty
            if player.guild:
                await self._update_bot_nickname(player.guild)

            # Prepare the "Finished playing" embed
            finished_embed = discord.Embed(
                title="Playback Finished! ⏹️",
                description="The music queue is now empty. See you next time!",
                color=discord.Color.red()
            )
            
            # --- Attempt to edit the panel message ---
            if player.panel_message:
                try:
                    await player.panel_message.edit(embed=finished_embed, view=None) # Set view=None to remove buttons
                except discord.HTTPException as e:
                    # Short, single-line warning
                    logger.warning(f"[{guild_name} ({guild_id})] Failed to edit music panel message: {e}")
                    try:
                        await player.panel_message.delete()
                        logger.info(f"[{guild_name} ({guild_id})] Deleted music panel message after failed edit.")
                    except:
                        pass
                except Exception as e:
                    logger.warning(f"[{guild_name} ({guild_id})] Unexpected error during panel cleanup: {e}")
                finally:
                    player.panel_message = None # Clear the reference regardless of success

            try:
                await player.disconnect()
            except Exception as e:
                logger.warning(f"[{guild_name} ({guild_id})] Error disconnecting player: {e}")
            return

        next_track = player.queue.get()
        try:
            await player.play(next_track)
        except Exception as e:
            logger.warning(f"[{guild_name} ({guild_id})] Failed to play next track: {e}")
        else:
            if player.panel_message:
                await self.update_panel_message(player)

    # --- Logic Functions ---
    async def disconnect_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc: return
        
        # Reset nickname before disconnecting
        if vc.guild:
            await self._update_bot_nickname(vc.guild)
            
        guild_name = vc.guild.name
        guild_id = vc.guild.id
        channel_name = vc.channel.name
        
        try:
            await vc.disconnect()
        except Exception as e:
            logger.warning(f"[{guild_name} ({guild_id})] Error during disconnect: {e}")

        if vc.panel_message:
            try: await vc.panel_message.delete()
            except: pass
            vc.panel_message = None
        
        await reply("Playback stopped and I left the channel!")
        # 🎯 UPDATED LOGGING HERE

    async def skip_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc or not vc.playing: return await reply("Nothing is playing to skip!")
        await vc.stop() 

    async def pause_resume_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc or not vc.playing: return await reply("Nothing is playing to pause/resume! ⏸️▶️")
        await vc.pause(not vc.paused)
        status = "Paused" if vc.paused else "Resumed"
        
        # Update nickname to reflect new pause state
        if vc.guild and vc.current:
            await self._update_bot_nickname(vc.guild, vc.current)
        
        if not isinstance(interaction_or_ctx, discord.Interaction):
            await reply(f"Playback **{status}**.")
            
    # --- Music Command Group ---
    @commands.group(invoke_without_command=True, aliases=['m'])
    async def music(self, ctx: commands.Context):
        """Music commands group. Use subcommands like play, skip, pause, etc."""
        embed = discord.Embed(
            title="Music Commands",
            description=f"Use `{PREFIX}music play <song>` to start the music!"
        )
        
        embed.add_field(name=PREFIX+"music play <query>", value="Play a song or add to queue", inline=False)
        embed.add_field(name=PREFIX+"music playnow <query>", value="Play the song immediately, bypassing the queue", inline=False)
        embed.add_field(name=PREFIX+"music skip", value="Skip the current song", inline=False)
        embed.add_field(name=PREFIX+"music pause", value="Pause the current song", inline=False)
        embed.add_field(name=PREFIX+"music resume", value="Resume the paused song", inline=False)
        embed.add_field(name=PREFIX+"music stop", value="Stop playback and leave VC", inline=False)
        embed.add_field(name=PREFIX+"music queue", value="Show the current queue", inline=False)
        embed.add_field(name=PREFIX+"music panel", value="Show the music control panel", inline=False)
        
        await ctx.send(embed=embed)


    @music.command(name="play", aliases=["pl"])
    async def play(self, ctx: commands.Context, *, search: str):
        vc: CustomPlayer = ctx.voice_client
        if not vc:
            if not ctx.author.voice: return await ctx.send("Join a VC first!")
            try:
                vc = await ctx.author.voice.channel.connect(cls=CustomPlayer)
                vc.text_channel = ctx.channel
            except Exception as e:
                logger.warning(f"[{ctx.guild.name if ctx.guild else 'N/A'} ({ctx.guild.id if ctx.guild else 'N/A'})] Failed to connect to VC: {e}")
                return await ctx.send("Failed to join your voice channel.")
            # set default volume quietly
            try:
                await vc.set_volume(50)
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to set initial volume: {e}")


        if not vc.panel_message:
            # Send initial panel message with the persistent view
            try:
                vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
                # Then update the placeholder immediately after sending
                await self.update_panel_message(vc)
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to create music panel message: {e}")
                vc.panel_message = None

        tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.YouTube)

        if not tracks: 
            await ctx.send(f"❌ No music found for `{search}`!")
            logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] No music found for search: {search}")
            return

        track = tracks[0]

        if vc.playing or vc.paused: 
            vc.queue.put(track)
            await ctx.send(f"**Queued:** `{track.title}` - Position **{len(vc.queue)}**")
            logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Queued: {track.title}")
        else:
            try:
                await vc.play(track)
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to start playing {track.title}: {e}")
                return await ctx.send("Failed to play the track.")
            else:
                # concise play log (track start will also be logged by on_wavelink_track_start when it triggers)
                logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Started play request: {track.title}")
                if vc.panel_message:
                    await self.update_panel_message(vc) 
                # 🎯 UPDATED LOGGING HERE

    @music.command(name="playnow", aliases=['pn'])
    async def playnow_cmd(self, ctx: commands.Context, *, search: str):
        """Plays the track immediately, bypassing the queue."""
        vc: CustomPlayer = ctx.voice_client
        if not vc:
            if not ctx.author.voice: 
                return await ctx.send("Join a VC first!")
            try:
                vc = await ctx.author.voice.channel.connect(cls=CustomPlayer)
                vc.text_channel = ctx.channel
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to connect to VC for playnow: {e}")
                return await ctx.send("Failed to join your voice channel.")

        try:
            tracks = await wavelink.Playable.search(search)
            if not tracks:
                return await ctx.send("No results found.")
            track = tracks[0]
            track.requester = ctx.author
        except Exception as e:
            logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Playnow search failed: {e}")
            return await ctx.send("Error searching for that track.")

        # Clear queue and stop current track if playing
        await self._clear_queue(vc)
        if vc.playing or vc.paused:
            await vc.stop()

        await vc.play(track)

        if not vc.panel_message:
            vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
        else:
            await self.update_panel_message(vc)
        

    @music.command(name="skip", aliases=['s'])
    async def skip_cmd(self, ctx: commands.Context):
        await self.skip_logic(ctx)

    @music.command(name="pause", aliases=['p'])
    async def pause_cmd(self, ctx: commands.Context):
        await self.pause_resume_logic(ctx)

    @music.command(name="resume", aliases=['r'])
    async def resume_cmd(self, ctx: commands.Context):
        await self.pause_resume_logic(ctx)
        
    @music.command(name="stop", aliases=["disconnect"])
    async def stop_cmd(self, ctx: commands.Context):
        await self.disconnect_logic(ctx)

    @music.command(name="queue", aliases=['q'])
    async def queue_cmd(self, ctx: commands.Context):
        vc: CustomPlayer = ctx.voice_client
        if not vc or vc.queue.is_empty: return await ctx.send("Queue is empty!")
        queue_list = "\n".join(f"`{i+1}.` **{track.title}**" for i, track in enumerate(vc.queue[:10]))
        embed = discord.Embed(title=f"Queue ({len(vc.queue)} tracks)", description=queue_list, color=discord.Color.gold())
        await ctx.send(embed=embed)

    @music.command(name="panel", aliases=['np'])
    async def panel_cmd(self, ctx: commands.Context):
        vc: CustomPlayer = ctx.voice_client
        if not vc: return await ctx.send("I need to be playing music to show the panel!")
        
        if vc.panel_message:
            try: await vc.panel_message.delete()
            except: pass
            
        vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
        await self.update_panel_message(vc) # Update button/select colors/defaults

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Minimal command error handler: never expose exception details to users."""
        # Unwrap CommandInvokeError to its original exception type for concise logging
        original = getattr(error, "original", error)

        # Ignore common non-actionable errors
        if isinstance(original, commands.CommandNotFound):
            return

        # Log full exception with traceback internally for debugging (no user exposure)
        logger.exception(f"Command '{getattr(ctx, 'command', None)}' raised an exception")

        # Send a short, user-friendly message (no exception text)
        try:
            await ctx.send("An internal error occurred while running that command. The error has been logged.")
        except:
            pass

    async def _notify_guilds(self, message: str, throttle: int = 300):
        """Send short, throttled notifications to guilds with active voice clients."""
        now = time.time()
        for vc in list(self.bot.voice_clients):
            guild = vc.guild
            if not guild:
                continue
            last = self._last_notify.get(guild.id, 0)
            if now - last < throttle:
                continue
            txt = getattr(vc, "text_channel", None)
            if txt:
                try:
                    await txt.send(message)
                except Exception:
                    # don't expose details to users; log internally
                    logger.debug(f"Failed to notify guild {guild.id} about Lavalink state.")
            self._last_notify[guild.id] = now

    @tasks.loop(seconds=20.0)
    async def lavalink_monitor(self):
        """Periodic TCP check of the Lavalink server and lightweight reconnect logic."""
        host = self._lavalink_host
        port = self._lavalink_port
        if not host or not port:
            return  # nothing to check

        try:
            # quick TCP connection to check reachability
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3.0)
            writer.close()
            # py38 compatibility
            try:
                await writer.wait_closed()
            except Exception:
                pass
            # If we were previously offline, try to reconnect and notify guilds
            if not self._lavalink_online:
                logger.info("Lavalink server reachable again. Attempting to reconnect wavelink.Pool...")
                self._lavalink_online = True
                try:
                    node = wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)
                    await wavelink.Pool.connect(client=self.bot, nodes=[node])
                    logger.info("Reconnected to Lavalink node.")
                except Exception:
                    logger.exception("Failed to reconnect to Lavalink node after server came back.")
                # Notify affected guilds once (friendly, no exception details)
                await self._notify_guilds("Lavalink is back online — attempting to resume music playback.")
        except Exception:
            # server appears offline / unreachable
            if self._lavalink_online:
                # state change -> notify and log
                self._lavalink_online = False
                logger.warning("Detected Lavalink server is unreachable. Will attempt to reconnect periodically.")
                await self._notify_guilds("Lavalink appears to be offline. The bot will try to reconnect; playback may stop temporarily.")
            # else: remain silent (throttled notifications handled in _notify_guilds)

    @lavalink_monitor.before_loop
    async def _before_lavalink_monitor(self):
        # ensure bot ready before starting checks
        await self.bot.wait_until_ready()

    async def _clear_queue(self, vc: CustomPlayer):
        """Safely empty the player's queue without raising."""
        try:
            # wavelink queue uses is_empty + get()
            while not vc.queue.is_empty:
                try:
                    vc.queue.get()
                except Exception:
                    break
        except Exception:
            logger.debug(f"[{vc.guild.id if vc.guild else 'N/A'}] Error while clearing queue (ignored).")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Stop and cleanup the player if the bot is alone in its voice channel."""
        # Only care about guilds (ignore DMs)
        guild = member.guild
        if not guild:
            return

        vc: typing.Optional[CustomPlayer] = guild.voice_client
        if not vc:
            return

        # If bot has no channel, nothing to do
        channel = vc.channel
        if not channel:
            return

        # Count non-bot members left in the channel
        non_bot_count = sum(1 for m in channel.members if not m.bot)

        # If no non-bot members remain, stop and cleanup
        if non_bot_count == 0:
            guild_id = guild.id if guild else "N/A"
            logger.info(f"[{guild_id}] No users left in voice channel; stopping and disconnecting player.")

            try:
                # Stop playback if playing
                try:
                    if getattr(vc, "playing", False) or getattr(vc, "paused", False):
                        await vc.stop()
                except Exception:
                    # ignore failures to stop
                    pass

                # Clear queue
                await self._clear_queue(vc)

                # Remove panel message if possible
                if getattr(vc, "panel_message", None):
                    try:
                        await vc.panel_message.delete()
                    except Exception:
                        pass
                    vc.panel_message = None

                # Disconnect the player cleanly
                try:
                    await vc.disconnect()
                except Exception:
                    # if disconnect fails, log minimally
                    logger.warning(f"[{guild_id}] Disconnect attempt failed (ignored).")

                # Optionally notify the guild via the stored text channel
                txt = getattr(vc, "text_channel", None)
                if txt:
                    try:
                        await txt.send("No users remain in the voice channel — playback stopped and I left the channel.")
                    except Exception:
                        # don't expose details to users
                        logger.debug(f"[{guild_id}] Failed to send empty-channel notification (ignored).")

            except Exception:
                # Catch-all to ensure this listener never raises
                logger.exception(f"[{guild_id}] Error during empty-channel cleanup (ignored).")

    async def _update_bot_nickname(self, guild: discord.Guild, track=None):
        """Update the bot's nickname based on the current track."""
        try:
            if track:
                # Get bot's original nickname if not stored
                if guild.id not in self._original_nicknames:
                    self._original_nicknames[guild.id] = guild.me.display_name

                # Get player to check pause status
                player: CustomPlayer = guild.voice_client
                status_emoji = "⏸️" if player and player.paused else "▶️"

                # Create new nickname with track info and status
                base_name = self._original_nicknames[guild.id] or self.bot.user.name
                new_nick = f"{base_name} | {status_emoji} {track.title}"
                # Ensure nickname doesn't exceed Discord's 32-character limit
                if len(new_nick) > 32:
                    new_nick = new_nick[:29] + "..."
            else:
                # Reset to original nickname
                new_nick = self._original_nicknames.get(guild.id, self.bot.user.name)

            await guild.me.edit(nick=new_nick)
        except Exception as e:
            logger.warning(f"[{guild.id}] Failed to update nickname: {e}")

    # Helper method for context menu
    async def _play_from_url(self, interaction: discord.Interaction, url: str):
        query = url.strip()

        # Defer the interaction to give us time to process
        await interaction.response.defer(thinking=True)

        # Obtain or create the player exactly like the play command does
        vc: CustomPlayer = interaction.guild.voice_client
        if not vc:
            if not interaction.user.voice:
                return await interaction.followup.send("Join a voice channel first!", ephemeral=True)
            try:
                vc = await interaction.user.voice.channel.connect(cls=CustomPlayer)
                vc.text_channel = interaction.channel
            except Exception as e:
                logger.warning(f"[{interaction.guild.id}] Failed to connect to VC via context menu: {e}")
                return await interaction.followup.send("Could not join your voice channel.", ephemeral=True)
            # Set default volume quietly
            try:
                await vc.set_volume(50)
            except Exception as e:
                logger.warning(f"[{interaction.guild.id}] Failed to set initial volume via context menu: {e}")

        # Attempt to play/queue the URL
        try:
            tracks = await wavelink.Playable.search(query)
            if not tracks:
                return await interaction.followup.send("Could not find any playable audio for that link.", ephemeral=True)

            track = tracks[0]
            track.requester = interaction.user

            if vc.playing or not vc.queue.is_empty:
                vc.queue.put(track)
                embed = discord.Embed(
                    title="Added to Queue",
                    description=f"[{track.title}]({track.uri})",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed)
            else:
                await vc.play(track)
                await interaction.followup.send(embed=await self.build_embed(vc))

            # Ensure panel message exists
            if not vc.panel_message:
                vc.panel_message = await interaction.followup.send(embed=await self.build_embed(vc), view=self.panel_view)

        except Exception as e:
            logger.warning(f"[{interaction.guild.id}] Context-menu play failed: {e}")
            await interaction.followup.send("An error occurred while trying to play that link.", ephemeral=True)

async def setup(bot):
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
    
    # Create and register the context menu
    @app_commands.context_menu(name="Play Track")
    async def play_track_context_menu(interaction: discord.Interaction, message: discord.Message):
        """Finds the first valid audio URL in the message and plays or queues it."""
        # Look for any HTTP(S) link in the message content
        url_match = re.search(r'https?://\S+', message.content)
        if not url_match:
            return await interaction.response.send_message("No valid URL found in that message.", ephemeral=True)
        
        url = url_match.group(0)
        await music_cog._play_from_url(interaction, url)
    
    bot.tree.add_command(play_track_context_menu)
    await bot.tree.sync()
    
    bot.loop.create_task(music_cog.connect_to_nodes())
    
    # This block ensures persistence across bot restarts
    if not hasattr(bot, 'music_panel_view'):
        bot.music_panel_view = music_cog.panel_view
        
        for item in bot.music_panel_view.children:
            if item.custom_id == 'music:repeat_toggle' and isinstance(item, discord.ui.Button):
                item.style = discord.ButtonStyle.gray # Default state on startup
                
        # Re-add the view so Discord knows to listen for its custom IDs
        bot.add_view(bot.music_panel_view)