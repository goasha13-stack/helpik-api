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
            'Origin': 'https://yoomoney.ru',
            'Referer': 'https://yoomoney.ru/'
        })
    
    def normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return '+' + digits
    
    def check_yoomoney_binding(self, phone: str) -> Dict:
        normalized = self.normalize_phone(phone)
        
        try:
            url = "https://yoomoney.ru/api/transfer-search"
            params = {
                'pattern_id': 'p2p',
                'receiver': normalized,
                'amount': '1.00'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'error' in data:
                    error = str(data['error'])
                    if 'not-found' in error or 'illegal_params' in error:
                        return {
                            'phone': normalized,
                            'has_wallet': False,
                            'status': 'clean'
                        }
                    elif 'limit' in error.lower():
                        return {
                            'phone': normalized,
                            'has_wallet': True,
                            'status': 'occupied'
                        }
                
                if any(key in data for key in ['contract_amount', 'request_id', 'balance']):
                    return {
                        'phone': normalized,
                        'has_wallet': True,
                        'status': 'occupied',
                        'details': data.get('contract_amount')
                    }
                
                return {
                    'phone': normalized,
                    'has_wallet': False,
                    'status': 'clean'
                }
            
            elif response.status_code == 404:
                return {
                    'phone': normalized,
                    'has_wallet': False,
                    'status': 'clean'
                }
            
            else:
                return {
                    'phone': normalized,
                    'has_wallet': None,
                    'status': 'error',
                    'code': response.status_code
                }
                
        except Exception as e:
            return {
                'phone': normalized,
                'has_wallet': None,
                'status': 'error',
                'message': str(e)
            }
    
    def full_check(self, phone: str) -> Dict:
        print(f"🔍 Проверка: {phone}")
        
        yoomoney = self.check_yoomoney_binding(phone)
        has_any = yoomoney.get('has_wallet', False)
        
        return {
            'phone': yoomoney['phone'],
            'is_clean': not has_any if has_any is not None else None,
            'has_yoomoney': yoomoney.get('has_wallet', False),
            'has_yandex_pay': False,  # ЮMoney и Яндекс Pay - одно целое
            'status': yoomoney.get('status'),
            'recommendation': '✅ Чистый - можно использовать' if not has_any else '❌ Занят - привязан кошелек'
        }