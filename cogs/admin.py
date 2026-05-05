import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="setup_tickets", description="Initial ticket system setup")
    @app_commands.describe(
        category="Category where tickets will be created",
        transcript_channel="Channel for ticket transcripts/logs",
        support_role="Main support role for tickets"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        transcript_channel: discord.TextChannel,
        support_role: discord.Role
    ):
        await self.bot.db.execute(
            '''INSERT INTO ticket_configs (guild_id, ticket_category, transcript_channel, support_role, ticket_counter)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(guild_id) DO UPDATE SET
               ticket_category = excluded.ticket_category,
               transcript_channel = excluded.transcript_channel,
               support_role = excluded.support_role''',
            (interaction.guild.id, category.id, transcript_channel.id, support_role.id)
        )
        await self.bot.db.commit()
        
        embed = discord.Embed(
            title="✅ Ticket System Configured",
            description=f"**Ticket Category:** {category.mention}\n**Transcript Channel:** {transcript_channel.mention}\n**Support Role:** {support_role.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="add_category", description="Add a custom ticket category")
    @app_commands.describe(
        name="Category name",
        description="Description shown in dropdown",
        emoji="Emoji for the category",
        specific_role="Specific role that can see this category's tickets",
        channel_category="Discord category channel for these tickets"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_category(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = None,
        emoji: str = None,
        specific_role: discord.Role = None,
        channel_category: discord.CategoryChannel = None
    ):
        await self.bot.db.execute(
            '''INSERT INTO ticket_categories (guild_id, name, description, emoji, role_id, category_id)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (
                interaction.guild.id,
                name,
                description or f"Create a {name} ticket",
                emoji or '🎫',
                specific_role.id if specific_role else None,
                channel_category.id if channel_category else None
            )
        )
        await self.bot.db.commit()
        
        embed = discord.Embed(
            title="✅ Category Added",
            description=f"**Name:** {name}\n**Description:** {description or f'Create a {name} ticket'}\n**Emoji:** {emoji or '🎫'}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        if specific_role:
            embed.add_field(name="Specific Role", value=specific_role.mention, inline=False)
        if channel_category:
            embed.add_field(name="Channel Category", value=channel_category.mention, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="remove_category", description="Remove a ticket category")
    @app_commands.describe(name="Category name to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_category(self, interaction: discord.Interaction, name: str):
        cursor = await self.bot.db.execute(
            'DELETE FROM ticket_categories WHERE guild_id = ? AND name = ?',
            (interaction.guild.id, name)
        )
        await self.bot.db.commit()
        
        if cursor.rowcount > 0:
            await interaction.response.send_message(f"✅ Category `{name}` removed!")
        else:
            await interaction.response.send_message(f"❌ Category `{name}` not found!", ephemeral=True)
    
    @app_commands.command(name="list_categories", description="List all ticket categories")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_categories(self, interaction: discord.Interaction):
        async with self.bot.db.execute(
            'SELECT name, description, emoji FROM ticket_categories WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            categories = await cursor.fetchall()
        
        if not categories:
            return await interaction.response.send_message("❌ No categories found!", ephemeral=True)
        
        embed = discord.Embed(
            title="🎫 Ticket Categories",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        for cat in categories:
            embed.add_field(
                name=f"{cat[2]} {cat[0]}",
                value=cat[1] or "No description",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ticket_stats", description="View ticket statistics")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_stats(self, interaction: discord.Interaction):
        # Total tickets
        async with self.bot.db.execute(
            'SELECT COUNT(*) FROM tickets WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            total = (await cursor.fetchone())[0]
        
        # Open tickets
        async with self.bot.db.execute(
            'SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND closed_at IS NULL',
            (interaction.guild.id,)
        ) as cursor:
            open_tickets = (await cursor.fetchone())[0]
        
        # Closed tickets
        closed_tickets = total - open_tickets
        
        # Tickets by category
        async with self.bot.db.execute(
            'SELECT category, COUNT(*) FROM tickets WHERE guild_id = ? GROUP BY category',
            (interaction.guild.id,)
        ) as cursor:
            by_category = await cursor.fetchall()
        
        embed = discord.Embed(
            title="📊 Ticket Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Total Tickets", value=str(total), inline=True)
        embed.add_field(name="🟢 Open", value=str(open_tickets), inline=True)
        embed.add_field(name="🔴 Closed", value=str(closed_tickets), inline=True)
        
        if by_category:
            cat_stats = "\n".join([f"{cat[0]}: {cat[1]}" for cat in by_category])
            embed.add_field(name="By Category", value=cat_stats, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="close_all", description="Close all open tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def close_all(self, interaction: discord.Interaction):
        async with self.bot.db.execute(
            'SELECT channel_id FROM tickets WHERE guild_id = ? AND closed_at IS NULL',
            (interaction.guild.id,)
        ) as cursor:
            channels = await cursor.fetchall()
        
        if not channels:
            return await interaction.response.send_message("❌ No open tickets found!", ephemeral=True)
        
        await interaction.response.defer()
        
        count = 0
        for channel_id in channels:
            channel = interaction.guild.get_channel(channel_id[0])
            if channel:
                await self.bot.db.execute(
                    'UPDATE tickets SET closed_at = ?, closed_by = ? WHERE channel_id = ?',
                    (datetime.now(), interaction.user.id, channel_id[0])
                )
                try:
                    await channel.delete()
                    count += 1
                except:
                    pass
        
        await self.bot.db.commit()
        await interaction.followup.send(f"✅ Closed {count} tickets!")
    
    @app_commands.command(name="embed_media", description="Send media creator recruitment embed")
    @app_commands.describe(channel="Channel to send the embed to")
    @app_commands.checks.has_permissions(administrator=True)
    async def embed_media(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        
        embed = discord.Embed(
            title="🎬 We're Looking for Media Creators",
            description="We're building a strong content team, so if you enjoy editing or creating content, this is your chance to get involved.",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="What we're looking for:",
            value="• Clean, high-quality video editing skills\n"
                  "• Experience with short-form content (clips, edits, highlights)\n"
                  "• Creativity and strong attention to detail\n"
                  "• Consistency and ability to meet deadlines\n"
                  "• A positive mindset — willing to learn and collaborate",
            inline=False
        )
        
        embed.add_field(
            name="What you'll be doing:",
            value="• Creating engaging content for the community\n"
                  "• Editing clips, highlights, and promotional videos\n"
                  "• Helping grow and improve our overall media presence",
            inline=False
        )
        
        embed.add_field(
            name="🎟️ Spots Available:",
            value="0/10",
            inline=True
        )
        
        embed.add_field(
            name="🔑 Keys:",
            value="Handed out on Tuesday",
            inline=True
        )
        
        embed.add_field(
            name="👉 Open a ticket here:",
            value="<#1494581979750862949>",
            inline=False
        )
        
        embed.set_footer(text=f"Mercyy.cc Recruitment • {interaction.guild.name}")
        
        await target.send(content="@everyone", embed=embed)
        await interaction.response.send_message(f"✅ Media creator embed sent to {target.mention}!")
    
    @app_commands.command(name="embed_custom", description="Send a custom embed with @everyone")
    @app_commands.describe(
        channel="Channel to send to",
        title="Embed title",
        description="Embed description",
        color="Color (red, blue, green, purple, yellow, orange, black, white)",
        ping_everyone="Ping @everyone?"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def embed_custom(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        color: str = "blue",
        ping_everyone: bool = True
    ):
        colors = {
            "red": discord.Color.red(),
            "blue": discord.Color.blue(),
            "green": discord.Color.green(),
            "purple": discord.Color.purple(),
            "yellow": discord.Color.yellow(),
            "orange": discord.Color.orange(),
            "black": discord.Color.dark_theme(),
            "white": discord.Color.light_gray()
        }
        
        embed_color = colors.get(color.lower(), discord.Color.blue())
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Posted by {interaction.user.name}")
        
        content = "@everyone" if ping_everyone else None
        await channel.send(content=content, embed=embed)
        await interaction.response.send_message(f"✅ Embed sent to {channel.mention}!")
    
    @remove_category.autocomplete("name")
    async def category_autocomplete(self, interaction: discord.Interaction, current: str):
        async with self.bot.db.execute(
            'SELECT name FROM ticket_categories WHERE guild_id = ? AND name LIKE ?',
            (interaction.guild.id, f'%{current}%')
        ) as cursor:
            categories = await cursor.fetchall()
        
        return [
            app_commands.Choice(name=cat[0], value=cat[0])
            for cat in categories[:25]
        ]
    
    @app_commands.command(name="setup_logs", description="Configure logging channels (transcript, minor, major)")
    @app_commands.describe(
        transcript_channel="Channel for ticket transcripts",
        minor_logs="Channel for minor events (claims, renames, etc.)",
        major_logs="Channel for major events (ticket open/close, purchases)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_logs(
        self,
        interaction: discord.Interaction,
        transcript_channel: discord.TextChannel = None,
        minor_logs: discord.TextChannel = None,
        major_logs: discord.TextChannel = None
    ):
        # Build update query dynamically
        columns = []
        params = []
        
        if transcript_channel:
            columns.append("transcript_channel")
            params.append(transcript_channel.id)
        if minor_logs:
            columns.append("log_channel_minor")
            params.append(minor_logs.id)
        if major_logs:
            columns.append("log_channel_major")
            params.append(major_logs.id)
        
        if not columns:
            return await interaction.response.send_message("❌ Please provide at least one channel!", ephemeral=True)
        
        # Build SQL properly
        col_names = ', '.join(columns)
        placeholders = ', '.join(['?' for _ in params])
        updates = ', '.join([f"{col} = excluded.{col}" for col in columns])
        
        await self.bot.db.execute(
            f'''INSERT INTO ticket_configs (guild_id, {col_names})
               VALUES (?, {placeholders})
               ON CONFLICT(guild_id) DO UPDATE SET
               {updates}''',
            (interaction.guild.id, *params)
        )
        await self.bot.db.commit()
        
        # Build response
        desc_parts = []
        if transcript_channel:
            desc_parts.append(f"**Transcripts:** {transcript_channel.mention}")
        if minor_logs:
            desc_parts.append(f"**Minor Logs:** {minor_logs.mention}")
        if major_logs:
            desc_parts.append(f"**Major Logs:** {major_logs.mention}")
        
        embed = discord.Embed(
            title="✅ Logging Channels Configured",
            description="\n".join(desc_parts),
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
