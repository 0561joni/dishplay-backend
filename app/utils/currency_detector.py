# app/utils/currency_detector.py
from typing import Optional, Dict
import re
import logging

logger = logging.getLogger(__name__)

# Currency symbol to code mapping
CURRENCY_SYMBOLS = {
    '$': 'USD',
    '€': 'EUR', 
    '£': 'GBP',
    '¥': 'JPY',
    '₹': 'INR',
    '₽': 'RUB',
    '₩': 'KRW',
    '¢': 'USD',  # cents, assume USD
    'C$': 'CAD',
    'A$': 'AUD',
    'NZ$': 'NZD',
    'HK$': 'HKD',
    'S$': 'SGD',
    'R$': 'BRL',
    'CHF': 'CHF',
    'kr': 'SEK',  # Could be DKK, NOK as well - would need more context
    'zł': 'PLN',
    'Kč': 'CZK',
    '₪': 'ILS',
    '₦': 'NGN',
    '₨': 'PKR',
    '৳': 'BDT',
    '₡': 'CRC',
    '₱': 'PHP',
    '₫': 'VND',
    '₵': 'GHS',
    '₸': 'KZT',
    '₴': 'UAH',
}

# Common currency codes
CURRENCY_CODES = {
    'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CAD', 'AUD', 'CHF', 'SEK', 'NOK', 'DKK',
    'PLN', 'CZK', 'HUF', 'RUB', 'INR', 'KRW', 'SGD', 'HKD', 'NZD', 'MXN', 'BRL',
    'ZAR', 'THB', 'MYR', 'IDR', 'PHP', 'VND', 'EGP', 'ILS', 'TRY', 'AED', 'SAR'
}

# Regional context hints (restaurant names, addresses, etc.)
REGIONAL_CURRENCY_HINTS = {
    'USD': ['usa', 'america', 'united states', 'us', 'california', 'new york', 'texas', 'florida'],
    'EUR': ['europe', 'germany', 'france', 'italy', 'spain', 'netherlands', 'belgium', 'austria'],
    'GBP': ['uk', 'britain', 'england', 'london', 'scotland', 'wales', 'british'],
    'CAD': ['canada', 'canadian', 'toronto', 'vancouver', 'montreal'],
    'AUD': ['australia', 'australian', 'sydney', 'melbourne', 'brisbane'],
    'JPY': ['japan', 'japanese', 'tokyo', 'osaka', 'kyoto'],
    'INR': ['india', 'indian', 'mumbai', 'delhi', 'bangalore'],
    'CNY': ['china', 'chinese', 'beijing', 'shanghai', 'guangzhou'],
}

def detect_currency_from_text(text: str) -> Optional[str]:
    """
    Detect currency from extracted text content
    
    Args:
        text: Text content from menu (restaurant name, addresses, etc.)
        
    Returns:
        Currency code (e.g., 'USD') or None if not detected
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Look for explicit currency codes
    for code in CURRENCY_CODES:
        if code.lower() in text_lower:
            return code
    
    # Look for currency symbols
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    
    # Look for regional hints
    for currency, hints in REGIONAL_CURRENCY_HINTS.items():
        for hint in hints:
            if hint in text_lower:
                return currency
    
    return None

def detect_currency_from_prices(prices: list) -> Optional[str]:
    """
    Detect currency from price formatting patterns
    
    Args:
        prices: List of price strings/numbers
        
    Returns:
        Currency code or None
    """
    if not prices:
        return None
    
    # Look for currency symbols in price strings
    for price in prices:
        if isinstance(price, str):
            for symbol, code in CURRENCY_SYMBOLS.items():
                if symbol in price:
                    return code
    
    return None

def validate_currency_code(currency: str) -> str:
    """
    Validate and normalize currency code
    
    Args:
        currency: Currency code to validate
        
    Returns:
        Valid currency code or 'USD' as fallback
    """
    if not currency:
        return 'USD'
    
    currency_upper = currency.upper()
    
    if currency_upper in CURRENCY_CODES:
        return currency_upper
    
    # Check if it's a symbol we can map
    if currency in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[currency]
    
    logger.warning(f"Unknown currency '{currency}', defaulting to USD")
    return 'USD'

def detect_currency_comprehensive(restaurant_name: str = None, 
                                location_text: str = None, 
                                price_strings: list = None) -> str:
    """
    Comprehensive currency detection using multiple signals
    
    Args:
        restaurant_name: Name of the restaurant
        location_text: Any location/address information
        price_strings: List of price strings from the menu
        
    Returns:
        Detected currency code (defaults to USD)
    """
    # Try multiple detection methods
    detected_currencies = []
    
    # Method 1: Check restaurant name
    if restaurant_name:
        currency = detect_currency_from_text(restaurant_name)
        if currency:
            detected_currencies.append(currency)
    
    # Method 2: Check location text
    if location_text:
        currency = detect_currency_from_text(location_text)
        if currency:
            detected_currencies.append(currency)
    
    # Method 3: Check price formatting
    if price_strings:
        currency = detect_currency_from_prices(price_strings)
        if currency:
            detected_currencies.append(currency)
    
    # Return most common currency detected, or USD as fallback
    if detected_currencies:
        # Count occurrences and return most frequent
        currency_counts = {}
        for curr in detected_currencies:
            currency_counts[curr] = currency_counts.get(curr, 0) + 1
        
        most_common = max(currency_counts, key=currency_counts.get)
        logger.info(f"Detected currency: {most_common} (from {detected_currencies})")
        return validate_currency_code(most_common)
    
    logger.info("No currency detected, defaulting to USD")
    return 'USD'