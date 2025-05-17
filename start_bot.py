import os
import asyncio
import logging
import sys
import argparse
from dotenv import load_dotenv
from netflix_bot_main import main
from netflix_db import NetflixDatabase
from telethon.sessions import StringSession
from telethon import TelegramClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
if os.path.exists(".env"):
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
else:
    logger.info("No .env file found, using system environment variables")

async def load_session_manually(session_string):
    """Manually load a Telegram session without the bot interface"""
    # Initialize the database
    db = NetflixDatabase()
    
    # Validate API credentials
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    
    if not api_id or not api_hash:
        logger.error("Missing Telegram API credentials (TELEGRAM_API_ID, TELEGRAM_API_HASH)")
        return False
    
    # Basic validation on session string
    if not session_string or len(session_string) < 10:
        logger.error("Invalid session string format")
        return False
    
    try:
        # Test the session to ensure it's valid
        client = TelegramClient(StringSession(session_string), 
                                api_id=int(api_id), 
                                api_hash=api_hash)
        
        await client.connect()
        if await client.is_user_authorized():
            # Session is valid, save it to the database
            db.save_session(session_string)
            logger.info("Session loaded and saved to database successfully")
            await client.disconnect()
            return True
        else:
            logger.error("Session is not authorized")
            await client.disconnect()
            return False
    except Exception as e:
        logger.error(f"Error loading session: {e}")
        return False

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Netflix Automation Bot')
    parser.add_argument('--session', help='Load a Telegram session string manually')
    parser.add_argument('--session-file', help='Load a Telegram session string from a file')
    args = parser.parse_args()
    
    # Check if environment variables are set
    required_vars = ["BOT_TOKEN", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these environment variables and try again")
        exit(1)
    
    # Create necessary directories
    os.makedirs("screenshots", exist_ok=True)
    
    # Handle manual session loading if provided
    if args.session:
        logger.info("Attempting to load session string from command line argument...")
        asyncio.run(load_session_manually(args.session))
    
    if args.session_file:
        try:
            with open(args.session_file, 'r') as f:
                session_string = f.read().strip()
                logger.info(f"Attempting to load session string from file: {args.session_file}")
                asyncio.run(load_session_manually(session_string))
        except FileNotFoundError:
            logger.error(f"Session file not found: {args.session_file}")
        except Exception as e:
            logger.error(f"Error reading session file: {e}")
    
    try:
        # Start the main bot
        logger.info("Starting Netflix Automation Bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        exit(1)