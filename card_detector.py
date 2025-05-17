import re
from typing import Dict, Optional, List, Tuple, Any

class CardDetector:
    """
    Enhanced credit card detection with advanced pattern recognition
    and validation for multiple card formats.
    """
    
    def __init__(self):
        # Basic card pattern - catches various formats with or without spaces
        self.card_patterns = [
            # Specialized pattern for messages with "CC -»" format
            r'(?:CC -»|𝘾𝘾 -»|𝘾𝘾\s*[-:]\s*[»❯>])?\s*(\d{16})\|(\d{2})\|(\d{4})\|(\d{3})',
            
            # Pattern for card numbers with pipes
            r'(\d{16})\|(\d{2})\|(\d{4})\|(\d{3})',
            
            # Pattern for card numbers with spaces/dashes
            r'(?:4[0-9]{3}|5[1-5][0-9]{2}|6(?:011|5[0-9]{2})|3[47][0-9]{2})'
            r'(?:[ -]?[0-9]{4}){3}',
            
            # Pattern for card numbers without spaces
            r'(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9]{2})[0-9]{12}|3[47][0-9]{13})',
            
            # Pattern for card numbers in groups of 4 digits
            r'\b(?:\d{4}[ ]?){4}\b',
            
            # Pattern for card numbers with some obfuscation (X's at the beginning)
            r'(?:X{4}|x{4}|[*]{4})[ -]?(?:[0-9]{4})[ -]?(?:[0-9]{4})[ -]?(?:[0-9]{4})',
            
            # Broader pattern to catch more potential card numbers
            r'\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b',
        ]
        
        # Expiry date patterns
        self.expiry_patterns = [
            # Direct capture from piped format CC|MM|YYYY|CVV
            r'\d{16}\|(\d{2})\|(\d{4})\|\d{3}',
            
            # MM/YY format
            r'\b(0[1-9]|1[0-2])[/\-](2[3-9]|[3-9][0-9])\b',
            
            # MM/YYYY format
            r'\b(0[1-9]|1[0-2])[/\-](20[2-9][0-9])\b',
            
            # MMYY format (no separator)
            r'\b(0[1-9]|1[0-2])(2[3-9]|[3-9][0-9])\b',
            
            # MMYYYY format (no separator)
            r'\b(0[1-9]|1[0-2])(20[2-9][0-9])\b',
            
            # Expiry text markers
            r'(?:exp|Exp|EXP)[:\.\s-]*(0[1-9]|1[0-2])[/\-](2[3-9]|[3-9][0-9])',
            r'(?:exp|Exp|EXP)[:\.\s-]*(0[1-9]|1[0-2])[/\-](20[2-9][0-9])',
            r'(?:expiry|Expiry|EXPIRY|expiration|Expiration)[:\.\s-]*(0[1-9]|1[0-2])[/\-](2[3-9]|[3-9][0-9])',
            
            # Date patterns like "05/25"
            r'\b(0[1-9]|1[0-2])[/](2[3-9]|[3-9][0-9])\b',
        ]
        
        # CVV patterns
        self.cvv_patterns = [
            # Direct capture from piped format CC|MM|YYYY|CVV
            r'\d{16}\|\d{2}\|\d{4}\|(\d{3})',
            
            # Standard CVV
            r'\b([0-9]{3})\b',
            
            # CVV with label
            r'(?:cvv|CVV|cvc|CVC|cv2|CV2)[:\.\s-]*([0-9]{3})\b',
            r'(?:security code|Security Code|security number)[:\.\s-]*([0-9]{3})\b',
            
            # 4-digit CVV (for Amex)
            r'\b([0-9]{4})\b',
            r'(?:cvv|CVV|cvc|CVC|cv2|CV2)[:\.\s-]*([0-9]{4})\b',
        ]
    
    def clean_card_number(self, card_number: str) -> str:
        """Clean the card number by removing spaces, dashes, etc."""
        # Remove non-digit characters
        cleaned = re.sub(r'[^0-9]', '', card_number)
        
        # Validate length (between 13-19 digits for most cards)
        if len(cleaned) < 13 or len(cleaned) > 19:
            return ""
            
        return cleaned
    
    def format_expiry_date(self, expiry: str) -> str:
        """Format expiry date to MM/YY format"""
        # Remove non-digit/non-slash characters
        cleaned = re.sub(r'[^0-9/]', '', expiry)
        
        # If it's just digits, format appropriately
        if re.match(r'^[0-9]+$', cleaned):
            if len(cleaned) == 4:  # MMYY format
                return f"{cleaned[:2]}/{cleaned[2:]}"
            elif len(cleaned) == 6:  # MMYYYY format
                return f"{cleaned[:2]}/{cleaned[2:]}"
        
        # Already has a separator
        if '/' in cleaned:
            parts = cleaned.split('/')
            if len(parts) == 2:
                month, year = parts
                # Ensure month is 2 digits
                if len(month) == 1:
                    month = f"0{month}"
                # Convert 4-digit year to 2-digit
                if len(year) == 4:
                    year = year[2:]
                return f"{month}/{year}"
        
        return cleaned
    
    def is_valid_card(self, card_number: str) -> bool:
        """
        Validate card number using Luhn algorithm and basic checks
        """
        # Must be digits only and have valid length
        if not card_number.isdigit():
            return False
            
        if len(card_number) < 13 or len(card_number) > 19:
            return False
            
        # Luhn algorithm check
        check_sum = 0
        num_digits = len(card_number)
        oddeven = num_digits & 1
        
        for i in range(num_digits):
            digit = int(card_number[i])
            
            if ((i & 1) ^ oddeven) == 0:
                digit = digit * 2
                if digit > 9:
                    digit = digit - 9
                    
            check_sum = check_sum + digit
            
        return (check_sum % 10) == 0
    
    def is_valid_expiry(self, expiry: str) -> bool:
        """Validate expiry date format and check if it's not expired"""
        # Basic format validation
        if '/' in expiry:
            parts = expiry.split('/')
            if len(parts) != 2:
                return False
                
            try:
                month = int(parts[0])
                year = int(parts[1])
                
                # Convert 2-digit year to 4-digit
                if year < 100:
                    year += 2000
                    
                # Basic validity checks
                if month < 1 or month > 12:
                    return False
                    
                # Must be a future date (very basic check)
                if year < 2023:  # Adjust as needed
                    return False
                    
                return True
            except ValueError:
                return False
        return False
    
    def is_valid_cvv(self, cvv: str) -> bool:
        """Validate CVV format"""
        # Must be 3 or 4 digits
        if not cvv.isdigit():
            return False
            
        return len(cvv) in [3, 4]
    
    def check_piped_format(self, text: str) -> Optional[Dict[str, str]]:
        """
        Special handling for the pipe-separated card format: number|mm|yyyy|cvv
        This format is common in card checker outputs
        """
        # Look for the piped format pattern
        pattern = r'(\d{16})\|(\d{2})\|(\d{4})\|(\d{3})'
        match = re.search(pattern, text)
        
        if match:
            card_number = match.group(1)
            month = match.group(2)
            year = match.group(3)
            cvv = match.group(4)
            
            # Validate the card
            if self.is_valid_card(card_number):
                # Format expiry date properly
                expiry_date = f"{month}/{year[2:]}"
                
                return {
                    'card_number': card_number,
                    'expiry_date': expiry_date,
                    'cvv': cvv
                }
        
        return None
    
    def find_potential_cards(self, text: str) -> List[Dict[str, str]]:
        """Find all potential card information in text"""
        potential_cards = []
        
        # First try the specialized piped format detection
        piped_card = self.check_piped_format(text)
        if piped_card:
            potential_cards.append(piped_card)
            return potential_cards
        
        # If no piped format found, continue with regular pattern detection
        # Search for card numbers
        for pattern in self.card_patterns:
            card_matches = re.finditer(pattern, text)
            
            for card_match in card_matches:
                card_number = card_match.group(0)
                cleaned_card = self.clean_card_number(card_number)
                
                if not cleaned_card:
                    continue
                
                # Basic validation - can be disabled for higher recall
                if not self.is_valid_card(cleaned_card):
                    continue
                
                # Search for expiry dates near the card number
                card_index = card_match.start()
                # Expand search window for better chances of finding expiry and CVV
                search_window = 200  # characters
                search_text = text[max(0, card_index - search_window):min(len(text), card_index + search_window)]
                
                # Find expiry date
                expiry_date = None
                for exp_pattern in self.expiry_patterns:
                    exp_matches = re.search(exp_pattern, search_text)
                    if exp_matches:
                        expiry_raw = exp_matches.group(0)
                        # If it's a labeled match, extract just the date part
                        if any(label in expiry_raw.lower() for label in ['exp', 'expiry', 'expiration']):
                            date_part = re.search(r'(0[1-9]|1[0-2])[/\-](2[3-9]|[3-9][0-9]|20[2-9][0-9])', expiry_raw)
                            if date_part:
                                expiry_raw = date_part.group(0)
                        
                        expiry_date = self.format_expiry_date(expiry_raw)
                        if self.is_valid_expiry(expiry_date):
                            break
                
                # If no valid expiry date found, skip this card
                if not expiry_date:
                    continue
                
                # Find CVV - try various patterns
                cvv = None
                
                # First look for labeled CVV patterns which are more reliable
                for cvv_pattern in self.cvv_patterns:
                    if 'cvv' in cvv_pattern.lower() or 'security' in cvv_pattern.lower():
                        cvv_matches = re.search(cvv_pattern, search_text)
                        if cvv_matches:
                            cvv_raw = cvv_matches.group(0)
                            # Extract just the digits
                            cvv_digits = re.findall(r'\d+', cvv_raw)
                            if cvv_digits:
                                cvv_candidate = cvv_digits[-1]  # Take the last group of digits
                                if self.is_valid_cvv(cvv_candidate):
                                    cvv = cvv_candidate
                                    break
                
                # If no labeled CVV found, look for standalone 3-4 digit numbers
                if not cvv:
                    # Look for 3-digit numbers that aren't part of other data
                    cvv_candidates = re.finditer(r'\b([0-9]{3,4})\b', search_text)
                    for cvv_match in cvv_candidates:
                        cvv_candidate = cvv_match.group(0)
                        
                        # Skip if it's part of the card number or expiry
                        if cvv_candidate in cleaned_card or cvv_candidate in expiry_date:
                            continue
                        
                        # Skip if it's at the exact position of the card number (likely part of it)
                        if card_index - 5 <= cvv_match.start() <= card_index + len(card_number) + 5:
                            continue
                        
                        if self.is_valid_cvv(cvv_candidate):
                            cvv = cvv_candidate
                            break
                
                # If we found all required information, add it to the results
                if cleaned_card and expiry_date and cvv:
                    # Check if this card is already in our results
                    is_duplicate = False
                    for existing_card in potential_cards:
                        if existing_card['card_number'] == cleaned_card:
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        potential_cards.append({
                            'card_number': cleaned_card,
                            'expiry_date': expiry_date,
                            'cvv': cvv
                        })
        
        return potential_cards
    
    def detect_credit_card_info(self, text: str) -> Optional[Dict[str, str]]:
        """
        Detect credit card information from text
        Returns dict with card_number, expiry_date, cvv or None if no card found
        """
        potential_cards = self.find_potential_cards(text)
        
        # Return the first valid card found
        if potential_cards:
            return potential_cards[0]
            
        return None
    
    def detect_all_cards(self, text: str) -> List[Dict[str, str]]:
        """
        Detect all credit cards in the text
        Returns list of dicts with card_number, expiry_date, cvv
        """
        return self.find_potential_cards(text)