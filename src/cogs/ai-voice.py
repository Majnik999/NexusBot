import os
import asyncio
import tempfile
from typing import Dict, Optional, Any

import discord
from discord.ext import commands

from main import logger
from settings import PREFIX

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None

# Optional internal ffmpeg provider (downloads a static binary automatically)
_FFMPEG_INTERNAL_PATH: Optional[str] = None
try:
    import imageio_ffmpeg
    _FFMPEG_INTERNAL_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _FFMPEG_INTERNAL_PATH = None


def _get_ffmpeg_executable() -> Optional[str]:
    """Return a usable ffmpeg executable path.

    Priority:
    1) FFMPEG_EXE env var
    2) System PATH (ffmpeg)
    3) imageio-ffmpeg internal binary (auto-downloaded)
    """
    env_path = os.getenv("FFMPEG_EXE")
    if env_path and os.path.exists(env_path):
        return env_path
    from shutil import which
    sys_path = which("ffmpeg")
    if sys_path:
        return sys_path
    if _FFMPEG_INTERNAL_PATH and os.path.exists(_FFMPEG_INTERNAL_PATH):
        return _FFMPEG_INTERNAL_PATH
    return None


def _chunk_text(text: str, max_len: int = 350) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for piece in text.replace("\n", " ").split(" "):
        if length + len(piece) + 1 > max_len:
            parts.append(" ".join(current))
            current = [piece]
            length = len(piece)
        else:
            current.append(piece)
            length += len(piece) + 1
    if current:
        parts.append(" ".join(current))
    return parts


class GuildAIVoiceSession:
    """State for an AI voice session in a guild."""

    def __init__(self, guild_id: int, text_channel: discord.TextChannel, voice_client: discord.VoiceClient,
                 tts_lang: str, ffmpeg_exe: Optional[str]):
        self.guild_id = guild_id
        self.text_channel = text_channel
        self.voice_client = voice_client
        self.tts_lang = tts_lang
        self.ffmpeg_exe = ffmpeg_exe

        # Audio queue and worker
        self.audio_queue: asyncio.Queue[str] = asyncio.Queue()
        self.player_task: Optional[asyncio.Task] = None

        # Gemini chat sessions per user-id to maintain personal context
        self.user_chats: Dict[int, Any] = {}

        # Keep track of last bot message for reply following
        self.last_bot_message_id: Optional[int] = None

    def set_last_bot_message(self, message: discord.Message):
        self.last_bot_message_id = message.id


