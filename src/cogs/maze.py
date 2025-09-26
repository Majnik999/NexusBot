import os
import io
import json
import random
from PIL import Image, ImageDraw, ImageFont

import discord
from discord.ext import commands
from discord.ui import View, Button

from main import logger, PREFIX
from settings import MAZE_HEIGHT, MAZE_WIDTH
from src.config.versions import MAZE_VERSION

SAVE_FILE = "src/games/maze_games.json"

# ================= CONFIG =================
USE_IMAGE_RENDER = True       # Toggle between image and text mode
CELL_SIZE = 32                # Size of each cell (px)
FONT_SIZE = 24                # Font size for text (player/goal)
FONT_PATH = "src/font/arial.ttf"

LEVEL_TO_DARK_MAZE = 5
LEVEL_TO_DARK_MAZE_VISIBILITY = 5

# Colors
COLORS = {
    "wall": (30, 30, 30),
    "path": (230, 230, 230),
    "player": (50, 150, 250),
    "goal": (250, 100, 100),
    "grid": (200, 200, 200),
    "fog": (50, 50, 50)  # For dark/blind levels
}

# Characters
PLAYER = "@"
GOAL = "F"
WALL = "▓"
PATH = "░"
# ==========================================


# --- Maze Logic ---
def create_maze(width: int, height: int):
    """Generate a random maze using DFS backtracking."""
    maze = [[WALL for _ in range(width)] for _ in range(height)]

    def carve(x, y):
        maze[y][x] = PATH
        directions = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        random.shuffle(directions)
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 1 <= nx < width - 1 and 1 <= ny < height - 1 and maze[ny][nx] == WALL:
                maze[y + dy // 2][x + dx // 2] = PATH
                carve(nx, ny)

    start_x, start_y = random.randrange(1, width, 2), random.randrange(1, height, 2)
    carve(start_x, start_y)

    # Place player
    maze[start_y][start_x] = PLAYER

    # Place goal
    gx, gy = start_x, start_y
    while (gx, gy) == (start_x, start_y) or maze[gy][gx] == WALL:
        gx, gy = random.randrange(1, width - 1), random.randrange(1, height - 1)
    maze[gy][gx] = GOAL

    return maze


def locate_player(maze):
    for y, row in enumerate(maze):
        for x, cell in enumerate(row):
            if cell == PLAYER:
                return y, x
    return None, None


# --- Rendering ---
def render_board_text(maze, level, moves):
    rows = [" ".join(r) for r in maze]
    return f"Level: {level} | Moves: {moves}\n```\n" + "\n".join(rows) + "\n```"


def render_board_image(maze, level, moves, player_view=None):
    """
    Render maze board as an image with Pillow.
    player_view: int | None -> only render square of size player_view around player
    """
    # If blind/dark level, create viewport
    if player_view:
        r, c = locate_player(maze)
        h = len(maze)
        w = len(maze[0])
        half = player_view // 2
        top = max(r - half, 0)
        bottom = min(r + half + 1, h)
        left = max(c - half, 0)
        right = min(c + half + 1, w)
        maze_view = [row[left:right] for row in maze[top:bottom]]
    else:
        maze_view = maze

    width = len(maze_view[0]) * CELL_SIZE
    height = len(maze_view) * CELL_SIZE
    img = Image.new("RGB", (width, height), COLORS["path"])
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    def get_text_size(text, font):
        try:
            bbox = draw.textbbox((0, 0), text, font=font)  # Pillow >= 10
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            return draw.textsize(text, font=font)

    for y, row in enumerate(maze_view):
        for x, cell in enumerate(row):
            px, py = x * CELL_SIZE, y * CELL_SIZE
            rect = [px, py, px + CELL_SIZE, py + CELL_SIZE]

            # If blind level, unknown cells are fog
            if player_view and cell not in (PLAYER, GOAL, WALL, PATH):
                draw.rectangle(rect, fill=COLORS["fog"])
                draw.rectangle(rect, outline=COLORS["grid"], width=1)
                continue

            if cell == WALL:
                draw.rectangle(rect, fill=COLORS["wall"])
            elif cell == PATH:
                draw.rectangle(rect, fill=COLORS["path"])
            elif cell == PLAYER:
                draw.rectangle(rect, fill=COLORS["path"])
                w, h = get_text_size(PLAYER, font)
                draw.text((px + (CELL_SIZE - w) / 2, py + (CELL_SIZE - h) / 2),
                          PLAYER, fill=COLORS["player"], font=font)
            elif cell == GOAL:
                draw.rectangle(rect, fill=COLORS["path"])
                w, h = get_text_size(GOAL, font)
                draw.text((px + (CELL_SIZE - w) / 2, py + (CELL_SIZE - h) / 2),
                          GOAL, fill=COLORS["goal"], font=font)

            # grid lines
            draw.rectangle(rect, outline=COLORS["grid"], width=1)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def send_board(ctx_or_interaction, maze, level, moves, title="Maze Game", view=None):
    """Send board as embed + image OR embed + text depending on config."""
    # Determine blind view
    player_view = None
    if level >= LEVEL_TO_DARK_MAZE:
        player_view = LEVEL_TO_DARK_MAZE_VISIBILITY  # 5x5 around player for blind/dark levels
        title += " 🌑 Dark Maze"

    if USE_IMAGE_RENDER:
        buffer = render_board_image(maze, level, moves, player_view=player_view)
        file = discord.File(buffer, filename="maze.png")
        embed = discord.Embed(title=title, description=f"Level: {level} | Moves: {moves}")
        embed.set_image(url="attachment://maze.png")
        embed.set_footer(text=f"Version: {MAZE_VERSION}")
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.edit_message(embed=embed, attachments=[file], view=view)
        else:
            await ctx_or_interaction.send(embed=embed, file=file, view=view)
    else:
        embed = discord.Embed(title=title)
        embed.add_field(name="Board", value=render_board_text(maze, level, moves), inline=False)
        embed.set_footer(text=f"Version: {MAZE_VERSION}")
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.edit_message(embed=embed, view=view)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)


