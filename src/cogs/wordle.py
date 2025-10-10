import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import random
import io
import json
import os
from settings import WORDLE_WORDS, PREFIX
from src.config.versions import WORDLE_VERSION
from datetime import datetime
from main import logger  # added: use the main logger for single game-summary logs

# Example 100 words
WORDS = WORDLE_WORDS

# Constants for UI and layout
FONT_PATH = "src/font/arial.ttf"
DEFAULT_FONT_PATH = "arial.ttf"  # Fallback for systems without a specific font
CELL_SIZE = 60
PADDING = 10
KEY_SIZE = 40
KEY_PADDING = 5
SAVE_FILE = "src/games/wordle_games.json"

# Colors (as RGB tuples)
BG_COLOR = (30, 30, 30)
OUTLINE_COLOR = (255, 255, 255)
FILL_COLOR = (50, 50, 50)  # Default cell color
CORRECT_COLOR = (106, 170, 100)  # Green
PRESENT_COLOR = (201, 180, 88)  # Yellow
WRONG_COLOR = (120, 124, 126)  # Grey

class Wordle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = self.load_games()
        self.font = self.load_font(FONT_PATH, 40)
        self.key_font = self.load_font(FONT_PATH, 20)
        self.score_font = self.load_font(FONT_PATH, 25)

    def load_font(self, path, size):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            # Fallback to default system font if custom font isn't found
            print(f"Warning: Font file not found at {path}. Using default font.")
            return ImageFont.load_default()

    # --- Save / Load ---
    def save_games(self):
        with open(SAVE_FILE, "w") as f:
            json.dump(self.active_games, f)

    def load_games(self):
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        return {}

    # helper to log a single summary for a finished game
    def log_game_summary(self, user_id, user_name, result, word, guesses, channel_id=None, guild_id=None):
        summary = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "user_name": user_name,
            "result": result,  # "won", "lost", or "stopped"
            "word": word,
            "attempts": len(guesses),
            "guesses": guesses,
            "word_length": len(word) if word else None,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "version": WORDLE_VERSION
        }
        try:
            logger.info("WordleGameSummary: " + json.dumps(summary, ensure_ascii=False))
        except Exception:
            # ensure logging never breaks the bot flow
            logger.info(f"WordleGameSummary: user={user_id} result={result} word={word} attempts={len(guesses)}")

    @commands.group(name="wordle", invoke_without_command=True)
    async def wordle_group(self, ctx):
        embed = discord.Embed(
            title="Wordle 🟩 🟨 ⬜ | Help",
            description=f"Use `{PREFIX}wordle start <length>` to start a game or `{PREFIX}wordle stop` to stop your game.\n\nStart playing wordle now with these commands!:",
            color=discord.Color.blue()
        )
        embed.add_field(name=f"`{PREFIX}wordle` or `{PREFIX}wordle help`", value="Shows this message!", inline=False)
        embed.add_field(name=f"`{PREFIX}wordle start <length>`", value=f"Starts a new game with a word of a specified length (default 5).", inline=False)
        embed.add_field(name=f"`{PREFIX}wordle stop`", value=f"Stops your current game.", inline=False)
        embed.set_footer(text=f"Version: {WORDLE_VERSION}")
        await ctx.send(embed=embed)

    @wordle_group.command(name="start")
    async def start_wordle(self, ctx, length: int = 5):
        if length < 3 or length > 10:
            return await ctx.send("Word length must be between 3 and 10 letters.")
        if ctx.author.id in self.active_games:
            return await ctx.send("You already have an active game! Type `!stopwordle` to end it.")

        possible_words = [w for w in WORDS if len(w) == length]
        if not possible_words:
            return await ctx.send(f"No words available for a length of {length}.")
        word = random.choice(possible_words).lower()

        self.active_games[ctx.author.id] = {
            "word": word,
            "guesses": [],
            "current_guess": ""
        }
        self.save_games()

        embed = discord.Embed(
            title=f"Wordle 🟩 🟨 ⬜ ({length} letters)",
            description=f"Guess the word by typing `!<yourguess>`\nStop the game with `{PREFIX}wordle stop`",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Version: {WORDLE_VERSION}")
        img_file = self.generate_image(ctx.author.id)
        embed.set_image(url="attachment://wordle.png")
        await ctx.send(embed=embed, file=img_file)

    @wordle_group.command(name="stop")
    async def stop_wordle(self, ctx):
        if ctx.author.id not in self.active_games:
            return await ctx.send("You have no active game.")
        game = self.active_games[ctx.author.id]
        word = game.get("word")
        guesses = game.get("guesses", [])
        # log the stop once with full game info
        self.log_game_summary(ctx.author.id, str(ctx.author), "stopped", word, guesses, channel_id=ctx.channel.id, guild_id=getattr(ctx.guild, "id", None))
        del self.active_games[ctx.author.id]
        self.save_games()
        await ctx.send(f"Wordle game stopped. The word was `{word}`.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.content.startswith("!"):
            return
        
        guess = message.content[1:].lower()
        user_id = message.author.id

        if user_id not in self.active_games:
            return

        game = self.active_games[user_id]
        word = game["word"]

        if len(guess) != len(word):
            await message.channel.send(f"Your guess must be {len(word)} letters long.")
            return
        if len(game["guesses"]) >= 6:
            await message.channel.send(f"You've already used all your guesses! The word was `{word}`.")
            del self.active_games[user_id]
            self.save_games()
            return
        
        game["guesses"].append(guess)
        self.save_games()

        # Check if the guess is correct
        if guess == word:
            embed = discord.Embed(
                title="Wordle 🟩 🟨 ⬜",
                description=f"🎉 Congrats {message.author.mention}! You guessed the word `{word}` in {len(game['guesses'])} tries!",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Version: {WORDLE_VERSION}")
            img_file = self.generate_image(user_id)
            embed.set_image(url="attachment://wordle.png")
            await message.channel.send(embed=embed, file=img_file)
            # Log the finished (won) game once with full details
            self.log_game_summary(user_id, str(message.author), "won", word, game.get("guesses", []), channel_id=message.channel.id, guild_id=getattr(message.guild, "id", None))
            del self.active_games[user_id]
            self.save_games()
            return

        # Check if max guesses have been reached
        if len(game["guesses"]) == 6:
            embed = discord.Embed(
                title="Wordle 🟩 🟨 ⬜",
                description=f"😢 Game over! The word was `{word}`.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Version: {WORDLE_VERSION}")
            img_file = self.generate_image(user_id)
            embed.set_image(url="attachment://wordle.png")
            await message.channel.send(embed=embed, file=img_file)
            # Log the finished (lost) game once with full details
            self.log_game_summary(user_id, str(message.author), "lost", word, game.get("guesses", []), channel_id=message.channel.id, guild_id=getattr(message.guild, "id", None))
            del self.active_games[user_id]
            self.save_games()
            return

        # Normal update for an incorrect guess
        embed = discord.Embed(
            title=f"Wordle 🟩 🟨 ⬜ ({len(word)} letters)",
            description=f"Guess the word by typing `!<yourguess>`\nStop game with `{PREFIX}wordle stop`",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Version: {WORDLE_VERSION}")
        img_file = self.generate_image(user_id)
        embed.set_image(url="attachment://wordle.png")
        await message.channel.send(embed=embed, file=img_file)

    def generate_image(self, user_id):
        game = self.active_games[user_id]
        guesses = game["guesses"]
        word = game["word"]
        word_length = len(word)
        max_rows = 6

        # Calculate image dimensions based on content
        grid_width = word_length * (CELL_SIZE + PADDING) + PADDING
        grid_height = max_rows * (CELL_SIZE + PADDING) + PADDING
        
        # Keyboard layout
        keyboard_rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
        key_width = len(max(keyboard_rows, key=len)) * (KEY_SIZE + KEY_PADDING) + KEY_PADDING
        keyboard_height = len(keyboard_rows) * (KEY_SIZE + KEY_PADDING) + KEY_PADDING

        # Total image dimensions
        img_width = max(grid_width, key_width) + PADDING * 2
        img_height = 50 + PADDING * 2 + grid_height + keyboard_height + PADDING * 2

        image = Image.new("RGB", (img_width, img_height), color=BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Draw score at the top
        score_text = f"Attempts: {len(guesses)}/6"
        bbox = draw.textbbox((0, 0), score_text, font=self.score_font)
        draw.text(((img_width - bbox[2]) / 2, PADDING), score_text, font=self.score_font, fill=OUTLINE_COLOR)

        # Draw guesses grid
        grid_start_y = 50 + PADDING * 2
        grid_start_x = (img_width - grid_width) / 2
        for row in range(max_rows):
            for col in range(word_length):
                x0 = grid_start_x + PADDING + col * (CELL_SIZE + PADDING)
                y0 = grid_start_y + PADDING + row * (CELL_SIZE + PADDING)
                x1 = x0 + CELL_SIZE
                y1 = y0 + CELL_SIZE
                
                fill_color = FILL_COLOR
                letter = ""

                if row < len(guesses):
                    guess_word = guesses[row]
                    letter = guess_word[col]
                    if letter == word[col]:
                        fill_color = CORRECT_COLOR
                    elif letter in word:
                        fill_color = PRESENT_COLOR
                    else:
                        fill_color = WRONG_COLOR
                
                draw.rectangle([x0, y0, x1, y1], outline=OUTLINE_COLOR, width=3, fill=fill_color)
                if letter:
                    bbox = draw.textbbox((0, 0), letter.upper(), font=self.font)
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    draw.text((x0 + (CELL_SIZE - w) / 2, y0 + (CELL_SIZE - h) / 2), letter.upper(), font=self.font, fill=OUTLINE_COLOR)

        # Draw keyboard
        key_colors = {k: WRONG_COLOR for k in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
        for guess in guesses:
            temp_word = list(word) # Use a temp list to handle duplicate letters
            for i, letter in enumerate(guess):
                if letter == word[i]:
                    key_colors[letter.upper()] = CORRECT_COLOR
                    if letter in temp_word:
                        temp_word.remove(letter)

        for guess in guesses:
            for i, letter in enumerate(guess):
                if letter in temp_word and key_colors[letter.upper()] != CORRECT_COLOR:
                    key_colors[letter.upper()] = PRESENT_COLOR
                    if letter in temp_word:
                        temp_word.remove(letter)
        
        keyboard_start_y = grid_start_y + grid_height + PADDING
        for r_idx, row_keys in enumerate(keyboard_rows):
            row_width = len(row_keys) * (KEY_SIZE + KEY_PADDING) - KEY_PADDING
            start_x = (img_width - row_width) / 2
            for k_idx, key in enumerate(row_keys):
                x0 = start_x + k_idx * (KEY_SIZE + KEY_PADDING)
                y0 = keyboard_start_y + r_idx * (KEY_SIZE + KEY_PADDING)
                x1 = x0 + KEY_SIZE
                y1 = y0 + KEY_SIZE
                draw.rectangle([x0, y0, x1, y1], fill=key_colors[key], outline=OUTLINE_COLOR, width=2)
                bbox = draw.textbbox((0, 0), key, font=self.key_font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                draw.text((x0 + (KEY_SIZE - w) / 2, y0 + (KEY_SIZE - h) / 2), key, font=self.key_font, fill=OUTLINE_COLOR)

        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        buffer.seek(0)
        return discord.File(fp=buffer, filename="wordle.png")

async def setup(bot):
    await bot.add_cog(Wordle(bot))