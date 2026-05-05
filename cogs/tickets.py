import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button
import aiosqlite
from datetime import datetime
import io

class TicketDropdown(Select):
    def __init__(self, categories, bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label=cat['name'],
                description=cat['description'] or f"Create a {cat['name']} ticket",
                emoji=cat['emoji'] or '🎫',
                value=str(cat['id'])
            ) for cat in categories
        ]
        
        super().__init__(
            placeholder="🎫 Select a ticket category...",
            options=options,
            custom_id="ticket_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        category_id = int(self.values[0])
        
        async with self.bot.db.execute(
            'SELECT * FROM ticket_categories WHERE id = ?', (category_id,)
        ) as cursor:
            category = await cursor.fetchone()
        
        if not category:
            return await interaction.response.send_message(
                "❌ Category not found!", ephemeral=True
            )
        
        # Check if user already has an open ticket in this category
        async with self.bot.db.execute(
            '''SELECT channel_id FROM tickets 
               WHERE guild_id = ? AND user_id = ? AND category = ? AND closed_at IS NULL''',
            (interaction.guild.id, interaction.user.id, category[2])
        ) as cursor:
            existing = await cursor.fetchone()
        
        if existing:
            channel = interaction.guild.get_channel(existing[0])
            if channel:
                return await interaction.response.send_message(
                    f"❌ You already have an open ticket: {channel.mention}", ephemeral=True
                )
        
        # Get config
        async with self.bot.db.execute(
            'SELECT ticket_category, ticket_counter, support_role FROM ticket_configs WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            config = await cursor.fetchone()
        
        ticket_category = interaction.guild.get_channel(category[6]) if category[6] else None
        if not ticket_category and config:
            ticket_category = interaction.guild.get_channel(config[0])
        
        # Create ticket channel
        ticket_number = config[1] + 1 if config else 1
        channel_name = f"{category[2].lower().replace(' ', '-')}-{ticket_number:04d}"
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True, embed_links=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            )
        }
        
        # Add support role permissions
        if config and config[2]:
            support_role = interaction.guild.get_role(config[2])
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )
        
        # Add category-specific role
        if category[5]:
            role = interaction.guild.get_role(category[5])
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )
        
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=ticket_category,
            overwrites=overwrites,
            topic=f"Ticket for {interaction.user.name} | Category: {category[2]}"
        )
        
        # Save to database
        await self.bot.db.execute(
            '''INSERT INTO tickets (channel_id, guild_id, user_id, category, created_at)
               VALUES (?, ?, ?, ?, ?)''',
            (channel.id, interaction.guild.id, interaction.user.id, category[2], datetime.now())
        )
        # Update or insert ticket counter
        await self.bot.db.execute(
            '''INSERT INTO ticket_configs (guild_id, ticket_counter) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET ticket_counter = excluded.ticket_counter''',
            (interaction.guild.id, ticket_number)
        )
        await self.bot.db.commit()
        
        # Send welcome message
        embed = discord.Embed(
            title=f"🎫 {category[2]} Ticket",
            description=f"Welcome {interaction.user.mention}!\n\n**Category:** {category[2]}\n**Ticket #:** {ticket_number:04d}\n\nPlease describe your issue and a staff member will assist you shortly.",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"User ID: {interaction.user.id}")
        
        view = TicketControlView(self.bot)
        await channel.send(embed=embed, view=view)
        
        # Ping support roles
        pings = []
        if config and config[2]:
            support_role = interaction.guild.get_role(config[2])
            if support_role:
                pings.append(support_role.mention)
        if category[5]:
            role = interaction.guild.get_role(category[5])
            if role:
                pings.append(role.mention)
        
        if pings:
            await channel.send(" ".join(pings))
        
        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}", ephemeral=True
        )
        
        # Log ticket opened
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.log_ticket_open(interaction.guild, interaction.user, category[2], channel)

