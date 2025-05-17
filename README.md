# Netflix Automation Telegram Bot

This Telegram bot automates Netflix account creation and management using credit card information detected from Telegram groups.

## Prerequisites

- Python 3.8 or higher
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Telegram API credentials (API ID and API Hash) from [my.telegram.org](https://my.telegram.org)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/netflix-bot.git
cd netflix-bot
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root directory:

```
BOT_TOKEN=your_bot_token
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

## Running the Bot

### Local Development
```bash
python start_bot.py
```

### VPS Deployment

1. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

2. **Set up as a systemd service**

Edit the `netflix-bot.service` file:
- Update the paths to match your deployment
- Fill in your actual API credentials

Then deploy the service:
```bash
# Copy the service file
sudo cp netflix-bot.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable netflix-bot.service

# Start the service
sudo systemctl start netflix-bot.service

# Check status
sudo systemctl status netflix-bot.service
```

3. **View logs**
```bash
sudo journalctl -u netflix-bot.service -f
```

## Usage

1. Start the bot by sending `/start` to your bot on Telegram
2. Use the menu to interact with the bot:
   - Load your Telegram session
   - Add groups to monitor
   - Add Netflix accounts
   - Configure proxies
   - View statistics

## Session Loading

To load your Telegram session:
1. Generate a session string using Telethon's StringSession
2. Select "Load Session" from the bot menu
3. Send the session string to the bot

## Troubleshooting

If you encounter issues with session loading:
1. Ensure your API credentials are correct
2. Make sure your session string is valid
3. Check the logs for detailed error messages

If the bot crashes on your VPS:
1. Check the logs: `sudo journalctl -u netflix-bot.service -f`
2. Ensure all dependencies are properly installed
3. Verify that the service has the correct working directory path