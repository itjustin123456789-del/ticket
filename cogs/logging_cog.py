import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import io

class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Default hardcoded channel IDs as requested
        self.default_transcript = 1494581928219775108
        self.default_minor = 1494581932539772958
        self.default_major = 1494581924046569562
    
    async def get_log_channels(self, guild_id):
        """Get configured log channels or use defaults"""
        async with self.bot.db.execute(
            'SELECT transcript_channel, log_channel_minor, log_channel_major FROM ticket_configs WHERE guild_id = ?',
            (guild_id,)
        ) as cursor:
            config = await cursor.fetchone()
        
        if config:
            return {
                'transcript': config[0] or self.default_transcript,
                'minor': config[1] or self.default_minor,
                'major': config[2] or self.default_major
            }
        return {
            'transcript': self.default_transcript,
            'minor': self.default_minor,
            'major': self.default_major
        }
    
    async def send_transcript(self, guild, ticket_data, messages_text, closed_by):
        """Send ticket transcript to dedicated channel"""
        channels = await self.get_log_channels(guild.id)
        channel = guild.get_channel(channels['transcript'])
        if not channel:
            return
        
        user_id, category, created_at = ticket_data[0], ticket_data[1], ticket_data[2]
        
        # Handle created_at as string or datetime
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except:
                created_at = datetime.now()
        
        try:
            user = await self.bot.fetch_user(user_id)
            user_mention = user.mention if user else f"<@{user_id}>"
            user_name = user.name if user else "Unknown"
        except:
            user_mention = f"<@{user_id}>"
            user_name = "Unknown"
        
        try:
            closer = await self.bot.fetch_user(closed_by)
            closer_name = closer.name
        except:
            closer_name = "Unknown"
        
        embed = discord.Embed(
            title=f"📝 Ticket Transcript - {category}",
            description=f"**User:** {user_mention} ({user_name})\n"
                        f"**Ticket:** {category}\n"
                        f"**Created:** <t:{int(created_at.timestamp())}:F>\n"
                        f"**Closed by:** {closer_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        file = discord.File(io.StringIO(messages_text), filename=f"transcript-{user_id}.txt")
        await channel.send(embed=embed, file=file)
    
    async def log_minor_event(self, guild, title, description, user=None):
        """Log less important events (ticket claims, renames, etc.)"""
        channels = await self.get_log_channels(guild.id)
        channel = guild.get_channel(channels['minor'])
        if not channel:
            return
        
        embed = discord.Embed(
            title=f"📋 {title}",
            description=description,
            color=discord.Color.light_gray(),
            timestamp=datetime.now()
        )
        if user:
            embed.set_footer(text=f"By: {user.name} ({user.id})")
        
        await channel.send(embed=embed)
    
    async def log_major_event(self, guild, title, description, user=None, fields=None):
        """Log important events (ticket open/close, purchases, etc.)"""
        channels = await self.get_log_channels(guild.id)
        channel = guild.get_channel(channels['major'])
        if not channel:
            return
        
        embed = discord.Embed(
            title=f"🔔 {title}",
            description=description,
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)
        
        if user:
            embed.set_footer(text=f"User: {user.name} | ID: {user.id}", icon_url=user.display_avatar.url)
        
        await channel.send(embed=embed)
    
    async def log_ticket_open(self, guild, user, category, channel):
        """Log when a ticket is opened"""
        await self.log_major_event(
            guild,
            "Ticket Opened",
            f"A new {category} ticket has been created.",
            user=user,
            fields=[
                ("Category", category, True),
                ("Channel", channel.mention, True),
                ("User", user.mention, True)
            ]
        )
    
    async def log_ticket_close(self, guild, user, category, channel_name, closed_by):
        """Log when a ticket is closed"""
        closer = guild.get_member(closed_by)
        closer_name = closer.mention if closer else f"<@{closed_by}>"
        
        await self.log_major_event(
            guild,
            "Ticket Closed",
            f"{category} ticket has been closed.",
            user=user,
            fields=[
                ("Category", category, True),
                ("Channel", f"#{channel_name}", True),
                ("Closed By", closer_name, True)
            ]
        )
    
    async def log_ticket_claim(self, guild, ticket_channel, claimed_by):
        """Log when a ticket is claimed"""
        await self.log_minor_event(
            guild,
            "Ticket Claimed",
            f"{claimed_by.mention} claimed {ticket_channel.mention}",
            user=claimed_by
        )
    
    async def log_ticket_rename(self, guild, ticket_channel, old_name, new_name, renamed_by):
        """Log when a ticket is renamed"""
        await self.log_minor_event(
            guild,
            "Ticket Renamed",
            f"{ticket_channel.mention} renamed from `{old_name}` to `{new_name}`",
            user=renamed_by
        )
    
    async def log_user_add(self, guild, ticket_channel, added_user, added_by):
        """Log when a user is added to a ticket"""
        await self.log_minor_event(
            guild,
            "User Added to Ticket",
            f"{added_user.mention} added to {ticket_channel.mention} by {added_by.mention}",
            user=added_by
        )
    
    async def log_user_remove(self, guild, ticket_channel, removed_user, removed_by):
        """Log when a user is removed from a ticket"""
        await self.log_minor_event(
            guild,
            "User Removed from Ticket",
            f"{removed_user.mention} removed from {ticket_channel.mention} by {removed_by.mention}",
            user=removed_by
        )
    
    async def log_purchase(self, guild, user, product, price, payment_method):
        """Log a purchase (for future use with payment system)"""
        await self.log_major_event(
            guild,
            "💰 Purchase Made",
            f"New purchase completed",
            user=user,
            fields=[
                ("Product", product, True),
                ("Price", price, True),
                ("Payment", payment_method, True),
                ("User", user.mention, False)
            ]
        )

async def setup(bot):
    await bot.add_cog(Logging(bot))
