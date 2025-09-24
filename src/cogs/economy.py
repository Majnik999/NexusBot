import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import aiosqlite
import random
import datetime
import asyncio
from main import logger
from settings import PREFIX, DEFAULT_DAILY_REWARD, DAILY_COOLDOWN_HOURS, SHOP_PAGE_SIZE, EMOJIS, GAMBLE_LOSE_COLOR, GAMBLE_WIN_COLOR, DAILY_COLOR, BALANCE_COLOR, INVENTORY_COLOR, LOOT_COLOR, SELL_COLOR, HELP_COLOR, FISH_CHANCES, FISH_ITEMS, DIG_ITEMS, DIG_CHANCES, COOLDOWN_DIG_FISH_MINUTES
from src.config.versions import ECONOMY_VERSION

# ===================== CONFIG =====================
DB_PATH = "src/databases/economy.db"

# ===================== ECONOMY COG =====================
class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ================= INITIALIZATION =================
    async def cog_load(self):
        await self.initialize_database()
        logger.info("[Economy] Database initialized")

    async def initialize_database(self):
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
                    last_used INTEGER,
                )
            """)
            
            await db.commit()

    # ================= HELPER FUNCTIONS =================
    async def get_cooldown(self, user_id: int, command: str) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_used FROM cooldowns WHERE user_id = ? AND command = ?", (user_id, command)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
            
    async def set_cooldown(self, user_id: int, command: str):
        now = int(datetime.datetime.utcnow().timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO cooldowns (user_id, command, last_used) VALUES (?, ?, ?)",
                             (user_id, command, now))
            await db.commit()
    
    async def has_user_cooldown(self, user_id: int, command: str, cooldown_seconds: int) -> bool:
        last_used = await self.get_cooldown(user_id, command)
        now = int(datetime.datetime.utcnow().timestamp())
        return (now - last_used) < cooldown_seconds
    
    async def clear_cooldowns(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cooldowns WHERE user_id = ?", (user_id,))
            await db.commit()
    
    async def get_balance(self, user_id: int) -> int:
        if user_id == self.bot.user.id:
            return 0
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await db.execute("INSERT INTO economy (user_id, balance, last_daily) VALUES (?, ?, ?)",
                                     (user_id, 0, None))
                    await db.commit()
                    return 0
                return row[0]

    async def update_balance(self, user_id: int, amount: int):
        balance = await self.get_balance(user_id)
        new_balance = max(0, balance + amount)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE economy SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            await db.commit()

    async def get_inventory(self, user_id: int) -> dict:
        items = {}
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT item, quantity FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
                async for item, qty in cursor:
                    items[item] = qty
        return items

    async def add_item(self, user_id: int, item: str, qty: int = 1):
        item = item.lower()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT quantity FROM inventory WHERE user_id = ? AND item = ?", (user_id, item)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await db.execute("UPDATE inventory SET quantity = quantity + ? WHERE user_id = ? AND item = ?",
                                     (qty, user_id, item))
                else:
                    await db.execute("INSERT INTO inventory (user_id, item, quantity) VALUES (?, ?, ?)",
                                     (user_id, item, qty))
            await db.commit()

    async def remove_item(self, user_id: int, item: str, qty: int = 1) -> bool:
        item = item.lower()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT quantity FROM inventory WHERE user_id = ? AND item = ?", (user_id, item)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] < qty:
                    return False
                new_qty = row[0] - qty
                if new_qty == 0:
                    await db.execute("DELETE FROM inventory WHERE user_id = ? AND item = ?", (user_id, item))
                else:
                    await db.execute("UPDATE inventory SET quantity = ? WHERE user_id = ? AND item = ?",
                                     (new_qty, user_id, item))
            await db.commit()
        return True

    async def fetch_shop_items(self) -> dict:
        items = {}
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT item_id, name, price FROM shop_items") as cursor:
                async for item_id, name, price in cursor:
                    items[item_id] = {"name": name, "price": price}
        return items

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
        embed.add_field(name=PREFIX+"economy gamble <amount>", value="Coinflip to gamble coins", inline=False)
        embed.add_field(name=PREFIX+"economy trade", value="Trade items with another user", inline=False)
        
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
    async def dig(self, ctx, times: int = 1):
        # set cooldown to be 5minutes
        if await self.has_user_cooldown(ctx.author.id, "dig", COOLDOWN_DIG_FISH_MINUTES*60):
            return await ctx.send("❌ You are on cooldown for this command. Please wait before digging again.")
        await self.set_cooldown(ctx.author.id, "dig")
        if times <= 0:
            return await ctx.send("❌ Times must be positive.")
        elif times >= 11:
            return await ctx.send("❌ Maximum is 10 per command!")

        possible_items = DIG_ITEMS
        # Corresponding weights: stone common, diamond very rare
        item_weights = DIG_CHANCES

        found_items = []
        for _ in range(times):
            found = random.choices(possible_items, weights=item_weights, k=random.randint(1,3))
            for item in found:
                await self.add_item(ctx.author.id, item, 1)
            found_items.extend(found)

        embed = discord.Embed(title=f"⛏️ You dug {times} times and found:", color=LOOT_COLOR)
        desc_dict = {}
        for item in found_items:
            desc_dict[item] = desc_dict.get(item, 0) + 1
        embed.description = "\n".join(f"{EMOJIS.get(item,'❔')} {item.capitalize()} x{qty}" for item, qty in desc_dict.items())
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)


    # ===================== FISH =====================
    @economy_group.command(name="fish")
    async def fish(self, ctx, times: int = 1):
        if await self.has_user_cooldown(ctx.author.id, "fish", COOLDOWN_DIG_FISH_MINUTES*60):
            return await ctx.send("❌ You are on cooldown for this command. Please wait before fishing again.")
        await self.set_cooldown(ctx.author.id, "fish")
        if times <= 0:
            return await ctx.send("❌ Times must be positive.")
        elif times >= 11:
            return await ctx.send("❌ Maximum is 10 per command!")

        fish_items = FISH_ITEMS
        # Base chance to catch each fish if something is caught
        fish_weights = FISH_CHANCES  # salmon most common, pufferfish rare

        caught_items = []
        for _ in range(times):
            if random.randint(1, 100) <= 15:  # 15% chance to catch something
                caught = random.choices(fish_items, weights=fish_weights, k=random.randint(1,2))
                for fish in caught:
                    await self.add_item(ctx.author.id, fish.lower(), 1)
                caught_items.extend(caught)

        if not caught_items:
            return await ctx.send("🎣 You fished but didn't catch anything this time!")

        embed = discord.Embed(title=f"🎣 You fished {times} times and caught:", color=LOOT_COLOR)
        desc_dict = {}
        for fish in caught_items:
            desc_dict[fish] = desc_dict.get(fish, 0) + 1
        embed.description = "\n".join(f"{EMOJIS.get(fish,'❔')} {fish.capitalize()} x{qty}" for fish, qty in desc_dict.items())
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)


    # ===================== GAMBLE =====================
    @economy_group.command(name="gamble", aliases=["coinflip"])
    async def gamble(self, ctx, amount: int):
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        balance = await self.get_balance(ctx.author.id)
        if balance < amount:
            return await ctx.send("❌ Not enough coins.")
        won = random.choice([True, False])
        await self.update_balance(ctx.author.id, amount if won else -amount)
        embed = discord.Embed(title="🎲 Coinflip", description=f"You {'won' if won else 'lost'} {amount} coins!", color=GAMBLE_WIN_COLOR if won else GAMBLE_LOSE_COLOR)
        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")
        await ctx.send(embed=embed)

    # ===================== TRADE =====================
    @economy_group.command(name="trade")
    async def trade(self, ctx, member: discord.Member):
        if member.bot:
            return await ctx.send("❌ You cannot trade with bots.")

        your_inv = await self.get_inventory(ctx.author.id)
        their_inv = await self.get_inventory(member.id)
        if not your_inv or not their_inv:
            return await ctx.send("❌ Both users must have items to trade.")

        # Select your item
        options = [discord.SelectOption(label=f"{item} x{qty}", value=item) for item, qty in your_inv.items()]
        your_select = Select(placeholder="Select your item to trade", options=options, min_values=1, max_values=1)

        # Select their item
        options2 = [discord.SelectOption(label=f"{item} x{qty}", value=item) for item, qty in their_inv.items()]
        their_select = Select(placeholder=f"Select {member.display_name}'s item", options=options2, min_values=1, max_values=1)

        async def your_callback(interaction: discord.Interaction):
            selected_item = your_select.values[0]
            await interaction.response.send_message(f"You selected {selected_item}", ephemeral=True)

        async def their_callback(interaction: discord.Interaction):
            selected_item = their_select.values[0]
            await interaction.response.send_message(f"{member.display_name}'s item selected: {selected_item}", ephemeral=True)

        your_select.callback = your_callback
        their_select.callback = their_callback

        view = View()
        view.add_item(your_select)
        view.add_item(their_select)
        await ctx.send(f"Trading items with {member.display_name}. Select items below:", view=view)

    # ===================== ADMIN =====================
    @economy_group.group(name="admin", invoke_without_command=True)
    @commands.is_owner()
    async def admin_group(self, ctx):
        embed = discord.Embed(
            title="Economy Admin Commands",
            description=f"Manage the economy system."
        )

        embed.add_field(name=PREFIX+"eco admin give <user> <amount>", value=f"Gives coins to a user.", inline=False)
        embed.add_field(name=PREFIX+"eco admin take <user> <amount>", value=f"Takes coins from a user.", inline=False)
        embed.add_field(name=PREFIX+"eco admin reset <user>", value=f"Resets a user's economy data.", inline=False)
        embed.add_field(name=PREFIX+"eco admin shopadd <item_id> <price> <item_name>", value=f"Adds an item to the shop.", inline=False)
        embed.add_field(name=PREFIX+"eco admin shopremove <item_id>", value=f"Removes an item from the shop.", inline=False)
        embed.add_field(name=PREFIX+"eco admin setbalance <user> <amount>", value=f"Sets a user's balance.", inline=False)
        embed.add_field(name=PREFIX+"eco admin resetdaily <user>", value=f"Resets a user's daily cooldown.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventoryclear <user>", value=f"Clears a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventorygive <user> <item_id> [amount]", value=f"Gives an item to a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventorytake <user> <item_id> [amount]", value=f"Takes an item from a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin inventorysee <user>", value=f"Sees a user's inventory.", inline=False)
        embed.add_field(name=PREFIX+"eco admin clearcooldowns <user>", value=f"Clears all cooldowns for a user.", inline=False)
        embed.add_field(name=PREFIX+"eco admin clearcooldown <user> <command>", value=f"Clears a specific command cooldown for a user.", inline=False)

        embed.set_footer(text=f"Version: {ECONOMY_VERSION}")

        await ctx.send(embed=embed)

    @admin_group.command(name="give")
    @commands.is_owner()
    async def give(self, ctx, member: discord.Member, amount: int):
        await self.update_balance(member.id, amount)
        await ctx.send(f"✅ Gave {amount} coins to {member.mention}")

    @admin_group.command(name="take")
    @commands.is_owner()
    async def take(self, ctx, member: discord.Member, amount: int):
        await self.update_balance(member.id, -amount)
        await ctx.send(f"✅ Took {amount} coins from {member.mention}")

    @admin_group.command(name="reset")
    @commands.is_owner()
    async def reset(self, ctx, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM economy WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM inventory WHERE user_id = ?", (member.id,))
            await db.commit()
        await ctx.send(f"✅ Reset {member.mention}'s profile.")

    @admin_group.command(name="shopadd")
    @commands.is_owner()
    async def shop_add(self, ctx, item_id: str, price: int, *, name: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO shop_items (item_id, name, price) VALUES (?, ?, ?)",
                (item_id.lower(), name, price)
            )
            await db.commit()
        await ctx.send(f"✅ Added/Updated shop item `{item_id}` → {name} ({price} coins)")

    @admin_group.command(name="shopremove")
    @commands.is_owner()
    async def shop_remove(self, ctx, item_id: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM shop_items WHERE item_id = ?", (item_id.lower(),))
            await db.commit()
        await ctx.send(f"✅ Removed shop item `{item_id}`")
    
    @admin_group.command(name="inventoryclear", aliases=["clearinventory", "invclear"])
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

    @admin_group.command(name="invenotorygive", aliases=["inventoryadd", "invgive"])
    @commands.is_owner()
    async def inventory_give(self, ctx, member: discord.Member, item: str, amount: int = 1):
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive.")
        await self.add_item(member.id, item.lower(), amount)
        await ctx.send(f"✅ Gave {amount} x {item} to {member.mention}'s inventory.")
    
    @admin_group.command(name="inventorytake", aliases=["inventoryremove", "invtake"])
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
    
    @admin_group.command(name="inventorysee", aliases=["inventoryview", "invsee", "seeinventory", "viewinventory", "invview"])
    @commands.is_owner()
    async def inventory_see(self, ctx, member: discord.Member):
        user_inventory = await self.get_inventory(member.id)
        if not user_inventory:
            return await ctx.send(f"❌ {member.mention} has no items in their inventory.")
        inventory_list = "\n".join([f"{item}: {amount}" for item, amount in user_inventory.items()])
        await ctx.send(f"📦 {member.mention}'s Inventory:\n{inventory_list}")
    
    @admin_group.command(name="clearcooldowns", aliases=["resetcooldowns", "cooldownclear", "cooldownreset"])
    @commands.is_owner()
    async def clear_cooldowns(self, ctx, member: discord.Member):
        await self.clear_cooldowns(member.id)
        await ctx.send(f"✅ Cleared all cooldowns for {member.mention}.")
        
    @admin_group.command(name="clearcooldown", aliases=["resetcooldown", "cooldownclearone", "cooldownresetone"])
    @commands.is_owner()
    async def clear_cooldown(self, ctx, member: discord.Member, command: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cooldowns WHERE user_id = ? AND command = ?", (member.id, command))
            await db.commit()
        await ctx.send(f"✅ Cleared cooldown for command '{command}' for {member.mention}.")

# ===================== SETUP =====================
async def setup(bot):
    await bot.add_cog(Economy(bot))
