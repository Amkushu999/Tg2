import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import logging
import time
import random
import json
import os
from typing import Dict, Optional, Any, Tuple, List, Union

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class NetflixAutomation:
    """Enhanced Netflix signup automation with human-like behavior patterns"""
    
    def __init__(self, proxy: Optional[Dict[str, str]] = None):
        """Initialize Netflix automation with optional proxy"""
        self.driver = None
        self.proxy = proxy
        self.last_page = None
        self.retry_count = 0
        self.max_retries = 3
        
        # Base URLs
        self.netflix_url = "https://www.netflix.com"
        self.login_url = "https://www.netflix.com/login"
        self.signup_url = "https://www.netflix.com/signup"
    
    def setup_driver(self) -> None:
        """Initialize and configure the Chrome WebDriver with advanced anti-detection"""
        try:
            options = uc.ChromeOptions()
            
            # Random window size for fingerprint diversity
            width = random.randint(1200, 1600)
            height = random.randint(800, 1000)
            options.add_argument(f"--window-size={width},{height}")
            
            # Disable automation flags
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # Add random user agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
            selected_ua = random.choice(user_agents)
            options.add_argument(f"--user-agent={selected_ua}")
            
            # Disable features that might reveal automation
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            
            # Add proxy if provided
            if self.proxy:
                if 'http' in self.proxy:
                    proxy_str = self.proxy['http'].replace('http://', '')
                    options.add_argument(f'--proxy-server={proxy_str}')
                    logger.info(f"Using proxy: {proxy_str}")
            
            # Create the WebDriver
            self.driver = uc.Chrome(options=options)
            
            # Set page load timeout
            self.driver.set_page_load_timeout(60)
            
            # Additional anti-detection measures
            self._execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en', 'de']
                });
                """
            })
            
            logger.info("WebDriver setup complete")
            return True
        except Exception as e:
            logger.error(f"Error setting up WebDriver: {e}")
            return False
    
    def _execute_cdp_cmd(self, cmd: str, params: Dict[str, Any]) -> None:
        """Execute Chrome DevTools Protocol command"""
        if self.driver:
            try:
                self.driver.execute_cdp_cmd(cmd, params)
            except Exception as e:
                logger.error(f"Error executing CDP command: {e}")
    
    def load_cookies(self, cookies_str: str) -> bool:
        """Load cookies into the browser session"""
        if not self.driver:
            logger.error("Driver not initialized. Call setup_driver first.")
            return False
        
        try:
            # Navigate to Netflix domain first (required for setting cookies)
            self.driver.get(self.netflix_url)
            
            # Small delay to ensure page is loaded
            time.sleep(2)
            
            # Parse cookies JSON
            cookies = json.loads(cookies_str)
            
            # Add cookies to driver
            for cookie in cookies:
                if isinstance(cookie, dict):
                    # Skip problematic cookies
                    if 'sameSite' in cookie and cookie['sameSite'] == 'None':
                        cookie['sameSite'] = 'Strict'
                    
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        logger.warning(f"Could not add cookie: {e}")
            
            # Refresh page to apply cookies
            self.driver.refresh()
            
            # Wait for page to load and verify we're logged in
            time.sleep(5)
            
            # Check if we're logged in
            if "netflix.com/browse" in self.driver.current_url:
                logger.info("Successfully loaded cookies and logged in")
                return True
                
            logger.info("Cookies loaded, but not yet logged in")
            return True
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")
            return False
    
    def get_cookies(self) -> Optional[str]:
        """Get current browser cookies as a JSON string"""
        if not self.driver:
            logger.error("Driver not initialized")
            return None
        
        try:
            cookies = self.driver.get_cookies()
            return json.dumps(cookies)
        except Exception as e:
            logger.error(f"Error getting cookies: {e}")
            return None
    
    async def login_with_credentials(self, email: str, password: str) -> Tuple[bool, str]:
        """Login to Netflix using email and password with advanced human-like interaction"""
        if not self.driver:
            return False, "Driver not initialized"
        
        try:
            # Navigate to login page
            self.driver.get(self.login_url)
            
            # Wait for login form to load with dynamic timeout
            try:
                email_field = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.ID, "id_userLoginId"))
                )
                password_field = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "id_password"))
                )
                
                # Clear fields with human-like interaction
                email_field.clear()
                self._type_like_human(email_field, email)
                
                # Random pause between fields
                time.sleep(random.uniform(0.5, 1.5))
                
                password_field.clear()
                self._type_like_human(password_field, password)
                
                # Find and click login button with human-like delay
                time.sleep(random.uniform(0.7, 1.3))
                login_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-uia='login-submit-button']"))
                )
                
                # Move mouse to button naturally before clicking
                action = ActionChains(self.driver)
                action.move_to_element(login_button).pause(random.uniform(0.2, 0.5)).click().perform()
                
                # Wait for login to complete
                time.sleep(5)
                
                # Check if login was successful
                if "browse" in self.driver.current_url or "signup" in self.driver.current_url:
                    logger.info("Login successful")
                    return True, "Login successful"
                    
                # Check for error messages
                try:
                    error_message = self.driver.find_element(By.CSS_SELECTOR, ".ui-message-contents")
                    return False, f"Login failed: {error_message.text}"
                except NoSuchElementException:
                    pass
                    
                return False, "Login failed: Unknown error"
                
            except TimeoutException:
                logger.error("Timeout waiting for login form")
                return False, "Timeout waiting for login form"
                
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False, f"Login error: {str(e)}"
    
    def detect_current_page(self) -> str:
        """Detect which page in the Netflix signup flow we're currently on"""
        if not self.driver:
            return "unknown"
        
        current_url = self.driver.current_url
        
        if "login" in current_url:
            return "login"
        elif "planform" in current_url or "registration/planselection" in current_url:
            return "plan_selection"
        elif "payment" in current_url or "creditoption" in current_url:
            return "payment_method"
        elif "creditoption" in current_url or "creditcardpayment" in current_url:
            return "credit_card_form"
        elif "browse" in current_url:
            return "browse"
        elif "signup" in current_url:
            return "signup"
        elif "registration" in current_url:
            return "registration"
        else:
            # Get the page source and look for specific elements to further identify the page
            page_source = self.driver.page_source.lower()
            
            if "choose your plan" in page_source:
                return "plan_selection"
            elif "how would you like to pay" in page_source:
                return "payment_method"
            elif "credit or debit card" in page_source and ("cvv" in page_source or "card number" in page_source):
                return "credit_card_form"
            
            # Take a screenshot to aid debugging
            timestamp = int(time.time())
            self.take_screenshot(f"unknown_page_{timestamp}.png")
            
            return "unknown"
    
    def handle_finish_signup(self) -> bool:
        """Click the Finish Sign-Up button"""
        try:
            finish_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-uia='next-button']"))
            )
            
            # Human-like pause before clicking
            time.sleep(random.uniform(0.5, 1.5))
            
            # Move mouse naturally and click
            action = ActionChains(self.driver)
            action.move_to_element(finish_button).pause(random.uniform(0.2, 0.5)).click().perform()
            
            # Wait for next page to load
            time.sleep(random.uniform(3, 5))
            return True
        except Exception as e:
            logger.error(f"Error clicking finish signup button: {e}")
            return False
    
    def handle_plan_selection(self) -> bool:
        """Select a plan on the plan selection page with human-like interaction"""
        try:
            # Try multiple selectors for plan buttons as Netflix may change them
            plan_selectors = [
                "label.nf-radios-button", 
                "button[data-uia*='plan-']",
                "button[data-uia*='continue']",
                "button[data-uia='plan-selection-continue']"
            ]
            
            plan_found = False
            for selector in plan_selectors:
                try:
                    # Find all available plans
                    plan_buttons = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                    )
                    
                    if plan_buttons:
                        plan_found = True
                        # Choose the middle plan if there are at least three options
                        if len(plan_buttons) >= 3:
                            selected_plan = plan_buttons[1]  # Middle option
                        else:
                            selected_plan = plan_buttons[-1]  # Last option
                        
                        # Scroll to plan button with natural mouse movement
                        action = ActionChains(self.driver)
                        action.move_to_element(selected_plan)
                        action.perform()
                        
                        # Human-like pause before clicking
                        time.sleep(random.uniform(0.7, 1.5))
                        
                        selected_plan.click()
                        break
                except:
                    continue
            
            if not plan_found:
                # If no plan elements found, try to find the continue button directly
                continue_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-uia*='continue']"))
                )
                
                # Human-like pause before clicking
                time.sleep(random.uniform(0.5, 1.5))
                continue_button.click()
            
            # Wait for next page to load
            time.sleep(random.uniform(3, 5))
            
            # Check if we need to handle any additional steps
            self.handle_finish_signup()
            
            return True
        except Exception as e:
            logger.error(f"Error selecting plan: {e}")
            
            # Retry logic with exponential backoff
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                delay = 2 ** self.retry_count
                logger.info(f"Retrying plan selection after {delay} seconds (attempt {self.retry_count})")
                time.sleep(delay)
                return self.handle_plan_selection()
                
            return False
    
    def handle_payment_method(self) -> bool:
        """Select credit card payment method with human-like behavior"""
        try:
            # Try multiple methods to find and click the credit card option
            credit_card_selectors = [
                "button[data-uia='payment-method-credit-card']",
                "button[data-uia*='credit']",
                "button[data-uia*='card']",
                "a[data-uia*='credit']"
            ]
            
            for selector in credit_card_selectors:
                try:
                    credit_card_option = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    
                    # Scroll to element with natural mouse movement
                    action = ActionChains(self.driver)
                    action.move_to_element(credit_card_option)
                    action.perform()
                    
                    # Human-like pause before clicking
                    time.sleep(random.uniform(0.7, 1.5))
                    
                    credit_card_option.click()
                    
                    # Wait for the form to appear
                    time.sleep(random.uniform(2, 3))
                    return True
                except:
                    continue
            
            # If direct method fails, try a more general approach
            # Look for any clickable buttons and click the one that likely leads to credit card
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                try:
                    button_text = button.text.lower()
                    if "credit" in button_text or "card" in button_text or "payment" in button_text:
                        # Human-like pause
                        time.sleep(random.uniform(0.5, 1))
                        
                        # Move mouse naturally and click
                        action = ActionChains(self.driver)
                        action.move_to_element(button).pause(random.uniform(0.2, 0.4)).click().perform()
                        
                        time.sleep(2)
                        return True
                except:
                    continue
            
            logger.error("Could not find credit card payment option")
            return False
        except Exception as e:
            logger.error(f"Error selecting payment method: {e}")
            return False
    
    def handle_credit_card_form(self, card_info: Dict[str, str]) -> bool:
        """Fill in and submit the credit card form with human-like behavior"""
        try:
            # Try multiple selectors for credit card fields as Netflix may change them
            card_field_selectors = {
                "card_number": ["[data-uia='credit-card-number-input']", 
                               "input[id*='creditCardNumber']",
                               "input[name*='creditCardNumber']"],
                "expiry_month": ["[data-uia='credit-card-expiration-month-input']",
                                "select[id*='expirationMonth']",
                                "select[name*='expirationMonth']"],
                "expiry_year": ["[data-uia='credit-card-expiration-year-input']",
                               "select[id*='expirationYear']",
                               "select[name*='expirationYear']"],
                "cvv": ["[data-uia='credit-card-cvv-input']",
                       "input[id*='cvv']",
                       "input[name*='cvv']"],
                "name": ["[data-uia='credit-card-name-input']",
                        "input[id*='firstName']",
                        "input[name*='firstName']"],
                "last_name": ["[data-uia='credit-card-last-name-input']",
                             "input[id*='lastName']",
                             "input[name*='lastName']"]
            }
            
            # Parse expiry date
            expiry_parts = card_info['expiry_date'].split('/')
            expiry_month = expiry_parts[0]
            expiry_year = expiry_parts[1]
            if len(expiry_year) == 2:
                expiry_year = f"20{expiry_year}"
            
            # Fill in card number
            card_number_element = None
            for selector in card_field_selectors["card_number"]:
                try:
                    card_number_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if card_number_element:
                        break
                except:
                    continue
                    
            if card_number_element:
                # Clear field and type like a human
                card_number_element.clear()
                self._type_like_human(card_number_element, card_info['card_number'])
                
                # Random pause between fields to simulate human behavior
                time.sleep(random.uniform(0.7, 1.5))
            else:
                logger.error("Could not find card number field")
                return False
            
            # Handle expiry month
            expiry_month_element = None
            for selector in card_field_selectors["expiry_month"]:
                try:
                    expiry_month_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if expiry_month_element:
                        break
                except:
                    continue
                    
            if expiry_month_element:
                # Check if it's a select element or input
                if expiry_month_element.tag_name.lower() == 'select':
                    # Use select class
                    from selenium.webdriver.support.ui import Select
                    select = Select(expiry_month_element)
                    
                    # Human-like delay before selecting
                    time.sleep(random.uniform(0.3, 0.6))
                    select.select_by_value(expiry_month)
                else:
                    # It's an input field
                    expiry_month_element.clear()
                    self._type_like_human(expiry_month_element, expiry_month)
                
                # Random pause between fields
                time.sleep(random.uniform(0.7, 1.5))
            else:
                logger.warning("Could not find expiry month field")
            
            # Handle expiry year
            expiry_year_element = None
            for selector in card_field_selectors["expiry_year"]:
                try:
                    expiry_year_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if expiry_year_element:
                        break
                except:
                    continue
                    
            if expiry_year_element:
                # Check if it's a select element or input
                if expiry_year_element.tag_name.lower() == 'select':
                    # Use select class
                    from selenium.webdriver.support.ui import Select
                    select = Select(expiry_year_element)
                    
                    # Human-like delay before selecting
                    time.sleep(random.uniform(0.3, 0.6))
                    select.select_by_value(expiry_year)
                else:
                    # It's an input field
                    expiry_year_element.clear()
                    self._type_like_human(expiry_year_element, expiry_year)
                
                # Random pause between fields
                time.sleep(random.uniform(0.7, 1.5))
            else:
                logger.warning("Could not find expiry year field")
            
            # Fill in CVV
            cvv_element = None
            for selector in card_field_selectors["cvv"]:
                try:
                    cvv_element = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if cvv_element:
                        break
                except:
                    continue
                    
            if cvv_element:
                cvv_element.clear()
                self._type_like_human(cvv_element, card_info['cvv'])
                
                # Random pause between fields
                time.sleep(random.uniform(0.7, 1.5))
            else:
                logger.warning("Could not find CVV field")
            
            # Fill in cardholder name if required
            name_element = None
            for selector in card_field_selectors["name"]:
                try:
                    name_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if name_element:
                        break
                except:
                    continue
                    
            if name_element:
                name_element.clear()
                self._type_like_human(name_element, "John")
                
                # Random pause between fields
                time.sleep(random.uniform(0.7, 1.5))
            
            # Fill in last name if required
            last_name_element = None
            for selector in card_field_selectors["last_name"]:
                try:
                    last_name_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if last_name_element:
                        break
                except:
                    continue
                    
            if last_name_element:
                last_name_element.clear()
                self._type_like_human(last_name_element, "Smith")
                
                # Random pause before submission
                time.sleep(random.uniform(0.7, 1.5))
            
            # Check "I agree" checkbox if present
            try:
                checkbox = self.driver.find_element(By.CSS_SELECTOR, "[data-uia='checkbox-toc']")
                if checkbox and not checkbox.is_selected():
                    # Human-like pause
                    time.sleep(random.uniform(0.4, 0.8))
                    checkbox.click()
                    time.sleep(random.uniform(0.5, 1))
            except:
                pass
            
            # Find and click submit button
            submit_button_selectors = [
                "button[data-uia='payment-continue-button']",
                "button[type='submit']",
                "button[data-uia*='continue']",
                "button.continue-btn"
            ]
            
            submit_button = None
            for selector in submit_button_selectors:
                try:
                    submit_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if submit_button:
                        break
                except:
                    continue
            
            if submit_button:
                # Scroll to button with natural mouse movement
                action = ActionChains(self.driver)
                action.move_to_element(submit_button).pause(random.uniform(0.2, 0.5))
                action.perform()
                
                # Human-like pause before clicking
                time.sleep(random.uniform(0.7, 1.5))
                
                submit_button.click()
                
                # Wait for processing
                time.sleep(random.uniform(5, 8))
                return True
            else:
                logger.error("Could not find submit button")
                return False
            
        except Exception as e:
            logger.error(f"Error filling credit card form: {e}")
            
            # Take a screenshot to help debug the issue
            self.take_screenshot(f"card_error_{int(time.time())}.png")
            
            return False
    
    def check_payment_success(self) -> bool:
        """Check if payment was successful"""
        try:
            # Wait for page to load
            time.sleep(5)
            
            # Check URL for success indicators
            current_url = self.driver.current_url
            if "browse" in current_url:
                logger.info("Payment successful - redirected to browse page")
                return True
                
            if "signup/credithandle" in current_url:
                # This could be a success page or error page
                # Look for success indicators
                success_indicators = [
                    "welcome to netflix",
                    "thank you",
                    "membership",
                    "continue",
                    "welcome back"
                ]
                
                page_text = self.driver.page_source.lower()
                
                for indicator in success_indicators:
                    if indicator in page_text:
                        logger.info(f"Found success indicator: {indicator}")
                        return True
                
                # Check for error indicators
                error_indicators = [
                    "declined",
                    "invalid",
                    "error",
                    "fail",
                    "please try again",
                    "card not valid",
                    "unable to process"
                ]
                
                for indicator in error_indicators:
                    if indicator in page_text:
                        logger.error(f"Found error indicator: {indicator}")
                        return False
                
                # If we find the "continue" button, assume success
                try:
                    continue_button = self.driver.find_element(By.CSS_SELECTOR, "button[data-uia*='continue']")
                    if continue_button:
                        # Click it to continue
                        time.sleep(random.uniform(0.5, 1))
                        continue_button.click()
                        time.sleep(3)
                        
                        # If we're redirected to browse, that's a success
                        if "browse" in self.driver.current_url:
                            return True
                except:
                    pass
                    
                # If we can't determine conclusively, check for more indicators
                try:
                    # Take screenshot for debugging
                    self.take_screenshot(f"payment_result_{int(time.time())}.png")
                    
                    # Check for specific success indicators:
                    # 1. Profile selection screen
                    if "profile" in self.driver.current_url or "profiles" in page_text:
                        return True
                        
                    # 2. Email confirmation message
                    if "email" in page_text and "confirm" in page_text:
                        return True
                        
                except:
                    pass
            
            # Default to assuming failure if we can't conclusively determine success
            logger.warning("Could not determine payment success/failure")
            return False
            
        except Exception as e:
            logger.error(f"Error checking payment success: {e}")
            return False
    
    def _type_like_human(self, element, text):
        """Type text into an element with random delays like a human"""
        try:
            for char in text:
                # Occasional longer delay like a human thinking
                if random.random() < 0.1:  # 10% chance for a longer pause
                    time.sleep(random.uniform(0.2, 0.5))
                
                # Type character with variable speed
                element.send_keys(char)
                
                # Random delay between keystrokes (faster in the middle, slower at start/end)
                index = text.index(char)
                if index < 3 or index > len(text) - 3:
                    # Slower at beginning and end
                    time.sleep(random.uniform(0.05, 0.15))
                else:
                    # Faster in the middle
                    time.sleep(random.uniform(0.01, 0.08))
                
                # Occasional typo and correction (1% chance)
                if random.random() < 0.01 and index < len(text) - 1:
                    wrong_char = random.choice("qwertyuiopasdfghjklzxcvbnm")
                    element.send_keys(wrong_char)
                    time.sleep(random.uniform(0.1, 0.3))
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(random.uniform(0.1, 0.2))
        except Exception as e:
            logger.error(f"Error typing like human: {e}")
            # Fallback to regular typing
            element.clear()
            element.send_keys(text)
    
    def take_screenshot(self, filename):
        """Take a screenshot for debugging"""
        try:
            if self.driver:
                # Create screenshots directory if it doesn't exist
                screenshots_dir = "screenshots"
                if not os.path.exists(screenshots_dir):
                    os.makedirs(screenshots_dir)
                
                # Save screenshot
                filepath = os.path.join(screenshots_dir, filename)
                self.driver.save_screenshot(filepath)
                logger.info(f"Screenshot saved: {filepath}")
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
    
    def close(self):
        """Close the browser"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")