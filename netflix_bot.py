import logging
import asyncio
import os
import time
from typing import Dict, List, Any, Optional, Union, cast
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import events

from database import BotDatabase
from card_detector import CardDetector
from netflix_automation import NetflixAutomation

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants for callback data
MENU_CALLBACK = {
    "MAIN_MENU": "main_menu",
    "LOAD_SESSION": "load_session",
    "ADD_ACCOUNT": "add_account",
    "LIST_ACCOUNTS": "list_accounts",
    "REMOVE_ACCOUNT": "remove_account",
    "ADD_PROXY": "add_proxy",
    "LIST_PROXIES": "list_proxies",
    "REMOVE_PROXY": "remove_proxy",
    "ADD_GROUP": "add_group",
    "LIST_GROUPS": "list_groups",
    "REMOVE_GROUP": "remove_group",
    "VIEW_STATS": "view_stats",
    "SETTINGS": "settings",
    "CANCEL": "cancel",
    "BACK": "back",
    "CONFIRM": "confirm",
    "YES": "yes",
    "NO": "no"
}

# State management for conversation flows
USER_STATE = {}

# Class for managing Telegram user session client
class SessionManager:
    def __init__(self, db: BotDatabase):
        self.db = db
        self.client: Optional[TelegramClient] = None
        self.monitoring_groups = False
        self.card_detector = CardDetector()
        self.netflix_automation = None
        self._processing_lock = asyncio.Lock()
        self._new_card_event = asyncio.Event()
    
    async def load_session(self, session_string: str) -> bool:
        """Load a Telegram user session from string"""
        try:
            # Close existing client if any
            if self.client and self.client.is_connected():
                await self.client.disconnect()
            
            # Create new client with the session
            self.client = TelegramClient(StringSession(session_string), 
                                         api_id=os.environ.get("TELEGRAM_API_ID", ""), 
                                         api_hash=os.environ.get("TELEGRAM_API_HASH", ""))
            
            # Connect and verify it works
            await self.client.connect()
            if await self.client.is_user_authorized():
                # Save the working session to database
                self.db.save_session(session_string)
                
                # Set up event handlers for the client
                self._setup_event_handlers()
                
                return True
            else:
                # Session is not valid/authorized
                return False
        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return False
    
    def _setup_event_handlers(self):
        """Set up event handlers for the Telethon client"""
        if not self.client:
            return
        
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            """Handle new messages in monitored groups"""
            try:
                # Only process messages from groups we're monitoring
                chat = await event.get_chat()
                chat_id = str(chat.id)
                
                # Get monitored groups from database
                monitored_groups = self.db.get_monitored_groups()
                active_group_ids = [g['group_id'] for g in monitored_groups if g['is_active']]
                
                if chat_id not in active_group_ids:
                    return
                
                # Process the message for card information
                await self._process_message(event, chat_id)
            except Exception as e:
                logger.error(f"Error handling message: {e}")
    
    async def _process_message(self, event, chat_id: str):
        """Process a message for card detection"""
        message_text = event.message.text if event.message.text else ""
        
        # Check for card information in the message
        card_info = self.card_detector.detect_credit_card_info(message_text)
        
        if card_info:
            logger.info(f"Credit card detected in group {chat_id}")
            
            # Add the card to the database
            try:
                card_id = self.db.add_credit_card(
                    card_info['card_number'],
                    card_info['expiry_date'],
                    card_info['cvv'],
                    chat_id
                )
                
                # Trigger new card event
                self._new_card_event.set()
                self._new_card_event.clear()
                
                # Start processing accounts if not already processing
                if not self._processing_lock.locked():
                    asyncio.create_task(self.process_accounts())
            except Exception as e:
                logger.error(f"Error adding card to database: {e}")
    
    async def start_monitoring(self):
        """Start monitoring groups for cards"""
        if not self.client or not self.client.is_connected():
            # Try to load the last active session
            session_string = self.db.get_active_session()
            if session_string:
                success = await self.load_session(session_string)
                if not success:
                    return False
            else:
                return False
        
        self.monitoring_groups = True
        return True
    
    async def stop_monitoring(self):
        """Stop monitoring groups"""
        self.monitoring_groups = False
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            self.client = None
        return True
    
    async def process_accounts(self):
        """Process accounts with available cards"""
        async with self._processing_lock:
            logger.info("Starting account processing")
            
            while True:
                # Get next pending account
                account = self.db.get_next_pending_account()
                if not account:
                    logger.info("No pending accounts to process")
                    break
                
                # Update account status to processing
                self.db.update_account_status(account['id'], 'processing')
                
                # Process the account
                await self._process_single_account(account)
                
                # Small delay between accounts
                await asyncio.sleep(2)
    
    async def _process_single_account(self, account: Dict[str, Any]):
        """Process a single Netflix account"""
        logger.info(f"Processing account: {account['email']}")
        
        try:
            # Get a card to use
            card = self.db.get_latest_unused_card()
            if not card:
                logger.info(f"No cards available, waiting for new card")
                self.db.update_account_status(account['id'], 'pending')
                return
            
            # Get proxy based on card country
            proxy = self.db.get_proxy_by_country(card['country'])
            if not proxy:
                logger.warning(f"No proxy available for country {card['country']}")
                proxy = self.db.get_next_proxy()
                if not proxy:
                    logger.error("No proxies available at all")
                    self.db.update_account_status(account['id'], 'failed', "No proxies available")
                    return
            
            # Initialize Netflix automation with the proxy
            start_time = time.time()
            proxy_data = {
                'http': f"http://{proxy['username']}:{proxy['password']}@{proxy['ip']}:{proxy['port']}" 
                        if proxy['username'] and proxy['password'] else 
                        f"http://{proxy['ip']}:{proxy['port']}"
            }
            
            # Create Netflix automation instance
            netflix = NetflixAutomation(proxy=proxy_data)
            
            # Try processing the account with the card
            success = False
            error_msg = None
            
            try:
                # Set up the browser
                netflix.setup_driver()
                
                if account['cookies']:
                    # Try to use cookies if available
                    netflix.load_cookies(account['cookies'])
                    logger.info(f"Loaded cookies for account {account['email']}")
                else:
                    # Login with credentials
                    success = await netflix.login_with_credentials(account['email'], account['password'])
                    if not success:
                        error_msg = "Failed to login with credentials"
                        raise Exception(error_msg)
                
                # Process the Netflix signup flow with the card
                success = await self._process_netflix_flow(netflix, card)
                if success:
                    # Mark account and card as used successfully
                    self.db.mark_account_success(account['id'], card['id'])
                    if proxy:
                        self.db.update_proxy_status(proxy['id'], 'active', True)
                    
                    processing_time = int(time.time() - start_time)
                    self.db.add_statistic('billing', True, proxy['id'] if proxy else None, 
                                        account['id'], card['id'], processing_time)
                    
                    logger.info(f"Successfully billed account {account['email']}")
                else:
                    error_msg = "Failed to process Netflix flow"
                    raise Exception(error_msg)
            except Exception as e:
                logger.error(f"Error processing account {account['email']}: {e}")
                error_msg = str(e)
                
                # Check retry count
                if account['retry_count'] < 3:
                    # Update status for retry
                    self.db.update_account_status(account['id'], 'pending', error_msg)
                    
                    # Mark card as failed
                    self.db.mark_card_failed(card['id'], error_msg)
                    
                    # Mark proxy as failed
                    if proxy:
                        self.db.update_proxy_status(proxy['id'], 'active', False)
                else:
                    # Mark account as failed after max retries
                    self.db.update_account_status(account['id'], 'failed', error_msg)
                    
                    # Record failure statistic
                    processing_time = int(time.time() - start_time)
                    self.db.add_statistic('billing', False, proxy['id'] if proxy else None, 
                                        account['id'], card['id'], processing_time, error_msg)
            finally:
                # Always close the browser
                if netflix:
                    netflix.close()
        except Exception as e:
            logger.error(f"Unexpected error processing account {account['email']}: {e}")
            self.db.update_account_status(account['id'], 'failed', str(e))
    
    async def _process_netflix_flow(self, netflix: NetflixAutomation, card: Dict[str, Any]) -> bool:
        """Process the Netflix signup flow with a card"""
        try:
            # Check current page in the flow
            current_page = netflix.detect_current_page()
            
            # Process depending on the current page
            if current_page == 'login':
                # If still on login page, something went wrong
                return False
            
            elif current_page == 'plan_selection':
                if not netflix.handle_plan_selection():
                    return False
                current_page = netflix.detect_current_page()
            
            if current_page == 'payment_method':
                if not netflix.handle_payment_method():
                    return False
                current_page = netflix.detect_current_page()
            
            if current_page == 'credit_card_form':
                # Fill in the credit card form
                if not netflix.handle_credit_card_form(card):
                    return False
                
                # Check for payment success
                if not netflix.check_payment_success():
                    return False
            
            # If we've reached this point, consider it successful
            return True
        except Exception as e:
            logger.error(f"Error in Netflix flow: {e}")
            return False
    
    async def stop_client(self):
        """Stop the Telethon client"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            self.client = None


# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    main_menu_keyboard = get_main_menu_keyboard()
    
    await update.message.reply_text(
        "Welcome to the Netflix Automation Bot!\n\n"
        "This bot will help you automate Netflix account billing using your Telegram session.\n\n"
        "Please use the menu below to get started:",
        reply_markup=main_menu_keyboard
    )

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get the main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📱 Load Session", callback_data=MENU_CALLBACK["LOAD_SESSION"])],
        [InlineKeyboardButton("👤 Add Account", callback_data=MENU_CALLBACK["ADD_ACCOUNT"]),
         InlineKeyboardButton("📋 List Accounts", callback_data=MENU_CALLBACK["LIST_ACCOUNTS"])],
        [InlineKeyboardButton("🌐 Add Proxy", callback_data=MENU_CALLBACK["ADD_PROXY"]),
         InlineKeyboardButton("📋 List Proxies", callback_data=MENU_CALLBACK["LIST_PROXIES"])],
        [InlineKeyboardButton("👥 Add Group", callback_data=MENU_CALLBACK["ADD_GROUP"]),
         InlineKeyboardButton("📋 List Groups", callback_data=MENU_CALLBACK["LIST_GROUPS"])],
        [InlineKeyboardButton("📊 View Statistics", callback_data=MENU_CALLBACK["VIEW_STATS"])],
        [InlineKeyboardButton("⚙️ Settings", callback_data=MENU_CALLBACK["SETTINGS"])]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from inline keyboard buttons."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Main menu options
    if callback_data == MENU_CALLBACK["MAIN_MENU"]:
        await query.edit_message_text(
            "Main Menu - Please select an option:",
            reply_markup=get_main_menu_keyboard()
        )
    elif callback_data == MENU_CALLBACK["LOAD_SESSION"]:
        await handle_load_session(query, context)
    elif callback_data == MENU_CALLBACK["ADD_ACCOUNT"]:
        await handle_add_account(query, context)
    elif callback_data == MENU_CALLBACK["LIST_ACCOUNTS"]:
        await handle_list_accounts(query, context)
    elif callback_data == MENU_CALLBACK["ADD_PROXY"]:
        await handle_add_proxy(query, context)
    elif callback_data == MENU_CALLBACK["LIST_PROXIES"]:
        await handle_list_proxies(query, context)
    elif callback_data == MENU_CALLBACK["ADD_GROUP"]:
        await handle_add_group(query, context)
    elif callback_data == MENU_CALLBACK["LIST_GROUPS"]:
        await handle_list_groups(query, context)
    elif callback_data == MENU_CALLBACK["VIEW_STATS"]:
        await handle_view_stats(query, context)
    elif callback_data == MENU_CALLBACK["SETTINGS"]:
        await handle_settings(query, context)
    elif callback_data.startswith("remove_account:"):
        account_id = int(callback_data.split(":")[1])
        await handle_remove_account(query, context, account_id)
    elif callback_data.startswith("remove_proxy:"):
        proxy_id = int(callback_data.split(":")[1])
        await handle_remove_proxy(query, context, proxy_id)
    elif callback_data.startswith("remove_group:"):
        group_id = int(callback_data.split(":")[1])
        await handle_remove_group(query, context, group_id)
    elif callback_data == MENU_CALLBACK["CANCEL"]:
        await query.edit_message_text(
            "Operation cancelled. Returning to main menu.",
            reply_markup=get_main_menu_keyboard()
        )
    elif callback_data == MENU_CALLBACK["YES"]:
        await handle_yes_response(query, context, user_id)
    elif callback_data == MENU_CALLBACK["NO"]:
        await handle_no_response(query, context, user_id)

async def handle_load_session(query, context):
    """Handle the Load Session option."""
    user_id = query.from_user.id
    USER_STATE[user_id] = {"state": "waiting_for_session"}
    
    await query.edit_message_text(
        "Please send your Telegram session string.\n\n"
        "You can obtain this by using the Telethon StringSession generator. "
        "This is required for the bot to access groups using your account.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
        ]])
    )

async def handle_add_account(query, context):
    """Handle the Add Account option."""
    user_id = query.from_user.id
    USER_STATE[user_id] = {"state": "waiting_for_email"}
    
    await query.edit_message_text(
        "Please send the Netflix account email address:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
        ]])
    )

async def handle_list_accounts(query, context):
    """Handle the List Accounts option."""
    db = context.bot_data.get("db")
    if not db:
        await query.edit_message_text(
            "Database not initialized. Please try again later.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    accounts = db.get_accounts()
    
    if not accounts:
        await query.edit_message_text(
            "No accounts found in the database.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
            ]])
        )
        return
    
    # Create message and keyboard for accounts list
    message = "📋 Netflix Accounts:\n\n"
    keyboard = []
    
    for account in accounts:
        status_emoji = "✅" if account["successfully_billed"] else "⏳" if account["status"] == "pending" else "❌"
        validated_emoji = "✓" if account["validated"] else "✗"
        
        message += f"{status_emoji} {account['email']} - Status: {account['status']} - Validated: {validated_emoji}\n"
        
        # Add remove button for each account
        keyboard.append([
            InlineKeyboardButton(f"Remove {account['email']}", 
                                callback_data=f"remove_account:{account['id']}")
        ])
    
    # Add back button
    keyboard.append([
        InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_add_proxy(query, context):
    """Handle the Add Proxy option."""
    user_id = query.from_user.id
    USER_STATE[user_id] = {"state": "waiting_for_proxy"}
    
    await query.edit_message_text(
        "Please send the proxy details in one of these formats:\n\n"
        "1. IP:PORT\n"
        "2. IP:PORT:USERNAME:PASSWORD\n"
        "3. IP:PORT:USERNAME:PASSWORD:COUNTRY\n\n"
        "Example: 192.168.1.1:8080:user:pass:US",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
        ]])
    )

async def handle_list_proxies(query, context):
    """Handle the List Proxies option."""
    db = context.bot_data.get("db")
    if not db:
        await query.edit_message_text(
            "Database not initialized. Please try again later.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    proxies = db.get_proxies()
    
    if not proxies:
        await query.edit_message_text(
            "No proxies found in the database.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
            ]])
        )
        return
    
    # Create message and keyboard for proxies list
    message = "📋 Proxies:\n\n"
    keyboard = []
    
    for proxy in proxies:
        status_emoji = "✅" if proxy["status"] == "active" else "❌"
        country = f"({proxy['country']})" if proxy["country"] else ""
        success_rate = f"{proxy['success_rate']:.1f}%" if "success_rate" in proxy else "N/A"
        
        message += f"{status_emoji} {proxy['ip']}:{proxy['port']} {country} - Success Rate: {success_rate}\n"
        
        # Add remove button for each proxy
        keyboard.append([
            InlineKeyboardButton(f"Remove {proxy['ip']}:{proxy['port']}", 
                                callback_data=f"remove_proxy:{proxy['id']}")
        ])
    
    # Add back button
    keyboard.append([
        InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_add_group(query, context):
    """Handle the Add Group option."""
    user_id = query.from_user.id
    
    # Check if session is loaded
    session_manager = context.bot_data.get("session_manager")
    if not session_manager or not session_manager.client or not session_manager.client.is_connected():
        await query.edit_message_text(
            "Please load your Telegram session first before adding groups.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Load Session", callback_data=MENU_CALLBACK["LOAD_SESSION"]),
                InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
            ]])
        )
        return
    
    USER_STATE[user_id] = {"state": "waiting_for_group_link"}
    
    await query.edit_message_text(
        "Please send the group/channel link or username:\n\n"
        "Examples:\n"
        "- https://t.me/example\n"
        "- @example",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
        ]])
    )

async def handle_list_groups(query, context):
    """Handle the List Groups option."""
    db = context.bot_data.get("db")
    if not db:
        await query.edit_message_text(
            "Database not initialized. Please try again later.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    groups = db.get_monitored_groups()
    
    if not groups:
        await query.edit_message_text(
            "No groups/channels being monitored.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
            ]])
        )
        return
    
    # Create message and keyboard for groups list
    message = "📋 Monitored Groups/Channels:\n\n"
    keyboard = []
    
    for group in groups:
        status_emoji = "✅" if group["is_active"] else "❌"
        message += f"{status_emoji} {group['group_title']} - Cards Found: {group['cards_found']}\n"
        
        # Add remove button for each group
        keyboard.append([
            InlineKeyboardButton(f"Remove {group['group_title']}", 
                                callback_data=f"remove_group:{group['id']}")
        ])
    
    # Add back button
    keyboard.append([
        InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
    ])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_view_stats(query, context):
    """Handle the View Statistics option."""
    db = context.bot_data.get("db")
    if not db:
        await query.edit_message_text(
            "Database not initialized. Please try again later.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    stats = db.get_statistics()
    
    # Create message with statistics
    message = "📊 Bot Statistics 📊\n\n"
    
    # Accounts section
    message += "👤 Accounts:\n"
    message += f"Total: {stats['accounts']['total']}\n"
    message += f"Completed: {stats['accounts']['completed']}\n"
    message += f"Pending: {stats['accounts']['pending']}\n"
    message += f"Failed: {stats['accounts']['failed']}\n\n"
    
    # Cards section
    message += "💳 Cards:\n"
    message += f"Total: {stats['cards']['total']}\n"
    message += f"Used: {stats['cards']['used']}\n"
    message += f"Unused: {stats['cards']['unused']}\n"
    message += f"Failed: {stats['cards']['failed']}\n\n"
    
    # Proxies section
    message += "🌐 Proxies:\n"
    message += f"Total: {stats['proxies']['total']}\n"
    message += f"Active: {stats['proxies']['active']}\n"
    message += f"Success Rate: {stats['proxies']['success_rate']:.1f}%\n\n"
    
    # Overall stats
    message += "📈 Overall:\n"
    message += f"Success Rate: {stats['success_rate']:.1f}%\n"
    
    if stats['average_processing_time'] > 0:
        avg_time = stats['average_processing_time']
        minutes = int(avg_time // 60)
        seconds = int(avg_time % 60)
        message += f"Average Processing Time: {minutes}m {seconds}s\n"
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
        ]])
    )

async def handle_settings(query, context):
    """Handle the Settings option."""
    keyboard = [
        [InlineKeyboardButton("Start Bot Monitoring", callback_data="setting:start_monitoring")],
        [InlineKeyboardButton("Stop Bot Monitoring", callback_data="setting:stop_monitoring")],
        [InlineKeyboardButton("Remove Session", callback_data="setting:remove_session")],
        [InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])]
    ]
    
    await query.edit_message_text(
        "⚙️ Settings:\n\n"
        "Control your bot's behavior with these options:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_remove_account(query, context, account_id):
    """Handle removing an account."""
    user_id = query.from_user.id
    USER_STATE[user_id] = {"state": "confirm_remove_account", "account_id": account_id}
    
    db = context.bot_data.get("db")
    accounts = db.get_accounts()
    account = next((a for a in accounts if a["id"] == account_id), None)
    
    if not account:
        await query.edit_message_text(
            "Account not found.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Accounts", callback_data=MENU_CALLBACK["LIST_ACCOUNTS"])
            ]])
        )
        return
    
    await query.edit_message_text(
        f"Are you sure you want to remove the account {account['email']}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data=MENU_CALLBACK["YES"]),
             InlineKeyboardButton("No", callback_data=MENU_CALLBACK["NO"])],
            [InlineKeyboardButton("Back to Accounts", callback_data=MENU_CALLBACK["LIST_ACCOUNTS"])]
        ])
    )

async def handle_remove_proxy(query, context, proxy_id):
    """Handle removing a proxy."""
    user_id = query.from_user.id
    USER_STATE[user_id] = {"state": "confirm_remove_proxy", "proxy_id": proxy_id}
    
    db = context.bot_data.get("db")
    proxies = db.get_proxies()
    proxy = next((p for p in proxies if p["id"] == proxy_id), None)
    
    if not proxy:
        await query.edit_message_text(
            "Proxy not found.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Proxies", callback_data=MENU_CALLBACK["LIST_PROXIES"])
            ]])
        )
        return
    
    await query.edit_message_text(
        f"Are you sure you want to remove the proxy {proxy['ip']}:{proxy['port']}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data=MENU_CALLBACK["YES"]),
             InlineKeyboardButton("No", callback_data=MENU_CALLBACK["NO"])],
            [InlineKeyboardButton("Back to Proxies", callback_data=MENU_CALLBACK["LIST_PROXIES"])]
        ])
    )

async def handle_remove_group(query, context, group_id):
    """Handle removing a group."""
    user_id = query.from_user.id
    USER_STATE[user_id] = {"state": "confirm_remove_group", "group_id": group_id}
    
    db = context.bot_data.get("db")
    groups = db.get_monitored_groups()
    group = next((g for g in groups if g["id"] == group_id), None)
    
    if not group:
        await query.edit_message_text(
            "Group not found.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Groups", callback_data=MENU_CALLBACK["LIST_GROUPS"])
            ]])
        )
        return
    
    await query.edit_message_text(
        f"Are you sure you want to remove the group {group['group_title']}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data=MENU_CALLBACK["YES"]),
             InlineKeyboardButton("No", callback_data=MENU_CALLBACK["NO"])],
            [InlineKeyboardButton("Back to Groups", callback_data=MENU_CALLBACK["LIST_GROUPS"])]
        ])
    )

async def handle_yes_response(query, context, user_id):
    """Handle Yes responses in various confirmation dialogs."""
    if user_id not in USER_STATE:
        await query.edit_message_text(
            "Operation timed out. Please try again.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    state = USER_STATE[user_id]["state"]
    db = context.bot_data.get("db")
    
    if state == "confirm_remove_account":
        account_id = USER_STATE[user_id]["account_id"]
        success = db.remove_account(account_id)
        
        if success:
            await query.edit_message_text(
                "Account removed successfully.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Accounts", callback_data=MENU_CALLBACK["LIST_ACCOUNTS"])
                ]])
            )
        else:
            await query.edit_message_text(
                "Failed to remove account.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Accounts", callback_data=MENU_CALLBACK["LIST_ACCOUNTS"])
                ]])
            )
    
    elif state == "confirm_remove_proxy":
        proxy_id = USER_STATE[user_id]["proxy_id"]
        success = db.remove_proxy(proxy_id)
        
        if success:
            await query.edit_message_text(
                "Proxy removed successfully.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Proxies", callback_data=MENU_CALLBACK["LIST_PROXIES"])
                ]])
            )
        else:
            await query.edit_message_text(
                "Failed to remove proxy.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Proxies", callback_data=MENU_CALLBACK["LIST_PROXIES"])
                ]])
            )
    
    elif state == "confirm_remove_group":
        group_id = USER_STATE[user_id]["group_id"]
        success = db.remove_monitored_group(group_id)
        
        if success:
            await query.edit_message_text(
                "Group removed successfully.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Groups", callback_data=MENU_CALLBACK["LIST_GROUPS"])
                ]])
            )
        else:
            await query.edit_message_text(
                "Failed to remove group.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Groups", callback_data=MENU_CALLBACK["LIST_GROUPS"])
                ]])
            )
    
    elif state == "waiting_for_add_cookies":
        USER_STATE[user_id]["state"] = "waiting_for_cookies"
        
        await query.edit_message_text(
            "Please send the cookies string for this account:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
            ]])
        )
    
    # Clear state if not moving to a new state
    if state != "waiting_for_add_cookies":
        if user_id in USER_STATE:
            del USER_STATE[user_id]

async def handle_no_response(query, context, user_id):
    """Handle No responses in various confirmation dialogs."""
    if user_id not in USER_STATE:
        await query.edit_message_text(
            "Operation timed out. Please try again.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    state = USER_STATE[user_id]["state"]
    
    if state == "confirm_remove_account":
        await query.edit_message_text(
            "Account removal cancelled.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Accounts", callback_data=MENU_CALLBACK["LIST_ACCOUNTS"])
            ]])
        )
    
    elif state == "confirm_remove_proxy":
        await query.edit_message_text(
            "Proxy removal cancelled.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Proxies", callback_data=MENU_CALLBACK["LIST_PROXIES"])
            ]])
        )
    
    elif state == "confirm_remove_group":
        await query.edit_message_text(
            "Group removal cancelled.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back to Groups", callback_data=MENU_CALLBACK["LIST_GROUPS"])
            ]])
        )
    
    elif state == "waiting_for_add_cookies":
        # Skip adding cookies, continue with account creation
        email = USER_STATE[user_id].get("email", "")
        password = USER_STATE[user_id].get("password", "")
        
        if email and password:
            db = context.bot_data.get("db")
            account_id = db.add_account(email, password, None)
            
            await query.edit_message_text(
                f"Account {email} added successfully without cookies.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Back to Main Menu", callback_data=MENU_CALLBACK["MAIN_MENU"])
                ]])
            )
        else:
            await query.edit_message_text(
                "Account information incomplete. Please try adding the account again.",
                reply_markup=get_main_menu_keyboard()
            )
    
    # Clear state
    if user_id in USER_STATE:
        del USER_STATE[user_id]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages based on the current state."""
    user_id = update.effective_user.id
    message = update.message.text
    
    if user_id not in USER_STATE:
        # No active state, just show the main menu
        await update.message.reply_text(
            "Please use the menu to interact with the bot:",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    state = USER_STATE[user_id]["state"]
    db = context.bot_data.get("db")
    session_manager = context.bot_data.get("session_manager")
    
    if state == "waiting_for_session":
        # User is sending a session string
        session_string = message.strip()
        
        # Try to load the session
        if session_manager:
            success = await session_manager.load_session(session_string)
            if success:
                # Session loaded successfully
                await update.message.reply_text(
                    "✅ Session loaded successfully! You can now add groups to monitor.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                # Failed to load session
                await update.message.reply_text(
                    "❌ Failed to load the session. Please check that the session string is correct and try again.",
                    reply_markup=get_main_menu_keyboard()
                )
        else:
            await update.message.reply_text(
                "❌ Session manager not initialized. Please try again later.",
                reply_markup=get_main_menu_keyboard()
            )
        
        # Clear state
        del USER_STATE[user_id]
    
    elif state == "waiting_for_email":
        # User is sending an email address
        email = message.strip()
        USER_STATE[user_id] = {"state": "waiting_for_password", "email": email}
        
        await update.message.reply_text(
            f"Email: {email}\nNow, please send the password for this account:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
            ]])
        )
    
    elif state == "waiting_for_password":
        # User is sending a password
        password = message.strip()
        email = USER_STATE[user_id].get("email", "")
        
        if not email:
            await update.message.reply_text(
                "Error: Email address missing. Please try adding the account again.",
                reply_markup=get_main_menu_keyboard()
            )
            del USER_STATE[user_id]
            return
        
        USER_STATE[user_id] = {
            "state": "waiting_for_add_cookies", 
            "email": email, 
            "password": password
        }
        
        # Ask if they want to add cookies
        await update.message.reply_text(
            f"Email: {email}\nPassword: {'*' * len(password)}\n\n"
            "Would you like to add cookies for this account?\n"
            "Cookies can help with login if email/password authentication fails.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes", callback_data=MENU_CALLBACK["YES"]),
                 InlineKeyboardButton("No", callback_data=MENU_CALLBACK["NO"])],
                [InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])]
            ])
        )
    
    elif state == "waiting_for_cookies":
        # User is sending cookies
        cookies = message.strip()
        email = USER_STATE[user_id].get("email", "")
        password = USER_STATE[user_id].get("password", "")
        
        if not email or not password:
            await update.message.reply_text(
                "Error: Account information incomplete. Please try adding the account again.",
                reply_markup=get_main_menu_keyboard()
            )
            del USER_STATE[user_id]
            return
        
        # Add account with cookies
        account_id = db.add_account(email, password, cookies)
        
        await update.message.reply_text(
            f"Account {email} added successfully with cookies.",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Clear state
        del USER_STATE[user_id]
    
    elif state == "waiting_for_proxy":
        # User is sending proxy details
        proxy_info = message.strip().split(":")
        
        if len(proxy_info) < 2:
            await update.message.reply_text(
                "Invalid proxy format. Please use one of the formats:\n"
                "1. IP:PORT\n"
                "2. IP:PORT:USERNAME:PASSWORD\n"
                "3. IP:PORT:USERNAME:PASSWORD:COUNTRY",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
                ]])
            )
            return
        
        try:
            ip = proxy_info[0]
            port = int(proxy_info[1])
            username = proxy_info[2] if len(proxy_info) > 2 else None
            password = proxy_info[3] if len(proxy_info) > 3 else None
            country = proxy_info[4] if len(proxy_info) > 4 else None
            
            # Add proxy to database
            proxy_id = db.add_proxy(ip, port, username, password, country)
            
            await update.message.reply_text(
                f"Proxy {ip}:{port} added successfully.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Clear state
            del USER_STATE[user_id]
        except Exception as e:
            logger.error(f"Error adding proxy: {e}")
            await update.message.reply_text(
                f"Error adding proxy: {str(e)}. Please try again.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
                ]])
            )
    
    elif state == "waiting_for_group_link":
        # User is sending a group/channel link
        group_link = message.strip()
        
        # Process the group link
        if not session_manager or not session_manager.client:
            await update.message.reply_text(
                "Session not loaded or invalid. Please load a valid session first.",
                reply_markup=get_main_menu_keyboard()
            )
            del USER_STATE[user_id]
            return
        
        try:
            # Try to get the group/channel
            if group_link.startswith("@"):
                entity = await session_manager.client.get_entity(group_link)
            elif "t.me/" in group_link:
                username = group_link.split("t.me/")[1].split("/")[0]
                entity = await session_manager.client.get_entity(f"@{username}")
            else:
                entity = await session_manager.client.get_entity(group_link)
            
            # Add the group to database
            group_id = db.add_monitored_group(str(entity.id), getattr(entity, "title", group_link))
            
            await update.message.reply_text(
                f"Group/channel {getattr(entity, 'title', group_link)} added successfully for monitoring.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Start monitoring if not already
            await session_manager.start_monitoring()
            
            # Clear state
            del USER_STATE[user_id]
        except Exception as e:
            logger.error(f"Error adding group: {e}")
            await update.message.reply_text(
                f"Error adding group/channel: {str(e)}. Please check the link/username and try again.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Cancel", callback_data=MENU_CALLBACK["CANCEL"])
                ]])
            )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram-python-bot library."""
    logger.error(f"Exception while handling an update: {context.error}")

async def main() -> None:
    """Start the bot."""
    # Initialize database
    db = BotDatabase()
    
    # Initialize session manager
    session_manager = SessionManager(db)
    
    # Create the Application
    application = Application.builder().token(os.environ.get("BOT_TOKEN", "")).build()
    
    # Store database and session manager in bot_data
    application.bot_data["db"] = db
    application.bot_data["session_manager"] = session_manager
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start the Bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Load the last active session if available
    session_string = db.get_active_session()
    if session_string:
        logger.info("Loading last active session")
        await session_manager.load_session(session_string)
        await session_manager.start_monitoring()
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started")
    
    try:
        await application.updater.stop()
        await application.stop()
    finally:
        # Close the database connection
        db.close()
        
        # Stop the session client
        await session_manager.stop_client()

if __name__ == "__main__":
    asyncio.run(main())