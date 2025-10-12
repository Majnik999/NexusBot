# steam_customhelp_cog.py
import aiohttp
import asyncio
import discord
import io
import json
import re
import urllib.parse
from bs4 import BeautifulSoup
from discord.ext import commands
from typing import Dict, Tuple, Optional

from settings import PREFIX

# Helper for flag parsing
_FLAG_RE = re.compile(r"--(\w+)(?:\s+([^\s][^\-]*?)(?=(?:\s+--\w+)|$))", re.IGNORECASE)


def parse_flags(argstr: str) -> Tuple[Dict[str, str], str]:
    """Parse command flags from argument string.
    
    Args:
        argstr: The string containing flags and arguments
        
    Returns:
        Tuple of (flags dict, cleaned string without flags)
    """
    flags = {}
    for m in _FLAG_RE.finditer(argstr):
        key = m.group(1).lower()
        val = m.group(2).strip() if m.group(2) else ""
        flags[key] = val
    cleaned = _FLAG_RE.sub("", argstr).strip()
    return flags, cleaned


def short(text: str, limit: int = 1900) -> str:
    """Truncate text if it exceeds limit.
    
    Args:
        text: Text to truncate
        limit: Maximum length allowed
        
    Returns:
        Truncated text with [...] suffix or original if under limit
    """
    if not text:
        return "N/A"
    if len(text) <= limit:
        return text
    return text[: limit - 200] + "\n\n[...] (truncated)"


