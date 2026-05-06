import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime
import io
import aiosqlite


class ModMailCloseView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🔒 Close Thread", style=discord.ButtonStyle.danger, custom_id="modmail_close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        async with self.bot.db.execute(
            'SELECT user_id, opened_at FROM modmail_threads WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            thread = await cursor.fetchone()

        if not thread:
            return await interaction.followup.send("❌ This is not an active modmail thread!", ephemeral=True)

        user_id, opened_at = thread

        # Generate transcript
        messages = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = msg.content or "(embed/attachment)"
            messages.append(f"[{ts}] {msg.author.name}: {content}")
        transcript_text = "\n".join(messages)

        # Update DB
        await self.bot.db.execute(
            'UPDATE modmail_threads SET closed_at = ?, closed_by = ? WHERE channel_id = ?',
            (datetime.now(), interaction.user.id, interaction.channel.id)
        )
        await self.bot.db.commit()

        # Notify user via DM
        try:
            user = await self.bot.fetch_user(user_id)
            close_embed = discord.Embed(
                title="📬 ModMail Closed",
                description=f"Your modmail thread in **{interaction.guild.name}** has been closed by staff.\n\nFeel free to DM me again if you need further help.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            file = discord.File(io.StringIO(transcript_text), filename="modmail-transcript.txt")
            await user.send(embed=close_embed, file=file)
        except Exception:
            pass

        # Send transcript to log channel if configured
        async with self.bot.db.execute(
            'SELECT log_channel_id FROM modmail_configs WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            config = await cursor.fetchone()

        if config and config[0]:
            log_channel = interaction.guild.get_channel(config[0])
            if log_channel:
                log_embed = discord.Embed(
                    title="📋 ModMail Transcript",
                    description=f"**User:** <@{user_id}>\n**Closed by:** {interaction.user.mention}\n**Opened:** {opened_at}",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                file2 = discord.File(io.StringIO(transcript_text), filename="modmail-transcript.txt")
                await log_channel.send(embed=log_embed, file=file2)

        await interaction.channel.delete()


class ModMail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await self.bot.db.execute('''
            CREATE TABLE IF NOT EXISTS modmail_configs (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                log_channel_id INTEGER,
                enabled INTEGER DEFAULT 1
            )
        ''')
        await self.bot.db.execute('''
            CREATE TABLE IF NOT EXISTS modmail_threads (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                opened_at TIMESTAMP,
                closed_at TIMESTAMP,
                closed_by INTEGER
            )
        ''')
        await self.bot.db.commit()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only handle DMs from real users
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        # Find a guild where this user is a member and modmail is configured
        target_guild = None
        config = None

        for guild in self.bot.guilds:
            member = guild.get_member(message.author.id)
            if not member:
                continue
            async with self.bot.db.execute(
                'SELECT category_id, log_channel_id, enabled FROM modmail_configs WHERE guild_id = ?',
                (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row and row[2]:  # enabled
                target_guild = guild
                config = row
                break

        if not target_guild or not config:
            return  # No guild has modmail set up for this user

        category_id, log_channel_id, _ = config

        # Check if there's already an open thread for this user
        async with self.bot.db.execute(
            'SELECT channel_id FROM modmail_threads WHERE guild_id = ? AND user_id = ? AND closed_at IS NULL',
            (target_guild.id, message.author.id)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            # Forward message to existing thread
            channel = target_guild.get_channel(existing[0])
            if channel:
                embed = discord.Embed(
                    description=message.content or "(no text content)",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                embed.set_footer(text=f"User ID: {message.author.id}")

                files = []
                for attachment in message.attachments:
                    try:
                        files.append(await attachment.to_file())
                    except Exception:
                        pass

                await channel.send(embed=embed, files=files)
                await message.add_reaction("✅")
            return

        # Create new modmail thread
        category = target_guild.get_channel(category_id) if category_id else None

        overwrites = {
            target_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            target_guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        channel_name = f"modmail-{message.author.name.lower().replace(' ', '-')}"
        channel = await target_guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"ModMail from {message.author} (ID: {message.author.id})"
        )

        # Save to DB
        await self.bot.db.execute(
            'INSERT INTO modmail_threads (channel_id, guild_id, user_id, opened_at) VALUES (?, ?, ?, ?)',
            (channel.id, target_guild.id, message.author.id, datetime.now())
        )
        await self.bot.db.commit()

        # Send opening embed in thread
        open_embed = discord.Embed(
            title="📬 New ModMail Thread",
            description=f"**User:** {message.author.mention} (`{message.author.id}`)\n**Account Created:** <t:{int(message.author.created_at.timestamp())}:R>",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        open_embed.set_thumbnail(url=message.author.display_avatar.url)

        view = ModMailCloseView(self.bot)
        await channel.send(embed=open_embed, view=view)

        # Forward the first message
        msg_embed = discord.Embed(
            description=message.content or "(no text content)",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        msg_embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        msg_embed.set_footer(text=f"User ID: {message.author.id}")

        files = []
        for attachment in message.attachments:
            try:
                files.append(await attachment.to_file())
            except Exception:
                pass

        await channel.send(embed=msg_embed, files=files)

        # Notify user
        try:
            confirm_embed = discord.Embed(
                title="📬 ModMail Opened",
                description=f"Your message has been received by **{target_guild.name}** staff. We'll get back to you shortly!\n\nYou can continue sending messages here and they'll be forwarded.",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            await message.author.send(embed=confirm_embed)
        except Exception:
            pass

        await message.add_reaction("✅")

        # Log to log channel
        if log_channel_id:
            log_channel = target_guild.get_channel(log_channel_id)
            if log_channel:
                log_embed = discord.Embed(
                    title="📬 ModMail Opened",
                    description=f"**User:** {message.author.mention}\n**Channel:** {channel.mention}",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                await log_channel.send(embed=log_embed)

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        pass

    # Staff reply: any message sent in a modmail channel gets forwarded to the user
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):  # noqa: F811
        if message.author.bot:
            return

        # Handle DMs
        if isinstance(message.channel, discord.DMChannel):
            await self._handle_dm(message)
            return

        # Handle staff replies in modmail channels
        if isinstance(message.channel, discord.TextChannel):
            await self._handle_staff_reply(message)

    async def _handle_dm(self, message: discord.Message):
        target_guild = None
        config = None

        for guild in self.bot.guilds:
            member = guild.get_member(message.author.id)
            if not member:
                continue
            async with self.bot.db.execute(
                'SELECT category_id, log_channel_id, enabled FROM modmail_configs WHERE guild_id = ?',
                (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row and row[2]:
                target_guild = guild
                config = row
                break

        if not target_guild or not config:
            return

        category_id, log_channel_id, _ = config

        # Check existing open thread
        async with self.bot.db.execute(
            'SELECT channel_id FROM modmail_threads WHERE guild_id = ? AND user_id = ? AND closed_at IS NULL',
            (target_guild.id, message.author.id)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            channel = target_guild.get_channel(existing[0])
            if channel:
                embed = discord.Embed(
                    description=message.content or "(no text content)",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                embed.set_footer(text=f"User ID: {message.author.id}")
                files = []
                for attachment in message.attachments:
                    try:
                        files.append(await attachment.to_file())
                    except Exception:
                        pass
                await channel.send(embed=embed, files=files)
                await message.add_reaction("✅")
            return

        # Create new thread
        category = target_guild.get_channel(category_id) if category_id else None
        overwrites = {
            target_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            target_guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        channel_name = f"modmail-{message.author.name.lower().replace(' ', '-')}"
        channel = await target_guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"ModMail from {message.author} (ID: {message.author.id})"
        )

        await self.bot.db.execute(
            'INSERT INTO modmail_threads (channel_id, guild_id, user_id, opened_at) VALUES (?, ?, ?, ?)',
            (channel.id, target_guild.id, message.author.id, datetime.now())
        )
        await self.bot.db.commit()

        open_embed = discord.Embed(
            title="📬 New ModMail Thread",
            description=f"**User:** {message.author.mention} (`{message.author.id}`)\n**Account Created:** <t:{int(message.author.created_at.timestamp())}:R>",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        open_embed.set_thumbnail(url=message.author.display_avatar.url)

        view = ModMailCloseView(self.bot)
        await channel.send(embed=open_embed, view=view)

        msg_embed = discord.Embed(
            description=message.content or "(no text content)",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        msg_embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        msg_embed.set_footer(text=f"User ID: {message.author.id}")

        files = []
        for attachment in message.attachments:
            try:
                files.append(await attachment.to_file())
            except Exception:
                pass
        await channel.send(embed=msg_embed, files=files)

        try:
            confirm_embed = discord.Embed(
                title="📬 ModMail Opened",
                description=f"Your message has been received by **{target_guild.name}** staff. We'll get back to you shortly!\n\nYou can continue sending messages here and they'll be forwarded.",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            await message.author.send(embed=confirm_embed)
        except Exception:
            pass

        await message.add_reaction("✅")

        if log_channel_id:
            log_channel = target_guild.get_channel(log_channel_id)
            if log_channel:
                log_embed = discord.Embed(
                    title="📬 ModMail Opened",
                    description=f"**User:** {message.author.mention}\n**Channel:** {channel.mention}",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                await log_channel.send(embed=log_embed)

    async def _handle_staff_reply(self, message: discord.Message):
        if not message.guild:
            return

        async with self.bot.db.execute(
            'SELECT user_id FROM modmail_threads WHERE channel_id = ? AND closed_at IS NULL',
            (message.channel.id,)
        ) as cursor:
            thread = await cursor.fetchone()

        if not thread:
            return

        user_id = thread[0]

        try:
            user = await self.bot.fetch_user(user_id)
            reply_embed = discord.Embed(
                description=message.content or "(no text content)",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            reply_embed.set_author(
                name=f"{message.author.display_name} (Staff)",
                icon_url=message.author.display_avatar.url
            )
            reply_embed.set_footer(text=message.guild.name, icon_url=message.guild.icon.url if message.guild.icon else None)

            files = []
            for attachment in message.attachments:
                try:
                    files.append(await attachment.to_file())
                except Exception:
                    pass

            await user.send(embed=reply_embed, files=files)
            await message.add_reaction("✅")
        except discord.Forbidden:
            await message.add_reaction("❌")
            await message.channel.send("⚠️ Could not DM the user — they may have DMs disabled.", delete_after=5)
        except Exception:
            await message.add_reaction("❌")

    # --- Slash Commands ---

    @app_commands.command(name="modmail_setup", description="Set up the modmail system")
    @app_commands.describe(
        category="Category where modmail threads will be created",
        log_channel="Channel to log modmail activity"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def modmail_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel = None
    ):
        await self.bot.db.execute(
            '''INSERT INTO modmail_configs (guild_id, category_id, log_channel_id, enabled)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(guild_id) DO UPDATE SET
                   category_id = excluded.category_id,
                   log_channel_id = excluded.log_channel_id,
                   enabled = 1''',
            (interaction.guild.id, category.id, log_channel.id if log_channel else None)
        )
        await self.bot.db.commit()

        embed = discord.Embed(
            title="✅ ModMail Configured",
            description=f"**Category:** {category.mention}\n**Log Channel:** {log_channel.mention if log_channel else 'None'}\n\nUsers can now DM the bot to open a modmail thread.",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="modmail_disable", description="Disable the modmail system")
    @app_commands.checks.has_permissions(administrator=True)
    async def modmail_disable(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            'UPDATE modmail_configs SET enabled = 0 WHERE guild_id = ?',
            (interaction.guild.id,)
        )
        await self.bot.db.commit()
        await interaction.response.send_message("✅ ModMail has been disabled.", ephemeral=True)

    @app_commands.command(name="modmail_close", description="Close the current modmail thread")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modmail_close_cmd(self, interaction: discord.Interaction):
        async with self.bot.db.execute(
            'SELECT user_id, opened_at FROM modmail_threads WHERE channel_id = ? AND closed_at IS NULL',
            (interaction.channel.id,)
        ) as cursor:
            thread = await cursor.fetchone()

        if not thread:
            return await interaction.response.send_message("❌ This is not an active modmail thread!", ephemeral=True)

        await interaction.response.defer()

        user_id, opened_at = thread

        messages = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = msg.content or "(embed/attachment)"
            messages.append(f"[{ts}] {msg.author.name}: {content}")
        transcript_text = "\n".join(messages)

        await self.bot.db.execute(
            'UPDATE modmail_threads SET closed_at = ?, closed_by = ? WHERE channel_id = ?',
            (datetime.now(), interaction.user.id, interaction.channel.id)
        )
        await self.bot.db.commit()

        try:
            user = await self.bot.fetch_user(user_id)
            close_embed = discord.Embed(
                title="📬 ModMail Closed",
                description=f"Your modmail thread in **{interaction.guild.name}** has been closed.\n\nFeel free to DM me again if you need further help.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            file = discord.File(io.StringIO(transcript_text), filename="modmail-transcript.txt")
            await user.send(embed=close_embed, file=file)
        except Exception:
            pass

        async with self.bot.db.execute(
            'SELECT log_channel_id FROM modmail_configs WHERE guild_id = ?',
            (interaction.guild.id,)
        ) as cursor:
            config = await cursor.fetchone()

        if config and config[0]:
            log_channel = interaction.guild.get_channel(config[0])
            if log_channel:
                log_embed = discord.Embed(
                    title="📋 ModMail Transcript",
                    description=f"**User:** <@{user_id}>\n**Closed by:** {interaction.user.mention}\n**Opened:** {opened_at}",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                file2 = discord.File(io.StringIO(transcript_text), filename="modmail-transcript.txt")
                await log_channel.send(embed=log_embed, file=file2)

        await interaction.channel.delete()


async def setup(bot):
    await bot.add_cog(ModMail(bot))
