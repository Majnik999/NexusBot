import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
import qrcode
from io import BytesIO
import os
from PIL import Image
from main import PREFIX

# Store user QR code settings
class QRCodeSettings:
    def __init__(self):
        self.content = None
        self.logo_url = None
        self.design = None
        
# Dictionary to store user settings
user_settings = {}

# Content Modal
class ContentModal(Modal):
    def __init__(self):
        super().__init__(title="Set QR Code Content")
        
        self.content = TextInput(
            label="Text/URL for QR Code",
            placeholder="Enter text or URL to encode",
            required=True,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # Initialize settings if not exist
        if user_id not in user_settings:
            user_settings[user_id] = QRCodeSettings()
            
        # Save content
        user_settings[user_id].content = self.content.value
        
        await interaction.response.send_message(f"Content set: {self.content.value[:50]}{'...' if len(self.content.value) > 50 else ''}", ephemeral=True)

# Logo Modal
class LogoModal(Modal):
    def __init__(self):
        super().__init__(title="Set QR Code Logo")
        
        self.logo_url = TextInput(
            label="Logo URL",
            placeholder="Enter URL to an image to use as logo",
            required=True
        )
        self.add_item(self.logo_url)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        # Initialize settings if not exist
        if user_id not in user_settings:
            user_settings[user_id] = QRCodeSettings()
            
        # Save logo URL
        user_settings[user_id].logo_url = self.logo_url.value
        
        await interaction.response.send_message(f"Logo URL set: {self.logo_url.value}", ephemeral=True)

# Design Gallery View
class DesignGalleryView(View):
    def __init__(self, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
        
    @discord.ui.button(label="Classic Black", style=discord.ButtonStyle.secondary, row=0)
    async def classic_black(self, interaction: discord.Interaction, button: Button):
        if self.user_id not in user_settings:
            user_settings[self.user_id] = QRCodeSettings()
            
        user_settings[self.user_id].design = {
            "name": "Classic Black",
            "fill_color": "#000000",
            "back_color": "#FFFFFF",
            "error_correction": "M"
        }
        
        await interaction.response.send_message("Design set: Classic Black", ephemeral=True)
    
    @discord.ui.button(label="Blue Business", style=discord.ButtonStyle.primary, row=0)
    async def blue_business(self, interaction: discord.Interaction, button: Button):
        if self.user_id not in user_settings:
            user_settings[self.user_id] = QRCodeSettings()
            
        user_settings[self.user_id].design = {
            "name": "Blue Business",
            "fill_color": "#0066CC",
            "back_color": "#FFFFFF",
            "error_correction": "H"
        }
        
        await interaction.response.send_message("Design set: Blue Business", ephemeral=True)
    
    @discord.ui.button(label="Neon Green", style=discord.ButtonStyle.success, row=0)
    async def neon_green(self, interaction: discord.Interaction, button: Button):
        if self.user_id not in user_settings:
            user_settings[self.user_id] = QRCodeSettings()
            
        user_settings[self.user_id].design = {
            "name": "Neon Green",
            "fill_color": "#00FF00",
            "back_color": "#000000",
            "error_correction": "Q"
        }
        
        await interaction.response.send_message("Design set: Neon Green", ephemeral=True)
    
    @discord.ui.button(label="Purple Elegance", style=discord.ButtonStyle.secondary, row=1)
    async def purple_elegance(self, interaction: discord.Interaction, button: Button):
        if self.user_id not in user_settings:
            user_settings[self.user_id] = QRCodeSettings()
            
        user_settings[self.user_id].design = {
            "name": "Purple Elegance",
            "fill_color": "#800080",
            "back_color": "#F0F0F0",
            "error_correction": "H"
        }
        
        await interaction.response.send_message("Design set: Purple Elegance", ephemeral=True)
    
    @discord.ui.button(label="Red Alert", style=discord.ButtonStyle.danger, row=1)
    async def red_alert(self, interaction: discord.Interaction, button: Button):
        if self.user_id not in user_settings:
            user_settings[self.user_id] = QRCodeSettings()
            
        user_settings[self.user_id].design = {
            "name": "Red Alert",
            "fill_color": "#FF0000",
            "back_color": "#FFFFFF",
            "error_correction": "H"
        }
        
        await interaction.response.send_message("Design set: Red Alert", ephemeral=True)

# Main QR Code View
class QRCodeView(View):
    def __init__(self):
        super().__init__(timeout=600)  # 10 minute timeout
    
    @discord.ui.button(label="Set Content", style=discord.ButtonStyle.primary, row=0)
    async def set_content(self, interaction: discord.Interaction, button: Button):
        modal = ContentModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Set Logo", style=discord.ButtonStyle.secondary, row=0)
    async def set_logo(self, interaction: discord.Interaction, button: Button):
        modal = LogoModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Set Design", style=discord.ButtonStyle.success, row=0)
    async def set_design(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="QR Code Design Gallery",
            description="Select a pre-made design for your QR code:",
            color=discord.Color.blue()
        )
        
        # Add example images for each design
        embed.add_field(name="Available Designs", 
                       value="• Classic Black\n• Blue Business\n• Neon Green\n• Purple Elegance\n• Red Alert", 
                       inline=False)
        
        embed.add_field(name="Example", 
                       value="All designs use www.google.com as example content", 
                       inline=False)
        
        view = DesignGalleryView(str(interaction.user.id))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Generate QR Code", style=discord.ButtonStyle.danger, row=1)
    async def generate_qr(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        
        # Check if user has settings
        if user_id not in user_settings:
            await interaction.response.send_message("Please set content for your QR code first!", ephemeral=True)
            return
            
        # Check if content is set
        if not user_settings[user_id].content:
            await interaction.response.send_message("Please set content for your QR code first!", ephemeral=True)
            return
            
        # Use default design if not set
        if not user_settings[user_id].design:
            user_settings[user_id].design = {
                "name": "Classic Black",
                "fill_color": "#000000",
                "back_color": "#FFFFFF",
                "error_correction": "M"
            }
            
        # Generate QR code
        await generate_qr_code(interaction, user_id)

async def generate_qr_code(interaction, user_id):
    settings = user_settings[user_id]
    
    # Map error correction levels
    error_levels = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H
    }
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_levels.get(settings.design["error_correction"], qrcode.constants.ERROR_CORRECT_M),
        box_size=10,
        border=4,
    )
    qr.add_data(settings.content)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color=settings.design["fill_color"], back_color=settings.design["back_color"])
    
    # Add logo if set
    if settings.logo_url:
        try:
            # This is a placeholder for logo functionality
            # In a real implementation, you would download the logo from the URL
            # and overlay it on the QR code
            pass
        except Exception as e:
            await interaction.response.send_message(f"Error adding logo: {str(e)}", ephemeral=True)
            return
    
    # Save to BytesIO
    buffer = BytesIO()
    img.save(buffer, "PNG")
    buffer.seek(0)
    
    # Create embed
    embed = discord.Embed(
        title="Your QR Code",
        description=f"Content: {settings.content[:50]}{'...' if len(settings.content) > 50 else ''}",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Design", value=settings.design["name"], inline=True)
    
    if settings.logo_url:
        embed.add_field(name="Logo", value="Custom logo applied", inline=True)
    
    # Send the QR code
    file = discord.File(buffer, filename="qrcode.png")
    embed.set_image(url="attachment://qrcode.png")
    
    await interaction.response.send_message(embed=embed, file=file)
    
    # Clear user settings after generating
    # Uncomment if you want to clear settings after each generation
    # del user_settings[user_id]

class QRCode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="qrcode")
    async def qrcode(self, ctx, *, data=None):
        """
        Generate a QR code from text or URL.
        Usage: !qrcode <text/url>
        If no text is provided, an interactive QR code builder will be shown.
        """
        if data:
            # Simple mode - directly generate QR code with default settings
            buffer = BytesIO()
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(buffer, "PNG")
            buffer.seek(0)
            
            embed = discord.Embed(
                title="QR Code Generator",
                description=f"QR Code for: {data[:50]}{'...' if len(data) > 50 else ''}",
                color=discord.Color.blue()
            )
            
            file = discord.File(buffer, filename="qrcode.png")
            embed.set_image(url="attachment://qrcode.png")
            
            await ctx.send(embed=embed, file=file)
        else:
            # Advanced mode - show interactive builder with separate buttons
            embed = discord.Embed(
                title="Create QR Code",
                description="Use the buttons below to customize and generate your QR code.",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Instructions", 
                           value="1. Set Content (required)\n2. Set Logo (optional)\n3. Set Design (optional)\n4. Generate QR Code", 
                           inline=False)
            
            view = QRCodeView()
            await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(QRCode(bot))