# --- Save / Load ---
def save_games(games):
    with open(SAVE_FILE, "w") as f:
        json.dump(games, f)


def load_games():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            return json.load(f)
    return {}


# --- UI View ---
class MazeView(View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = str(user_id)

        # Hollow - Up - Hollow
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=0))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=0))
        self.add_item(Button(label="↑", style=discord.ButtonStyle.secondary, custom_id="up", row=0))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=0))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=0))

        # Left - Down - Right
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=1))
        self.add_item(Button(label="←", style=discord.ButtonStyle.secondary, custom_id="left", row=1))
        self.add_item(Button(label="↓", style=discord.ButtonStyle.secondary, custom_id="down", row=1))
        self.add_item(Button(label="→", style=discord.ButtonStyle.secondary, custom_id="right", row=1))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=1))

        # Hollow - Stop - Hollow
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=2))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=2))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=2))
        self.add_item(Button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True, row=2))
        self.add_item(Button(label="Stop", style=discord.ButtonStyle.danger, custom_id="stop", row=2))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data and "custom_id" in interaction.data:
            await self.on_button_click(interaction, interaction.data["custom_id"])
            return False
        return True

    async def on_button_click(self, interaction: discord.Interaction, button_id: str):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Not your game.", ephemeral=True)

        if button_id == "stop":
            if self.user_id in self.cog.games:
                game = self.cog.games[self.user_id]
                del self.cog.games[self.user_id]
                save_games(self.cog.games)
                return await send_board(interaction, game["maze"], game["level"], game["moves"], title="🛑 Game Ended", view=None)
            return await interaction.response.send_message("⚠️ No active game.", ephemeral=True)

        moves = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
        dr, dc = moves[button_id]

        game = self.cog.games.get(self.user_id)
        if not game:
            return await interaction.response.send_message(f"⚠️ No active game. Start one with `{PREFIX}maze start`.", ephemeral=True)

        maze, level, move_count = game["maze"], game["level"], game["moves"]
        r, c = locate_player(maze)
        nr, nc = r + dr, c + dc

        if not (0 <= nr < len(maze) and 0 <= nc < len(maze[0])):
            return await interaction.response.send_message("🚧 Outside bounds!", ephemeral=True)
        if maze[nr][nc] == WALL:
            return await interaction.response.send_message("❌ You hit a wall!", ephemeral=True)

        if maze[nr][nc] == GOAL:
            game["level"] += 1
            game["moves"] = 0
            game["width"] += 2
            game["height"] += 2
            game["maze"] = create_maze(game["width"], game["height"])
            save_games(self.cog.games)
            return await send_board(interaction, game["maze"], game["level"], game["moves"], title="🎉 Level Complete!", view=self)

        # regular move
        maze[r][c] = PATH
        maze[nr][nc] = PLAYER
        game["moves"] += 1
        save_games(self.cog.games)

        await send_board(interaction, maze, game["level"], game["moves"], title="Maze Game", view=self)


