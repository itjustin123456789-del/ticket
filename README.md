# 🎫 Ultimate Discord Ticket Bot

The best Discord ticket bot with **custom categories**, **dropdown menus**, and a sleek modern design.

## ✨ Features

- 🎯 **Dropdown Ticket Creation** - Users select categories from a beautiful dropdown menu
- 🏷️ **Custom Categories** - Create unlimited ticket types (Support, Report, Purchase, etc.)
- 👥 **Role-Based Access** - Assign specific roles to different ticket categories
- 📝 **Auto Transcripts** - Generated when tickets close, sent to user and log channel
- 🔒 **Smart Permissions** - Only ticket creator and staff can see tickets
- 📊 **Statistics** - Track ticket metrics
- 🎨 **Modern UI** - Clean embeds with buttons and dropdowns

## 🚀 Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and fill in:
```env
TOKEN=your_bot_token_here
```

### 3. Run the Bot
```bash
python bot.py
```

## 🛠️ Configuration Commands

### Initial Setup
```
/setup_tickets <category> <transcript_channel> <support_role>
```

### Manage Categories
```
/add_category <name> [description] [emoji] [specific_role] [channel_category]
/remove_category <name>
/list_categories
```

### Create Ticket Panel
```
/ticket_panel [channel]
```

### View Stats
```
/ticket_stats
```

## 📁 Project Structure
```
discord-ticket-bot/
├── bot.py              # Main bot file
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── cogs/
│   ├── tickets.py      # Ticket system (dropdowns, controls)
│   └── admin.py        # Admin configuration commands
├── tickets.db          # SQLite database (auto-created)
└── README.md
```

## 🔗 Invite URL
After starting the bot, check console for the invite link with proper permissions.

## License
MIT
