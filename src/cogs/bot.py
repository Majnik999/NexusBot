import discord
from discord.ext import commands
from settings import QUIT_COMMAND, PREFIX
from src.config.versions import BOT_VERSION

import time

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
    embed2.add_field(name=PREFIX+"activity set <type> <input>", value=f"Set bot activity! Type: can be activity / status, Input: ", inline=False)
    embed2.add_field(name=PREFIX+"activity reset", value=f"Reset bot activity!", inline=False)
    embed2.add_field(name=PREFIX+"activity loop <json input/file>", value=f"Set looping activity via json", inline=False)
    
    
    #embed3 = discord.Embed(
    #    title="🔧 Config | Help",
    #    description=f"Manage configuration from discord!"
    #)
    
    return [embed, embed2]

class OwnerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
    async def handle_error_quitting(self, ctx, error):
        await ctx.send("❌ You are not owner or some error happened!")
    
    @botgroup.command(name="ping", hidden=True)
    @commands.is_owner()
    async def botping(self, ctx):
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds and round
        
        await ctx.send(f"Pong! Bot latency: {latency}")
    
    @botping.error
    async def handle_error_quitting(self, ctx, error):
        await ctx.send("❌ You are not owner or some error happened!")
    
    @commands.command(name="changes")
    async def changes(self, ctx):
        embed = discord.Embed(
            title="Changes",
            description="Here are the latest changes and updates:"
        )

        embed.add_field(name=BOT_VERSION, value="Latest bot version | Changes: \n\n* Fixed bugs\n* Added economy system", inline=False)
        embed.set_footer(text="Version: "+BOT_VERSION)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))