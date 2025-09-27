import discord
from discord.ext import commands, tasks
import wavelink
import typing
from main import logger 
from settings import LAVALINK_URI, LAVALINK_PASSWORD

# --- 1. Custom Player Class ---
class CustomPlayer(wavelink.Player):
    """A custom Wavelink Player that tracks the control panel message and queue."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text_channel: typing.Optional[discord.TextChannel] = None
        self.panel_message: typing.Optional[discord.Message] = None


# --- 2. Panel Buttons (View) ---
class MusicPanel(discord.ui.View):
    """The persistent view for the music control panel."""
    def __init__(self, cog: 'Music'):
        super().__init__(timeout=None)
        self.cog = cog

    async def _update_panel(self, interaction: discord.Interaction, vc: 'CustomPlayer'):
        """Helper to update the panel after any button interaction."""
        new_embed = await self.cog.build_embed(vc)
        # Use edit_message to stop the ephemeral reply from showing
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.red, custom_id='music:stop_disconnect')
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge the interaction immediately
        await interaction.response.defer()
        await self.cog.disconnect_logic(interaction)

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.secondary, custom_id='music:skip')
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return 
        
        # Acknowledge interaction (to stop the reply) and then run logic that sends a message
        await interaction.response.defer() 
        await self.cog.skip_logic(interaction)

    @discord.ui.button(label='Pause/Resume', style=discord.ButtonStyle.green, custom_id='music:pause_resume')
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return
        
        await self.cog.pause_resume_logic(interaction) # Logic handles the pause/resume
        await self._update_panel(interaction, vc) # Update the panel immediately

    @discord.ui.button(label='+10%', style=discord.ButtonStyle.blurple, custom_id='music:vol_up')
    async def vol_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return
        
        await self.cog.volume_change_logic(interaction, change=10)
        await self._update_panel(interaction, vc)

    @discord.ui.button(label='-10%', style=discord.ButtonStyle.blurple, custom_id='music:vol_down')
    async def vol_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return

        await self.cog.volume_change_logic(interaction, change=-10)
        await self._update_panel(interaction, vc)

    @discord.ui.button(label='Refresh 🔄', style=discord.ButtonStyle.grey, custom_id='music:refresh_panel')
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, reply = await self.cog.get_player_and_validate(interaction)
        if not vc: return
        
        # Simply update the panel!
        await self._update_panel(interaction, vc)


# --- 3. Main Music Cog ---
class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.panel_view = MusicPanel(self)
        logger.info("Music cog loaded")

    def cog_unload(self):
        logger.info("Music cog unloaded")

    async def connect_to_nodes(self):
        """Connects to the Lavalink node using the correct wavelink.Pool syntax."""
        await self.bot.wait_until_ready()

        try:
            # Create the Node object
            node = wavelink.Node(
                uri=LAVALINK_URI, # Correct URI format
                password=LAVALINK_PASSWORD
            )
            
            # Connect the Node Pool to the defined node
            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            logger.info(f"Attempting to connect to Lavalink node at {node.uri}")
            
        except Exception as e:
            logger.error(f"Failed to connect Lavalink node: {e}")
            
    # --- Helper Functions ---
    async def get_player_and_validate(self, interaction_or_ctx):
        if isinstance(interaction_or_ctx, discord.Interaction):
            guild = interaction_or_ctx.guild
            user_voice = interaction_or_ctx.user.voice
            async def reply(msg):
                # Use follow up for messages after defer, or send ephemeral for immediate replies on validation failure
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

    async def build_embed(self, vc: CustomPlayer) -> discord.Embed:
        def format_time(ms):
            seconds = int(ms / 1000)
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                return f"{hours}:{minutes:02}:{seconds:02}"
            return f"{minutes:02}:{seconds:02}"

        # FIX: Use vc.playing
        if vc and vc.playing:
            track = vc.current
            time_string = f"{format_time(vc.position)} / {format_time(track.length)}"
            status = "⏸️ Paused" if vc.paused else "▶️ Playing"

            embed = discord.Embed(
                title=f"{status} | {track.title}",
                url=track.uri,
                color=discord.Color.blue()
            )
            embed.set_author(name="Music Control Panel")
            embed.add_field(name="Queue Size", value=f"{len(vc.queue)} tracks", inline=True)
            embed.add_field(name="Volume", value=f"{vc.volume}%", inline=True)
            embed.add_field(name="Progress", value=f"`{time_string}`", inline=False)
            embed.set_thumbnail(url=getattr(track, "thumbnail", None))
        else:
            embed = discord.Embed(
                title="Nothing is currently playing. 🎵",
                description="Use `!music play <song>` to start the music!",
                color=discord.Color.red()
            )
        return embed

    # --- Wavelink Listeners ---
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logger.info(f"Lavalink Node '{payload.node.identifier}' ready at {payload.node.uri}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: CustomPlayer = payload.player
        if player.queue.is_empty:
            # Disconnect bot after queue ends
            await player.disconnect()
            if player.panel_message:
                try:
                    # Clear the panel when music stops
                    await player.panel_message.delete()
                except: pass
                player.panel_message = None
            return

        next_track = player.queue.get()
        await player.play(next_track)
        if player.panel_message:
            await player.panel_message.edit(embed=await self.build_embed(player), view=self.panel_view)

    # --- Logic Functions ---
    async def disconnect_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc: return
        await vc.disconnect()
        if vc.panel_message:
            try: await vc.panel_message.delete()
            except: pass
            vc.panel_message = None
        await reply("Playback stopped and I left the channel! 👋")
        logger.info(f"Disconnected from {vc.channel}")

    async def skip_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        # FIX: Use vc.playing
        if not vc or not vc.playing: return await reply("Nothing is playing to skip! 🤷‍♀️")
        await vc.stop() # stop() triggers track_end, which handles the skip
        await reply("Skipping to the next song! ⏩")

    async def pause_resume_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        # FIX: Use vc.playing
        if not vc or not vc.playing: return await reply("Nothing is playing to pause/resume! ⏸️▶️")
        await vc.pause(not vc.paused)
        status = "Paused" if vc.paused else "Resumed"
        
        # Only send reply for context commands (not button interactions, which update the panel)
        if not isinstance(interaction_or_ctx, discord.Interaction):
            await reply(f"Playback **{status}**.")
            

    async def volume_change_logic(self, interaction_or_ctx, change: int):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc: return
        new_volume = max(0, min(100, vc.volume + change))
        await vc.set_volume(new_volume)
        
        # Only send reply for context commands (not button interactions, which update the panel)
        if not isinstance(interaction_or_ctx, discord.Interaction):
            await reply(f"Volume set to **{new_volume}%**.")

    # --- Music Command Group ---
    @commands.group(invoke_without_command=True, aliases=['m'])
    async def music(self, ctx: commands.Context):
        """Music commands group. Use subcommands like play, skip, pause, etc."""
        await ctx.send("Use subcommands: play, skip, pause, resume, volume, queue, stop, panel")

    @music.command(name="play", aliases=["pl"])
    async def play(self, ctx: commands.Context, *, search: str):
        vc: CustomPlayer = ctx.voice_client
        if not vc:
            if not ctx.author.voice: return await ctx.send("Join a VC first!")
            vc = await ctx.author.voice.channel.connect(cls=CustomPlayer)
            vc.text_channel = ctx.channel

        if not vc.panel_message:
                vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)

        # 🎯 FIX: Use wavelink.Playable.search and specify the source
        tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.YouTube)

        if not tracks: return await ctx.send(f"No music found for `{search}` 😔")
        track = tracks[0]

        # FIX: Use vc.playing
        if vc.playing or vc.paused: 
            vc.queue.put(track)
            await ctx.send(f"**Queued:** `{track.title}` - Position **{len(vc.queue)}**")
        else:
            await vc.play(track)
            # Update panel immediately after starting to play the first track
            if vc.panel_message:
                await vc.panel_message.edit(embed=await self.build_embed(vc), view=self.panel_view)
            
    @music.command(name="skip", aliases=['s'])
    async def skip_cmd(self, ctx: commands.Context):
        await self.skip_logic(ctx)

    @music.command(name="pause", aliases=['p'])
    async def pause_cmd(self, ctx: commands.Context):
        await self.pause_resume_logic(ctx)

    @music.command(name="resume", aliases=['r'])
    async def resume_cmd(self, ctx: commands.Context):
        await self.pause_resume_logic(ctx)

    @music.command(name="volume", aliases=['v'])
    async def volume_cmd(self, ctx: commands.Context, volume: int):
        vc: CustomPlayer = ctx.voice_client
        if not vc: return await ctx.send("I'm not in a VC!")
        if not 0 <= volume <= 100: return await ctx.send("Volume must be 0-100!")
        await self.volume_change_logic(ctx, volume - vc.volume)

    @music.command(name="stop", aliases=["disconnect"])
    async def stop_cmd(self, ctx: commands.Context):
        await self.disconnect_logic(ctx)

    @music.command(name="queue", aliases=['q'])
    async def queue_cmd(self, ctx: commands.Context):
        vc: CustomPlayer = ctx.voice_client
        if not vc or vc.queue.is_empty: return await ctx.send("Queue is empty! 😅")
        queue_list = "\n".join(f"`{i+1}.` **{track.title}**" for i, track in enumerate(vc.queue[:10]))
        embed = discord.Embed(title=f"Queue ({len(vc.queue)} tracks)", description=queue_list, color=discord.Color.gold())
        await ctx.send(embed=embed)

    @music.command(name="panel", aliases=['np'])
    async def panel_cmd(self, ctx: commands.Context):
        vc: CustomPlayer = ctx.voice_client
        if not vc: return await ctx.send("I need to be playing music to show the panel!")
        # If panel already exists, delete the old one
        if vc.panel_message:
            try: await vc.panel_message.delete()
            except: pass
        # Send a new one and save the reference
        vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)


async def setup(bot):
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
    
    # ⚡️ Start the connection task
    bot.loop.create_task(music_cog.connect_to_nodes())
    
    # Re-add the persistent view (buttons)
    if not hasattr(bot, 'music_panel_view'):
        bot.music_panel_view = music_cog.panel_view
        bot.add_view(bot.music_panel_view)