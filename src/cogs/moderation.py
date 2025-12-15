import discord
from discord.ext import commands
from settings import ADMIN_IDS, MAX_PURGE_LIMIT, CLEAR_COMMAND
import aiosqlite
import os
import asyncio
from datetime import timedelta
import re

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join("src", "databases", "user.db")
        # schedule DB initialization
        try:
            self.init_db()
        except Exception:
            pass

    @commands.command(name="clear", description="Deletes a specified number of messages.")
    @commands.bot_has_permissions(manage_messages=True)
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, messages: int):
        if not CLEAR_COMMAND: return
        if messages and messages <= 1:
            await ctx.send("⚠️ The specified number must be greater than 1!")
        
        await ctx.channel.purge(limit=messages + 1)
        
        await ctx.send(f"✅ Successfully cleared {messages} messages!", delete_after=5)
        
    @clear.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have permissions for deleting messages. Please check my permission!")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permissions for deleting messages. This is moderator only command!")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("⚠️ Missing required argument. Please double check the command!")
        else:
            await ctx.send("❌ An Unexpected Error occurred!")
            
    @commands.command(name="announce", description="Owner: DM everyone. In DMs use 'announce on/off' to toggle.")
    @commands.is_owner()
    async def announce(self, ctx, *, content: str):
        # initialize DB-backed preference storage (per-user)
        # DM-only toggle: "announce on" or "announce off" -> persist pref
        if ctx.guild is None and content.strip().lower() in ("on", "off"):
            enabled = content.strip().lower() == "on"
            await self.set_announce_pref(ctx.author.id, enabled)
            await ctx.send(f"✅ Announce set to {'on' if enabled else 'off'}.")
            return

        if not ctx.author.id in ADMIN_IDS:
            await ctx.send("❌ Only the bot owner can use this command.")
            return

        sent = 0
        failed = 0
        for user in set(self.bot.users):
            if user.bot:
                continue
            # check per-user preference; default to enabled
            try:
                pref = await self.get_announce_pref(user.id)
            except Exception:
                pref = 1
            if pref == 0:
                continue
            try:
                await user.send(content)
                sent += 1
            except Exception:
                failed += 1

        await ctx.send(f"✅ Announcement sent to {sent} users. Failed: {failed}.")

    async def init_db(self):
        # create announce table if missing
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS announce(
                        user_id INTEGER PRIMARY KEY,
                        enabled INTEGER NOT NULL
                    )
                    """
                )
                await db.commit()
        except Exception:
            pass

    async def set_announce_pref(self, user_id: int, enabled: bool):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO announce(user_id, enabled) VALUES(?, ?)",
                    (user_id, 1 if enabled else 0),
                )
                await db.commit()
        except Exception:
            pass

    async def get_announce_pref(self, user_id: int) -> int:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cur = await db.execute("SELECT enabled FROM announce WHERE user_id = ?", (user_id,))
                row = await cur.fetchone()
                if row is None:
                    return 1
                return int(row[0])
        except Exception:
            return 1

def parse_time_duration(duration_str: str) -> timedelta:
    """Parses a duration string (e.g., '1d', '3h', '30m') into a timedelta object."""
    if not duration_str:
        raise commands.BadArgument("Duration cannot be empty.")

    # Regex to match duration components: number followed by a unit (d, h, m, s)
    pattern = re.compile(r"(\d+)([dhms])")
    matches = pattern.findall(duration_str)

    if not matches:
        raise commands.BadArgument("Invalid duration format. Use e.g., '1d', '3h', '30m', '15s'.")

    total_seconds = 0
    for value_str, unit in matches:
        value = int(value_str)
        if unit == 'd':
            total_seconds += value * 86400  # 24 * 60 * 60
        elif unit == 'h':
            total_seconds += value * 3600   # 60 * 60
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value

    if total_seconds <= 0:
        raise commands.BadArgument("Duration must be a positive value.")

    return timedelta(seconds=total_seconds)
    
    @commands.command(name="ban", help="Bans a member, optionally for a specified duration (e.g., '1d', '30m').")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban_member(self, ctx, member: discord.Member, duration: str = None, *, reason: str = "No reason provided."):
        

        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("❌ You cannot ban a user with a higher or equal role.")
            
        await ctx.guild.ban(member, reason=reason)
        
        if duration:
            try:
                ban_time = parse_time_duration(duration)
                
                await ctx.send(f"✅ Banned **{member.display_name}** for: *{reason}* (Duration: {duration}). Unbanning in {ban_time}.")
                

                await asyncio.sleep(ban_time.total_seconds())
                

                try:
                    await ctx.guild.unban(member, reason=f"Automatic unban after {duration}.")
                    await ctx.send(f"✅ **{member.display_name}** has been automatically unbanned.")
                except discord.NotFound:
                    pass 
                
            except commands.BadArgument as e:
                await ctx.send(f"⚠️ User banned, but time format is invalid: {e}. Ban is permanent until manually removed.")
                
        else:
            await ctx.send(f"✅ Permanently banned **{member.display_name}** for: *{reason}*")
    
    @commands.command(name="kick", help="Kicks a member from the server.")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick_member(self, ctx, member: discord.Member, *, reason: str = "No reason provided."):
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("❌ You cannot kick a user with a higher or equal role.")
        

        await member.kick(reason=reason)
        

        await ctx.send(f"✅ Kicked **{member.display_name}** for: *{reason}*")

    @commands.command(name="mute", help="Mutes/timeouts a member for a specified duration (e.g., '30m', '1d').")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute_member(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided."):
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("❌ You cannot mute a user with a higher or equal role.")
        

        try:

            timeout_time = parse_time_duration(duration)
        except commands.BadArgument as e:
            return await ctx.send(f"❌ Invalid duration")
        
        await member.timeout(timeout_time, reason=reason)
        

        await ctx.send(f"✅ **{member.display_name}** has been timed out for **{duration}** for: *{reason}*")

    @commands.command(name="unmute", aliases=['untimeout'], help="Removes the timeout (mute) from a member.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute_member(self, ctx, member: discord.Member, *, reason: str = "Timeout manually removed."):
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("❌ You cannot manage timeout for a user with a higher or equal role.")
        
        await member.timeout(timedelta(seconds=0), reason=reason)
        
        await ctx.send(f"✅ **{member.display_name}** is now unmuted. Reason: *{reason}*")
    
    @commands.command(name="unban", help="Unbans a user using their ID or Name#Discriminator.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban_user(self, ctx, user_input: str, *, reason: str = "Ban manually removed."):
        
        try:

            banned_users = [entry async for entry in ctx.guild.bans()]
            target_user = None


            for ban_entry in banned_users:
                user = ban_entry.user
                

                if str(user.id) == user_input:
                    target_user = user
                    break
                
                user_full_name = f"{user.name}#{user.discriminator}"
                if user_full_name.lower() == user_input.lower():
                    target_user = user
                    break
            

            if target_user:
                await ctx.guild.unban(target_user, reason=reason)
                await ctx.send(f"✅ Successfully unbanned **{target_user.name}** ({target_user.id}). Reason: *{reason}*")
            else:
                await ctx.send("❌ Could not find a banned user matching that ID or Name.")

        except discord.NotFound:
            await ctx.send("⚠️ User is not currently banned or could not be found.")
        except Exception as e:
            await ctx.send(f"❌ An error occurred during unban.")

async def setup(bot):
    await bot.add_cog(Moderation(bot))