class AIVoice(commands.Cog):
    """Owner-activated AI voice chat using Gemini + free TTS (gTTS).

    Uses an internal FFmpeg binary via imageio-ffmpeg when system FFmpeg is unavailable.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: Dict[int, GuildAIVoiceSession] = {}

        # Configure Gemini
        if genai is None:
            logger.warning("google-generativeai is not installed. AI responses will be unavailable.")
            self.model = None
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY not set in environment. AI Voice will not respond until set.")
                self.model = None
            else:
                try:
                    genai.configure(api_key=api_key)
                    self.model = genai.GenerativeModel("gemini-1.5-flash")
                except Exception as e:
                    logger.error(f"Failed to initialize Gemini model: {e}")
                    self.model = None

        # TTS language and ffmpeg executable
        self.tts_lang_default = os.getenv("VOICE_LANGUAGE", "en")
        self.ffmpeg_exe = _get_ffmpeg_executable()
        if self.ffmpeg_exe:
            logger.info(f"AI Voice using FFmpeg executable: {self.ffmpeg_exe}")
        else:
            logger.error("No FFmpeg available (PATH/env/internal). Audio playback will fail. Install imageio-ffmpeg or set FFMPEG_EXE.")

        # Optional STT via Vosk (offline & free) if installed
        self._vosk_available = False
        try:
            import vosk  # noqa: F401
            self._vosk_available = True
        except Exception:
            self._vosk_available = False

    # --------------- Helper methods ---------------
    def _get_or_create_chat(self, session: GuildAIVoiceSession, user_id: int):
        chat = session.user_chats.get(user_id)
        if chat is None and self.model is not None:
            try:
                chat = self.model.start_chat(history=[])
                session.user_chats[user_id] = chat
            except Exception as e:
                logger.error(f"Gemini start_chat failed: {e}")
                return None
        return chat

    async def _ensure_player_task(self, session: GuildAIVoiceSession):
        if session.player_task and not session.player_task.done():
            return

        async def _player():
            try:
                while True:
                    path = await session.audio_queue.get()
                    if not session.voice_client or not session.voice_client.is_connected():
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                        continue

                    # Play with FFmpeg (internal if available)
                    try:
                        source = discord.FFmpegPCMAudio(path, executable=session.ffmpeg_exe, before_options="-nostdin", options="-vn")
                        session.voice_client.play(source)
                        while session.voice_client.is_playing():
                            await asyncio.sleep(0.2)
                    except Exception as e:
                        logger.error(f"FFmpeg playback error: {e}")
                    finally:
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                        session.audio_queue.task_done()
            except asyncio.CancelledError:
                pass

        session.player_task = self.bot.loop.create_task(_player())

    async def _enqueue_tts(self, session: GuildAIVoiceSession, text: str):
        if gTTS is None:
            logger.error("gTTS not installed; cannot speak. Add `gTTS` to requirements.txt.")
            return
        for chunk in _chunk_text(text):
            try:
                tts = gTTS(chunk, lang=session.tts_lang)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tts.save(fp.name)
                    await session.audio_queue.put(fp.name)
            except Exception as e:
                logger.error(f"gTTS failed: {e}")
        await self._ensure_player_task(session)

    async def _generate_reply(self, chat, prompt: str) -> str:
        if chat is None:
            return "AI is not configured yet. Ask the owner to set GEMINI_API_KEY."
        try:
            resp = await asyncio.to_thread(chat.send_message, prompt)
            content = getattr(resp, "text", None)
            if not content:
                try:
                    content = resp.candidates[0].content.parts[0].text  # type: ignore[attr-defined]
                except Exception:
                    content = "(No response)"
            return content
        except Exception as e:
            logger.error(f"Gemini send_message error: {e}")
            return "Sorry, I encountered an error generating a response."

    async def _stop_session(self, guild_id: int):
        session = self.sessions.pop(guild_id, None)
        if not session:
            return False
        try:
            if session.player_task and not session.player_task.done():
                session.player_task.cancel()
            if session.voice_client and session.voice_client.is_connected():
                try:
                    session.voice_client.stop()
                except Exception:
                    pass
                await session.voice_client.disconnect(force=True)
        except Exception as e:
            logger.error(f"Error stopping AI voice session: {e}")
        return True

    # --------------- Owner Commands ---------------
    @commands.group(name="voiceai", aliases=("aivoice",), invoke_without_command=True)
    @commands.is_owner()
    async def voiceai(self, ctx: commands.Context):
        msg = (
            f"AI Voice Chat (Gemini + gTTS)\n"
            f"Commands:\n"
            f"- {PREFIX}voiceai start [#text-channel]\n"
            f"- {PREFIX}voiceai stop\n"
            f"- {PREFIX}voiceai status\n"
            f"- {PREFIX}voiceai lang <code> (e.g., en, en-GB)\n\n"
            f"Note: FFmpeg is handled automatically via imageio-ffmpeg if not on PATH."
        )
        await ctx.send(msg)

    @voiceai.command(name="start")
    @commands.is_owner()
    async def voiceai_start(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("You must be connected to a voice channel to start the AI voice session.")

        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")

        if guild.voice_client and guild.voice_client.is_connected():
            return await ctx.send("I am already connected to a voice channel (possibly music). Please stop that first.")

        if self.ffmpeg_exe is None:
            # Try again in case imageio-ffmpeg became available at runtime
            self.ffmpeg_exe = _get_ffmpeg_executable()
            if self.ffmpeg_exe is None:
                return await ctx.send("❌ FFmpeg is not available. Set FFMPEG_EXE env var or install imageio-ffmpeg.")

        voice_channel = ctx.author.voice.channel
        try:
            vc = await voice_channel.connect(reconnect=True)
        except Exception as e:
            logger.error(f"Failed to connect to voice: {e}")
            return await ctx.send("Failed to join voice channel. Ensure the bot has voice permissions.")

        text_channel = channel or ctx.channel
        session = GuildAIVoiceSession(
            guild_id=guild.id,
            text_channel=text_channel,
            voice_client=vc,
            tts_lang=self.tts_lang_default,
            ffmpeg_exe=self.ffmpeg_exe,
        )
        self.sessions[guild.id] = session

        await self._ensure_player_task(session)
        await ctx.send(
            f"✅ AI voice session started in {voice_channel.mention}. Listening in {text_channel.mention}.\n"
            f"Mention me or use `{PREFIX}ai chat <message>` here, and I'll speak back in voice."
        )

    @voiceai.command(name="stop")
    @commands.is_owner()
    async def voiceai_stop(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")
        ok = await self._stop_session(guild.id)
        if ok:
            await ctx.send("🛑 Stopped AI voice session and disconnected.")
        else:
            await ctx.send("No active AI voice session to stop.")

    @voiceai.command(name="status")
    @commands.is_owner()
    async def voiceai_status(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")
        session = self.sessions.get(guild.id)
        if not session:
            return await ctx.send("No active AI voice session.")
        await ctx.send(
            f"Session in voice: `{session.voice_client.channel}` | text: {session.text_channel.mention} | "
            f"queue: `{session.audio_queue.qsize()}` | TTS lang: `{session.tts_lang}` | "
            f"FFmpeg: `{session.ffmpeg_exe or 'None'}` | Vosk STT installed: `{self._vosk_available}`"
        )

    @voiceai.command(name="lang")
    @commands.is_owner()
    async def voiceai_lang(self, ctx: commands.Context, code: str):
        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")
        session = self.sessions.get(guild.id)
        if not session:
            self.tts_lang_default = code
            return await ctx.send(f"Default TTS language set to `{code}`.")
        session.tts_lang = code
        await ctx.send(f"TTS language updated to `{code}` for the current session.")

    # --------------- Public AI Commands ---------------
    @commands.group(name="ai", invoke_without_command=True)
    async def ai_group(self, ctx: commands.Context):
        await ctx.send(
            f"Use `{ctx.prefix}ai chat <message>` to talk to the AI. I will respond in voice.\n"
            f"You can also send a voice message attachment in this channel."
        )

    @ai_group.command(name="chat")
    async def ai_chat(self, ctx: commands.Context, *, message: str):
        guild = ctx.guild
        if not guild:
            return
        session = self.sessions.get(guild.id)
        if not session:
            return await ctx.send("ℹ️ AI Voice is not active. Ask the owner to run `voiceai start`.")
        if ctx.channel.id != session.text_channel.id:
            return await ctx.send("ℹ️ Please chat in the channel where AI Voice is linked.")
        chat = self._get_or_create_chat(session, ctx.author.id)
        reply_text = await self._generate_reply(chat, message)
        await self._enqueue_tts(session, reply_text)
        bot_msg = await session.text_channel.send(f"🤖 {reply_text}")
        session.set_last_bot_message(bot_msg)

    @ai_group.command(name="say")
    async def ai_say(self, ctx: commands.Context, *, message: str):
        guild = ctx.guild
        if not guild:
            return
        session = self.sessions.get(guild.id)
        if not session:
            return await ctx.send("ℹ️ AI Voice is not active. Ask the owner to run `voiceai start`.")
        if ctx.channel.id != session.text_channel.id:
            return await ctx.send("ℹ️ Please use this in the linked text channel.")
        await self._enqueue_tts(session, message)
        await ctx.message.add_reaction("🔊")

    # --------------- Message Listener ---------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        guild = message.guild
        if not guild:
            return
        session = self.sessions.get(guild.id)
        if not session:
            return
        if message.channel.id != session.text_channel.id:
            return

        # Trigger if bot mentioned or reply to last bot message
        mentioned_bot = self.bot.user.mentioned_in(message) if self.bot.user else False
        is_reply_to_bot = False
        if message.reference and message.reference.message_id and session.last_bot_message_id:
            is_reply_to_bot = message.reference.message_id == session.last_bot_message_id

        if not (mentioned_bot or is_reply_to_bot or message.content.startswith(f"{PREFIX}ai chat")):
            return

        user_text: Optional[str] = None

        audio_attachments = [a for a in message.attachments if (a.content_type or "").startswith("audio/")]
        if audio_attachments and self._vosk_available:
            try:
                data = await audio_attachments[0].read()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as fp:
                    fp.write(data)
                    path = fp.name
                user_text = await self._transcribe_with_vosk(path)
                try:
                    os.remove(path)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to process audio attachment: {e}")

        if not user_text:
            content = message.content
            if self.bot.user:
                content = content.replace(self.bot.user.mention, "").strip()
            user_text = content

        if not user_text:
            return

        chat = self._get_or_create_chat(session, message.author.id)
        reply_text = await self._generate_reply(chat, user_text)
        await self._enqueue_tts(session, reply_text)
        bot_msg = await session.text_channel.send(f"{message.author.mention} {reply_text}")
        session.set_last_bot_message(bot_msg)

    # --------------- Optional STT (Vosk) ---------------
    async def _transcribe_with_vosk(self, audio_path: str) -> Optional[str]:
        if not self._vosk_available:
            return None
        try:
            import subprocess
            import json
            model_path = os.getenv("VOSK_MODEL")
            if not model_path:
                return None

            # Convert to mono 16k PCM WAV using FFmpeg (internal if needed)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as out_wav:
                out_path = out_wav.name
            cmd = [self.ffmpeg_exe or "ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", "-f", "wav", out_path]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                return None

            import vosk
            rec = vosk.KaldiRecognizer(vosk.Model(model_path), 16000)
            with open(out_path, "rb") as f:
                while True:
                    data = f.read(4000)
                    if len(data) == 0:
                        break
                    rec.AcceptWaveform(data)
            result = json.loads(rec.FinalResult())
            text = result.get("text")
            try:
                os.remove(out_path)
            except Exception:
                pass
            return text or None
        except Exception as e:
            logger.error(f"Vosk transcription error: {e}")
            return None

    async def cog_unload(self):
        tasks = [self._stop_session(gid) for gid in list(self.sessions.keys())]
        await asyncio.gather(*tasks, return_exceptions=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIVoice(bot))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIVoice(bot))
import os
import io
import asyncio
import tempfile
from typing import Dict, Optional, Any

import discord
from discord.ext import commands

# External libs
import google.generativeai as genai  # Gemini
from gtts import gTTS  # Free TTS

from main import logger
from settings import PREFIX


def _chunk_text(text: str, max_len: int = 350) -> list[str]:
    """Split text into chunks safe for gTTS and voice playback."""
    # Simple sentence-based chunking
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for piece in text.replace("\n", " ").split(" "):
        if length + len(piece) + 1 > max_len:
            parts.append(" ".join(current))
            current = [piece]
            length = len(piece)
        else:
            current.append(piece)
            length += len(piece) + 1
    if current:
        parts.append(" ".join(current))
    return parts


class GuildAIVoiceSession:
    """State for an AI voice session in a guild."""
    def __init__(self, guild_id: int, text_channel: discord.TextChannel, voice_client: discord.VoiceClient,
                 tts_lang: str, ffmpeg_exe: Optional[str] = None):
        self.guild_id = guild_id
        self.text_channel = text_channel
        self.voice_client = voice_client
        self.tts_lang = tts_lang
        self.ffmpeg_exe = ffmpeg_exe

        # Audio queue and worker
        self.audio_queue: asyncio.Queue[str] = asyncio.Queue()
        self.player_task: Optional[asyncio.Task] = None

        # Gemini chat sessions per user-id to maintain personal context
        self.user_chats: Dict[int, Any] = {}

        # Keep track of last bot message for reply following
        self.last_bot_message_id: Optional[int] = None

    def set_last_bot_message(self, message: discord.Message):
        self.last_bot_message_id = message.id


class AIVoice(commands.Cog):
    """Owner-activated AI voice chat using Gemini + free TTS (gTTS)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: Dict[int, GuildAIVoiceSession] = {}

        # Configure Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set in environment. AI Voice will not respond until set.")
        genai.configure(api_key=api_key)
        # Lightweight, fast model for chat
        try:
            self.model = genai.GenerativeModel("gemini-1.5-flash")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {e}")
            self.model = None

        # TTS language and ffmpeg executable
        self.tts_lang_default = os.getenv("VOICE_LANGUAGE", "en")
        self.ffmpeg_exe = os.getenv("FFMPEG_EXE")  # optional; else discord.py will try system ffmpeg

        # Optional STT via Vosk (offline & free) if installed
        self._vosk_available = False
        try:
            import vosk  # noqa: F401
            self._vosk_available = True
        except Exception:
            self._vosk_available = False

    # --------------- Helper methods ---------------
    def _get_or_create_chat(self, session: GuildAIVoiceSession, user_id: int):
        chat = session.user_chats.get(user_id)
        if chat is None and self.model is not None:
            try:
                chat = self.model.start_chat(history=[])
                session.user_chats[user_id] = chat
            except Exception as e:
                logger.error(f"Gemini start_chat failed: {e}")
                return None
        return chat

    async def _ensure_player_task(self, session: GuildAIVoiceSession):
        if session.player_task and not session.player_task.done():
            return

        async def _player():
            try:
                while True:
                    path = await session.audio_queue.get()
                    if not session.voice_client or not session.voice_client.is_connected():
                        # If not connected, drop audio
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                        continue

                    # Play with FFmpeg
                    try:
                        source = discord.FFmpegPCMAudio(path, executable=session.ffmpeg_exe)
                        session.voice_client.play(source)
                        while session.voice_client.is_playing():
                            await asyncio.sleep(0.2)
                    except Exception as e:
                        logger.error(f"FFmpeg playback error: {e}")
                    finally:
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                        session.audio_queue.task_done()
            except asyncio.CancelledError:
                pass

        session.player_task = self.bot.loop.create_task(_player())

    async def _enqueue_tts(self, session: GuildAIVoiceSession, text: str):
        for chunk in _chunk_text(text):
            # Generate TTS audio to a temp file
            try:
                tts = gTTS(chunk, lang=session.tts_lang)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tts.save(fp.name)
                    await session.audio_queue.put(fp.name)
            except Exception as e:
                logger.error(f"gTTS failed: {e}")

        await self._ensure_player_task(session)

    async def _generate_reply(self, chat, prompt: str) -> str:
        if chat is None:
            return "AI is not configured yet. Ask the owner to set GEMINI_API_KEY."
        try:
            resp = await asyncio.to_thread(chat.send_message, prompt)
            # google-generativeai returns text via .text
            content = getattr(resp, "text", None)
            if not content:
                # Fallback to candidates
                try:
                    content = resp.candidates[0].content.parts[0].text  # type: ignore[attr-defined]
                except Exception:
                    content = "(No response)"
            return content
        except Exception as e:
            logger.error(f"Gemini send_message error: {e}")
            return "Sorry, I encountered an error generating a response."

    async def _stop_session(self, guild_id: int):
        session = self.sessions.pop(guild_id, None)
        if not session:
            return False
        try:
            # Cancel player task
            if session.player_task and not session.player_task.done():
                session.player_task.cancel()
            # Stop and disconnect
            if session.voice_client and session.voice_client.is_connected():
                try:
                    session.voice_client.stop()
                except Exception:
                    pass
                await session.voice_client.disconnect(force=True)
        except Exception as e:
            logger.error(f"Error stopping AI voice session: {e}")
        return True

    # --------------- Commands ---------------
    @commands.group(name="voiceai", invoke_without_command=True)
    @commands.is_owner()
    async def voiceai(self, ctx: commands.Context):
        """Owner-only controls for AI voice chat."""
        msg = (
            f"AI Voice Chat (Gemini + gTTS)\n"
            f"Commands:\n"
            f"- {PREFIX}voiceai start [#text-channel]\n"
            f"- {PREFIX}voiceai stop\n"
            f"- {PREFIX}voiceai status\n"
            f"- {PREFIX}voiceai lang <code> (e.g., en, en-GB)\n\n"
            f"Usage: Activate in any server voice channel. Users can talk by mentioning the bot or replying to it in the linked text channel."
        )
        await ctx.send(msg)

    @voiceai.command(name="start")
    @commands.is_owner()
    async def voiceai_start(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("You must be connected to a voice channel to start the AI voice session.")

        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")

        # Prevent conflict with existing voice client (e.g., music)
        if guild.voice_client and guild.voice_client.is_connected():
            return await ctx.send("I am already connected to a voice channel (possibly music). Please stop that first.")

        voice_channel = ctx.author.voice.channel
        try:
            vc = await voice_channel.connect(reconnect=True)
        except Exception as e:
            logger.error(f"Failed to connect to voice: {e}")
            return await ctx.send("Failed to join voice channel. Ensure the bot has voice permissions.")

        text_channel = channel or ctx.channel
        session = GuildAIVoiceSession(
            guild_id=guild.id,
            text_channel=text_channel,
            voice_client=vc,
            tts_lang=self.tts_lang_default,
            ffmpeg_exe=self.ffmpeg_exe,
        )
        self.sessions[guild.id] = session

        await self._ensure_player_task(session)
        await ctx.send(
            f"✅ AI voice session started in {voice_channel.mention}. Listening in {text_channel.mention}.\n"
            f"Mention me or reply to my messages there, and I'll speak back in voice."
        )

    @voiceai.command(name="stop")
    @commands.is_owner()
    async def voiceai_stop(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")
        ok = await self._stop_session(guild.id)
        if ok:
            await ctx.send("🛑 Stopped AI voice session and disconnected.")
        else:
            await ctx.send("No active AI voice session to stop.")

    @voiceai.command(name="status")
    @commands.is_owner()
    async def voiceai_status(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")
        session = self.sessions.get(guild.id)
        if not session:
            return await ctx.send("No active AI voice session.")
        await ctx.send(
            f"Session in voice: `{session.voice_client.channel}` | text: {session.text_channel.mention} | "
            f"queue: `{session.audio_queue.qsize()}` | TTS lang: `{session.tts_lang}` | Vosk STT installed: `{self._vosk_available}`"
        )

    @voiceai.command(name="lang")
    @commands.is_owner()
    async def voiceai_lang(self, ctx: commands.Context, code: str):
        guild = ctx.guild
        if not guild:
            return await ctx.send("This command must be used in a server.")
        session = self.sessions.get(guild.id)
        if not session:
            self.tts_lang_default = code
            return await ctx.send(f"Default TTS language set to `{code}`.")
        session.tts_lang = code
        await ctx.send(f"TTS language updated to `{code}` for the current session.")

    # --------------- Message Listener ---------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        guild = message.guild
        if not guild:
            return
        session = self.sessions.get(guild.id)
        if not session:
            return
        if message.channel.id != session.text_channel.id:
            return

        # Trigger if bot mentioned or replying to bot's last message
        mentioned_bot = self.bot.user.mentioned_in(message)
        is_reply_to_bot = False
        if message.reference and message.reference.message_id and session.last_bot_message_id:
            is_reply_to_bot = message.reference.message_id == session.last_bot_message_id

        if not (mentioned_bot or is_reply_to_bot):
            return

        # Text is either message content without mention or via STT from audio attachment
        user_text: Optional[str] = None

        # Prefer audio attachment (Discord voice messages are audio/ogg; content_type starts with 'audio/')
        audio_attachments = [a for a in message.attachments if (a.content_type or "").startswith("audio/")]
        if audio_attachments and self._vosk_available:
            try:
                # Download the first audio attachment for transcription
                data = await audio_attachments[0].read()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as fp:
                    fp.write(data)
                    path = fp.name
                # Transcribe via Vosk (if installed)
                user_text = await self._transcribe_with_vosk(path)
                try:
                    os.remove(path)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to process audio attachment: {e}")

        if not user_text:
            # Fallback to plain text; remove bot mention
            content = message.content
            if self.bot.user:
                content = content.replace(self.bot.user.mention, "").strip()
            user_text = content

        if not user_text:
            return

        chat = self._get_or_create_chat(session, message.author.id)
        reply_text = await self._generate_reply(chat, user_text)

        # Enqueue TTS and respond in text channel
        await self._enqueue_tts(session, reply_text)
        bot_msg = await session.text_channel.send(f"{message.author.mention} {reply_text}")
        session.set_last_bot_message(bot_msg)

    # --------------- Optional STT (Vosk) ---------------
    async def _transcribe_with_vosk(self, audio_path: str) -> Optional[str]:
        if not self._vosk_available:
            return None
        try:
            # Lazy import to avoid hard dependency
            import subprocess
            import json
            # Vosk usage here assumes ffmpeg converts to PCM WAV for recognition.
            # Requires vosk model path from env VOSK_MODEL (optional). If not present, return None.
            model_path = os.getenv("VOSK_MODEL")
            if not model_path:
                return None

            # Convert to mono 16k PCM WAV
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as out_wav:
                out_path = out_wav.name
            cmd = [self.ffmpeg_exe or "ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", "-f", "wav", out_path]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                return None

            # Minimal Vosk transcription
            import vosk
            rec = vosk.KaldiRecognizer(vosk.Model(model_path), 16000)
            with open(out_path, "rb") as f:
                while True:
                    data = f.read(4000)
                    if len(data) == 0:
                        break
                    rec.AcceptWaveform(data)
            result = json.loads(rec.FinalResult())
            text = result.get("text")
            try:
                os.remove(out_path)
            except Exception:
                pass
            return text or None
        except Exception as e:
            logger.error(f"Vosk transcription error: {e}")
            return None

    # --------------- Cleanup ---------------
    async def cog_unload(self):
        # Stop all sessions gracefully
        tasks = [self._stop_session(gid) for gid in list(self.sessions.keys())]
        await asyncio.gather(*tasks, return_exceptions=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIVoice(bot))