class Steam(commands.Cog):
    """Steam command group with custom help"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

    def cog_unload(self):
        try:
            asyncio.create_task(self.session.close())
        except Exception:
            pass

    @commands.group(name="steam", invoke_without_command=True)
    async def steam(self, ctx):
        """Steam command group."""
        await self.steam_help(ctx)

    @steam.command(name="help")
    async def steam_help(self, ctx):
        """Custom help embed for Steam commands"""
        embed = discord.Embed(
            title="Steam Commands — Help",
            description="All commands for Steam operations (no API key required).",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=PREFIX+"steam search <game> [--currency EUR] [--platform windows]",
            value="Search Steam store for a game. Returns top 5 results with price, platforms, controller, Steam Deck, tags, genres, and screenshots.",
            inline=False,
        )
        embed.add_field(
            name=PREFIX+"steam manifest <id or game name>",
            value="Fetch a manifest of the steam game from [Steam Manifest Hub](https://killhack.alwaysdata.net/).",
            inline=False,
        )
        embed.add_field(
            name=PREFIX+"steam user <vanity_or_steamid_or_URL>",
            value="Scrape public Steam profile info: display name, avatar, level, country, recently played games, owned games count.",
            inline=False,
        )
        embed.set_footer(text="Example: !steam search volcanoids --currency eur --platform windows")
        await ctx.send(embed=embed)

    # ----- Search -----
    @steam.command(name="search")
    async def steam_search(self, ctx, *, argstr: str):
        """Search Steam store reliably using official app list API."""
        flags, game_name = parse_flags(argstr)
        currency = flags.get("currency", "usd").lower()
        platform_filter = flags.get("platform")

        if not game_name:
            await ctx.send("❌ Please provide a game name.")
            return

        msg = await ctx.send("🔎 Searching Steam... this may take a few seconds.")

        try:
            # Step 1: Get full app list
            async with self.session.get("https://api.steampowered.com/ISteamApps/GetAppList/v0002/?format=json") as resp:
                data = await resp.json()
            apps = data.get("applist", {}).get("apps", [])

            # Step 2: Local search
            matches = [app for app in apps if game_name.lower() in app["name"].lower()]
            if not matches:
                await msg.edit(content=f"❌ No results found for **{game_name}**.")
                return

            matches = matches[:1] # top 1 matches

            # Step 3: Fetch details
            for app in matches:
                appid = app["appid"]
                details_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={currency}&l=en"
                async with self.session.get(details_url) as dresp:
                    details = await dresp.json()
                info = details.get(str(appid), {}).get("data")
                if not info:
                    continue

                title = info.get("name", "Unknown")
                desc = short(info.get("short_description", "No description"), 500)
                release = info.get("release_date", {}).get("date", "Unknown")
                is_free = info.get("is_free", False)

                # Price
                price_text = "Free" if is_free else "Unknown"
                if not is_free and info.get("price_overview"):
                    po = info["price_overview"]
                    final = po.get("final", 0) / 100
                    initial = po.get("initial", 0) / 100
                    discount = po.get("discount_percent", 0)
                    price_text = f"{final:.2f} {currency.upper()}"
                    if discount:
                        price_text += f" (discount {discount}% — original {initial:.2f})"

                # Platform filter
                platforms_list = [p.capitalize() for p, ok in info.get("platforms", {}).items() if ok] or ["N/A"]
                if platform_filter and platform_filter.lower() not in [p.lower() for p in platforms_list]:
                    continue

                controller = info.get("controller_support", "N/A")
                steam_deck = info.get("steam_deck_compatibility", "N/A")
                genres = ", ".join([g.get("description", "") for g in info.get("genres", [])]) or "N/A"

                header_img = info.get("header_image")
                
                # Create main embed
                embed = discord.Embed(title=title, url=f"https://store.steampowered.com/app/{appid}", description=desc, color=discord.Color.blurple())
                if header_img:
                    embed.set_thumbnail(url=header_img)
                embed.add_field(name="Price", value=price_text, inline=True)
                embed.add_field(name="Release", value=release, inline=True)
                embed.add_field(name="Platforms", value=", ".join(platforms_list), inline=True)
                embed.add_field(name="Controller", value=controller, inline=True)
                embed.add_field(name="Steam Deck", value=steam_deck, inline=True)
                embed.add_field(name="App ID", value=str(appid), inline=True)
                embed.add_field(name="Genres", value=genres, inline=False)

                # Create gallery embeds
                gallery_embeds = []
                store_url = f"https://store.steampowered.com/app/{appid}"

                # Add screenshots to gallery
                screenshots = info.get("screenshots", [])
                for screenshot in screenshots[:4]:  # Limit to 4 screenshots
                    gallery_embed = discord.Embed(url=store_url)
                    gallery_embed.set_image(url=screenshot["path_full"])
                    gallery_embeds.append(gallery_embed)

                # Add videos/movies to gallery
                movies = info.get("movies", [])
                for movie in movies[:2]:  # Limit to 2 videos
                    if "mp4" in movie:
                        # Prefer "max" if it exists, otherwise largest numeric
                        mp4_dict = movie["mp4"]
                        if "max" in mp4_dict:
                            max_video = mp4_dict["max"]
                        else:
                            numeric_keys = [int(k) for k in mp4_dict.keys() if k.isdigit()]
                            if numeric_keys:
                                best_quality = str(max(numeric_keys))
                                max_video = mp4_dict[best_quality]
                            else:
                                max_video = list(mp4_dict.values())[0]  # fallback
                        gallery_embed = discord.Embed(url=store_url)
                        gallery_embed.description = f"🎬 [Watch video]({max_video})"
                        if "thumbnail" in movie:
                            gallery_embed.set_image(url=movie["thumbnail"])
                        gallery_embeds.append(gallery_embed)

                # Send all embeds
                await msg.edit(content="", embeds=[embed] + gallery_embeds)

        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")


    # ----- Manifest -----
    @steam.command(name="manifest")
    async def steam_manifest(self, ctx: commands.Context, *, game_name: str) -> None:
        """Fetch manifest for a Steam game using official app list API."""
        msg = await ctx.send("🔎 Searching Steam... this may take a few seconds.")
        try:
            # Step 1: Get full app list
            async with self.session.get("https://api.steampowered.com/ISteamApps/GetAppList/v0002/?format=json") as resp:
                data = await resp.json()
            apps = data.get("applist", {}).get("apps", [])

            # Step 2: Local search
            matches = [app for app in apps if game_name.lower() in app["name"].lower()]
            if not matches:
                await ctx.send(f"❌ No results found for **{game_name}**.")
                return

            app = matches[0]  # take first match
            app_id = str(app["appid"])
            game_name = app["name"]

            # Step 3: Get header image
            details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=en"
            async with self.session.get(details_url) as resp:
                details = await resp.json()
            header_img = details.get(app_id, {}).get("data", {}).get("header_image")

            embed = discord.Embed(
                title=f"Manifest for {game_name}",
                description=f"Steam App ID: {app_id}",
                color=discord.Color.blue()
            )
            if header_img:
                embed.set_thumbnail(url=header_img)

            await msg.edit(content="🔎 Fetching manifest...")

            # Step 4: Fetch manifest from GitHub
            manifest_url = f"https://codeload.github.com/SteamAutoCracks/ManifestHub/zip/refs/heads/{app_id}"
            async with self.session.get(manifest_url) as resp:
                if resp.status == 200:
                    file_data = await resp.read()
                    file = discord.File(fp=io.BytesIO(file_data), filename=f"manifest_{app_id}.zip")
                    await msg.edit(content="", embed=embed, file=file)
                else:
                    await msg.edit(content="", embed=discord.Embed(title="Error", description="No manifest found for this game", color=discord.Color.red()))

        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")


    # ----- User scraping -----
    @steam.command(name="user")
    async def steam_user(self, ctx, identifier: str):
        identifier = identifier.strip("/")
        if identifier.isdigit() and len(identifier) >= 16:
            profile_url = f"https://steamcommunity.com/profiles/{identifier}/"
        else:
            if "steamcommunity.com" in identifier:
                m = re.search(r"steamcommunity\.com/(id|profiles)/([^/]+)", identifier)
                if not m:
                    await ctx.send("❌ Could not parse URL.")
                    return
                profile_url = f"https://steamcommunity.com/{m.group(1)}/{m.group(2)}/"
            else:
                profile_url = f"https://steamcommunity.com/id/{identifier}/"

        try:
            async with self.session.get(profile_url) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ HTTP {resp.status}")
                    return
                text = await resp.text()
        except Exception as e:
            await ctx.send(f"❌ Failed: {e}")
            return

        soup = BeautifulSoup(text, "html.parser")
        name_tag = soup.find("span", {"class": "actual_persona_name"})
        name = name_tag.text.strip() if name_tag else "N/A"
        avatar_tag = soup.find("div", {"class": "playerAvatarAutoSizeInner"})
        avatar_url = avatar_tag.img["src"] if avatar_tag and avatar_tag.img else None
        level_tag = soup.find("span", {"class": "friendPlayerLevelNum"})
        level = level_tag.text.strip() if level_tag else "N/A"
        country_tag = soup.find("div", {"class": "header_real_name ellipsis"})
        country = country_tag.text.strip() if country_tag else "N/A"

        recent_games = []
        recent_section = soup.find("div", {"id": "recentlyPlayedGames"})
        if recent_section:
            games = recent_section.find_all("div", {"class": "recent_game"})
            for g in games[:5]:
                title_tag = g.find("div", {"class": "game_name"})
                time_tag = g.find("div", {"class": "game_info"})
                if title_tag:
                    recent_games.append(f"{title_tag.text.strip()} — {time_tag.text.strip() if time_tag else ''}")

        owned_count = "N/A"
        stats_tag = soup.find("div", {"class": "profile_count_link_total"})
        if stats_tag:
            try:
                owned_count = int(stats_tag.text.strip().replace(",", ""))
            except:
                owned_count = stats_tag.text.strip()

        embed = discord.Embed(title=name, url=profile_url, color=discord.Color.green())
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Profile URL", value=profile_url, inline=False)
        embed.add_field(name="Level", value=level, inline=True)
        embed.add_field(name="Country", value=country, inline=True)
        embed.add_field(name="Owned games count", value=owned_count, inline=True)
        if recent_games:
            embed.add_field(name="Recently played (top 5)", value="\n".join(recent_games), inline=False)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Steam(bot))
