import requests
import re
from typing import Dict

class YandexPayChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://yoomoney.ru',
            'Referer': 'https://yoomoney.ru/',
            'X-Requested-With': 'XMLHttpRequest'
        })
    
    def normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return '+' + digits
    
    def check_wallet_exists(self, phone: str) -> Dict:
        normalized = self.normalize_phone(phone)
        
        try:
            url = "https://yoomoney.ru/api/request-payment"
            data = {
                'pattern_id': 'p2p',
                'to': normalized,
                'amount': '1.00',
                'comment': 'Проверка'
            }
            
            response = self.session.post(url, data=data, timeout=15)
            
            if response.status_code != 200:
                return {
                    'phone': normalized, 
                    'exists': None, 
                    'status': 'error', 
                    'message': f'HTTP {response.status_code}'
                }
            
            result = response.json()
            print(f"DEBUG: {normalized} -> {result}")
            
            status = result.get('status', '')
            error = result.get('error', '')
            
            if 'contract_amount' in result:
                return {
                    'phone': normalized, 
                    'exists': True, 
                    'status': 'occupied', 
                    'message': 'Кошелек существует'
                }
            
            if error == 'payee_not_found':
                return {
                    'phone': normalized, 
                    'exists': False, 
                    'status': 'clean', 
                    'message': 'Кошелек не существует'
                }
            
            if error == 'limit_exceeded':
                return {
                    'phone': normalized, 
                    'exists': True, 
                    'status': 'occupied', 
                    'message': 'Кошелек существует (лимит)'
                }
            
            if status == 'success':
                return {
                    'phone': normalized, 
                    'exists': True, 
                    'status': 'occupied', 
                    'message': 'Кошелек найден'
                }
            
            return {
                'phone': normalized, 
                'exists': False, 
                'status': 'clean', 
                'message': f'Неизвестно: {error}'
            }
            
        except Exception as e:
            return {
                'phone': normalized, 
                'exists': None, 
                'status': 'error', 
                'message': str(e)
            }
