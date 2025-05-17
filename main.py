import asyncio
import logging
import time
import os
import argparse
from typing import Dict, List, Optional

from modules.database import BotDatabase
from modules.telegram_client import TelegramHandler
from modules.netflix_automation import NetflixAutomation
from modules.proxy_manager import ProxyManager
from config import MAX_RETRIES, ADMIN_USER_ID

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Global variables
db = None
telegram_handler = None
proxy_manager = None
processing_lock = asyncio.Lock()  # Ensure only one account is processed at a time

async def process_account(account: Dict):
    """Process a single Netflix account"""
    global db, telegram_handler, proxy_manager
    
    # Lock to ensure only one account is processed at a time
    async with processing_lock:
        logging.info(f"Processing account: {account['email']}")
        
        # Update account status to processing
        db.update_account_status(account['id'], 'processing')
        
        # Send status update
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, 
            f"🔄 Processing account: {account['email']}\nAttempt #{account['retry_count'] + 1}"
        )
        
        # Get the latest credit card
        card = db.get_latest_unused_card()
        if not card:
            await telegram_handler.send_status_update(
                ADMIN_USER_ID,
                "⚠️ No credit card available. Waiting for a card to be posted..."
            )
            
            # Wait for a new card
            await telegram_handler.wait_for_new_card()
            
            # Get the new card
            card = db.get_latest_unused_card()
            if not card:
                # This should not happen but just in case
                db.update_account_status(account['id'], 'pending', "No credit card available")
                return
        
        # Get a proxy
        proxy = proxy_manager.get_next_proxy()
        
        # Setup Netflix automation
        netflix = NetflixAutomation(proxy_manager.format_proxy_for_selenium() if proxy else None)
        
        try:
            # Try to authenticate
            auth_success = False
            auth_error = ""
            
            # Try cookie-based auth first
            if account['cookies']:
                await telegram_handler.send_status_update(
                    ADMIN_USER_ID, "🔑 Attempting login with cookies..."
                )
                cookie_success = netflix.load_cookies(account['cookies'])
                
                if cookie_success:
                    # Navigate to Netflix to check if cookies worked
                    netflix.driver.get("https://www.netflix.com")
                    time.sleep(5)
                    
                    # Check current page
                    current_page = netflix.detect_current_page()
                    if current_page != "login":
                        auth_success = True
                        await telegram_handler.send_status_update(
                            ADMIN_USER_ID, "✅ Login with cookies successful"
                        )
            
            # Fall back to credentials if cookies failed
            if not auth_success:
                await telegram_handler.send_status_update(
                    ADMIN_USER_ID, "🔑 Attempting login with credentials..."
                )
                auth_success, auth_error = netflix.login_with_credentials(
                    account['email'], account['password']
                )
                
                if auth_success:
                    await telegram_handler.send_status_update(
                        ADMIN_USER_ID, "✅ Login with credentials successful"
                    )
                else:
                    await telegram_handler.send_status_update(
                        ADMIN_USER_ID, f"❌ Login failed: {auth_error}"
                    )
            
            # If authentication failed, mark account as failed
            if not auth_success:
                db.update_account_status(account['id'], 'failed', auth_error)
                netflix.close()
                return
            
            # Save cookies for future use
            new_cookies = netflix.get_cookies()
            if new_cookies:
                # Update account with new cookies
                db.cursor.execute(
                    "UPDATE accounts SET cookies = ? WHERE id = ?",
                    (new_cookies, account['id'])
                )
                db.conn.commit()
            
            # Process the Netflix flow
            flow_success = await process_netflix_flow(netflix, card)
            
            # If flow successful, mark account and card as successful
            if flow_success:
                db.mark_account_success(account['id'], card['id'])
                if proxy:
                    proxy_manager.mark_proxy_success()
                
                await telegram_handler.send_status_update(
                    ADMIN_USER_ID,
                    f"✅ Account {account['email']} successfully billed with card ending in {card['card_number'][-4:]}"
                )
            else:
                # Failed - put account back in queue if under max retries
                if account['retry_count'] < MAX_RETRIES:
                    db.update_account_status(account['id'], 'pending', "Payment failed, will retry")
                    if proxy:
                        proxy_manager.mark_proxy_failure()
                        
                    await telegram_handler.send_status_update(
                        ADMIN_USER_ID,
                        f"⚠️ Payment failed for {account['email']}. Will retry with different proxy. Current retry: {account['retry_count']}/{MAX_RETRIES}"
                    )
                else:
                    # Max retries reached
                    db.update_account_status(account['id'], 'failed', "Max retry attempts reached")
                    
                    await telegram_handler.send_status_update(
                        ADMIN_USER_ID,
                        f"❌ Payment failed for {account['email']} after {MAX_RETRIES} attempts. Account moved to failed status."
                    )
        except Exception as e:
            logging.error(f"Error processing account {account['email']}: {str(e)}")
            db.update_account_status(account['id'], 'failed', str(e))
            
            await telegram_handler.send_status_update(
                ADMIN_USER_ID,
                f"❌ Error processing account {account['email']}: {str(e)}"
            )
        finally:
            # Always close the browser
            netflix.close()

