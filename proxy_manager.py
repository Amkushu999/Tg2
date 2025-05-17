from modules.database import BotDatabase
from typing import Dict, Optional, List
import logging

class ProxyManager:
    def __init__(self, database: BotDatabase):
        self.db = database
        self.current_proxy = None
    
    def get_next_proxy(self) -> Optional[Dict]:
        """Get the next available proxy from the database"""
        proxy = self.db.get_next_proxy()
        self.current_proxy = proxy
        return proxy
    
    def mark_proxy_success(self):
        """Mark the current proxy as successful"""
        if self.current_proxy:
            self.db.update_proxy_status(
                self.current_proxy['id'],
                'active',  # Set back to active so it can be used again
                True       # Success = True
            )
    
    def mark_proxy_failure(self):
        """Mark the current proxy as failed"""
        if self.current_proxy:
            self.db.update_proxy_status(
                self.current_proxy['id'],
                'active',  # Set back to active so it can be used again
                False      # Success = False
            )
    
    def format_proxy_for_selenium(self) -> Dict:
        """Format the current proxy for use with Selenium WebDriver"""
        if not self.current_proxy:
            return None
            
        proxy_dict = {
            'ip': self.current_proxy['ip'],
            'port': self.current_proxy['port'],
            'username': self.current_proxy.get('username'),
            'password': self.current_proxy.get('password')
        }
        
        return proxy_dict
    
    def bulk_add_proxies(self, proxies_list: List[str]):
        """
        Add multiple proxies from a list of strings
        Format: "ip:port" or "ip:port:username:password"
        """
        for proxy_str in proxies_list:
            parts = proxy_str.split(':')
            
            if len(parts) >= 2:
                ip = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    logging.warning(f"Invalid port in proxy: {proxy_str}")
                    continue
                    
                username = parts[2] if len(parts) > 2 else None
                password = parts[3] if len(parts) > 3 else None
                
                self.db.add_proxy(ip, port, username, password)
            else:
                logging.warning(f"Invalid proxy format: {proxy_str}")
