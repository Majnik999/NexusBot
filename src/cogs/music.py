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
import yt_dlp

class CustomPlayer(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text_channel: typing.Optional[discord.TextChannel] = None
        self.panel_message: typing.Optional[discord.Message] = None
        self.repeat_track: bool = False

class VolumeSelect(discord.ui.Select):
    def __init__(self, cog: 'Music'):
        self.cog = cog
        options = [discord.SelectOption(label=f"{i}%", value=str(i)) for i in range(5, 101, 5)]
        super().__init__(placeholder="Select Volume", options=options, custom_id="music:volume_select")

    async def callback(self, interaction: discord.Interaction):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc:
            return await interaction.response.defer()
        try:
            new_volume = int(self.values[0])
            await vc.set_volume(new_volume)
            await self.cog.update_panel_message(vc, interaction=interaction)
        except wavelink.LavalinkException:
            try:
                await vc.stop()
                await vc.disconnect()
                if vc.panel_message:
                    try:
                        await vc.panel_message.delete()
                    except:
                        pass
                    vc.panel_message = None
                await interaction.response.send_message("Lost connection to music server. Stopping playback.", ephemeral=True)
            except Exception:
                await interaction.response.send_message("An error occurred with the music player.", ephemeral=True)
            return
        except ValueError:
            await interaction.response.send_message("Invalid volume selection.", ephemeral=True)
        if not interaction.response.is_done():
            await interaction.response.defer()

class MusicPanel(discord.ui.View):
    def __init__(self, cog: 'Music'):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(VolumeSelect(cog))

    async def _update_panel(self, interaction: discord.Interaction, vc: 'CustomPlayer'):
        await self.cog.update_panel_message(vc, interaction=interaction)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.danger, custom_id='music:stop_disconnect', row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.disconnect_logic(interaction)

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.secondary, custom_id='music:skip', row=1)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc:
            return
        await interaction.response.defer()
        await self.cog.skip_logic(interaction)

    @discord.ui.button(label='Pause/Resume', style=discord.ButtonStyle.success, custom_id='music:pause_resume', row=1)
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc:
            return
        await self.cog.pause_resume_logic(interaction)
        await self._update_panel(interaction, vc)