# --- Cog ---
class MazeGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = load_games()

    @commands.group(name="maze", invoke_without_command=True)
    async def maze(self, ctx):
        embed = discord.Embed(
            title="Maze Game 🌀 - Help",
            description=f"How to play:\n* Start game with `{PREFIX}maze start`\n* Navigate to `{GOAL}` with the buttons\n\nCommands:"
        )
        embed.add_field(name=PREFIX+"maze", value="Shows this message!", inline=False)
        embed.add_field(name=PREFIX+"maze start", value="Starts a maze game!", inline=False)
        embed.add_field(name=PREFIX+"maze here", value="Calls maze game to channel!", inline=False)
        embed.add_field(name=PREFIX+"maze board", value="Shows current board.", inline=False)
        embed.add_field(name=PREFIX+"maze status", value="Shows status of maze game.", inline=False)
        embed.set_footer(text=f"Help command for maze game! | Version: {MAZE_VERSION}")
        await ctx.send(embed=embed)

    @maze.command(name="start")
    async def start_maze(self, ctx):
        user_id = str(ctx.author.id)

        if user_id in self.games:
            return await ctx.send(f"⚠️ You have an active game. Use `{PREFIX}maze board` or `{PREFIX}maze here`")

        width, height = MAZE_WIDTH, MAZE_HEIGHT
        maze = create_maze(width, height)
        self.games[user_id] = {
            "maze": maze,
            "level": 1,
            "moves": 0,
            "width": width,
            "height": height
        }
        save_games(self.games)
        await send_board(ctx, maze, 1, 0, title="Maze Game 🌀", view=MazeView(self, user_id))

    @maze.command(name="here")
    async def maze_here(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.games:
            return await ctx.send(f"⚠️ No active game. Start one with `{PREFIX}maze start`.")
        game = self.games[user_id]
        await send_board(ctx, game["maze"], game["level"], game["moves"], title="🌀 Maze Here", view=MazeView(self, user_id))

    @maze.command(name="board")
    async def maze_board(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.games:
            return await ctx.send(f"⚠️ No active game. Start one with `{PREFIX}maze start`.")
        game = self.games[user_id]
        await send_board(ctx, game["maze"], game["level"], game["moves"], title="🌀 Maze Board")

    @maze.command(name="status")
    async def maze_status(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.games:
            return await ctx.send(f"⚠️ No active game. Start one with `{PREFIX}maze start`.")
        game = self.games[user_id]
        embed = discord.Embed(title="🌀 Maze Status")
        embed.add_field(name="Status:", value=f"Level: {game['level']} | Moves: {game['moves']}", inline=False)
        embed.set_footer(text=f"Version: {MAZE_VERSION}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MazeGame(bot))
