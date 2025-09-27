import discord
from discord.ext import commands, tasks
import wavelink
import typing
from main import logger 
from settings import LAVALINK_URI, LAVALINK_PASSWORD, PREFIX

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
    """Dropdown menu for volume control (10% to 100%)."""
    def __init__(self, cog: 'Music'):
        self.cog = cog
        
        options = [
            discord.SelectOption(label=f"{i}%", value=str(i)) 
            for i in range(10, 101, 10)
        ]

        super().__init__(
            placeholder="Select Volume (Current: ?%)",
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
            logger.info(f"Volume set to {new_volume}%")
            
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
        logger.info("Music cog loaded")

    def cog_unload(self):
        logger.info("Music cog unloaded")

    async def connect_to_nodes(self):
        """Connects to the Lavalink node using the correct wavelink.Pool syntax."""
        await self.bot.wait_until_ready()

        try:
            node = wavelink.Node(
                uri=LAVALINK_URI, 
                password=LAVALINK_PASSWORD
            )
            
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
        
        # 🎯 CRITICAL FIX: Always get the view from the original instance (self.panel_view) 
        # when we are editing the message *without* an interaction.
        # When we *have* an interaction, we let the response handle the view object.
        view_to_send = self.panel_view
        
        # The logic to update the state of the view items (volume placeholder, repeat button color)
        # must be run on the specific view instance we are about to send/edit with.
        # If we are using an interaction (like a button click), the view passed back to us 
        # by discord's API is the one being used. If we are doing a background edit (like track_end), 
        # we update the persistent view.
        
        for item in view_to_send.children:
            if isinstance(item, VolumeSelect):
                # Update placeholder to show current volume
                item.placeholder = f"Select Volume (Current: {vc.volume}%)"
                # Set the current volume as the default selected option
                for option in item.options:
                    # We must set .default on the persistent view item *before* sending it!
                    option.default = (option.value == str(vc.volume))
            elif item.custom_id == 'music:repeat_toggle' and isinstance(item, discord.ui.Button):
                # Ensure the repeat button color is correct
                item.style = discord.ButtonStyle.green if vc.repeat_track else discord.ButtonStyle.gray
                
        # --- SEND/EDIT LOGIC ---
        if interaction and not interaction.response.is_done():
            # Use interaction to edit the message, using the instance Discord provides
            # (which is already configured by the loop above via the reference 'view_to_send' being self.panel_view)
            await interaction.response.edit_message(embed=new_embed, view=view_to_send)
        else:
            # Use message.edit for non-interaction updates (e.g., track_end, play command)
            try:
                await vc.panel_message.edit(embed=new_embed, view=view_to_send)
            except discord.HTTPException as e:
                if e.status != 404: 
                    logger.error(f"Failed to edit panel message: {e}")
                else:
                    vc.panel_message = None 
        
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
        logger.info(f"Lavalink Node '{payload.node.identifier}' ready at {payload.node.uri}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: CustomPlayer = payload.player
        current_track = payload.track

        if player.repeat_track and current_track:
            await player.play(current_track, start=0) 
            if player.panel_message:
                await self.update_panel_message(player)
            return

        if player.queue.is_empty:
            await player.disconnect()
            if player.panel_message:
                try: await player.panel_message.delete()
                except: pass
                player.panel_message = None
            return

        next_track = player.queue.get()
        await player.play(next_track)
        if player.panel_message:
            await self.update_panel_message(player)

    # --- Logic Functions ---
    async def disconnect_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc: return
        await vc.disconnect()
        if vc.panel_message:
            try: await vc.panel_message.delete()
            except: pass
            vc.panel_message = None
        await reply("Playback stopped and I left the channel!")
        logger.info(f"Disconnected from {vc.channel}")

    async def skip_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc or not vc.playing: return await reply("Nothing is playing to skip!")
        await vc.stop() 

    async def pause_resume_logic(self, interaction_or_ctx):
        vc, reply = await self.get_player_and_validate(interaction_or_ctx)
        if not vc or not vc.playing: return await reply("Nothing is playing to pause/resume! ⏸️▶️")
        await vc.pause(not vc.paused)
        status = "Paused" if vc.paused else "Resumed"
        
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
            vc = await ctx.author.voice.channel.connect(cls=CustomPlayer)
            vc.text_channel = ctx.channel

        if not vc.panel_message:
            # Send initial panel message with the persistent view
            vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
            # Then update the placeholder immediately after sending
            await self.update_panel_message(vc)

        tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.YouTube)

        if not tracks: return await ctx.send(f"❌ No music found for `{search}`!")
        track = tracks[0]

        if vc.playing or vc.paused: 
            vc.queue.put(track)
            await ctx.send(f"**Queued:** `{track.title}` - Position **{len(vc.queue)}**")
        else:
            await vc.play(track)
            if vc.panel_message:
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
            
        # 🎯 FIX: Use the existing, persistent self.panel_view instance!
        vc.panel_message = await ctx.send(embed=await self.build_embed(vc), view=self.panel_view)
        await self.update_panel_message(vc) # Update button/select colors/defaults


async def setup(bot):
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
    
    bot.loop.create_task(music_cog.connect_to_nodes())
    
    # This block ensures persistence across bot restarts
    if not hasattr(bot, 'music_panel_view'):
        bot.music_panel_view = music_cog.panel_view
        
        for item in bot.music_panel_view.children:
            if item.custom_id == 'music:repeat_toggle' and isinstance(item, discord.ui.Button):
                item.style = discord.ButtonStyle.gray # Default state on startup
                
        # Re-add the view so Discord knows to listen for its custom IDs
        bot.add_view(bot.music_panel_view)