import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import aiofiles
import aiosqlite
from dotenv import load_dotenv
from datetime import datetime
import logging

# Setup logging to file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord')

load_dotenv()

class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
    async def setup_hook(self):
        await self.init_database()
        await self.load_cogs()
        
    async def init_database(self):
        import os
        db_path = os.getenv('DB_PATH', 'tickets.db')
        self.db = await aiosqlite.connect(db_path)
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS ticket_configs (
                guild_id INTEGER PRIMARY KEY,
                ticket_category INTEGER,
                transcript_channel INTEGER,
                support_role INTEGER,
                ticket_counter INTEGER DEFAULT 0,
                log_channel_minor INTEGER,
                log_channel_major INTEGER
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS ticket_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                description TEXT,
                emoji TEXT,
                role_id INTEGER,
                category_id INTEGER
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                category TEXT,
                created_at TIMESTAMP,
                closed_at TIMESTAMP,
                closed_by INTEGER
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS welcome_configs (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                enabled INTEGER DEFAULT 1
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS license_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                hwid TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')
        await self.db.commit()
        
    async def load_cogs(self):
        await self.load_extension('cogs.tickets')
        await self.load_extension('cogs.admin')
        await self.load_extension('cogs.welcome')
        await self.load_extension('cogs.logging_cog')
        await self.load_extension('cogs.modmail')
        
    async def on_ready(self):
        await self.tree.sync()
        logger.info(f'Bot logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Invite link: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=8&scope=bot%20applications.commands')
        print(f'🤖 Logged in as {self.user} (ID: {self.user.id})')
        print(f'🔗 Invite: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=8&scope=bot%20applications.commands')
    
    async def on_command_completion(self, ctx):
        logger.info(f'Command used: {ctx.command.name} by {ctx.author} in {ctx.guild.name}')
    
    async def on_app_command_completion(self, interaction, command):
        logger.info(f'Slash command used: {command.name} by {interaction.user} in {interaction.guild.name}')
    
    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f'Error in {event_method}: {args} {kwargs}', exc_info=True)

bot = TicketBot()

@bot.event
async def on_close():
    await bot.db.close()

if __name__ == "__main__":
    bot.run(os.getenv('TOKEN'))