class QueueView(discord.ui.View):
    def __init__(self, tracks: list, author_id: int, per_page: int = 10, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.tracks = tracks
        self.author_id = author_id
        self.per_page = per_page
        self.page = 0

    def _build_embed(self) -> discord.Embed:
        total = len(self.tracks)
        pages = max(1, (total + self.per_page - 1) // self.per_page)
        start = self.page * self.per_page
        end = start + self.per_page
        chunk = self.tracks[start:end]
        if chunk:
            lines = []
            for i, track in enumerate(chunk, start=start):
                title = getattr(track, 'title', 'Unknown')
                lines.append(f"`{i+1}.` **{title}**")
            desc = "\n".join(lines)
        else:
            desc = "No items on this page."
        embed = discord.Embed(title=f"Queue ({total} tracks)", description=desc, color=discord.Color.gold())
        embed.set_footer(text=f"Page {self.page+1}/{pages}")
        return embed

    async def _update_message(self, interaction: discord.Interaction):
        embed = self._build_embed()
        # Update button states
        total = len(self.tracks)
        pages = max(1, (total + self.per_page - 1) // self.per_page)
        for child in self.children:
            if getattr(child, 'custom_id', None) == 'music:queue_prev':
                child.disabled = (self.page <= 0)
            if getattr(child, 'custom_id', None) == 'music:queue_next':
                child.disabled = (self.page >= pages - 1)
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            try:
                await interaction.message.edit(embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary, custom_id='music:queue_prev', row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await self._update_message(interaction)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary, custom_id='music:queue_next', row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        total = len(self.tracks)
        pages = max(1, (total + self.per_page - 1) // self.per_page)
        if self.page < pages - 1:
            self.page += 1
        await self._update_message(interaction)

    async def on_timeout(self):
        # Disable buttons on timeout
        for child in self.children:
            child.disabled = True
        # Attempt to edit the original message to disable controls
        try:
            # The view does not have direct access to the message; rely on stored state via interaction history.
            # Best-effort: nothing to do here.
            pass
        except Exception:
            pass

    @discord.ui.button(label='Refresh', style=discord.ButtonStyle.secondary, custom_id='music:refresh_panel', row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc:
            return
        await self._update_panel(interaction, vc)

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.panel_view = MusicPanel(self)
        self._lavalink_online: bool = True
        self._last_notify: dict[int, float] = {}
        self._lavalink_host: typing.Optional[str] = None
        self._lavalink_port: typing.Optional[int] = None

    async def _ensure_deaf(self, vc: CustomPlayer):
        """Try to server-deafen the bot; ensure self-deaf is enabled as a fallback.

        We set `self_deaf=True` on connect which guarantees the bot won't hear users.
        This method attempts to server-deafen (`guild.me.edit(deafen=True)`) so moderators
        see the bot as server-deafened if permissions allow.
        """
        if not vc or not vc.guild:
            return
        # Try server-deafen first
        try:
            member = vc.guild.me
            # Only attempt if not already server-deaf
            if not getattr(member.voice, "deaf", False):
                await member.edit(deafen=True)
                logger.info(f"[{vc.guild.id}] Server-deafened bot successfully.")
                return
        except discord.Forbidden:
            logger.info(f"[{vc.guild.id}] Missing permissions to server-deafen; using self-deafen.")
        except Exception as e:
            logger.warning(f"[{vc.guild.id}] Error attempting server-deafen: {e}")
        # At this point, ensure the voice client is self-deafened (connect uses self_deaf=True).
        try:
            # Some VoiceClient implementations expose `self_deaf` via the voice state; set if possible
            if getattr(vc, "deaf", None) is False:
                # Best-effort: request a voice state update with self_deaf True via guild.change_voice_state
                try:
                    await vc.guild.change_voice_state(vc.guild.me, self_deaf=True)
                except Exception:
                    # If above API is unavailable, log and continue; the connect call sets self_deaf.
                    pass
        except Exception:
            pass

    async def cog_unload(self):
        """Disconnect all players when the cog is unloaded."""
        logger.info("Music cog unloaded. Disconnecting all players...")
        try:
            # Make a copy of nodes to avoid runtime mutation during iteration.
            nodes = list(getattr(wavelink.Pool, 'nodes', {}).items())
            for guild_id, player in nodes:
                try:
                    if getattr(player, 'is_connected', False):
                        await player.disconnect()
                        logger.info(f"Disconnected player in guild {guild_id}")
                except Exception as e:
                    # Keep logs concise during reloads; avoid printing stack traces.
                    logger.error(f"Error disconnecting player in guild {guild_id}: {e}")
        except Exception as e:
            # Catch any unexpected issues during unload and log succinctly.
            logger.error(f"Error during music cog unload: {e}")

    async def connect_to_nodes(self):
        await self.bot.wait_until_ready()
        try:
            node = wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)
            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            parsed = _urlparse.urlparse(LAVALINK_URI)
            self._lavalink_host = parsed.hostname
            self._lavalink_port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            try:
                self.lavalink_monitor.start()
            except RuntimeError:
                pass
            self._lavalink_online = True
            logger.info("Connected to Lavalink node and started monitor.")
        except Exception:
            logger.exception("Failed to connect Lavalink node during startup.")
            parsed = _urlparse.urlparse(LAVALINK_URI)
            self._lavalink_host = parsed.hostname
            self._lavalink_port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            try:
                self.lavalink_monitor.start()
            except RuntimeError:
                pass

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
        if not vc.panel_message:
            return
        new_embed = await self.build_embed(vc)
        view_to_send = self.panel_view
        for item in view_to_send.children:
            if isinstance(item, VolumeSelect):
                item.placeholder = f"Select Volume (Current: {vc.volume}%)"
                for option in item.options:
                    option.default = (option.value == str(vc.volume))
            elif item.custom_id == 'music:repeat_toggle' and isinstance(item, discord.ui.Button):
                item.style = discord.ButtonStyle.success if vc.repeat_track else discord.ButtonStyle.secondary
        if interaction and not interaction.response.is_done():
            try:
                await interaction.response.edit_message(embed=new_embed, view=view_to_send)
            except Exception as e:
                logger.warning(f"[{vc.guild.id if vc.guild else 'N/A'}] Failed to edit interaction message: {e}")
        else:
            try:
                await vc.panel_message.edit(embed=new_embed, view=view_to_send)
            except discord.HTTPException as e:
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
            if length == 0:
                return ""
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
            embed = discord.Embed(title=f"{status_emoji} | {track.title}", url=track.uri, color=discord.Color.blue())
            embed.set_author(name="Music Control Panel")
            embed.add_field(name="Queue Size", value=f"{len(vc.queue)} tracks", inline=True)
            embed.add_field(name="Volume", value=f"{vc.volume}%", inline=True)
            embed.add_field(name="Repeat", value=repeat_status, inline=True)
            embed.add_field(name="Progress", value=f"`{time_string}`\n{progress_bar}", inline=False)
            embed.set_thumbnail(url=getattr(track, "thumbnail", None))
        else:
            embed = discord.Embed(title="Nothing is currently playing. 🎵", description=f"Use `{PREFIX}music play <song>` to start the music!", color=discord.Color.red())
        return embed

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logger.info(f"Lavalink Node '{payload.node.identifier}' ready at {payload.node.uri}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: CustomPlayer = payload.player
        track = payload.track
        guild_name = player.guild.name if player.guild else "Unknown"
        guild_id = player.guild.id if player.guild else "N/A"
        requester = getattr(track, "requester", None)
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
            stopped_embed = discord.Embed(title="Music Stopped", description="Playback has ended and the queue is empty.", color=discord.Color.red())
            if player.panel_message:
                try:
                    await player.panel_message.edit(embed=stopped_embed, view=None)
                except discord.HTTPException as e:
                    # If the message is missing, clear the reference; otherwise log.
                    if getattr(e, "status", None) == 404:
                        player.panel_message = None
                    else:
                        logger.warning(f"[{guild_name} ({guild_id})] Failed to edit music panel message: {e}")
                except Exception as e:
                    logger.warning(f"[{guild_name} ({guild_id})] Unexpected error during panel cleanup: {e}")
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

    async def disconnect_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc:
            return
        try:
            await vc.disconnect()
        except Exception as e:
            logger.warning(f"[{vc.guild.name} ({vc.guild.id})] Error during disconnect: {e}")
        if vc.panel_message:
            # Update the existing panel to show stopped state instead of deleting it.
            try:
                stopped_embed = discord.Embed(
                    title="Music Stopped",
                    description=f"Playback has been stopped. Use `{PREFIX}music play <song>` to start playback again.",
                    color=discord.Color.red()
                )
                try:
                    await vc.panel_message.edit(embed=stopped_embed, view=None)
                except discord.HTTPException as e:
                    if getattr(e, "status", None) == 404:
                        vc.panel_message = None
                    else:
                        logger.warning(f"[{vc.guild.id if vc.guild else 'N/A'}] Failed to edit panel message on disconnect: {e}")
            except Exception as e:
                logger.warning(f"[{vc.guild.id if vc.guild else 'N/A'}] Error updating panel message on disconnect: {e}")

    async def skip_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc or not vc.playing:
            return await reply("Nothing is playing to skip!")
        await vc.stop()

    async def pause_resume_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc or not vc.playing:
            return await reply("Nothing is playing to pause/resume! ⏸️▶️")
        await vc.pause(not vc.paused)
        status = "Paused" if vc.paused else "Resumed"
        if not isinstance(interaction_or_ctx, discord.Interaction):
            await reply(f"Playback **{status}**.")

    @commands.group(invoke_without_command=True, aliases=['m'])
    async def music(self, ctx: commands.Context):
        embed = discord.Embed(title="Music Commands", description=f"Use `{PREFIX}music play <song>` to start the music!")
        embed.add_field(name=PREFIX+"music play <query>", value="Play a song or add to queue", inline=False)
        embed.add_field(name=PREFIX+"music playnow <query>", value="Play the song immediately, bypassing the queue", inline=False)
        embed.add_field(name=PREFIX+"music skip", value="Skip the current song", inline=False)
        embed.add_field(name=PREFIX+"music repeat", value="Toggle repeat for the current song", inline=False)
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
            if not ctx.author.voice:
                return await ctx.send("Join a VC first!")
            try:
                vc = await ctx.author.voice.channel.connect(cls=CustomPlayer, self_deaf=True)
                vc.text_channel = ctx.channel
                try:
                    await self._ensure_deaf(vc)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[{ctx.guild.name if ctx.guild else 'N/A'} ({ctx.guild.id if ctx.guild else 'N/A'})] Failed to connect to VC: {e}")
                return await ctx.send("Failed to join your voice channel.")
            try:
                await vc.set_volume(50)
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to set initial volume: {e}")
        if not vc.panel_message:
            try:
                vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
                await self.update_panel_message(vc)
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to create music panel message: {e}")
                vc.panel_message = None
        tracks = await wavelink.Playable.search(search)
        if not tracks:
            await ctx.send(f"❌ No music found for `{search}`!")
            logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] No music found for search: {search}")
            return

        if isinstance(tracks, wavelink.Playlist):
            added_count = 0
            for track in tracks.tracks:
                track.requester = ctx.author
                vc.queue.put(track)
                added_count += 1
            # Safely build a link for the playlist: some Playlist objects may not have `uri`.
            playlist_url = getattr(tracks, "uri", None)
            if not playlist_url:
                # Fall back to the first track's uri if available
                first = tracks.tracks[0] if getattr(tracks, "tracks", None) else None
                playlist_url = getattr(first, "uri", None) if first else None
            if playlist_url:
                desc = f"Added {added_count} tracks from [{tracks.name}]({playlist_url})"
            else:
                desc = f"Added {added_count} tracks from {tracks.name}"
            embed = discord.Embed(title="Playlist Added to Queue", description=desc, color=discord.Color.green())
            await ctx.send(embed=embed)
            logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Queued playlist: {tracks.name} with {added_count} tracks")
            if not vc.playing and not vc.paused:
                try:
                    await vc.play(vc.queue.get())
                except Exception as e:
                    logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to start playing playlist: {e}")
                    return await ctx.send("Failed to play the playlist.")
                else:
                    logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Started playing playlist.")
                    if vc.panel_message:
                        await self.update_panel_message(vc)
            return
        else:
            track = tracks[0]
            track.requester = ctx.author
            if vc.playing or vc.paused:
                vc.queue.put(track)
                embed = discord.Embed(title="Added to Queue", description=f"[{track.title}]({track.uri})", color=discord.Color.green())
                await ctx.send(embed=embed)
                logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Queued: {track.title}")
            else:
                try:
                    await vc.play(track)
                except Exception as e:
                    logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to start playing {track.title}: {e}")
                    return await ctx.send("Failed to play the track.")
                else:
                    logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Started play request: {track.title}")
                    if vc.panel_message:
                        await self.update_panel_message(vc)

    @music.command(name="playnow", aliases=['pn'])
    async def playnow_cmd(self, ctx: commands.Context, *, search: str):
        vc: CustomPlayer = ctx.voice_client
        if not vc:
            if not ctx.author.voice:
                return await ctx.send("Join a VC first!")
            try:
                vc = await ctx.author.voice.channel.connect(cls=CustomPlayer, self_deaf=True)
                vc.text_channel = ctx.channel
                try:
                    await self._ensure_deaf(vc)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to connect to VC for playnow: {e}")
                return await ctx.send("Failed to join your voice channel.")
            try:
                await vc.set_volume(50)
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to set initial volume for playnow: {e}")
        try:
            tracks = await wavelink.Playable.search(search)
            if not tracks:
                return await ctx.send("No results found.")
        except Exception as e:
            logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Playnow search failed: {e}")
            return await ctx.send("Error searching for that track.")

        # Prepend requested track(s) so they play immediately, preserving the existing queue order.
        def _prepend_tracks_to_queue(vc, new_tracks: list):
            try:
                # Drain existing queue into a temporary list
                existing = []
                try:
                    while not vc.queue.is_empty:
                        existing.append(vc.queue.get())
                except Exception:
                    # If queue access fails for any reason, fall back to leaving it unchanged
                    existing = []
                # Put new tracks first
                for t in new_tracks:
                    vc.queue.put(t)
                # Re-add the old items after
                for t in existing:
                    vc.queue.put(t)
            except Exception:
                # Best-effort; if unable to reorder, append to the end instead
                for t in new_tracks:
                    try:
                        vc.queue.put(t)
                    except Exception:
                        pass

        # If a playlist was returned, prepend all tracks and start playback from the first new item
        if isinstance(tracks, wavelink.Playlist):
            new_tracks = []
            for track in tracks.tracks:
                track.requester = ctx.author
                new_tracks.append(track)
            _prepend_tracks_to_queue(vc, new_tracks)
            try:
                if vc.playing or vc.paused:
                    await vc.stop()
                # Play the first of the newly prepended tracks
                await vc.play(vc.queue.get())
            except Exception as e:
                logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to play playlist for playnow: {e}")
                return await ctx.send("Failed to play the playlist.")
            else:
                embed = discord.Embed(title="Playlist Added to Queue", description=f"Added {len(new_tracks)} tracks from {tracks.name}", color=discord.Color.green())
                await ctx.send(embed=embed)
                logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Started playing playlist via playnow: {tracks.name}")
                if not vc.panel_message:
                    vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
                else:
                    await self.update_panel_message(vc)
            return

        # Otherwise, handle a single track result: prepend and play immediately
        track = tracks[0]
        track.requester = ctx.author
        _prepend_tracks_to_queue(vc, [track])
        try:
            if vc.playing or vc.paused:
                await vc.stop()
            await vc.play(vc.queue.get())
        except Exception as e:
            logger.warning(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Failed to start playing {getattr(track, 'title', 'track')}: {e}")
            return await ctx.send("Failed to play the track.")
        else:
            logger.info(f"[{ctx.guild.id if ctx.guild else 'N/A'}] Started playnow request: {getattr(track, 'title', 'track')}")
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
        if not vc or vc.queue.is_empty:
            return await ctx.send("Queue is empty!")
        # Snapshot the queue so pagination remains consistent while viewing
        try:
            tracks = list(vc.queue)
        except Exception:
            # Fallback to slicing if list() isn't supported
            tracks = vc.queue[:]
        total = len(tracks)
        per_page = 10
        # Build initial embed for page 1
        def build_page(page: int):
            start = page * per_page
            end = start + per_page
            chunk = tracks[start:end]
            if chunk:
                lines = []
                for i, track in enumerate(chunk, start=start):
                    title = getattr(track, 'title', 'Unknown')
                    lines.append(f"`{i+1}.` **{title}**")
                desc = "\n".join(lines)
            else:
                desc = "No items on this page."
            embed = discord.Embed(title=f"Queue ({total} tracks)", description=desc, color=discord.Color.gold())
            pages = max(1, (total + per_page - 1) // per_page)
            embed.set_footer(text=f"Page {1}/{pages}")
            return embed

        if total <= per_page:
            await ctx.send(embed=build_page(0))
            return

        view = QueueView(tracks=tracks, author_id=ctx.author.id, per_page=per_page)
        embed = view._build_embed()
        await ctx.send(embed=embed, view=view)

    @music.command(name="repeat", aliases=['loop', "l", "re"])
    async def repeat_cmd(self, ctx: commands.Context):
        vc: CustomPlayer = ctx.voice_client
        if not vc:
            return await ctx.send("I'm not connected to a voice channel!")
        vc.repeat_track = not vc.repeat_track
        status = "enabled" if vc.repeat_track else "disabled"
        await ctx.send(f"Track repeat has been **{status}**.")
        if vc.panel_message:
            await self.update_panel_message(vc)

    @music.command(name="panel", aliases=['np'])
    async def panel_cmd(self, ctx: commands.Context):
        vc: CustomPlayer = ctx.voice_client
        if not vc:
            return await ctx.send("I need to be playing music to show the panel!")
        if vc.panel_message:
            try:
                await vc.panel_message.delete()
            except:
                pass
        vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
        await self.update_panel_message(vc)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        original = getattr(error, "original", error)
        if isinstance(original, commands.CommandNotFound):
            return
        logger.exception(f"Command '{getattr(ctx, 'command', None)}' raised an exception")
        try:
            await ctx.send("An internal error occurred while running that command. The error has been logged.")
        except:
            pass

    async def _notify_guilds(self, message: str, throttle: int = 300):
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
                    logger.debug(f"Failed to notify guild {guild.id} about Lavalink state.")
            self._last_notify[guild.id] = now

    @tasks.loop(seconds=20.0)
    async def lavalink_monitor(self):
        host = self._lavalink_host
        port = self._lavalink_port
        if not host or not port:
            return
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3.0)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            if not self._lavalink_online:
                logger.info("Lavalink server reachable again. Attempting to reconnect wavelink.Pool...")
                self._lavalink_online = True
                try:
                    node = wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)
                    await wavelink.Pool.connect(client=self.bot, nodes=[node])
                    logger.info("Reconnected to Lavalink node.")
                except Exception:
                    logger.exception("Failed to reconnect to Lavalink node after server came back.")
                await self._notify_guilds("Lavalink is back online — attempting to resume music playback.")
        except Exception:
            if self._lavalink_online:
                self._lavalink_online = False
                logger.warning("Detected Lavalink server is unreachable. Will attempt to reconnect periodically.")
                await self._notify_guilds("Lavalink appears to be offline. The bot will try to reconnect; playback may stop temporarily.")

    @lavalink_monitor.before_loop
    async def _before_lavalink_monitor(self):
        await self.bot.wait_until_ready()

    async def _clear_queue(self, vc: CustomPlayer):
        try:
            while not vc.queue.is_empty:
                try:
                    vc.queue.get()
                except Exception:
                    break
        except Exception:
            logger.debug(f"[{vc.guild.id if vc.guild else 'N/A'}] Error while clearing queue (ignored).")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        if not guild:
            return
        vc: typing.Optional[CustomPlayer] = guild.voice_client
        if not vc:
            return
        channel = vc.channel
        if not channel:
            return
        non_bot_count = sum(1 for m in channel.members if not m.bot)
        if non_bot_count == 0:
            guild_id = guild.id if guild else "N/A"
            logger.info(f"[{guild_id}] No users left in voice channel; stopping and disconnecting player.")
            try:
                try:
                    if getattr(vc, "playing", False) or getattr(vc, "paused", False):
                        await vc.stop()
                except Exception:
                    pass
                await self._clear_queue(vc)
                if getattr(vc, "panel_message", None):
                    try:
                        await vc.panel_message.delete()
                    except Exception:
                        pass
                    vc.panel_message = None
                try:
                    await vc.disconnect()
                except Exception:
                    logger.warning(f"[{guild_id}] Disconnect attempt failed (ignored).")
            except Exception:
                logger.exception(f"[{guild_id}] Error during empty-channel cleanup (ignored).")


    async def _play_from_url(self, interaction: discord.Interaction, url: str):
        query = url.strip()
        await interaction.response.defer(thinking=True)
        vc: CustomPlayer = interaction.guild.voice_client
        if not vc:
            if not interaction.user.voice:
                return await interaction.followup.send("Join a voice channel first!", ephemeral=True)
            try:
                vc = await interaction.user.voice.channel.connect(cls=CustomPlayer, self_deaf=True)
                vc.text_channel = interaction.channel
                try:
                    await self._ensure_deaf(vc)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[{interaction.guild.id}] Failed to connect to VC via context menu: {e}")
                return await interaction.followup.send("Could not join your voice channel.", ephemeral=True)
            try:
                await vc.set_volume(50)
            except Exception as e:
                logger.warning(f"[{interaction.guild.id}] Failed to set initial volume via context menu: {e}")
        try:
            tracks = await wavelink.Playable.search(query)
            if not tracks:
                return await interaction.followup.send("Could not find any playable audio for that link.", ephemeral=True)

            if isinstance(tracks, wavelink.Playlist):
                added_count = 0
                for track in tracks.tracks:
                    track.requester = interaction.user
                    vc.queue.put(track)
                    added_count += 1
                # Safely build a link for the playlist: some Playlist objects may not have `uri`.
                playlist_url = getattr(tracks, "uri", None)
                if not playlist_url:
                    first = tracks.tracks[0] if getattr(tracks, "tracks", None) else None
                    playlist_url = getattr(first, "uri", None) if first else None
                if playlist_url:
                    desc = f"Added {added_count} tracks from [{tracks.name}]({playlist_url})"
                else:
                    desc = f"Added {added_count} tracks from {tracks.name}"
                embed = discord.Embed(title="Playlist Added to Queue", description=desc, color=discord.Color.green())
                await interaction.followup.send(embed=embed)
                logger.info(f"[{interaction.guild.id}] Queued playlist: {tracks.name} with {added_count} tracks")
                if not vc.playing and not vc.paused:
                    try:
                        await vc.play(vc.queue.get())
                    except Exception as e:
                        logger.warning(f"[{interaction.guild.id}] Failed to start playing playlist via context menu: {e}")
                        return await interaction.followup.send("Failed to play the playlist.", ephemeral=True)
                    else:
                        logger.info(f"[{interaction.guild.id}] Started playing playlist via context menu.")
                        if vc.panel_message:
                            await self.update_panel_message(vc)
            else:
                track = tracks[0]
                track.requester = interaction.user
                if vc.playing or not vc.queue.is_empty:
                    vc.queue.put(track)
                    embed = discord.Embed(title="Added to Queue", description=f"[{track.title}]({track.uri})", color=discord.Color.green())
                    await interaction.followup.send(embed=embed)
                else:
                    await vc.play(track)
                if not vc.panel_message:
                    vc.panel_message = await interaction.followup.send(embed=await self.build_embed(vc), view=self.panel_view)
        except Exception as e:
            logger.warning(f"[{interaction.guild.id}] Context-menu play failed: {e}")
            await interaction.followup.send("An error occurred while trying to play that link.", ephemeral=True)

async def setup(bot):
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
    @app_commands.context_menu(name="Play/Queue Song Link")
    async def play_track_context_menu(interaction: discord.Interaction, message: discord.Message):
        url_match = re.search(r'https?://\S+', message.content)
        if not url_match:
            return await interaction.response.send_message("No valid URL found in that message.", ephemeral=True)
        url = url_match.group(0)
        await music_cog._play_from_url(interaction, url)
    bot.tree.add_command(play_track_context_menu)
    await bot.tree.sync()
    bot.loop.create_task(music_cog.connect_to_nodes())
    if not hasattr(bot, 'music_panel_view'):
        bot.music_panel_view = music_cog.panel_view
        for item in bot.music_panel_view.children:
            if item.custom_id == 'music:repeat_toggle' and isinstance(item, discord.ui.Button):
                item.style = discord.ButtonStyle.secondary
        bot.add_view(bot.music_panel_view)