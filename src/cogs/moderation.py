import discord
from discord.ext import commands
from settings import ADMIN_IDS, MAX_PURGE_LIMIT
import aiosqlite
import os
import asyncio
from datetime import timedelta
import re

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

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join("src", "databases", "user.db")

    @commands.command(name="clear", description="Deletes a specified number of messages.")
    @commands.bot_has_permissions(manage_messages=True)
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, messages: int):
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
