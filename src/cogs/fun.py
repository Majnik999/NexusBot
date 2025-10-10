import discord
from discord.ext import commands
import asyncio
import random
from settings import DANCE_MOVES

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="sudo", invoke_without_command=False)
    async def sudo(self, ctx):
        pass

    @sudo.command(name="help")
    async def sudo_help(self, ctx):
        embed = discord.Embed(
            title="🛠️ Sudo Commands Help",
            description="Here are all the fun `sudo` commands you can try!",
            color=discord.Color.green()
        )
        embed.add_field(name="apt [package]", value="Simulate installing a package", inline=False)
        embed.add_field(name="make_me_a_sandwich / sandwich", value="Make the bot give you a sandwich (maybe 🍞)", inline=False)
        embed.add_field(name="rm_rf [target]", value="Pretend to delete files (safe 😎)", inline=False)
        embed.add_field(name="dance", value="Make the bot dance with emojis 🕺💃", inline=False)
        embed.add_field(name="random [command]", value="Run any random sudo command you imagine", inline=False)
        embed.add_field(name="delete_google", value="Fake-delete Google in a dramatic way 💥 (ends with Wow!)", inline=False)
        embed.set_footer(text="Try 'sudo [command]' and have fun! 🤖")
        await ctx.send(embed=embed)

    @sudo.command(name="apt")
    async def apt(self, ctx, *, description):
        msg = await ctx.send(f"Running `sudo apt {description}`...")
        await asyncio.sleep(random.uniform(1, 3))
        responses = [
            f"`{description}` installed successfully! Just kidding 😹",
            "Error 420: Package too cool to install 😎",
            "System overheated! 🔥 JK, all safe",
            "Nothing happened. Maybe try sudo dance? 🕺",
            f"`{description}` mysteriously vanished from the repositories 👻"
        ]
        await msg.edit(content=random.choice(responses))

    @sudo.command(name="make_me_a_sandwich", aliases=["sandwich"])
    async def sandwich(self, ctx):
        msg = await ctx.send("Running `sudo make me a sandwich`...")
        await asyncio.sleep(random.uniform(0.5, 2))
        responses = [
            "You now have an invisible sandwich 🥪✨",
            "Sandwich command not found. Error 404 🍞",
            "You must complete 5 push-ups before receiving your sandwich 💪",
            "You are allergic to sandwiches now! 🤧",
            "Congratulations! You are now the Sandwich King 👑"
        ]
        await msg.edit(content=random.choice(responses))

    @sudo.command(name="rm_rf")
    async def rm_rf(self, ctx, *, target="/"):
        msg = await ctx.send(f"Running `sudo rm -rf {target}`... 🚨")
        await asyncio.sleep(random.uniform(1, 3))
        responses = [
            "Everything is gone! Just kidding 😅",
            f"rm: cannot remove '{target}': Permission denied 😉",
            "Oops! You deleted your imaginary files 💻",
            "System crashed! JK, reboot not needed 🤖",
            f"Random explosion in '{target}' directory 💥"
        ]
        await msg.edit(content=random.choice(responses))

    @sudo.command(name="dance")
    async def dance(self, ctx):
        msg = await ctx.send("Running `sudo dance`... 🕺💃")
        await asyncio.sleep(0.5)

        dance_moves = DANCE_MOVES
        count = random.randint(5, 12)
        for _ in range(count):
            await msg.edit(content=f"The bot dances: {''.join(random.choices(dance_moves, k=random.randint(3, 7)))}")
            await asyncio.sleep(random.uniform(0.3, 1.0))

        final_responses = [
            "💥 Dance party over! Hope you enjoyed 😎",
            "The bot collapsed from dancing 😵",
            "Congratulations! You've witnessed a rare dance combo 🏆"
        ]
        await msg.edit(content=random.choice(final_responses))

    @sudo.command(name="random")
    async def random_sudo(self, ctx, *, command="something"):
        msg = await ctx.send(f"Running `sudo {command}`...")
        await asyncio.sleep(random.uniform(0.5, 2))
        responses = [
            f"`{command}` command executed successfully! Totally real 😎",
            f"Failed to run `{command}`. Just kidding 😹",
            f"{command} is not a valid command. But it should be! 🤔",
            "Command denied. Admin privileges required 🛑",
            f"You are now the ruler of `{command}` kingdom 👑",
            f"Unexpected side effects occurred while running `{command}` 💥"
        ]
        await msg.edit(content=random.choice(responses))

    @sudo.command(name="delete_google")
    async def delete_google(self, ctx):
        msg = await ctx.send("Running `sudo delete google`... 🚨")
        await asyncio.sleep(1)

        steps = [
            "Locating Google servers... 🌍",
            "Bypassing security protocols... 🔐",
            "Initiating deletion sequence... 💥",
            "Deleting all search results... 🗑️",
            "Warning: Internet may explode... 💣"
        ]
        random.shuffle(steps)  # Randomize step order
        for step in steps:
            await msg.edit(content=step)
            await asyncio.sleep(random.uniform(1, 2))

        final_responses = [
            "✅ Google has been successfully deleted... just kidding! Wow! 😲",
            "💥 Google vanished into an alternate universe! Wow! 😲",
            "🌌 Google is now a concept, not a website! Wow! 😲"
        ]
        await msg.edit(content=random.choice(final_responses))
    

async def setup(bot):
    await bot.add_cog(Fun(bot))
