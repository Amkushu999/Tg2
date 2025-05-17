from telethon import TelegramClient, events
import re
from telethon.sessions import StringSession
import asyncio
import logging
from modules.database import BotDatabase
from modules.card_detector import detect_credit_card_info
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING, GROUP_IDS

class TelegramHandler:
    def __init__(self, database: BotDatabase):
        self.db = database
        self.client = None
        self.new_card_event = asyncio.Event()
    
    async def start_client(self):
        """Start Telegram client with session string"""
        self.client = TelegramClient(
            StringSession(TELEGRAM_SESSION_STRING),
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )
        
        await self.client.start()
        logging.info("Telegram client started successfully")
        
        # Register message handler
        @self.client.on(events.NewMessage(chats=GROUP_IDS))
        async def handle_new_message(event):
            await self.process_message(event)
    
    async def process_message(self, event):
        """Process new messages to detect credit card information"""
        if event.message and event.message.text:
            message_text = event.message.text
            card_info = detect_credit_card_info(message_text)
            
            if card_info:
                logging.info("Credit card detected in message")
                
                # Add card to database
                card_id = self.db.add_credit_card(
                    card_info['card_number'],
                    card_info['expiry_date'],
                    card_info['cvv']
                )
                
                # Notify waiting processes that a new card is available
                self.new_card_event.set()
                self.new_card_event.clear()
                
                # Possibly send confirmation message privately
                # await self.client.send_message(event.sender_id, "Card detected and processing started")
    
    async def wait_for_new_card(self):
        """Wait for a new card to be detected"""
        await self.new_card_event.wait()
    
    async def send_status_update(self, user_id, message):
        """Send status update to a specific user"""
        await self.client.send_message(user_id, message)
    
    async def stop_client(self):
        """Disconnect the client"""
        if self.client:
            await self.client.disconnect()
