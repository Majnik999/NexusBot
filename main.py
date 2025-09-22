import discord
from discord.ext import commands
import os
import logging
from colorama import Fore, Style, init
from datetime import datetime
from dotenv import load_dotenv
from settings import PREFIX

# Initialize colorama
init(autoreset=True)

# Discord-style console formatter with bold timestamp and level
class DiscordStyledFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": Fore.CYAN + Style.BRIGHT,
        "INFO": Fore.BLUE + Style.BRIGHT,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }
    LOGGER_COLOR = Fore.MAGENTA
    TIME_COLOR = Fore.LIGHTBLACK_EX + Style.BRIGHT
    MESSAGE_COLOR = Fore.WHITE

    def format(self, record):
        time_str = f"{self.TIME_COLOR}{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}"
        level_str = f"{self.LEVEL_COLORS.get(record.levelname,'')}{record.levelname:<8}{Style.RESET_ALL}"
        logger_name = f"{self.LOGGER_COLOR}{record.name}{Style.RESET_ALL}"
        message = f"{self.MESSAGE_COLOR}{record.getMessage()}{Style.RESET_ALL}"
        return f"{time_str} {level_str} {logger_name} {message}"

# Create discord.bot logger
logger = logging.getLogger("discord.bot")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(DiscordStyledFormatter())
    logger.addHandler(console_handler)

    # File handler with new log each time
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = "src/logs"
    os.makedirs(log_dir, exist_ok=True)  # Ensure folder exists
    log_file = os.path.join(log_dir, f"BOT_{now}.log")

    file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)

# Bot setup
bot = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all(), help_command=None)

load_dotenv()
TOKEN = os.getenv("token", 'Please make .env file with toke="YOUR_TOKEN"')

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    logger.info("Syncing commands...")

    for filename in os.listdir("./src/cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"src.cogs.{filename[:-3]}")
            except discord.ext.commands.errors.ExtensionFailed as e:
                logger.error(f"Failed to load cog: {filename[:-3]} error:\n{e}")
            else:
                logger.info(f"Successfully loaded cog: {filename[:-3]}")

    logger.info("Syncing completed!")

ascii_art = """
 ____                                        __                              
/\  _`\   __                                /\ \                             
\ \ \/\ \/\_\    ____    ___    ___   _ __  \_\ \                            
 \ \ \ \ \/\ \  /',__\  /'___\ / __`\/\`'__\/'_` \                           
  \ \ \_\ \ \ \/\__, `\/\ \__//\ \L\ \ \ \//\ \L\ \                          
   \ \____/\ \_\/\____/\ \____\ \____/\ \_\\\\ \___,_\                         
    \/___/  \/_/\/___/  \/____/\/___/  \/_/ \/__,_ /                         
                                                                             
                                                                             
                                                                             
 ______  __       __          ______   __  __      _____   __  __  ____        ____     _____   ______   
/\  _  \/\ \     /\ \        /\__  _\ /\ \/\ \    /\  __`\/\ \/\ \/\  _`\     /\  _`\  /\  __`\/\__  _\  
\ \ \L\ \ \ \    \ \ \       \/_/\ \/ \ \ `\\\\ \   \ \ \/\ \ \ `\\\\ \ \ \L\_\   \ \ \L\ \\\\ \ \/\ \/_/\ \/  
 \ \  __ \ \ \  __\ \ \  __     \ \ \  \ \ , ` \   \ \ \ \ \ \ , ` \ \  _\L    \ \  _ <'\ \ \ \ \ \ \ \  
  \ \ \/\ \ \ \L\ \\\\ \ \L\ \     \_\ \__\ \ \`\ \   \ \ \_\ \ \ \`\ \ \ \L\ \   \ \ \L\ \\\\ \ \_\ \ \ \ \ 
   \ \_\ \_\ \____/ \ \____/     /\_____\\\\ \_\ \_\   \ \_____\ \_\ \_\ \____/    \ \____/ \ \_____\ \ \_\\
    \/_/\/_/\/___/   \/___/      \/_____/ \/_/\/_/    \/_____/\/_/\/_/\/___/      \/___/   \/_____/  \/_/
    

--------------------------------------------------------------------------------
"""

if __name__ == "__main__":
    os.system("clear")
    print(ascii_art)
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error("Cannot load bot!")
        logger.exception(e)
