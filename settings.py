from discord import Color

# Set bot prefix
PREFIX = ">"

# SUDO dance command emojis:
DANCE_MOVES: list[any] = ["💃", "🕺", "🩰", "🪩", "🤖", "🐒", "👯", "🎉"]

# Maze width and height
MAZE_WIDTH: int = 5
MAZE_HEIGHT: int = 5

# Wordle words
# As default there is about 100 words
WORDLE_WORDS: list[str] = ["apple","house","plant","light","water","table","chair","bread","phone","river","mount","earth","glass","heart","piano","music","stone","cloud","beach","night","dream","sunny","green","white","black","yellow","purple","orange","school","happy","smile","train","plane","movie","drink","juice","candy","tiger","zebra","mouse","horse","eagle","snake","watch","shoes","shirt","pants","laptop","paper","knife","fork","spoon","plate","plant","grass","tree","river","ocean","beach","storm","snow","rain","wind","fire","water","earth","light","sound","music","dance","sleep","laugh","crying","think","write","read","draw","paint","jump","run","walk","swim","fly","climb","cook","bake","clean","watch","listen","touch","smell","taste","fight","win","lose","play","game","work","rest","study"]

# Clear command toggle
# You may ask why sometimes you get limited by this command idk why but its good if you have bot public to turn it off
# False = off
# True = on
CLEAR_COMMAND: bool = False

# Quit command toggle
# Just for owner of bot if he wants quit command or not
# False = off
# True = on
QUIT_COMMAND: bool = True

# Bots invite link
INVITE_LINK: str = "https://discord.com/oauth2/authorize?client_id=1106265534426796133"

# Default daily reward
# DEFAULT_DAILY_REWARD: intiger = HOW MUCH COINS DO USERS GET ON DAILY COMMAND
# DAILY_COOLDOWN_HOURS: intiger = HOW MUCH HOURS DO USERS NEED TO WAIT TO GET DAILY REWARD IN HOURS
# SHOP_PAGE_SIZE:       intiger = ITEMS PER PAGE
DEFAULT_DAILY_REWARD: int = 250
DAILY_COOLDOWN_HOURS: int = 20
SHOP_PAGE_SIZE: int       = 5

EMOJIS: dict = {
    "stone": "🪨", "iron": "⛓️", "gold": "🪙", "diamond": "💎", "apple": "🍎", "shovel": "🛠️", "salmon": "🐟", "clownfish": "🐠", "crab": "🦀", "pufferfish": "🐡"
} # self explained

COOLDOWN_DIG_FISH_MINUTES:int = 5

FISH_ITEMS: list[str]          = ["salmon", "clownfish", "crab", "pufferfish"]
FISH_CHANCES: list[int, float] = [25, 10, 5, 0.5]

DIG_ITEMS: list[str]          = ["gold", "stone", "copper", "iron", "diamond"]
DIG_CHANCES: list[int, float] = [90, 25, 10, 5, 0.5]

# Can be a hex but need to be changed to string if you want to use HEX colors
GAMBLE_WIN_COLOR = Color.green()
GAMBLE_LOSE_COLOR = Color.red()
DAILY_COLOR = Color.gold()
BALANCE_COLOR = Color.green()
INVENTORY_COLOR = Color.blue()
LOOT_COLOR = Color.purple()
SELL_COLOR = Color.orange()
HELP_COLOR = Color.blurple()