# steam_customhelp_cog.py
import aiohttp
import asyncio
import discord
from discord.ext import commands
from bs4 import BeautifulSoup
import re
import urllib.parse
import json
import io

from settings import PREFIX

# Helper for flag parsing
_FLAG_RE = re.compile(r"--(\w+)(?:\s+([^\s][^\-]*?)(?=(?:\s+--\w+)|$))", re.IGNORECASE)


def parse_flags(argstr: str):
    flags = {}
    for m in _FLAG_RE.finditer(argstr):
        key = m.group(1).lower()
        val = m.group(2).strip() if m.group(2) else ""
        flags[key] = val
    cleaned = _FLAG_RE.sub("", argstr).strip()
    return flags, cleaned


def short(text: str, limit: int = 1900) -> str:
    if not text:
        return "N/A"
    if len(text) <= limit:
        return text
    return text[: limit - 200] + "\n\n[...] (truncated)"


class SteamCustomHelp(commands.Cog):
    """Steam command group with custom help"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

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
        """Search Steam store with optional currency/platform"""
        flags, game_name = parse_flags(argstr)
        currency = flags.get("currency", "usd").lower()
        platform_filter = flags.get("platform")

        if not game_name:
            await ctx.send("❌ Please provide a game name.")
            return

        search_url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(game_name)}&cc={currency}&l=en"
        async with self.session.get(search_url) as resp:
            data = await resp.json()
        items = data.get("items", [])[:10]
        if not items:
            await ctx.send(f"❌ No results for **{game_name}**.")
            return

        results = []
        for item in items:
            appid = item.get("id")
            if not appid:
                continue
            details_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={currency}&l=en"
            async with self.session.get(details_url) as dresp:
                details = await dresp.json()
            info = details.get(str(appid), {}).get("data")
            if not info:
                continue

            # platform filter
            if platform_filter:
                platforms = [p.lower() for p, ok in info.get("platforms", {}).items() if ok]
                if platform_filter.lower() not in platforms:
                    continue

            results.append((appid, info))
            if len(results) >= 5:
                break

        if not results:
            await ctx.send("❌ No games matched your filters.")
            return

        for appid, info in results:
            title = info.get("name", "Unknown")
            steam_url = f"https://store.steampowered.com/app/{appid}"
            desc = short(info.get("short_description", "No description"), 500)
            release = info.get("release_date", {}).get("date", "Unknown")
            is_free = info.get("is_free", False)

            # price
            price_text = "Free" if is_free else "Unknown"
            if not is_free and info.get("price_overview"):
                po = info["price_overview"]
                final = po.get("final", 0) / 100
                initial = po.get("initial", 0) / 100
                discount = po.get("discount_percent", 0)
                price_text = f"{final:.2f} {currency.upper()}"
                if discount:
                    price_text += f" (discount {discount}% — original {initial:.2f})"

            platforms_list = [p.capitalize() for p, ok in info.get("platforms", {}).items() if ok] or ["N/A"]
            controller = info.get("controller_support", "N/A")
            steam_deck = info.get("steam_deck_compatibility", "N/A")
            genres = ", ".join([g.get("description", "") for g in info.get("genres", [])]) or "N/A"

            header_img = info.get("header_image")
            screenshots = info.get("screenshots", [])[:1]
            screenshot_url = screenshots[0]["path_full"] if screenshots else None

            embed = discord.Embed(title=title, url=steam_url, description=desc, color=discord.Color.blurple())
            if header_img:
                embed.set_thumbnail(url=header_img)
            if screenshot_url:
                embed.set_image(url=screenshot_url)
            embed.add_field(name="Price", value=price_text, inline=True)
            embed.add_field(name="Release", value=release, inline=True)
            embed.add_field(name="Platforms", value=", ".join(platforms_list), inline=True)
            embed.add_field(name="Controller", value=controller, inline=True)
            embed.add_field(name="Steam Deck", value=steam_deck, inline=True)
            embed.add_field(name="Genres", value=genres, inline=False)

            await ctx.send(embed=embed)

    # ----- Manifest -----
    @steam.command(name="manifest")
    async def steam_manifest(self, ctx, *, game_name: str):
        """Fetch manifest for a Steam game"""
        import io
        import urllib.parse

        search_url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(game_name)}&l=en"

        try:
            # Search for the game
            async with self.session.get(search_url, timeout=10) as resp:
                if resp.status != 200:
                    await ctx.send("❌ Failed to reach Steam store. Please try again later.")
                    return
                data = await resp.json()
            
            items = data.get("items")
            if not items:
                await ctx.send(f"❌ No results found for **{game_name}**")
                return

            app_id = str(items[0]["id"])
            game_name = items[0]["name"]

            # Get game details for thumbnail
            details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=en"
            async with self.session.get(details_url, timeout=10) as resp:
                if resp.status != 200:
                    header_img = None
                else:
                    details = await resp.json()
                    header_img = details.get(app_id, {}).get("data", {}).get("header_image")

            # Build embed
            embed = discord.Embed(
                title=f"Manifest for {game_name}",
                description=f"Steam App ID: {app_id}",
                color=discord.Color.blue()
            )
            if header_img:
                embed.set_thumbnail(url=header_img)

            # Get manifest from GitHub
            manifest_url = f"https://codeload.github.com/SteamAutoCracks/ManifestHub/zip/refs/heads/{app_id}"
            async with self.session.get(manifest_url, timeout=15) as resp:
                if resp.status == 200:
                    file_data = await resp.read()
                    file = discord.File(fp=io.BytesIO(file_data), filename=f"manifest_{app_id}.zip")
                    await ctx.send(embed=embed)
                    await ctx.send(file=file)
                else:
                    embed.add_field(name="Error", value="No manifest found for this game")
                    await ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await ctx.send("❌ Request timed out. Please try again later.")
        except Exception:
            # Catch all other errors without exposing details
            await ctx.send("❌ An unexpected error occurred. Please try again.")

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


def setup(bot):
    bot.add_cog(SteamCustomHelp(bot))
