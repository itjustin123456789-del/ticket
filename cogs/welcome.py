import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Skip bots
        if member.bot:
            return
        
        # Get welcome config
        async with self.bot.db.execute(
            'SELECT channel_id, enabled FROM welcome_configs WHERE guild_id = ?',
            (member.guild.id,)
        ) as cursor:
            config = await cursor.fetchone()
        
        if not config or not config[1]:
            return
        
        channel = member.guild.get_channel(config[0])
        if not channel:
            return
        
        # Build welcome message - mention in content to ping user
        welcome_content = f"🎉 {member.mention} just joined!"
        welcome_msg = f"""Welcome to Mercyy.cc — the ultimate Fortnite cheat experience.

Looking to get started? Open a ticket using 🎫 in <#1494581979750862949> to purchase, or visit our website: https://mercyy-cc.vercel.app/

Fast setup, powerful features, and a smooth experience — everything you need to stay ahead. Join now and level up your game."""
        
        embed = discord.Embed(
            description=welcome_msg,
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        
        await channel.send(content=welcome_content, embed=embed)
    
    @app_commands.command(name="welcome_channel", description="Set the channel for welcome messages")
    @app_commands.describe(channel="Channel where welcome messages will be sent")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        
        await self.bot.db.execute(
            '''INSERT INTO welcome_configs (guild_id, channel_id, enabled)
               VALUES (?, ?, 1)
               ON CONFLICT(guild_id) DO UPDATE SET
               channel_id = excluded.channel_id''',
            (interaction.guild.id, target.id)
        )
        await self.bot.db.commit()
        
        embed = discord.Embed(
            title="✅ Welcome Channel Set",
            description=f"Welcome messages will be sent to {target.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="welcome_toggle", description="Enable or disable welcome messages")
    @app_commands.describe(enabled="Enable welcome messages?")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_toggle(self, interaction: discord.Interaction, enabled: bool):
        await self.bot.db.execute(
            '''INSERT INTO welcome_configs (guild_id, enabled)
               VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
               enabled = excluded.enabled''',
            (interaction.guild.id, 1 if enabled else 0)
        )
        await self.bot.db.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"✅ Welcome messages {status}!")
    
    @app_commands.command(name="test_welcome", description="Test the welcome message")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_welcome(self, interaction: discord.Interaction):
        member = interaction.user
        
        welcome_content = f"🎉 {member.mention} just joined!"
        welcome_msg = f"""Welcome to Mercyy.cc — the ultimate Fortnite cheat experience.

Looking to get started? Open a ticket using 🎫 in <#1494581979750862949> to purchase, or visit our website: https://mercyy-cc.vercel.app/

Fast setup, powerful features, and a smooth experience — everything you need to stay ahead. Join now and level up your game."""
        
        embed = discord.Embed(
            description=welcome_msg,
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        
        await interaction.response.send_message(content=welcome_content, embed=embed)

async def setup(bot):
    await bot.add_cog(Welcome(bot))
