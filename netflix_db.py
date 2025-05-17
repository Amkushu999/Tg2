import time
import json
import os
import logging
import sqlite3
import csv
from typing import Dict, List, Optional, Any, Union, Tuple, cast

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class NetflixDatabase:
    """Database manager for Netflix automation bot"""
    
    def __init__(self, db_path: str = "netflix_bot.db"):
        """Initialize database connection"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.bin_data = {}
        self.connect()
        self.setup_tables()
        self.load_bin_data("bins_all.csv")
    
    def connect(self):
        """Connect to SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def setup_tables(self):
        """Create necessary tables if they don't exist"""
        if not self.cursor:
            self.connect()
            
        # Create sessions table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            session_string TEXT NOT NULL,
            added_timestamp INTEGER,
            is_active INTEGER DEFAULT 1
        )
        ''')
        
        # Create monitored_groups table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitored_groups (
            id INTEGER PRIMARY KEY,
            group_id TEXT NOT NULL,
            group_title TEXT,
            is_active INTEGER DEFAULT 1,
            added_timestamp INTEGER,
            cards_found INTEGER DEFAULT 0
        )
        ''')
        
        # Create accounts table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            cookies TEXT,
            status TEXT DEFAULT 'pending',
            added_timestamp INTEGER,
            last_attempt_timestamp INTEGER,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            position_in_queue INTEGER,
            successfully_billed INTEGER DEFAULT 0,
            validated INTEGER DEFAULT 0
        )
        ''')
        
        # Create proxies table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY,
            ip_address TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT,
            password TEXT,
            country TEXT,
            status TEXT DEFAULT 'active',
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            last_used_timestamp INTEGER
        )
        ''')
        
        # Create credit_cards table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS credit_cards (
            id INTEGER PRIMARY KEY,
            card_number TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            cvv TEXT NOT NULL,
            country TEXT,
            bin TEXT,
            first_detected_timestamp INTEGER,
            status TEXT DEFAULT 'unused',
            used_with_account_id INTEGER,
            detected_in_group_id INTEGER,
            failure_reason TEXT
        )
        ''')
        
        # Create statistics table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY,
            timestamp INTEGER,
            action_type TEXT,
            success INTEGER,
            proxy_id INTEGER,
            account_id INTEGER,
            card_id INTEGER,
            processing_time INTEGER,
            error_message TEXT
        )
        ''')
        
        self.conn.commit()
    
    def load_bin_data(self, bin_file_path: str):
        """Load BIN data from CSV file"""
        try:
            if os.path.exists(bin_file_path):
                with open(bin_file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if 'number' in row:
                            bin_number = row['number']
                            self.bin_data[bin_number] = {
                                'country': row.get('country', ''),
                                'flag': row.get('flag', ''),
                                'vendor': row.get('vendor', ''),
                                'type': row.get('type', ''),
                                'level': row.get('level', ''),
                                'bank': row.get('bank_name', '')
                            }
                logger.info(f"Loaded {len(self.bin_data)} BIN entries")
            else:
                logger.warning(f"BIN list file not found: {bin_file_path}")
        except Exception as e:
            logger.error(f"Error loading BIN data: {e}")
    
    def get_card_country(self, card_number: str) -> str:
        """Get country code for a card based on BIN"""
        if not card_number or len(card_number) < 6:
            return "US"  # Default to US for invalid cards
            
        # Extract first 6 digits (BIN)
        bin_number = card_number[:6].strip()
        
        # Look up in BIN database
        if bin_number in self.bin_data:
            return self.bin_data[bin_number].get('country', 'US')
        
        # Try with 8 digits if 6 not found
        if len(card_number) >= 8:
            bin_number = card_number[:8].strip()
            if bin_number in self.bin_data:
                return self.bin_data[bin_number].get('country', 'US')
            
        return "US"  # Default to US if not found
    
    # Session methods
    def save_session(self, session_string: str) -> int:
        """Save a new Telegram session string"""
        if not self.cursor or not self.conn:
            self.connect()
            
        # Check if session already exists
        self.cursor.execute('''
        SELECT id FROM sessions WHERE session_string = ?
        ''', (session_string,))
        
        existing = self.cursor.fetchone()
        if existing:
            # Update existing session to active
            self.cursor.execute('''
            UPDATE sessions SET is_active = 1
            WHERE id = ?
            ''', (existing[0],))
            self.conn.commit()
            return existing[0]
        
        # Add new session
        self.cursor.execute('''
        INSERT INTO sessions (session_string, added_timestamp, is_active)
        VALUES (?, ?, 1)
        ''', (session_string, int(time.time())))
        
        self.conn.commit()
        return self.cursor.lastrowid or 0
    
    def get_active_session(self) -> Optional[str]:
        """Get the active session string"""
        if not self.cursor:
            self.connect()
            
        self.cursor.execute('''
        SELECT session_string FROM sessions WHERE is_active = 1
        ORDER BY added_timestamp DESC LIMIT 1
        ''')
        
        result = self.cursor.fetchone()
        if result:
            return result[0]
        return None
    
    def deactivate_session(self, session_id: int) -> bool:
        """Deactivate a session"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        UPDATE sessions SET is_active = 0
        WHERE id = ?
        ''', (session_id,))
        
        self.conn.commit()
        return True
    
    # Group management methods
    def add_monitored_group(self, group_id: str, group_title: str) -> int:
        """Add a group to monitor"""
        if not self.cursor or not self.conn:
            self.connect()
            
        # Check if group already exists
        self.cursor.execute('''
        SELECT id FROM monitored_groups WHERE group_id = ?
        ''', (group_id,))
        
        existing = self.cursor.fetchone()
        if existing:
            # Update existing group
            self.cursor.execute('''
            UPDATE monitored_groups 
            SET group_title = ?, is_active = 1
            WHERE id = ?
            ''', (group_title, existing[0]))
            self.conn.commit()
            return existing[0]
        
        # Add new group
        self.cursor.execute('''
        INSERT INTO monitored_groups (group_id, group_title, added_timestamp, is_active)
        VALUES (?, ?, ?, 1)
        ''', (group_id, group_title, int(time.time())))
        
        self.conn.commit()
        return self.cursor.lastrowid or 0
    
    def get_monitored_groups(self) -> List[Dict[str, Any]]:
        """Get all monitored groups"""
        if not self.cursor:
            self.connect()
            
        self.cursor.execute('''
        SELECT id, group_id, group_title, is_active, cards_found 
        FROM monitored_groups
        ORDER BY added_timestamp DESC
        ''')
        
        groups = []
        for row in self.cursor.fetchall():
            groups.append({
                'id': row[0],
                'group_id': row[1],
                'group_title': row[2],
                'is_active': bool(row[3]),
                'cards_found': row[4]
            })
        
        return groups
    
    def remove_monitored_group(self, group_id: int) -> bool:
        """Remove a group from monitoring"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        DELETE FROM monitored_groups WHERE id = ?
        ''', (group_id,))
        
        self.conn.commit()
        return True
    
    def toggle_group_status(self, group_id: int, is_active: bool) -> bool:
        """Toggle a group's active status"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        UPDATE monitored_groups SET is_active = ?
        WHERE id = ?
        ''', (1 if is_active else 0, group_id))
        
        self.conn.commit()
        return True
    
    def increment_group_card_counter(self, group_id: str) -> bool:
        """Increment the cards found counter for a group"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        UPDATE monitored_groups 
        SET cards_found = cards_found + 1
        WHERE group_id = ?
        ''', (group_id,))
        
        self.conn.commit()
        return True
    
    # Account management methods
    def add_account(self, email: str, password: str, cookies: Optional[str] = None, 
                   validated: bool = False) -> int:
        """Add a new Netflix account to the queue"""
        if not self.cursor or not self.conn:
            self.connect()
            
        # Check if account already exists
        self.cursor.execute('''
        SELECT id FROM accounts WHERE email = ?
        ''', (email,))
        
        existing = self.cursor.fetchone()
        if existing:
            # Update existing account
            query = '''
            UPDATE accounts 
            SET password = ?, status = 'pending', retry_count = 0
            '''
            params = [password]
            
            if cookies is not None:
                query += ", cookies = ?"
                params.append(cookies)
            
            query += ", validated = ?"
            params.append(1 if validated else 0)
            
            query += " WHERE id = ?"
            params.append(existing[0])
            
            self.cursor.execute(query, params)
            self.conn.commit()
            return existing[0]
        
        # Add new account
        timestamp = int(time.time())
        
        # Get current queue size for position
        self.cursor.execute('''
        SELECT COUNT(*) FROM accounts WHERE status = 'pending'
        ''')
        queue_size_row = self.cursor.fetchone()
        queue_size = queue_size_row[0] if queue_size_row else 0
        
        self.cursor.execute('''
        INSERT INTO accounts (
            email, password, cookies, status, 
            added_timestamp, position_in_queue, validated
        )
        VALUES (?, ?, ?, 'pending', ?, ?, ?)
        ''', (email, password, cookies, timestamp, queue_size + 1, 1 if validated else 0))
        
        self.conn.commit()
        return self.cursor.lastrowid or 0
    
    def get_next_pending_account(self) -> Optional[Dict[str, Any]]:
        """Get the next account to process"""
        if not self.cursor:
            self.connect()
            
        self.cursor.execute('''
        SELECT id, email, password, cookies, retry_count
        FROM accounts
        WHERE status = 'pending'
        ORDER BY position_in_queue ASC
        LIMIT 1
        ''')
        
        account = self.cursor.fetchone()
        if not account:
            return None
            
        return {
            'id': account[0],
            'email': account[1],
            'password': account[2],
            'cookies': account[3],
            'retry_count': account[4]
        }
    
    def update_account_status(self, account_id: int, status: str, error: Optional[str] = None) -> bool:
        """Update an account's status"""
        if not self.cursor or not self.conn:
            self.connect()
            
        timestamp = int(time.time())
        
        query = '''
        UPDATE accounts 
        SET status = ?, last_attempt_timestamp = ?
        '''
        params = [status, timestamp]
        
        if error:
            query += ", last_error = ?"
            params.append(error)
            
        if status == 'processing':
            query += ", retry_count = retry_count + 1"
            
        query += " WHERE id = ?"
        params.append(account_id)
        
        self.cursor.execute(query, params)
        self.conn.commit()
        return True
    
    def mark_account_success(self, account_id: int, card_id: int) -> bool:
        """Mark an account as successfully billed"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        UPDATE accounts
        SET status = 'completed', successfully_billed = 1, last_attempt_timestamp = ?
        WHERE id = ?
        ''', (int(time.time()), account_id))
        
        self.cursor.execute('''
        UPDATE credit_cards
        SET status = 'used', used_with_account_id = ?
        WHERE id = ?
        ''', (account_id, card_id))
        
        self.conn.commit()
        return True
    
    def get_accounts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all accounts, optionally filtered by status"""
        if not self.cursor:
            self.connect()
            
        query = '''
        SELECT id, email, status, retry_count, successfully_billed, validated
        FROM accounts
        '''
        
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
            
        query += " ORDER BY position_in_queue ASC"
        
        self.cursor.execute(query, params)
        
        accounts = []
        for row in self.cursor.fetchall():
            accounts.append({
                'id': row[0],
                'email': row[1],
                'status': row[2],
                'retry_count': row[3],
                'successfully_billed': bool(row[4]),
                'validated': bool(row[5])
            })
        
        return accounts
    
    def remove_account(self, account_id: int) -> bool:
        """Remove an account from the database"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        DELETE FROM accounts WHERE id = ?
        ''', (account_id,))
        
        self.conn.commit()
        return True
    
    # Proxy management methods
    def add_proxy(self, ip: str, port: int, username: Optional[str] = None, 
                 password: Optional[str] = None, country: Optional[str] = None) -> int:
        """Add a proxy to the database"""
        if not self.cursor or not self.conn:
            self.connect()
            
        # Check if proxy already exists
        self.cursor.execute('''
        SELECT id FROM proxies
        WHERE ip_address = ? AND port = ?
        ''', (ip, port))
        
        existing = self.cursor.fetchone()
        if existing:
            # Update existing proxy
            query = '''
            UPDATE proxies
            SET status = 'active'
            '''
            params = []
            
            if username is not None:
                query += ", username = ?"
                params.append(username)
                
            if password is not None:
                query += ", password = ?"
                params.append(password)
                
            if country is not None:
                query += ", country = ?"
                params.append(country)
                
            query += " WHERE id = ?"
            params.append(existing[0])
            
            self.cursor.execute(query, params)
            self.conn.commit()
            return existing[0]
        
        # Add new proxy
        self.cursor.execute('''
        INSERT INTO proxies (
            ip_address, port, username, password, country, 
            last_used_timestamp, status
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active')
        ''', (ip, port, username, password, country, int(time.time())))
        
        self.conn.commit()
        return self.cursor.lastrowid or 0
    
    def get_proxy_by_country(self, country: str) -> Optional[Dict[str, Any]]:
        """Get a proxy for a specific country"""
        if not self.cursor:
            self.connect()
            
        # First try active proxies from the specific country
        self.cursor.execute('''
        SELECT id, ip_address, port, username, password, country
        FROM proxies
        WHERE country = ? AND status = 'active'
        ORDER BY 
            CASE 
                WHEN success_count = 0 AND failure_count = 0 THEN 1 
                ELSE success_count * 1.0 / (success_count + failure_count) 
            END DESC,
            last_used_timestamp ASC
        LIMIT 1
        ''', (country,))
        
        proxy = self.cursor.fetchone()
        
        # If no proxy found for the country, get any active proxy
        if not proxy:
            return self.get_next_proxy()
            
        return {
            'id': proxy[0],
            'ip': proxy[1],
            'port': proxy[2],
            'username': proxy[3],
            'password': proxy[4],
            'country': proxy[5]
        }
    
    def get_next_proxy(self) -> Optional[Dict[str, Any]]:
        """Get the next available proxy"""
        if not self.cursor:
            self.connect()
            
        self.cursor.execute('''
        SELECT id, ip_address, port, username, password, country
        FROM proxies
        WHERE status = 'active'
        ORDER BY 
            CASE 
                WHEN success_count = 0 AND failure_count = 0 THEN 1 
                ELSE success_count * 1.0 / (success_count + failure_count) 
            END DESC,
            last_used_timestamp ASC
        LIMIT 1
        ''')
        
        proxy = self.cursor.fetchone()
        if not proxy:
            return None
            
        # Update last used timestamp
        self.cursor.execute('''
        UPDATE proxies
        SET last_used_timestamp = ?
        WHERE id = ?
        ''', (int(time.time()), proxy[0]))
        
        self.conn.commit()
            
        return {
            'id': proxy[0],
            'ip': proxy[1],
            'port': proxy[2],
            'username': proxy[3],
            'password': proxy[4],
            'country': proxy[5]
        }
    
    def update_proxy_status(self, proxy_id: int, status: str, success: Optional[bool] = None) -> bool:
        """Update proxy status and success/failure count"""
        if not self.cursor or not self.conn:
            self.connect()
            
        query = "UPDATE proxies SET status = ?"
        params = [status]
        
        if success is not None:
            if success:
                query += ", success_count = success_count + 1"
            else:
                query += ", failure_count = failure_count + 1"
                
        query += " WHERE id = ?"
        params.append(proxy_id)
        
        self.cursor.execute(query, params)
        self.conn.commit()
        return True
    
    def get_proxies(self) -> List[Dict[str, Any]]:
        """Get all proxies"""
        if not self.cursor:
            self.connect()
            
        self.cursor.execute('''
        SELECT id, ip_address, port, username, password, country, 
               status, success_count, failure_count
        FROM proxies
        ORDER BY 
            CASE 
                WHEN success_count = 0 AND failure_count = 0 THEN 1 
                ELSE success_count * 1.0 / (success_count + failure_count) 
            END DESC
        ''')
        
        proxies = []
        for row in self.cursor.fetchall():
            success = row[7] or 0
            failure = row[8] or 0
            success_rate = (success / (success + failure)) * 100 if (success + failure) > 0 else 0
            
            proxies.append({
                'id': row[0],
                'ip': row[1],
                'port': row[2],
                'username': row[3],
                'password': row[4],
                'country': row[5],
                'status': row[6],
                'success_count': success,
                'failure_count': failure,
                'success_rate': success_rate
            })
        
        return proxies
    
    def remove_proxy(self, proxy_id: int) -> bool:
        """Remove a proxy from the database"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        DELETE FROM proxies WHERE id = ?
        ''', (proxy_id,))
        
        self.conn.commit()
        return True
    
    # Credit card methods
    def add_credit_card(self, card_number: str, expiry_date: str, cvv: str, 
                         detected_in_group_id: Optional[str] = None) -> int:
        """Add a credit card to the database"""
        if not self.cursor or not self.conn:
            self.connect()
            
        # Remove spaces and clean card number
        card_number = card_number.replace(' ', '').strip()
        bin_number = card_number[:6]
        
        # Determine country based on BIN
        country = self.get_card_country(card_number)
        
        # Check if card already exists
        self.cursor.execute('''
        SELECT id FROM credit_cards
        WHERE card_number = ? AND status = 'unused'
        ''', (card_number,))
        
        existing = self.cursor.fetchone()
        if existing:
            return existing[0]
        
        # Add new card
        self.cursor.execute('''
        INSERT INTO credit_cards (
            card_number, expiry_date, cvv, country, bin,
            first_detected_timestamp, status, detected_in_group_id
        )
        VALUES (?, ?, ?, ?, ?, ?, 'unused', ?)
        ''', (card_number, expiry_date, cvv, country, bin_number, 
              int(time.time()), detected_in_group_id))
        
        self.conn.commit()
        
        # Update group card counter if group ID is provided
        if detected_in_group_id:
            self.increment_group_card_counter(detected_in_group_id)
            
        return self.cursor.lastrowid or 0
    
    def get_latest_unused_card(self) -> Optional[Dict[str, Any]]:
        """Get the most recently added unused credit card"""
        if not self.cursor:
            self.connect()
            
        self.cursor.execute('''
        SELECT id, card_number, expiry_date, cvv, country, bin
        FROM credit_cards
        WHERE status = 'unused'
        ORDER BY first_detected_timestamp DESC
        LIMIT 1
        ''')
        
        card = self.cursor.fetchone()
        if not card:
            return None
            
        return {
            'id': card[0],
            'card_number': card[1],
            'expiry_date': card[2],
            'cvv': card[3],
            'country': card[4],
            'bin': card[5]
        }
    
    def mark_card_failed(self, card_id: int, reason: str) -> bool:
        """Mark a card as failed with a reason"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        UPDATE credit_cards
        SET status = 'failed', failure_reason = ?
        WHERE id = ?
        ''', (reason, card_id))
        
        self.conn.commit()
        return True
    
    def get_cards(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all cards, optionally filtered by status"""
        if not self.cursor:
            self.connect()
            
        query = '''
        SELECT id, card_number, expiry_date, cvv, country, bin, 
               status, used_with_account_id, failure_reason
        FROM credit_cards
        '''
        
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
            
        query += " ORDER BY first_detected_timestamp DESC"
        
        self.cursor.execute(query, params)
        
        cards = []
        for row in self.cursor.fetchall():
            # Mask card number for security
            masked_number = f"{'*' * 12}{row[1][-4:]}" if row[1] else ''
            
            cards.append({
                'id': row[0],
                'card_number': masked_number,
                'expiry_date': row[2],
                'cvv': '***',  # Mask CVV for security
                'country': row[4],
                'bin': row[5],
                'status': row[6],
                'used_with_account_id': row[7],
                'failure_reason': row[8]
            })
        
        return cards
    
    # Statistics methods
    def add_statistic(self, action_type: str, success: bool, 
                      proxy_id: Optional[int] = None, account_id: Optional[int] = None,
                      card_id: Optional[int] = None, processing_time: Optional[int] = None,
                      error_message: Optional[str] = None) -> bool:
        """Add a statistic entry"""
        if not self.cursor or not self.conn:
            self.connect()
            
        self.cursor.execute('''
        INSERT INTO statistics (
            timestamp, action_type, success, proxy_id, account_id, 
            card_id, processing_time, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (int(time.time()), action_type, 1 if success else 0, proxy_id, 
              account_id, card_id, processing_time, error_message))
        
        self.conn.commit()
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics summary"""
        if not self.cursor:
            self.connect()
            
        stats = {
            'accounts': {
                'total': 0,
                'completed': 0,
                'pending': 0,
                'failed': 0
            },
            'cards': {
                'total': 0,
                'used': 0,
                'unused': 0,
                'failed': 0
            },
            'proxies': {
                'total': 0,
                'active': 0,
                'success_rate': 0
            },
            'success_rate': 0,
            'average_processing_time': 0
        }
        
        # Account statistics
        self.cursor.execute('''
        SELECT COUNT(*), 
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
        FROM accounts
        ''')
        
        result = self.cursor.fetchone()
        if result and result[0]:
            stats['accounts']['total'] = result[0] or 0
            stats['accounts']['completed'] = result[1] or 0
            stats['accounts']['pending'] = result[2] or 0
            stats['accounts']['failed'] = result[3] or 0
        
        # Card statistics
        self.cursor.execute('''
        SELECT COUNT(*), 
               SUM(CASE WHEN status = 'used' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'unused' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
        FROM credit_cards
        ''')
        
        result = self.cursor.fetchone()
        if result and result[0]:
            stats['cards']['total'] = result[0] or 0
            stats['cards']['used'] = result[1] or 0
            stats['cards']['unused'] = result[2] or 0
            stats['cards']['failed'] = result[3] or 0
        
        # Proxy statistics
        self.cursor.execute('''
        SELECT COUNT(*), 
               SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END),
               SUM(success_count),
               SUM(failure_count)
        FROM proxies
        ''')
        
        result = self.cursor.fetchone()
        if result and result[0]:
            stats['proxies']['total'] = result[0] or 0
            stats['proxies']['active'] = result[1] or 0
            
            success_count = result[2] or 0
            failure_count = result[3] or 0
            
            if success_count + failure_count > 0:
                stats['proxies']['success_rate'] = (success_count / (success_count + failure_count)) * 100
        
        # Overall success rate
        self.cursor.execute('''
        SELECT AVG(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 100,
               AVG(processing_time)
        FROM statistics
        WHERE action_type = 'billing'
        ''')
        
        result = self.cursor.fetchone()
        if result and result[0] is not None:
            stats['success_rate'] = result[0] or 0
            stats['average_processing_time'] = result[1] or 0
        
        return stats
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.cursor = None
            self.conn = None
            logger.info("Database connection closed")