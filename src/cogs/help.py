import discord
from discord.ext import commands
from main import PREFIX
from main import logger
from settings import CLEAR_COMMAND, INVITE_LINK

# This is our single source of truth for all categories + commands + descriptions
HELP_DATA = {
    "fun": {
        "description": "🎲 Fun commands like jokes and memes",
        "commands": {
            PREFIX + "joke help": "Tells a random joke",
            PREFIX + "meme <count> <subreddit>": "Sends a random meme / send a requested meme with parameters",
            PREFIX + "8ball <question>": "Ask the magic 8ball a question",
            PREFIX + "sudo help": "Play with fun sudo commands",
            PREFIX + "wordle help": "Play wordle game",
            PREFIX + "maze help": "Play maze game",
            PREFIX + "eco help": "Economy system!",
        }
    },
    "moderation": {
        "description": "🛡️ Kick, ban, mute, etc.",
        "commands": {
            PREFIX + "clear <amount>": "Clear messages from a channel like purge command!" if CLEAR_COMMAND else "Clear messages from a channel like purge command! (Disabled)",
        }
    },
    "utility": {
        "description": "🔧 Helpful tools like reminders",
        "commands": {
            PREFIX + "profile": "Get your profile info",
            PREFIX + "profile pic": "Get your profile picture",
            PREFIX + "embed help": "Get help with embeds and embed builder"
        }
    }
}

class InviteLinkView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for the view

        # Add the invite button
        self.add_item(discord.ui.Button(
            label="Invite Nexus Bot",
            url=INVITE_LINK,
            style=discord.ButtonStyle.link
        ))

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx):
        # Build the list of categories dynamically
        categories_text = "\n".join([
            f"• **{category}** – {data['description']}"
            for category, data in HELP_DATA.items()
        ])

        # Send the main help menu embed
        embed = discord.Embed(
            title="<:NexusBotprofilepicture:1419717002414653581> Help Menu",
            description=f"Please type a category name to see its commands:\n\n{categories_text}",
            color=discord.Color.blue()
        )
        menu = await ctx.send(embed=embed, view=InviteLinkView())
        # Function to check user input
        def check(message):
            return (
                message.author == ctx.author and
                message.channel == ctx.channel
            )

        category = None  # This will store the valid category once we get it

        # Loop until the user types a valid category
        while category is None:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                content = msg.content.lower()  # lowercase to make matching case-insensitive

                if content in HELP_DATA:
                    category = content  # valid category -> exit loop
                else:
                    # Invalid category -> DM user
                    try:
                        await msg.author.send(
                            f"⚠️ '{msg.content}' is not a valid category."
                        )
                    except discord.Forbidden:
                        pass
                    finally:
                        return
            except TimeoutError:
                # User took too long -> break loop
                await menu.edit(f"⏳ You took too long to respond. Use `{PREFIX}help` to try again.", view=None)
                return

        # Step 5: Once valid category is chosen, show commands + descriptions
        selected_category = HELP_DATA[category]
        commands_text = "\n".join([
            f"`{cmd}` — {desc}" for cmd, desc in selected_category["commands"].items()
        ])

        try:
            await msg.delete()
        except discord.Forbidden:
            logger.error(f"Help Command: User ({ctx.author.name}, {ctx.author.id}) tried to select category in dms or some internet connection error happened!")
            
            embed=discord.Embed(
                        title=f"<:NexusBotprofilepicture:1419717002414653581> {category.capitalize()} Commands",
                        description=f"**{selected_category['description']}**\n\n{commands_text}",
                        color=discord.Color.green()
            )
            
            embed.set_footer(text="BTW this command is better in some server not in dms!")
            
            await ctx.send(embed=embed)
            
            return
            
        await menu.edit(
            content="",
            embed=discord.Embed(
                title=f"<:NexusBotprofilepicture:1419717002414653581> {category.capitalize()} Commands",
                description=f"**{selected_category['description']}**\n\n{commands_text}",
                color=discord.Color.green()
            )
        )

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
