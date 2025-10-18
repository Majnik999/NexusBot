import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import aiosqlite
import random
import datetime
import asyncio
from main import logger
from settings import PREFIX, DEFAULT_DAILY_REWARD, FISH_CATCH_CHANCE_PERCENTAGE, DAILY_COOLDOWN_HOURS, SHOP_PAGE_SIZE, EMOJIS, GAMBLE_LOSE_COLOR, GAMBLE_WIN_COLOR, DAILY_COLOR, BALANCE_COLOR, INVENTORY_COLOR, LOOT_COLOR, SELL_COLOR, HELP_COLOR, FISH_CHANCES, FISH_ITEMS, DIG_ITEMS, DIG_CHANCES, COOLDOWN_DIG_FISH_MINUTES, BLACK_JACK_SUITS, BLACK_JACK_RANKS, CHOP_NOT_FALL_TREE_CHANCE_PERCENTAGE, CHOP_ITEMS, CHOP_CHANCES, VOICE_REWARD_INTERVAL_MINUTES, VOICE_REWARD_AMOUNT
from src.config.versions import ECONOMY_VERSION

# ===================== CONFIG =====================
DB_PATH = "src/databases/economy.db"

# ===================== ECONOMY COG =====================
class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def initialize_database(self):
        logger.info("Initializing database")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    last_daily TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id INTEGER,
                    item TEXT,
                    quantity INTEGER,
                    PRIMARY KEY (user_id, item)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    item_id TEXT PRIMARY KEY,
                    name TEXT,
                    price INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cooldowns (
                    user_id INTEGER,
                    command TEXT,
                    last_used INTEGER
                )
            """)

            
            await db.commit()
        logger.debug("Database schema ensured")

    self.voice_sessions = {}
    self.voice_reward_interval_minutes = VOICE_REWARD_INTERVAL_MINUTES
    self.voice_reward_amount = VOICE_REWARD_AMOUNT

    # ================= INITIALIZATION =================
    async def cog_load(self):
        logger.info("Cog load started")
        await self.initialize_database()
        logger.info("Cog load finished and database initialized")

    def cog_unload(self):
        sessions = list(self.voice_sessions.values())
        self.voice_sessions.clear()
        for session in sessions:
            try:
                session["task"].cancel()
            except Exception:
                pass

    def stop_voice_session(self, member: discord.Member):
        key = (member.guild.id, member.id)
        session = self.voice_sessions.pop(key, None)
        if session:
            try:
                session["task"].cancel()
            except Exception:
                pass

    def start_voice_session(self, member: discord.Member, channel: discord.VoiceChannel):
        if member.bot:
            return
        key = (member.guild.id, member.id)
        existing = self.voice_sessions.get(key)
        if existing and not existing["task"].done() and existing["channel_id"] == channel.id:
            return
        if existing:
            try:
                existing["task"].cancel()
            except Exception:
                pass
        task = asyncio.create_task(self._voice_reward_loop(member))
        self.voice_sessions[key] = {"channel_id": channel.id, "task": task}

    async def _voice_reward_loop(self, member: discord.Member):
        interval = self.voice_reward_interval_minutes * 60
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            voice_client = next((vc for vc in self.bot.voice_clients if vc.guild == member.guild), None)
            if not voice_client or not member.voice or not member.voice.channel or member.voice.channel.id != voice_client.channel.id:
                break
            await self.update_balance(member.id, self.voice_reward_amount)
            try:
                await member.send(f"🎉 You received {self.voice_reward_amount} coins for staying in voice!")
            except discord.Forbidden:
                logger.debug(f"Could not DM {member.id} about voice reward (DMs closed)")
            except Exception as e:
                logger.warning(f"Failed to DM {member.id} about voice reward: {e}")
        self.voice_sessions.pop((member.guild.id, member.id), None)
        interval = self.voice_reward_interval_minutes * 60
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            voice_client = next((vc for vc in self.bot.voice_clients if vc.guild == member.guild), None)
            if not voice_client or not member.voice or not member.voice.channel or member.voice.channel.id != voice_client.channel.id:
                break
            await self.update_balance(member.id, self.voice_reward_amount)
        self.voice_sessions.pop((member.guild.id, member.id), None)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        voice_client = next((vc for vc in self.bot.voice_clients if vc.guild == member.guild), None)

        if member.id == self.bot.user.id:
            for (guild_id, user_id), session in list(self.voice_sessions.items()):
                if guild_id == member.guild.id:
                    try:
                        session["task"].cancel()
                    except Exception:
                        pass
                    del self.voice_sessions[(guild_id, user_id)]
            if after.channel:
                for m in after.channel.members:
                    if not m.bot:
                        self.start_voice_session(m, after.channel)
            return

        if voice_client and after.channel and voice_client.channel and after.channel.id == voice_client.channel.id:
            self.start_voice_session(member, after.channel)
        else:
            self.stop_voice_session(member)

    # ================= HELPER FUNCTIONS =================
    async def get_cooldown(self, user_id: int, command: str) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT last_used FROM cooldowns WHERE user_id = ? AND command = ?",
                (user_id, command),
            ) as cursor:
                row = await cursor.fetchone()
                result = row[0] if row else 0
                logger.debug(f"get_cooldown user={user_id} command={command} -> {result}")
                return result

    async def set_cooldown(self, user_id: int, command: str):
        now = int(datetime.datetime.utcnow().timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO cooldowns (user_id, command, last_used) VALUES (?, ?, ?)",
                (user_id, command, now),
            )
            await db.commit()
        logger.debug(f"set_cooldown user={user_id} command={command} at={now}")

    async def delete_old_record_cooldown(self, user_id: int, command: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cooldowns WHERE user_id = ? AND command = ?", (user_id, command))
            await db.commit()
        logger.debug(f"delete_old_record_cooldown user={user_id} command={command}")

    async def has_user_cooldown(
        self, user_id: int, command: str, cooldown_seconds: int
    ) -> int | None:
        last_used = await self.get_cooldown(user_id, command)
        now = int(datetime.datetime.utcnow().timestamp())
        if (now - last_used) < cooldown_seconds:
            expiry = last_used + cooldown_seconds
            logger.info(f"cooldown active user={user_id} command={command} expires={expiry}")
            return expiry  # expiry timestamp
        logger.debug(f"no cooldown user={user_id} command={command}")
        return None

    async def clear_cooldowns(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cooldowns WHERE user_id = ?", (user_id,))
            await db.commit()
        logger.info(f"clear_cooldowns for user={user_id}")
    
    async def get_balance(self, user_id: int) -> int:
        if user_id == self.bot.user.id:
            logger.debug(f"get_balance requested for bot user {user_id}, returning 0")
            return 0
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await db.execute("INSERT INTO economy (user_id, balance, last_daily) VALUES (?, ?, ?)",
                                     (user_id, 0, None))
                    await db.commit()
                    logger.info(f"Created economy row for user={user_id} with balance=0")
                    return 0
                logger.debug(f"get_balance user={user_id} -> {row[0]}")
                return row[0]

    async def update_balance(self, user_id: int, amount: int):
        balance = await self.get_balance(user_id)
        new_balance = max(0, balance + amount)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE economy SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            await db.commit()
        logger.info(f"update_balance user={user_id} change={amount} old={balance} new={new_balance}")

    async def get_inventory(self, user_id: int) -> dict:
        items = {}
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT item, quantity FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
                async for item, qty in cursor:
                    items[item] = qty
        logger.debug(f"get_inventory user={user_id} -> {items}")
        return items

    async def add_item(self, user_id: int, item: str, qty: int = 1):
        item = item.lower()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT quantity FROM inventory WHERE user_id = ? AND item = ?", (user_id, item)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await db.execute("UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item = ?",
                                     (qty, user_id, item))
                    logger.debug(f"add_item increment user={user_id} item={item} qty={qty}")
                else:
                    await db.execute("INSERT INTO inventory (user_id, item, quantity) VALUES (?, ?, ?)",
                                     (user_id, item, qty))
                    logger.debug(f"add_item insert user={user_id} item={item} qty={qty}")
            await db.commit()

    async def remove_item(self, user_id: int, item: str, qty: int = 1) -> bool:
        item = item.lower()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT quantity FROM inventory WHERE user_id = ? AND item = ?", (user_id, item)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] < qty:
                    logger.info(f"remove_item failed user={user_id} item={item} requested={qty} available={(row[0] if row else 0)}")
                    return False
                new_qty = row[0] - qty
                if new_qty == 0:
                    await db.execute("DELETE FROM inventory WHERE user_id = ? AND item = ?", (user_id, item))
                else:
                    await db.execute("UPDATE inventory SET quantity = ? WHERE user_id = ? AND item = ?",
                                     (new_qty, user_id, item))
            await db.commit()
        logger.debug(f"remove_item success user={user_id} item={item} qty={qty} remaining={new_qty if 'new_qty' in locals() else 0}")
        return True

    async def fetch_shop_items(self) -> dict:
        items = {}
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT item_id, name, price FROM shop_items") as cursor:
                async for item_id, name, price in cursor:
                    items[item_id] = {"name": name, "price": price}
        logger.debug(f"fetch_shop_items -> {len(items)} items")
        return items

    async def fetch_leaderboard(self) -> list[tuple[int, int]]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
        logger.debug(f"fetch_leaderboard -> {len(rows)} rows")
        return rows

    # ===================== ECONOMY GROUP =====================
    @commands.group(name="economy", aliases=["eco"], invoke_without_command=True)
    async def economy_group(self, ctx):
        await self.eco_help(ctx)

    # ===================== HELP EMBED =====================
    async def eco_help(self, ctx):
        embed = discord.Embed(title="💰 Economy Commands", color=HELP_COLOR)
        
        embed.add_field(name=PREFIX+"economy balance [user]", value="Check balance of yourself or a user", inline=False)
        embed.add_field(name=PREFIX+"economy daily", value="Claim your daily reward", inline=False)
        embed.add_field(name=PREFIX+"economy shop", value="Browse the shop (with page navigation)", inline=False)
        embed.add_field(name=PREFIX+"economy buy <item_id> [amount]", value="Buy items from the shop", inline=False)
        embed.add_field(name=PREFIX+"economy sell <item_id> [amount]", value="Sell items to the shop", inline=False)
        embed.add_field(name=PREFIX+"economy inventory", value="Check your inventory", inline=False)
        embed.add_field(name=PREFIX+"economy dig [times]", value="Dig for resources multiple times", inline=False)
        embed.add_field(name=PREFIX+"economy fish [times]", value="Fish for items multiple times", inline=False)
        embed.add_field(name=PREFIX+"economy chop [times]", value="Chop for wood and items multiple times", inline=False)
        embed.add_field(name=PREFIX+"economy gamble <amount>", value="Coinflip to gamble coins", inline=False)
        embed.add_field(name=PREFIX+"economy trade [user]", value="Trade items with another user", inline=False)
        
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        
        await ctx.send(embed=embed)

    # ===================== BALANCE =====================
    @economy_group.command(name="balance", aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        if member.bot:
            return await ctx.send("❌ You cannot check a bot's balance.")
        balance = await self.get_balance(member.id)
        embed = discord.Embed(title=f"{member.display_name}'s Balance", color=BALANCE_COLOR)
        embed.add_field(name="💰 Coins", value=balance)
        embed.set_footer(text=f"Use {PREFIX}economy for more commands | Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== DAILY =====================
    @economy_group.command(name="daily")
    async def daily(self, ctx):
        user_id = ctx.author.id
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_daily FROM economy WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            last_daily = row[0] if row else None

            now = datetime.datetime.utcnow()
            cooldown = DAILY_COOLDOWN_HOURS * 3600
            if last_daily:
                last_time = datetime.datetime.fromisoformat(last_daily)
                elapsed = (now - last_time).total_seconds()
                if elapsed < cooldown:
                    reset_time = last_time + datetime.timedelta(seconds=cooldown)
                    unix_ts = int(reset_time.timestamp())
                    return await ctx.send(f"❌ Daily already claimed. Try again <t:{unix_ts}:R>")

            await self.update_balance(user_id, DEFAULT_DAILY_REWARD)
            await db.execute("UPDATE economy SET last_daily = ? WHERE user_id = ?", (now.isoformat(), user_id))
            await db.commit()

        embed = discord.Embed(title="🎁 Daily Reward", color=DAILY_COLOR)
        embed.add_field(name="Coins Earned", value=DEFAULT_DAILY_REWARD)
        embed.set_footer(text="Come back every day for more rewards!")
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== SHOP =====================
    @economy_group.command(name="shop")
    async def shop(self, ctx):
        items = await self.fetch_shop_items()
        if not items:
            return await ctx.send("🛒 The shop is currently empty.")

        sorted_items = list(items.items())
        pages = [sorted_items[i:i+SHOP_PAGE_SIZE] for i in range(0, len(sorted_items), SHOP_PAGE_SIZE)]

        class ShopView(View):
            def __init__(self, pages):
                super().__init__(timeout=120)
                self.pages = pages
                self.current = 0
                self.embed = self.create_embed()

                self.prev.disabled = True
                if len(self.pages) <= 1:
                    self.next.disabled = True

            def create_embed(self):
                embed = discord.Embed(title="🛒 Shop", color=BALANCE_COLOR)
                for item_id, data in self.pages[self.current]:
                    emoji = EMOJIS.get(item_id, "")
                    embed.add_field(name=f"{emoji} {data['name']} (`{item_id}`)", value=f"Price: {data['price']} coins", inline=False)
                embed.set_footer(text=f"Page {self.current+1}/{len(self.pages)} | {PREFIX}economy buy <item_id> <amount> | Version: {ECONOMY_VERSION}")
                return embed

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
            async def prev(self, interaction: discord.Interaction, button: Button):
                self.current -= 1
                if self.current <= 0:
                    self.prev.disabled = True
                self.next.disabled = False
                await interaction.response.edit_message(embed=self.create_embed(), view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
            async def next(self, interaction: discord.Interaction, button: Button):
                self.current += 1
                if self.current >= len(self.pages)-1:
                    self.next.disabled = True
                self.prev.disabled = False
                await interaction.response.edit_message(embed=self.create_embed(), view=self)

        await ctx.send(embed=ShopView(pages).create_embed(), view=ShopView(pages))

    # ===================== BUY =====================
    @economy_group.command(name="buy")
    async def buy(self, ctx, item_id: str, amount: int = 1):
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        shop_items = await self.fetch_shop_items()
        item_id = item_id.lower()
        if item_id not in shop_items:
            return await ctx.send("❌ That item does not exist in the shop.")
        item = shop_items[item_id]
        total_price = item['price'] * amount
        balance = await self.get_balance(ctx.author.id)
        if balance < total_price:
            return await ctx.send("❌ You do not have enough coins.")
        await self.update_balance(ctx.author.id, -total_price)
        await self.add_item(ctx.author.id, item_id, amount)
        embed = discord.Embed(title="🛒 Purchase Successful", description=f"You bought {amount} x {item['name']} for {total_price} coins.", color=BALANCE_COLOR)
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== SELL =====================
    @economy_group.command(name="sell")
    async def sell(self, ctx, item_id: str, amount: int = 1000000000000000000000000000000000):
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        item_id = item_id.lower()
        inventory = await self.get_inventory(ctx.author.id)
        if item_id not in inventory or inventory[item_id] < amount:
            # Sell all items if amount exceeds the inventory amount
            amount = inventory.get(item_id, 0)
            if amount == 0:
                return await ctx.send("❌ You do not have that item in your inventory.")
        shop_items = await self.fetch_shop_items()
        if item_id not in shop_items:
            return await ctx.send("❌ This item cannot be sold to the shop.")
        if shop_items[item_id]["price"] <= 1:
            sell_price = shop_items[item_id]["price"]
        else:
            sell_price = shop_items[item_id]["price"] // 2
        total_earnings = sell_price * amount
        await self.remove_item(ctx.author.id, item_id, amount)
        await self.update_balance(ctx.author.id, total_earnings)
        embed = discord.Embed(title="💰 Item Sold", description=f"You sold {amount} x {shop_items[item_id]['name']} for {total_earnings} coins.", color=SELL_COLOR)
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== INVENTORY =====================
    @economy_group.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx):
        inv = await self.get_inventory(ctx.author.id)
        if not inv:
            return await ctx.send("🎒 Your inventory is empty.")
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Inventory", color=INVENTORY_COLOR)
        embed.description = "\n".join(f"{EMOJIS.get(item, '❔')} {item.capitalize()} x{qty}" for item, qty in inv.items())
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== DIG =====================
    @economy_group.command(name="dig")
    async def dig(self, ctx, times: int = 10):
        cooldown_seconds = COOLDOWN_DIG_FISH_MINUTES * 60
        remaining = await self.has_user_cooldown(ctx.author.id, "dig", cooldown_seconds)
        if remaining:
            return await ctx.send(
                f"❌ You are on cooldown for this command. "
                f"Try again <t:{remaining}:R> (<t:{remaining}:T>)"
            )
        else:
            await self.delete_old_record_cooldown(ctx.author.id, "dig")
        
        
        await self.set_cooldown(ctx.author.id, "dig")
        if times <= 0:
            return await ctx.send("❌ Times must be positive.")
        elif times >= 11:
            return await ctx.send("❌ Maximum is 10 per command!")

        possible_items = DIG_ITEMS
        item_weights = DIG_CHANCES

        found_items = []
        for _ in range(times):
            found = random.choices(possible_items, weights=item_weights, k=random.randint(0, 5))
            for item in found:
                await self.add_item(ctx.author.id, item, 1)
            found_items.extend(found)
        logger.info(f"dig results user={ctx.author.id} found={len(found_items)} items")

        embed = discord.Embed(title=f"⛏️ You dug {times} times and found:", color=LOOT_COLOR)
        desc_dict = {}
        for item in found_items:
            desc_dict[item] = desc_dict.get(item, 0) + 1
        embed.description = "\n".join(
            f"{EMOJIS.get(item, '❔')} {item.capitalize()} x{qty}"
            for item, qty in desc_dict.items()
        )
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)


    @economy_group.command(name="chop")
    async def chop(self, ctx, times: int = 10):
        logger.info(f"Command: chop by user={ctx.author.id} times={times}")
        cooldown_seconds = COOLDOWN_DIG_FISH_MINUTES * 60
        remaining = await self.has_user_cooldown(ctx.author.id, "chop", cooldown_seconds)
        if remaining:
            return await ctx.send(
                f"❌ You are on cooldown for this command. "
                f"Try again <t:{remaining}:R> (<t:{remaining}:T>)"
            )
        else:
            await self.delete_old_record_cooldown(ctx.author.id, "chop")
        
        
        await self.set_cooldown(ctx.author.id, "chop")
        if times <= 0:
            return await ctx.send("❌ Times must be positive.")
        elif times >= 11:
            return await ctx.send("❌ Maximum is 10 per command!")

        possible_items = CHOP_ITEMS
        item_weights = CHOP_CHANCES

        found_items = []
        for _ in range(times):
            if random.randint(1, 100) > CHOP_NOT_FALL_TREE_CHANCE_PERCENTAGE:
                found = random.choices(possible_items, weights=item_weights, k=random.randint(0, 5))
                for item in found:
                    await self.add_item(ctx.author.id, item, 1)
                found_items.extend(found)

        if not found_items:
            logger.info(f"chop found nothing user={ctx.author.id}")
            return await ctx.send("🪓 You chopped but tree felt on you this time!")
        logger.info(f"chop results user={ctx.author.id} found={len(found_items)} items")

        embed = discord.Embed(title=f"🪓 You chopped {times} times and found:", color=LOOT_COLOR)
        desc_dict = {}
        for item in found_items:
            desc_dict[item] = desc_dict.get(item, 0) + 1
        embed.description = "\n".join(
            f"{EMOJIS.get(item, '❔')} {item.capitalize()} x{qty}"
            for item, qty in desc_dict.items()
        )
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)
    
    # ===================== FISH =====================
    @economy_group.command(name="fish")
    async def fish(self, ctx, times: int = 10):
        logger.info(f"Command: fish by user={ctx.author.id} times={times}")
        cooldown_seconds = COOLDOWN_DIG_FISH_MINUTES * 60
        remaining = await self.has_user_cooldown(ctx.author.id, "fish", cooldown_seconds)
        if remaining:
            return await ctx.send(
                f"❌ You are on cooldown for this command. "
                f"Try again <t:{remaining}:R> (<t:{remaining}:T>)"
            )
        else:
            await self.delete_old_record_cooldown(ctx.author.id, "fish")

        await self.set_cooldown(ctx.author.id, "fish")
        if times <= 0:
            return await ctx.send("❌ Times must be positive.")
        elif times >= 11:
            return await ctx.send("❌ Maximum is 10 per command!")

        fish_items = FISH_ITEMS
        fish_weights = FISH_CHANCES

        caught_items = []
        for _ in range(times):
            if random.randint(1, 100) <= FISH_CATCH_CHANCE_PERCENTAGE:
                caught = random.choices(fish_items, weights=fish_weights, k=random.randint(1, 2))
                for fish in caught:
                    await self.add_item(ctx.author.id, fish.lower(), 1)
                caught_items.extend(caught)

        if not caught_items:
            logger.info(f"fish caught nothing user={ctx.author.id}")
            return await ctx.send("🎣 You fished but didn't catch anything this time!")
        logger.info(f"fish results user={ctx.author.id} caught={len(caught_items)} fish")

        embed = discord.Embed(title=f"🎣 You fished {times} times and caught:", color=LOOT_COLOR)
        desc_dict = {}
        for fish in caught_items:
            desc_dict[fish] = desc_dict.get(fish, 0) + 1
        embed.description = "\n".join(
            f"{EMOJIS.get(fish, '❔')} {fish.capitalize()} x{qty}"
            for fish, qty in desc_dict.items()
        )
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)



    # ===================== GAMBLE =====================
    @economy_group.command(name="coinflip", aliases=["cf"])
    async def coinflip(self, ctx, amount: int):
        logger.info(f"Command: coinflip by user={ctx.author.id} amount={amount}")
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        balance = await self.get_balance(ctx.author.id)
        if balance < amount:
            logger.info(f"coinflip insufficient funds user={ctx.author.id} balance={balance} bet={amount}")
            return await ctx.send("❌ Not enough coins.")
        won = random.choice([True, False])
        if won:
            amount = amount*2
        await self.update_balance(ctx.author.id, amount if won else -amount)
        logger.info(f"coinflip result user={ctx.author.id} won={won} change={amount if won else -amount}")
        embed = discord.Embed(title="🎲 Coinflip", description=f"You {'won' if won else 'lost'} {amount} coins!", color=GAMBLE_WIN_COLOR if won else GAMBLE_LOSE_COLOR)
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # black jack with buttons
    @economy_group.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx, amount: int):
        logger.info(f"Command: blackjack by user={ctx.author.id} amount={amount}")
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        balance = await self.get_balance(ctx.author.id)
        if balance < amount:
            return await ctx.send("❌ Not enough coins.")

        # TAKE THE BET UP-FRONT
        await self.update_balance(ctx.author.id, -amount)
        logger.info(f"blackjack bet taken user={ctx.author.id} bet={amount}")

        suits = BLACK_JACK_SUITS
        ranks = BLACK_JACK_RANKS
        
        values = {rank: min(10, i+2) for i, rank in enumerate(ranks)}
        values['A'] = 11  # Ace can be 1 or 11, handled later

        def calculate_hand(hand):
            total = sum(values[card[1]] for card in hand)
            aces = sum(1 for card in hand if card[1] == 'A')
            while total > 21 and aces:
                total -= 10
                aces -= 1
            return total

        deck = [(suit, rank) for suit in suits for rank in ranks]
        random.shuffle(deck)

        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        def create_embed(final=False):
            embed = discord.Embed(title="🃏 Blackjack", color=BALANCE_COLOR)
            embed.add_field(name="Your Hand", value=" ".join(f"{suit}{rank}" for suit, rank in player_hand) + f" (Total: {calculate_hand(player_hand)})", inline=False)
            if final:
                embed.add_field(name="Dealer's Hand", value=" ".join(f"{suit}{rank}" for suit, rank in dealer_hand) + f" (Total: {calculate_hand(dealer_hand)})", inline=False)
            else:
                embed.add_field(name="Dealer's Hand", value=f"{dealer_hand[0][0]}{dealer_hand[0][1]} ??", inline=False)
            if final:
                player_total = calculate_hand(player_hand)
                dealer_total = calculate_hand(dealer_hand)
                if player_total > 21:
                    result = "You busted! You lose."
                elif dealer_total > 21 or player_total > dealer_total:
                    result = "You win!"
                elif player_total < dealer_total:
                    result = "You lose!"
                else:
                    result = "It's a draw!"
                embed.add_field(name="Result", value=result, inline=False)
            embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
            return embed
        
        class BlackjackView(View):
            def __init__(self):
                super().__init__(timeout=120)
                self.result = None

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("You are not allowed to use this control.")
                    return False
                return True

            @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
            async def hit(self, interaction: discord.Interaction, button: Button):
                player_hand.append(deck.pop())
                player_total = calculate_hand(player_hand)
                if player_total > 21:
                    self.result = "lose"
                    await interaction.response.edit_message(embed=create_embed(final=True), view=self)
                    self.stop()
                    return
                await interaction.response.edit_message(embed=create_embed(), view=self)

            @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
            async def stand(self, interaction: discord.Interaction, button: Button):
                while calculate_hand(dealer_hand) < 17:
                    dealer_hand.append(deck.pop())
                dealer_total = calculate_hand(dealer_hand)
                player_total = calculate_hand(player_hand)
                if dealer_total > 21 or player_total > dealer_total:
                    self.result = "win"
                elif player_total < dealer_total:
                    self.result = "lose"
                else:
                    self.result = "draw"
                await interaction.response.edit_message(embed=create_embed(final=True), view=self)
                self.stop()
        
        view = BlackjackView()
        await ctx.send(embed=create_embed(), view=view)
        await view.wait()

        res = view.result
        # TIMEOUT: refund bet
        if res is None:
            await self.update_balance(ctx.author.id, amount)
            logger.info(f"blackjack timeout - bet refunded user={ctx.author.id} bet={amount}")
            return await ctx.send("⏰ Game timed out. Your bet has been refunded.")

        # SETTLE
        if res == "win":
            # pay back stake + winnings: since stake already deducted, give 2*amount to net +amount
            await self.update_balance(ctx.author.id, amount * 2)
            await ctx.send(f"✅ You won {amount} coins!")
            logger.info(f"blackjack win user={ctx.author.id} bet={amount}")
        elif res == "lose":
            # bet already taken, nothing to do
            await ctx.send(f"❌ You lost {amount} coins.")
            logger.info(f"blackjack lose user={ctx.author.id} bet={amount}")
        else:  # draw
            await self.update_balance(ctx.author.id, amount)
            await ctx.send("It's a draw! Your bet has been returned.")
            logger.info(f"blackjack draw - bet returned user={ctx.author.id} bet={amount}")

        logger.debug(f"blackjack finished user={ctx.author.id} result={res}")

    @economy_group.command(name="trade")
    async def trade(self, ctx, member: discord.Member = None):
        logger.info(f"Command: trade invoked by user={ctx.author.id} target={(member.id if member else None)}")
        # If no member provided — show a selection menu
        if member is None:
            options = [
                discord.SelectOption(label=m.display_name, value=str(m.id))
                for m in ctx.guild.members if not m.bot and m != ctx.author
            ]
            if not options:
                return await ctx.send("❌ No one available to trade with.")

            select = Select(placeholder="Choose someone to trade with", options=options, min_values=1, max_values=1)

            async def select_callback(interaction: discord.Interaction):
                chosen_id = int(select.values[0])
                chosen_member = ctx.guild.get_member(chosen_id)
                await interaction.response.edit_message(
                    content=f"✅ You chose {chosen_member.display_name}. Now re-run `{PREFIX}economy trade {chosen_member.mention}` to start the trade.",
                    view=None
                )

            select.callback = select_callback

            class SelectUserView(View):
                async def interaction_check(self, interaction: discord.Interaction) -> bool:
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("You are not allowed to use this control.")
                        return False
                    return True

            view = SelectUserView()
            view.add_item(select)
            return await ctx.send("👥 Select a user to trade with:", view=view)

        # Provided a member
        if member.bot:
            return await ctx.send("❌ You cannot trade with bots.")

        # --- New DM-based real-time trade session implementation ---
        # Fetch inventories (allow trades with coins only as well)
        your_inv = await self.get_inventory(ctx.author.id) or {}
        their_inv = await self.get_inventory(member.id) or {}

        # Ensure DMs open for both
        try:
            dm_author = await ctx.author.create_dm()
            dm_partner = await member.create_dm()
            await dm_author.send("🔔 Preparing trade panel... (this is a quick check)", delete_after=1)
            await dm_partner.send("🔔 Preparing trade panel... (this is a quick check)", delete_after=1)
            logger.debug(f"DMs opened for trade initiator={ctx.author.id} partner={member.id}")
        except Exception:
            logger.exception(f"trade failed to open DMs initiator={ctx.author.id} partner={(member.id if member else None)}")
            return await ctx.send("❌ Could not open DMs with one or both users. Ensure DMs are open and try again.")

        # Build select options for each user
        def build_item_options(inv: dict):
            if not inv:
                return [discord.SelectOption(label="No items available", value="__none__", description="You have no items", default=True, emoji=None,)]
            opts = []
            for item, qty in inv.items():
                label = f"{item} x{qty}"
                opts.append(discord.SelectOption(label=label, value=item))
            return opts

        author_options = build_item_options(your_inv)
        partner_options = build_item_options(their_inv)

        # Shared session state
        session = {
            "initiator": ctx.author.id,
            "partner": member.id,
            "initiator_items": [],  # list of item ids
            "partner_items": [],
            "initiator_coins": 0,
            "partner_coins": 0,
            "initiator_msg": None,
            "partner_msg": None,
            "active": True
        }

        def create_trade_embed():
            embed = discord.Embed(title="🔁 Trade Panel", color=BALANCE_COLOR)
            # initiator side
            initiator_items_display = "None" if not session["initiator_items"] else "\n".join(f"{EMOJIS.get(i,'❔')} {i} x{(your_inv.get(i,0))}" for i in session["initiator_items"])
            partner_items_display = "None" if not session["partner_items"] else "\n".join(f"{EMOJIS.get(i,'❔')} {i} x{(their_inv.get(i,0))}" for i in session["partner_items"])
            embed.add_field(name=f"{ctx.author.display_name} offers", value=f"Items:\n{initiator_items_display}\nCoins: {session['initiator_coins']}", inline=True)
            embed.add_field(name=f"{member.display_name} offers", value=f"Items:\n{partner_items_display}\nCoins: {session['partner_coins']}", inline=True)
            embed.set_footer(text="Select items and set coins. Initiator must press 'Propose Trade' to request confirmation.")
            return embed

        # Views for each user's DM - they share callbacks via closure over session
        class UserTradeView(View):
            def __init__(self, bot, allowed_user_id: int, options: list[discord.SelectOption], is_initiator: bool):
                super().__init__(timeout=600)
                self.bot = bot
                self.allowed_user_id = allowed_user_id
                self.is_initiator = is_initiator

                # item select (allow multi select)
                if options and not (len(options) == 1 and options[0].value == "__none__"):
                    self.item_select = Select(placeholder="Select items to offer (multiple allowed)", options=options, min_values=0, max_values=len(options))
                    self.add_item(self.item_select)
                    self.item_select.callback = self.on_select_items
                else:
                    # disabled select to show no items
                    self.item_select = None

                # coin setter button
                self.set_coins_btn = Button(label="Set Coins", style=discord.ButtonStyle.primary)
                self.cancel_btn = Button(label="Cancel Trade", style=discord.ButtonStyle.red)
                # Initiator has propose button
                if is_initiator:
                    self.propose_btn = Button(label="Propose Trade", style=discord.ButtonStyle.green)
                    self.add_item(self.propose_btn)
                    self.propose_btn.callback = self.on_propose

                self.add_item(self.set_coins_btn)
                self.add_item(self.cancel_btn)

                self.set_coins_btn.callback = self.on_set_coins
                self.cancel_btn.callback = self.on_cancel

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != self.allowed_user_id:
                    await interaction.response.send_message("You are not allowed to use this control.")
                    return False
                return True

            async def on_select_items(self, interaction: discord.Interaction):
                # update session with selected items for the interacting user
                if self.is_initiator:
                    session["initiator_items"] = list(self.item_select.values)
                else:
                    session["partner_items"] = list(self.item_select.values)
                # edit both DM messages if present
                embed = create_trade_embed()
                if session["initiator_msg"]:
                    try:
                        await session["initiator_msg"].edit(embed=embed)
                    except Exception:
                        pass
                if session["partner_msg"]:
                    try:
                        await session["partner_msg"].edit(embed=embed)
                    except Exception:
                        pass
                await interaction.response.send_message("✅ Selection updated.")

            async def on_set_coins(self, interaction: discord.Interaction):
                await interaction.response.send_message("Please reply in this DM with the amount of coins you want to offer (integer). Send 0 to offer none. Timeout 60s.")
                def check(m: discord.Message):
                    return m.author.id == interaction.user.id and isinstance(m.channel, discord.DMChannel)
                try:
                    msg = await self.bot.wait_for("message", timeout=60.0, check=check)
                    try:
                        amount = int(msg.content.strip())
                        if amount < 0:
                            raise ValueError()
                    except Exception:
                        return await interaction.followup.send("❌ Invalid amount. Please enter a non-negative integer.")
                    if self.is_initiator:
                        session["initiator_coins"] = amount
                    else:
                        session["partner_coins"] = amount
                    # update both panels
                    embed = create_trade_embed()
                    if session["initiator_msg"]:
                        try:
                            await session["initiator_msg"].edit(embed=embed)
                        except Exception:
                            pass
                    if session["partner_msg"]:
                        try:
                            await session["partner_msg"].edit(embed=embed)
                        except Exception:
                            pass
                    await interaction.followup.send(f"✅ Coins set to {amount}.")
                except asyncio.TimeoutError:
                    await interaction.followup.send("⏰ Timed out; no coins were set.")

            async def on_cancel(self, interaction: discord.Interaction):
                session["active"] = False
                # notify both
                try:
                    if session["initiator_msg"]:
                        await session["initiator_msg"].edit(content="❌ Trade cancelled.", embed=None, view=None)
                    if session["partner_msg"]:
                        await session["partner_msg"].edit(content="❌ Trade cancelled.", embed=None, view=None)
                except Exception:
                    pass
                await interaction.response.send_message("❌ Trade cancelled.")
                self.stop()

            async def on_propose(self, interaction: discord.Interaction):
                # Only initiator will have this; sends confirmation to partner
                if not self.is_initiator:
                    return await interaction.response.send_message("Only the trade initiator can propose the trade.")
                # Basic validation: ensure something offered (items or coins)
                if not session["initiator_items"] and session["initiator_coins"] == 0:
                    return await interaction.response.send_message("You must offer at least items or coins to propose.")

                # Send confirmation to partner with accept/reject buttons
                confirm_embed = discord.Embed(title="🔔 Trade Confirmation Request", color=BALANCE_COLOR)
                initiator_offers_text = 'None' if not session['initiator_items'] else '\n'.join(session['initiator_items'])
                partner_requests_text = 'None' if not session['partner_items'] else '\n'.join(session['partner_items'])
                confirm_embed.description = (
                    f"{ctx.author.display_name} proposes a trade:\n\n"
                    f"**They offer:**\n"
                    f"{initiator_offers_text}\nCoins: {session['initiator_coins']}\n\n"
                    f"**They request from you:**\n"
                    f"{partner_requests_text}\nCoins: {session['partner_coins']}\n\n"
                    "Click Accept to accept the trade or Reject to decline. (60s)"
                )

                class ConfirmView(View):
                    def __init__(self):
                        super().__init__(timeout=60)
                        self.result = None
                        self.accept = Button(label="Accept", style=discord.ButtonStyle.green)
                        self.reject = Button(label="Reject", style=discord.ButtonStyle.red)
                        self.add_item(self.accept)
                        self.add_item(self.reject)
                        self.accept.callback = self.accept_cb
                        self.reject.callback = self.reject_cb

                    async def interaction_check(self, inter: discord.Interaction) -> bool:
                        if inter.user.id != member.id:
                            await inter.response.send_message("You are not allowed to respond to this confirmation.")
                            return False
                        return True

                    async def accept_cb(self, inter: discord.Interaction):
                        self.result = True
                        await inter.response.edit_message(content="✅ You accepted the trade.", embed=None, view=None)
                        self.stop()

                    async def reject_cb(self, inter: discord.Interaction):
                        self.result = False
                        await inter.response.edit_message(content="❌ You rejected the trade.", embed=None, view=None)
                        self.stop()

                try:
                    confirm_view = ConfirmView()
                    confirm_msg = await member.send(embed=confirm_embed, view=confirm_view)
                except discord.Forbidden:
                    return await interaction.response.send_message(f"❌ Could not DM {member.display_name} to request confirmation.")

                # wait for partner response
                try:
                    await confirm_view.wait()
                    res = confirm_view.result
                except Exception:
                    res = None

                if res is not True:
                    # partner rejected or timed out
                    # notify both panels
                    try:
                        if session["initiator_msg"]:
                            await session["initiator_msg"].edit(content="❌ Trade declined or timed out.", embed=None, view=None)
                        if session["partner_msg"]:
                            await session["partner_msg"].edit(content="❌ Trade declined or timed out.", embed=None, view=None)
                    except Exception:
                        pass
                    return await interaction.followup.send("❌ Trade was declined or timed out.")

                # Partner accepted — finalize trade after re-checks
                # Re-fetch inventories and balances
                fresh_your_inv = await self.get_inventory(ctx.author.id) or {}
                fresh_their_inv = await self.get_inventory(member.id) or {}
                your_balance = await self.get_balance(ctx.author.id)
                their_balance = await self.get_balance(member.id)

                # Validate items availability
                for it in session["initiator_items"]:
                    if fresh_your_inv.get(it, 0) < 1:
                        try:
                            await member.send("❌ Trade failed: initiator no longer has offered items.")
                        except Exception:
                            pass
                        try:
                            if session["initiator_msg"]:
                                await session["initiator_msg"].edit(content="❌ Trade failed: items changed.", embed=None, view=None)
                        except Exception:
                            pass
                        return await interaction.followup.send("❌ Trade failed: initiator no longer has offered items.")
                for it in session["partner_items"]:
                    if fresh_their_inv.get(it, 0) < 1:
                        try:
                            await ctx.author.send("❌ Trade failed: partner no longer has offered items.")
                        except Exception:
                            pass
                        try:
                            if session["partner_msg"]:
                                await session["partner_msg"].edit(content="❌ Trade failed: items changed.", embed=None, view=None)
                        except Exception:
                            pass
                        return await interaction.followup.send("❌ Trade failed: partner no longer has offered items.")

                # Validate coins availability
                if your_balance < session["initiator_coins"]:
                    return await interaction.followup.send("❌ You no longer have enough coins to offer.")
                if their_balance < session["partner_coins"]:
                    return await interaction.followup.send(f"❌ {member.display_name} no longer has enough coins to offer.")

                # Execute atomic-like swap (best effort)
                try:
                    # transfer items
                    for it in session["initiator_items"]:
                        await self.remove_item(ctx.author.id, it, 1)
                        await self.add_item(member.id, it, 1)
                    for it in session["partner_items"]:
                        await self.remove_item(member.id, it, 1)
                        await self.add_item(ctx.author.id, it, 1)
                    # transfer coins
                    if session["initiator_coins"] > 0:
                        await self.update_balance(ctx.author.id, -session["initiator_coins"])
                        await self.update_balance(member.id, session["initiator_coins"])
                    if session["partner_coins"] > 0:
                        await self.update_balance(member.id, -session["partner_coins"])
                        await self.update_balance(ctx.author.id, session["partner_coins"])
                except Exception:
                    # best-effort: inform users
                    try:
                        if session["initiator_msg"]:
                            await session["initiator_msg"].edit(content="❌ Trade failed due to an internal error.", embed=None, view=None)
                        if session["partner_msg"]:
                            await session["partner_msg"].edit(content="❌ Trade failed due to an internal error.", embed=None, view=None)
                    except Exception:
                        pass
                    return await interaction.followup.send("❌ Trade failed due to an internal error. Please try again later.")

                # Success
                try:
                    if session["initiator_msg"]:
                        await session["initiator_msg"].edit(content="✅ Trade completed successfully!", embed=None, view=None)
                    if session["partner_msg"]:
                        await session["partner_msg"].edit(content="✅ Trade completed successfully!", embed=None, view=None)
                except Exception:
                    pass

                await interaction.followup.send("✅ Trade completed successfully.")
                try:
                    await ctx.author.send(f"✅ Trade with {member.display_name} completed.")
                except Exception:
                    pass
                try:
                    await member.send(f"✅ Trade with {ctx.author.display_name} completed.")
                except Exception:
                    pass
                session["active"] = False
                self.stop()
        # send DMs with views and store messages for cross-editing
        initiator_view = UserTradeView(self.bot, ctx.author.id, author_options, is_initiator=True)
        partner_view = UserTradeView(self.bot, member.id, partner_options, is_initiator=False)

        try:
            init_msg = await ctx.author.send(embed=create_trade_embed(), view=initiator_view)
            part_msg = await member.send(embed=create_trade_embed(), view=partner_view)
            session["initiator_msg"] = init_msg
            session["partner_msg"] = part_msg
            logger.info(f"trade panels sent initiator={ctx.author.id} partner={member.id}")
        except Exception:
            logger.exception("failed to send trade panels")
            return await ctx.send("❌ Failed to open trade panels.")

        # Wait until either view times out or session becomes inactive
        try:
            await asyncio.wait_for(asyncio.gather(initiator_view.wait(), partner_view.wait()), timeout=600)
        except asyncio.TimeoutError:
            if session["active"]:
                # timeout - cancel trade panels
                try:
                    await init_msg.edit(content="⏰ Trade timed out.", embed=None, view=None)
                    await part_msg.edit(content="⏰ Trade timed out.", embed=None, view=None)
                except Exception:
                    pass

        # done
        return


    # leader board
    @economy_group.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx):
        logger.info(f"Command: leaderboard by user={ctx.author.id}")
        leaderboard = await self.fetch_leaderboard()
        if not leaderboard:
            return await ctx.send("❌ No data for leaderboard.")

        embed = discord.Embed(title="🏆 Economy Leaderboard", color=BALANCE_COLOR)
        description = ""
        for i, (user_id, balance) in enumerate(leaderboard, start=1):
            user = self.bot.get_user(user_id)
            username = user.display_name if user else f"User ID {user_id}"
            description += f"**{i}. {username}** - {balance} coins\n"
        embed.description = description
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== ADMIN =====================
    @economy_group.group(name="admin", invoke_without_command=True)
    @commands.is_owner()
    async def admin_group(self, ctx):
        logger.info(f"Command: admin help by owner={ctx.author.id}")
        embed = discord.Embed(
            title="Economy Admin Commands",
            description=f"Manage the economy system."
        )

        embed.add_field(name=PREFIX+"eco admin give <user> <amount>", value=f"Gives coins to a user.", inline=False)
        embed.add_field(name=PREFIX+"eco admin take <user> <amount>", value=f"Takes coins from a user.", inline=False)
        embed.add_field(name=PREFIX+"eco admin reset <user>", value=f"Resets a user's economy data.", inline=False)
        embed.add_field(name=PREFIX+"eco admin shop add <item_id> <price> <item_name>", value=f"Adds an item to the shop.", inline=False)
        embed.add_field(name=PREFIX+"eco admin shop remove <item_id>", value=f"Removes an item from the shop.", inline=False)
        embed.add_field(name=PREFIX+"eco admin setbalance <user> <amount>", value=f"Sets a user's balance.", inline=False)
        embed.add_field(name=PREFIX+"eco admin resetdaily <user>", value=f"Resets a user's daily cooldown.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventory clear <user>", value=f"Clears a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventory give <user> <item_id> [amount]", value=f"Gives an item to a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventory take <user> <item_id> [amount]", value=f"Takes an item from a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventory see <user>", value=f"Sees a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin cooldown all <user>", value=f"Clears all cooldowns for a user.", inline=False)
        embed.add_field(name=PREFIX+"eco admin cooldown one <user> <command>", value=f"Clears a specific command cooldown for a user.", inline=False)

        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")

        await ctx.send(embed=embed)

    @admin_group.command(name="give")
    @commands.is_owner()
    async def give(self, ctx, member: discord.Member, amount: int):
        await self.update_balance(member.id, amount)
        logger.info(f"admin give by owner={ctx.author.id} to={member.id} amount={amount}")
        await ctx.send(f"✅ Gave {amount} coins to {member.mention}")

    @admin_group.command(name="take")
    @commands.is_owner()
    async def take(self, ctx, member: discord.Member, amount: int):
        await self.update_balance(member.id, -amount)
        logger.info(f"admin take by owner={ctx.author.id} from={member.id} amount={amount}")
        await ctx.send(f"✅ Took {amount} coins from {member.mention}")

    @admin_group.command(name="reset")
    @commands.is_owner()
    async def reset(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM economy WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM inventory WHERE user_id = ?", (member.id,))
            await db.commit()
        logger.info(f"admin reset by owner={ctx.author.id} user={member.id}")
        await ctx.send(f"✅ Reset {member.mention}'s profile.")
    
    @admin_group.group(name="shop", invoke_without_command=False)
    async def shop_admin_group(self, ctx):
        pass

    @shop_admin_group.command(name="add")
    @commands.is_owner()
    async def shop_add(self, ctx, item_id: str, price: int, *, name: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO shop_items (item_id, name, price) VALUES (?, ?, ?)",
                (item_id.lower(), name, price)
            )
            await db.commit()
        await ctx.send(f"✅ Added/Updated shop item `{item_id}` → {name} ({price} coins)")

    @shop_admin_group.command(name="remove", aliases=["delete", "del", "rm", "rem"])
    @commands.is_owner()
    async def shop_remove(self, ctx, item_id: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM shop_items WHERE item_id = ?", (item_id.lower(),))
            await db.commit()
        await ctx.send(f"✅ Removed shop item `{item_id}`")
    
    @admin_group.group(name="inventory", invoke_without_command=False, aliases=["inv"])
    async def inventory_admin_group(self, ctx):
        pass

    @inventory_admin_group.command(name="clear", aliases=["clearinventory", "invclear"])
    @commands.is_owner()
    async def inventory_clear(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM inventory WHERE user_id = ?", (member.id,))
            await db.commit()
        await ctx.send(f"✅ Cleared {member.mention}'s inventory.")
    
    @admin_group.command(name="setbalance", aliases=["setbal"])
    @commands.is_owner()
    async def set_balance(self, ctx, member: discord.Member, amount: int):
        if amount < 0:
            return await ctx.send("❌ Balance cannot be negative.")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO economy (user_id, balance, last_daily) VALUES (?, ?, COALESCE((SELECT last_daily FROM economy WHERE user_id = ?), NULL))",
                            (member.id, amount, member.id))
            await db.commit()
        await ctx.send(f"✅ Set {member.mention}'s balance to {amount} coins.")
    
    @admin_group.command(name="resetdaily")
    @commands.is_owner()
    async def reset_daily(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE economy SET last_daily = NULL WHERE user_id = ?", (member.id,))
            await db.commit()
        await ctx.send(f"✅ Reset {member.mention}'s daily reward.")

    @inventory_admin_group.command(name="give", aliases=["add"])
    @commands.is_owner()
    async def inventory_give(self, ctx, member: discord.Member, item: str, amount: int = 1):
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        await self.add_item(member.id, item.lower(), amount)
        await ctx.send(f"✅ Gave {amount} x {item} to {member.mention}'s inventory.")

    @inventory_admin_group.command(name="take", aliases=["remove", "del", "rm", "rem"])
    @commands.is_owner()
    async def inventory_take(self, ctx, member: discord.Member, item: str, amount: int = 1):
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        # Make this so if user doesn't have enough, it takes all they have
        user_inventory = await self.get_inventory(member.id)
        if item.lower() not in user_inventory or user_inventory[item.lower()] < amount:
            amount = user_inventory.get(item.lower(), 0)
            if amount == 0:
                return await ctx.send(f"❌ {member.mention} does not have that item in their inventory.")
        await self.remove_item(member.id, item.lower(), amount)
        await ctx.send(f"✅ Took {amount} x {item} from {member.mention}'s inventory.")

    @inventory_admin_group.command(name="see", aliases=["inventoryview", "invsee", "seeinventory", "viewinventory", "invview"])
    @commands.is_owner()
    async def inventory_see(self, ctx, member: discord.Member):
        user_inventory = await self.get_inventory(member.id)
        if not user_inventory:
            return await ctx.send(f"❌ {member.mention} has no items in their inventory.")
        inventory_list = "\n".join([f"{item}: {amount}" for item, amount in user_inventory.items()])
        await ctx.send(f"📦 {member.mention}'s Inventory:\n{inventory_list}")
    
    @admin_group.group(name="cooldown", invoke_without_command=False)
    async def cooldown_admin_group(self, ctx):
        pass
    
    @cooldown_admin_group.command(name="all", aliases=["resetcooldowns", "cooldownclear", "cooldownreset"])
    @commands.is_owner()
    async def clear_cooldowns(self, ctx, member: discord.Member):
        await self.clear_cooldowns(member.id)
        await ctx.send(f"✅ Cleared all cooldowns for {member.mention}.")
        
    @cooldown_admin_group.command(name="one", aliases=["resetcooldown", "cooldownclearone", "cooldownresetone"])
    @commands.is_owner()
    async def clear_cooldown(self, ctx, member: discord.Member, command: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cooldowns WHERE user_id = ? AND command = ?", (member.id, command))
            await db.commit()
        await ctx.send(f"✅ Cleared cooldown for command '{command}' for {member.mention}.")

# ===================== SETUP =====================
async def setup(bot):
    try: 
        await bot.add_cog(Economy(bot))
    except Exception as e:
        logger.error(f"Failed to load Economy cog: {e}")
        raise e