async def process_netflix_flow(netflix: NetflixAutomation, card: Dict) -> bool:
    """Process the Netflix signup flow"""
    global telegram_handler
    
    # Check current page
    current_page = netflix.detect_current_page()
    await telegram_handler.send_status_update(
        ADMIN_USER_ID, f"📍 Current page: {current_page}"
    )
    
    # Handle each page in the flow
    if current_page == "finish_signup":
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, "🔄 Clicking 'Finish Sign-Up' button..."
        )
        success, message = netflix.handle_finish_signup()
        if not success:
            await telegram_handler.send_status_update(
                ADMIN_USER_ID, f"❌ Finish Sign-Up failed: {message}"
            )
            return False
        # Wait for next page to load
        time.sleep(3)
        current_page = netflix.detect_current_page()
    
    # Handle plan selection
    if current_page == "plan_selection":
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, "🔄 Selecting subscription plan..."
        )
        success, message = netflix.handle_plan_selection()
        if not success:
            await telegram_handler.send_status_update(
                ADMIN_USER_ID, f"❌ Plan selection failed: {message}"
            )
            return False
        # Wait for next page to load
        time.sleep(3)
        current_page = netflix.detect_current_page()
    
    # Handle payment method selection
    if current_page == "payment_method":
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, "🔄 Selecting credit card payment method..."
        )
        success, message = netflix.handle_payment_method()
        if not success:
            await telegram_handler.send_status_update(
                ADMIN_USER_ID, f"❌ Payment method selection failed: {message}"
            )
            return False
        # Wait for next page to load
        time.sleep(3)
        current_page = netflix.detect_current_page()
    
    # Handle credit card form
    if current_page == "credit_card_form":
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, f"🔄 Filling credit card form with card ending in {card['card_number'][-4:]}..."
        )
        success, message = netflix.handle_credit_card_form(card)
        if not success:
            await telegram_handler.send_status_update(
                ADMIN_USER_ID, f"❌ Credit card form failed: {message}"
            )
            return False
        # Wait for next page to load
        time.sleep(5)
    
    # Check for payment success
    await telegram_handler.send_status_update(
        ADMIN_USER_ID, "🔄 Checking payment status..."
    )
    success, message = netflix.check_payment_success()
    
    # Take a screenshot for verification
    screenshot_path = f"screenshots/payment_{int(time.time())}.png"
    os.makedirs("screenshots", exist_ok=True)
    netflix.take_screenshot(screenshot_path)
    
    if success:
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, f"✅ {message}"
        )
        return True
    else:
        await telegram_handler.send_status_update(
            ADMIN_USER_ID, f"❌ {message}"
        )
        return False

async def main_loop():
    """Main processing loop for the bot"""
    global db, telegram_handler
    
    while True:
        try:
            # Get next pending account
            account = db.get_next_pending_account()
            
            if account:
                # Process the account
                await process_account(account)
            else:
                # No pending accounts, wait a bit
                logging.info("No pending accounts, waiting...")
                await asyncio.sleep(30)
        except Exception as e:
            logging.error(f"Error in main loop: {str(e)}")
            await asyncio.sleep(30)

async def main():
    """Main entry point"""
    global db, telegram_handler, proxy_manager
    
    parser = argparse.ArgumentParser(description='Netflix Payment Bot')
    parser.add_argument('--add-account', nargs=2, metavar=('EMAIL', 'PASSWORD'), help='Add a Netflix account')
    parser.add_argument('--add-proxy', action='append', metavar='IP:PORT', help='Add a proxy')
    args = parser.parse_args()
    
    # Initialize database
    db = BotDatabase()
    
    # Initialize proxy manager
    proxy_manager = ProxyManager(db)
    
    # Add account if specified
    if args.add_account:
        email, password = args.add_account
        account_id = db.add_account(email, password)
        print(f"Added account {email} with ID {account_id}")
    
    # Add proxies if specified
    if args.add_proxy:
        for proxy in args.add_proxy:
            ip, port = proxy.split(':')
            proxy_id = db.add_proxy(ip, int(port))
            print(f"Added proxy {proxy} with ID {proxy_id}")
    
    # Initialize Telegram handler
    telegram_handler = TelegramHandler(db)
    await telegram_handler.start_client()
    
    # Start main processing loop
    await main_loop()

if __name__ == "__main__":
    # Run the main function
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    finally:
        # Close database connection
        if db:
            db.close()