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
            'Referer': 'https://yoomoney.ru/'
        })
    
    def normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return '+' + digits
    
    def check_wallet_exists(self, phone: str) -> Dict:
        """
        Проверка через API request-payment
        """
        normalized = self.normalize_phone(phone)
        
        try:
            url = "https://yoomoney.ru/api/request-payment"
            
            data = {
                'pattern_id': 'p2p',
                'to': normalized,
                'amount': '1.00',
                'comment': 'test',
                'test_payment': 'true'
            }
            
            response = self.session.post(url, data=data, timeout=10)
            result = response.json() if response.status_code == 200 else {}
            
            print(f"DEBUG: {normalized} -> {result}")  # Для отладки
            
            status = result.get('status', '')
            error = result.get('error', '')
            
            # Кошелек НЕ существует ТОЛЬКО если явно указано payee_not_found
            if error == 'payee_not_found' or 'not_found' in str(error):
                return {
                    'phone': normalized,
                    'exists': False,
                    'status': 'clean',
                    'message': 'Кошелек не существует'
                }
            
            # Если есть contract_amount - кошелек точно существует
            if 'contract_amount' in result:
                return {
                    'phone': normalized,
                    'exists': True,
                    'status': 'occupied',
                    'message': f'Кошелек существует (сумма: {result["contract_amount"]})'
                }
            
            # Если статус success и нет ошибок - проверяем дальше
            if status == 'success':
                # Проверяем есть ли информация о получателе
                if 'receiver' in str(result).lower() or 'recipient' in str(result).lower():
                    return {
                        'phone': normalized,
                        'exists': True,
                        'status': 'occupied',
                        'message': 'Кошелек найден (есть данные получателя)'
                    }
                
                # Если success но нет данных получателя - возможно кошелька нет
                # Нужно проверить через process-payment
                return self._verify_via_process_payment(normalized, result.get('request_id'))
            
            # Любая другая ошибка - считаем что кошелька нет (безопаснее)
            return {
                'phone': normalized,
                'exists': False,
                'status': 'clean',
                'message': f'Кошелек не найден (ошибка: {error})'
            }
            
        except Exception as e:
            return {
                'phone': normalized,
                'exists': None,
                'status': 'error',
                'message': str(e)
            }
    
    def _verify_via_process_payment(self, phone: str, request_id: str) -> Dict:
        """
        Дополнительная проверка через process-payment
        """
        if not request_id:
            return {
                'phone': phone,
                'exists': False,
                'status': 'unknown',
                'message': 'Нет request_id для проверки'
            }
        
        try:
            url = "https://yoomoney.ru/api/process-payment"
            data = {
                'request_id': request_id,
                'test_payment': 'true'
            }
            
            response = self.session.post(url, data=data, timeout=10)
            result = response.json() if response.status_code == 200 else {}
            
            error = result.get('error', '')
            
            # Если ошибка про получателя - кошелька нет
            if 'payee' in str(error).lower() or 'receiver' in str(error).lower() or 'not_found' in str(error):
                return {
                    'phone': phone,
                    'exists': False,
                    'status': 'clean',
                    'message': 'Кошелек не существует (проверка process-payment)'
                }
            
            # Если другая ошибка (например, не хватает денег) - кошелек есть
            if error and error != 'payee_not_found':
                return {
                    'phone': phone,
                    'exists': True,
                    'status': 'occupied',
                    'message': f'Кошелек существует (ошибка: {error})'
                }
            
            return {
                'phone': phone,
                'exists': True,
                'status': 'occupied',
                'message': 'Кошелек найден'
            }
            
        except Exception as e:
            return {
                'phone': phone,
                'exists': None,
                'status': 'error',
                'message': str(e)
            }
    
    def full_check(self, phone: str) -> Dict:
        result = self.check_wallet_exists(phone)
        
        return {
            'phone': result['phone'],
            'is_clean': not result['exists'] if result['exists'] is not None else None,
            'has_yoomoney': result['exists'],
            'has_yandex_pay': result['exists'],
            'status': result['status'],
            'message': result['message']
        }
