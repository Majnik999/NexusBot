import discord
from discord.ext import commands

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    # Creation of profile command
    @commands.group(name="profile", invoke_without_command=True, aliases=["pf"])
    async def profile(self, ctx, member: discord.Member = None):
        # Setting variable to get info about member
        member = member or ctx.author

        # Pre getting user profile description
        member_bio = await self.bot.fetch_user(member.id)
        
        # Trying to get users roles
        try: 
            roles = [role.name for role in member.roles if role.name != "@everyone"]
            roles_str = ", ".join(roles) if roles else "None"
        except AttributeError:
            roles_str = "None"
        except Exception:
            roles_str = "Error getting roles!"
        
        # Getting users status
        try:
            status = str(member.status).title()
        except AttributeError:
            status = "None"
        except Exception:
            status = "Error getting status!"
        
        try:
            activity = member.activity
        except AttributeError:
            activity = "None"
        except Exception:
            activity = "Error getting activity!"
        
        try:
            joined_at = member.joined_at.strftime("%Y-%m-%d %H:%M:%S")
        except AttributeError:
            joined_at = "None"
        except Exception:
            joined_at = "Error getting date of joining!"
        
        # Creating embed
        embed = discord.Embed(
            title=f"👤 {member.display_name}'s Profile",
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.add_field(name="Username", value=member.name, inline=False)
        embed.add_field(name="Discriminator", value=member.discriminator, inline=False)
        embed.add_field(name="User ID", value=member.id, inline=False)
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(name="Description", value=member_bio.bio if getattr(member_bio, "bio", False) else "Failed to find user description.", inline=False)
        embed.add_field(name="Activity", value=f"```{activity}```")
        embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed.add_field(name="Joined Server", value=joined_at, inline=False)
        embed.add_field(name="Roles", value=roles_str, inline=False)
        embed.add_field(name="Bot", value=member.bot, inline=False)
        try:
            embed.add_field(name="Boosted", value= True if member.premium_since else False, inline=False)
        except:
            pass

        await ctx.send(embed=embed)
        
    @profile.command(name="picture", aliases=["pic", "p", "pfp"])
    async def profile_picture(self, ctx, member: discord.Member = None):
        # Setting variable to get info about user
        member = member or ctx.author
        
        # Sending users profile picture
        embed = discord.Embed(description=f"### Successfully got {member.name}'s pfp (profile picture)", color=discord.Color.green())
        embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Profile(bot))
