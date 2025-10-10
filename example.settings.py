from discord import Color
from json import dumps

# Set bot prefix
PREFIX = "PREFIX"

# SUDO dance command emojis:
DANCE_MOVES: list[any] = ["💃", "🕺", "🩰", "🪩", "🤖", "🐒", "👯", "🎉"]

# Maze width and height
MAZE_WIDTH: int = 5
MAZE_HEIGHT: int = 5

# Wordle words
# As default there is about 200-400 words
WORDLE_WORDS: list[str] = ["apple","house","plant","light","water","table","chair","bread","phone","river","mount","earth","glass","heart","piano","music","stone","cloud","beach","night","dream","sunny","green","white","black","yellow","purple","orange","school","happy","smile","train","plane","movie","drink","juice","candy","tiger","zebra","mouse","horse","eagle","snake","watch","shoes","shirt","pants","laptop","paper","knife","fork","spoon","plate","plant","grass","tree","river","ocean","beach","storm","snow","rain","wind","fire","water","earth","light","sound","music","dance","sleep","laugh","crying","think","write","read","draw","paint","jump","run","walk","swim","fly","climb","cook","bake","clean","watch","listen","touch","smell","taste","fight","win","lose","play","game","work","rest","study","brave","crispy","foggy","quiet","funny","angry","clever","clumsy","forest","window","jungle","guitar","kitchen","computer","brother","sister","family","friend","discover","imagine","believe","promise","decide","happen","explore","journal","curious","perfect","excited","gentle","shiver","whisper","travel","journey","shelter","freedom","mystery","history","science","biology","planet","galaxy","monster","creature","heroic","legend","ancient","future","present","past","memory","forgot","remember","giggle","scream","silent","lonely","hungry","thirsty","blazing","flicker","glitter","shadow","bright","hollow","solid","liquid","breeze","tornado","volcano","garden","market","bridge","street","subway","station","airport","country","village","capital","special","unique","common","general","private","public","morning","evening","afternoon","midnight","daytime","weekend","holiday","season","autumn","winter","spring","summer","winter","warmth","freeze","shiver","breeze","sizzle","bubble","scream","silent","squeal","whistle","thunder","lightning","glisten","glimmer","sparkle","shimmer","twinkle","drizzle","blizzard","tornado","cyclone","volcano","tsunami","avalanche","gorgeous","amazing","awesome","terrible","horrible","fantastic","wonderful","amazing","awesome","terrible","horrible","fantastic","wonderful","breathe","yawn","gasp","sigh","sneeze","cough","stretch","hug","kiss","smile","frown","glance","stare","blink","wink","nod","shake","wave","point","fist","kick","punch","slap","tackle","tumble","stumble","crouch","kneel","crawl","glide","soar","hover","float","sink","dive","splash","drown","sprint","gallop","trot","waddle","slither","wiggle","jiggle","bounce","toss","catch","throw","lob","flip","spin","twist","turn","rotate","swirl","circle","spiral","curve","bend","straight","zigzag","cross","split","join","merge","connect","unite","divide","separate","combine","mix","blend","stir","shake","filter","drain","pour","fill","empty","spill","slosh","splash","drip","squirt","spray","blast","explode","ignite","quench","extinguish","ignite","kindle","spark","glow","shine","blaze","flare","flash","glare","beam","ray","gleam","glint","dazzle","blind","shadow","darkness","dusk","dawn","twilight","midnight","noon","sunrise","sunset","eclipse","lunar","solar","cosmic","celestial","stellar","planetoid","asteroid","meteor","comet","spaceship","astronaut","satellite","telescope","microscope","laboratory","experiment","hypothesis","theory","equation","variable","constant","solution","puzzle","riddle","mystery","clue","evidence","suspect","detective","criminal","justice","verdict","sentence","prison","jail","escape","freedom","liberty","rights","duty","honor","courage","bravery","kindness","patience","forgive","regret","apology","gratitude","joyful","ecstatic","elated","somber","gloomy","morose","solemn","calm","tranquil","serene","peaceful","noisy","chaotic","racket","uproar","hubbub","clamor","commotion","silence","quietude","stillness","whisper","murmur","gossip","rumor","secret","confess","reveal","conceal","hidden","exposed","visible","invisible","tangible","intangible","virtual","reality","dreamy","fantasy","fiction","nonfiction","memoir","biography","history","geology","biology","ecology","physics","chemistry","astronomy","geography","symphony","concerto","sonata","ballad","anthem","chorus","verse","rhythm","melody","harmony","pitch","tempo","instrument","orchestra","band","vocalist","soloist","conductor","composer","lyricist","poem","novel","epic","story","tale","legend","myth","fable","parable","allegory","metaphor","simile","idiom","phrase","sentence","paragraph","chapter","prologue","epilogue","appendix","index","glossary","footnote","citation","reference"]

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
INVITE_LINK: str = "https://www.discord.com/"

# Default economy settings
# DEFAULT_DAILY_REWARD: intiger = HOW MUCH COINS DO USERS GET ON DAILY COMMAND
# DAILY_COOLDOWN_HOURS: intiger = HOW MUCH HOURS DO USERS NEED TO WAIT TO GET DAILY REWARD IN HOURS
# SHOP_PAGE_SIZE:       intiger = ITEMS PER PAGE
DEFAULT_DAILY_REWARD: int = 250
DAILY_COOLDOWN_HOURS: int = 20
SHOP_PAGE_SIZE: int       = 5

EMOJIS = {
    "stone": "🪨", "iron": "⛓️", "gold": "🪙", "diamond": "💎", "apple": "🍎", "shovel": "🛠️", "salmon": "🐟", "clownfish": "🐠", "crab": "🦀", "pufferfish": "🐡"
} # self explained

COOLDOWN_DIG_FISH_MINUTES:int = 5

FISH_ITEMS: list[str]          = ["salmon", "clownfish", "crab", "pufferfish"]
FISH_CHANCES: list[int, float] = [25, 10, 5, 0.5]
FISH_CATCH_CHANCE_PERCENTAGE: int = 15

DIG_ITEMS: list[str]          = ["gold", "stone", "copper", "iron", "diamond"]
DIG_CHANCES: list[int, float] = [90, 25, 10, 5, 0.5]

BLACK_JACK_SUITS: list[str] = ['♠', '♥', '♦', '♣']
BLACK_JACK_RANKS: list[str] = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

# Can be a hex but need to be changed to string if you want to use HEX colors
GAMBLE_WIN_COLOR = Color.green()
GAMBLE_LOSE_COLOR = Color.red()
DAILY_COLOR = Color.gold()
BALANCE_COLOR = Color.green()
INVENTORY_COLOR = Color.blue()
LOOT_COLOR = Color.purple()
SELL_COLOR = Color.orange()
HELP_COLOR = Color.blurple()

LAVALINK_URI: str = 'https://lavalink.idk.com'  # Example format without http:// or https://
LAVALINK_PASSWORD: str = 'Password'

# Default JSON example for activity loop (copy-paste ready)
DEFAULT_ACTIVITY = dumps([
    {"type": "playing", "name": "Hello world", "duration": 30},
    {"type": "watching", "name": "the sky", "duration": 45},
    {"type": "listening", "name": "music", "duration": 20}
], indent=2)