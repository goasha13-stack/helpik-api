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
        Если кошелек существует - вернет статус отличный от payee_not_found
        """
        normalized = self.normalize_phone(phone)
        
        try:
            # Используем endpoint request-payment без авторизации
            # Это тестовый запрос, который показывает существует ли получатель
            url = "https://yoomoney.ru/api/request-payment"
            
            data = {
                'pattern_id': 'p2p',
                'to': normalized,
                'amount': '1.00',
                'comment': 'test',
                'message': 'test',
                'test_payment': 'true'
            }
            
            response = self.session.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status', '')
                error = result.get('error', '')
                
                # Если статус refused и ошибка payee_not_found - кошелька нет
                if status == 'refused' and error == 'payee_not_found':
                    return {
                        'phone': normalized,
                        'exists': False,
                        'status': 'clean',
                        'message': 'Кошелек не существует (payee_not_found)'
                    }
                
                # Если статус success или другая ошибка - кошелек существует
                if status == 'success' or error in ['limit_exceeded', 'not_enough_funds', 'authorization_reject']:
                    return {
                        'phone': normalized,
                        'exists': True,
                        'status': 'occupied',
                        'message': 'Кошелек существует!',
                        'details': result
                    }
                
                # Любой другой ответ - проверяем наличие contract_amount
                if 'contract_amount' in result or 'request_id' in result:
                    return {
                        'phone': normalized,
                        'exists': True,
                        'status': 'occupied',
                        'message': 'Кошелек найден (есть contract_amount)',
                        'details': result
                    }
                
                return {
                    'phone': normalized,
                    'exists': False,
                    'status': 'unknown',
                    'raw': result
                }
            
            # Если 401 или 403 - возможно кошелек существует но требует авторизации
            elif response.status_code in [401, 403]:
                return {
                    'phone': normalized,
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Возможно кошелек существует (требует авторизации)'
                }
            
            else:
                return {
                    'phone': normalized,
                    'exists': None,
                    'status': 'error',
                    'code': response.status_code
                }
                
        except Exception as e:
            return {
                'phone': normalized,
                'exists': None,
                'status': 'error',
                'message': str(e)
            }
    
    def check_via_quickpay(self, phone: str) -> Dict:
        """
        Альтернативная проверка через quickpay форму
        """
        normalized = self.normalize_phone(phone)
        
        try:
            url = "https://yoomoney.ru/quickpay/confirm"
            
            data = {
                'receiver': normalized,
                'quickpay-form': 'phone',
                'paymentType': 'AC',
                'sum': '1.00'
            }
            
            response = self.session.post(url, data=data, allow_redirects=False, timeout=10)
            
            # Анализируем ответ
            location = response.headers.get('Location', '')
            
            # Если редирект на страницу подтверждения - номер найден
            if 'request-payment' in location or 'process-payment' in location:
                return {
                    'phone': normalized,
                    'exists': True,
                    'method': 'quickpay',
                    'status': 'occupied'
                }
            
            # Если редирект на ошибку - номер не найден
            if 'error' in location or response.status_code == 400:
                return {
                    'phone': normalized,
                    'exists': False,
                    'method': 'quickpay',
                    'status': 'clean'
                }
            
            # Проверяем содержимое страницы
            if response.status_code == 200:
                text = response.text.lower()
                if 'получатель' in text or 'подтверждение' in text:
                    return {
                        'phone': normalized,
                        'exists': True,
                        'method': 'quickpay',
                        'status': 'occupied'
                    }
                if 'не найден' in text or 'ошибка' in text:
                    return {
                        'phone': normalized,
                        'exists': False,
                        'method': 'quickpay',
                        'status': 'clean'
                    }
            
            return {
                'phone': normalized,
                'exists': None,
                'method': 'quickpay',
                'status': 'unknown'
            }
            
        except Exception as e:
            return {
                'phone': normalized,
                'exists': None,
                'method': 'quickpay',
                'status': 'error',
                'message': str(e)
            }
    
    def full_check(self, phone: str) -> Dict:
        """
        Комплексная проверка двумя методами
        """
        print(f"🔍 Проверка: {phone}")
        
        # Метод 1: API request-payment
        result1 = self.check_wallet_exists(phone)
        
        # Если метод 1 дал чёткий ответ - используем его
        if result1['status'] in ['occupied', 'clean'] and result1['exists'] is not None:
            return {
                'phone': result1['phone'],
                'is_clean': not result1['exists'],
                'has_yoomoney': result1['exists'],
                'has_yandex_pay': result1['exists'],  # ЮMoney = Яндекс Pay
                'status': result1['status'],
                'message': result1['message'],
                'method': 'api_request_payment'
            }
        
        # Метод 2: Quickpay форма (fallback)
        result2 = self.check_via_quickpay(phone)
        
        return {
            'phone': result2['phone'],
            'is_clean': not result2['exists'] if result2['exists'] is not None else None,
            'has_yoomoney': result2['exists'],
            'has_yandex_pay': result2['exists'],
            'status': result2['status'],
            'message': result2.get('message', 'Проверка через quickpay'),
            'method': 'quickpay',
            'api_result': result1,
            'quickpay_result': result2
        }