class TicketControlView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        async with self.bot.db.execute(
            'SELECT * FROM tickets WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            ticket = await cursor.fetchone()
        
        if not ticket:
            return await interaction.followup.send("❌ This is not an active ticket channel!", ephemeral=True)
        
        # Verify user is ticket owner or staff
        is_staff = False
        async with self.bot.db.execute(
            'SELECT support_role FROM ticket_configs WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            config = await cursor.fetchone()
        
        if config and config[0]:
            role = interaction.guild.get_role(config[0])
            if role and role in interaction.user.roles:
                is_staff = True
        
        if interaction.user.id != ticket[2] and not is_staff and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("❌ You don't have permission to close this ticket!", ephemeral=True)
        
        # Create close confirmation
        view = CloseConfirmView(self.bot, ticket[2])
        await interaction.channel.send(
            f"⚠️ {interaction.user.mention} wants to close this ticket. Click below to confirm.",
            view=view
        )
        await interaction.followup.send("✅ Close request sent!", ephemeral=True)
    
    @discord.ui.button(label="📝 Claim", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        # Check if already claimed
        async with self.bot.db.execute(
            'SELECT * FROM tickets WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            ticket = await cursor.fetchone()
        
        if not ticket:
            return await interaction.response.send_message("❌ This is not an active ticket!", ephemeral=True)
        
        # Add user to channel with explicit permissions
        overwrites = interaction.channel.overwrites_for(interaction.user)
        overwrites.read_messages = True
        overwrites.send_messages = True
        await interaction.channel.set_permissions(interaction.user, overwrite=overwrites)
        
        embed = discord.Embed(
            title="👋 Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket and will assist you.",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ You have claimed this ticket!", ephemeral=True)
        
        # Log ticket claimed
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.log_ticket_claim(interaction.guild, interaction.channel, interaction.user)
    
    @discord.ui.button(label="📋 Transcript", style=discord.ButtonStyle.secondary, custom_id="ticket_transcript")
    async def transcript_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        messages = []
        async for message in interaction.channel.history(limit=1000, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = message.content or "(embed/attachment)"
            messages.append(f"[{timestamp}] {message.author.name}: {content}")
        
        transcript_text = "\n".join(messages)
        transcript_file = io.StringIO(transcript_text)
        
        file = discord.File(transcript_file, filename=f"transcript-{interaction.channel.name}.txt")
        await interaction.followup.send("📋 Here's the transcript:", file=file, ephemeral=True)

class CloseConfirmView(View):
    def __init__(self, bot, ticket_owner_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.ticket_owner_id = ticket_owner_id
    
    @discord.ui.button(label="✅ Confirm Close", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        
        # Generate transcript
        messages = []
        async for message in interaction.channel.history(limit=1000, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = message.content or "(embed/attachment)"
            messages.append(f"[{timestamp}] {message.author.name}: {content}")
        
        transcript_text = "\n".join(messages)
        transcript_file = io.StringIO(transcript_text)
        
        # Get ticket info
        async with self.bot.db.execute(
            'SELECT user_id, category, created_at FROM tickets WHERE channel_id = ?',
            (interaction.channel.id,)
        ) as cursor:
            ticket = await cursor.fetchone()
        
        if not ticket:
            return await interaction.followup.send("❌ Ticket not found in database!", ephemeral=True)
        
        user_id, category, created_at = ticket[0], ticket[1], ticket[2]
        
        # Get user object for logging
        try:
            user = await self.bot.fetch_user(user_id)
        except:
            user = None
        
        # Update database
        await self.bot.db.execute(
            'UPDATE tickets SET closed_at = ?, closed_by = ? WHERE channel_id = ?',
            (datetime.now(), interaction.user.id, interaction.channel.id)
        )
        await self.bot.db.commit()
        
        # Get logging cog and send transcript
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            ticket_data = (user_id, category, created_at)
            await logging_cog.send_transcript(interaction.guild, ticket_data, transcript_text, interaction.user.id)
            await logging_cog.log_ticket_close(interaction.guild, user, category, interaction.channel.name, interaction.user.id)
        
        # Send transcript to user if possible
        if user:
            try:
                dm_embed = discord.Embed(
                    title="🎫 Ticket Closed",
                    description=f"Your **{category}** ticket in **{interaction.guild.name}** has been closed.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                file = discord.File(io.StringIO(transcript_text), filename=f"transcript-{interaction.channel.name}.txt")
                await user.send(embed=dm_embed, file=file)
            except:
                pass
        
        # Delete channel (transcripts are sent by logging cog above)
        await interaction.channel.delete()
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await interaction.message.delete()
        await interaction.followup.send("✅ Close cancelled!", ephemeral=True)

class TicketPanelView(View):
    def __init__(self, categories, bot):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(categories, bot))

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ticket_panel", description="Send the ticket creation panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target_channel = channel or interaction.channel
        
        # Get categories
        async with self.bot.db.execute(
            'SELECT * FROM ticket_categories WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            categories = await cursor.fetchall()
        
        if not categories:
            return await interaction.response.send_message(
                "❌ No ticket categories found! Use `/add_category` to create categories first.",
                ephemeral=True
            )
        
        # Convert to dict format
        cat_list = [
            {'id': c[0], 'name': c[2], 'description': c[3], 'emoji': c[4], 'role_id': c[5], 'category_id': c[6]}
            for c in categories
        ]
        
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Select a category from the dropdown below to create a ticket.\n\n**Available Categories:**\n" + 
                        "\n".join([f"{c[4] or '🎫'} **{c[2]}** - {c[3] or 'Create a ticket'}" for c in categories]),
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"{interaction.guild.name} Ticket System")
        
        view = TicketPanelView(cat_list, self.bot)
        await target_channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(
            f"✅ Ticket panel sent to {target_channel.mention}!",
            ephemeral=True
        )
    
    @app_commands.command(name="add_user", description="Add a user to the current ticket")
    @app_commands.describe(user="The user to add")
    async def add_user(self, interaction: discord.Interaction, user: discord.Member):
        async with self.bot.db.execute(
            'SELECT * FROM tickets WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            ticket = await cursor.fetchone()
        
        if not ticket:
            return await interaction.response.send_message("❌ This is not an active ticket channel!", ephemeral=True)
        
        overwrites = interaction.channel.overwrites_for(user)
        overwrites.read_messages = True
        overwrites.send_messages = True
        await interaction.channel.set_permissions(user, overwrite=overwrites)
        
        await interaction.response.send_message(f"✅ Added {user.mention} to this ticket!")
        
        # Log user added
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.log_user_add(interaction.guild, interaction.channel, user, interaction.user)
    
    @app_commands.command(name="remove_user", description="Remove a user from the current ticket")
    @app_commands.describe(user="The user to remove")
    async def remove_user(self, interaction: discord.Interaction, user: discord.Member):
        async with self.bot.db.execute(
            'SELECT * FROM tickets WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            ticket = await cursor.fetchone()
        
        if not ticket:
            return await interaction.response.send_message("❌ This is not an active ticket channel!", ephemeral=True)
        
        if user.id == ticket[2]:
            return await interaction.response.send_message("❌ Cannot remove the ticket creator!", ephemeral=True)
        
        await interaction.channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {user.mention} from this ticket!")
        
        # Log user removed
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.log_user_remove(interaction.guild, interaction.channel, user, interaction.user)
    
    @app_commands.command(name="rename_ticket", description="Rename the current ticket channel")
    @app_commands.describe(name="New channel name")
    async def rename_ticket(self, interaction: discord.Interaction, name: str):
        async with self.bot.db.execute(
            'SELECT * FROM tickets WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            ticket = await cursor.fetchone()
        
        if not ticket:
            return await interaction.response.send_message("❌ This is not an active ticket channel!", ephemeral=True)
        
        old_name = interaction.channel.name
        await interaction.channel.edit(name=name)
        await interaction.response.send_message(f"✅ Ticket renamed to `{name}`!")
        
        # Log ticket renamed
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.log_ticket_rename(interaction.guild, interaction.channel, old_name, name, interaction.user)

async def setup(bot):
    await bot.add_cog(Tickets(bot))
