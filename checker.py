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
        """
        Проверка через API request-payment с правильной обработкой ответа
        """
        normalized = self.normalize_phone(phone)
        
        try:
            # Шаг 1: Создаем платеж
            url = "https://yoomoney.ru/api/request-payment"
            data = {
                'pattern_id': 'p2p',
                'to': normalized,
                'amount': '1.00',
                'comment': 'Проверка',
                'message': 'Проверка кошелька'
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
            
            # Логируем для отладки
            print(f"DEBUG {normalized}: {result}")
            
            status = result.get('status', '')
            error = result.get('error', '')
            
            # Точные признаки существования кошелька:
            
            # 1. Есть contract_amount - кошелек точно существует
            if 'contract_amount' in result:
                return {
                    'phone': normalized,
                    'exists': True,
                    'status': 'occupied',
                    'message': f'Кошелек существует (сумма: {result["contract_amount"]})',
                    'raw': result
                }
            
            # 2. Ошибка payee_not_found - кошелька нет
            if error == 'payee_not_found':
                return {
                    'phone': normalized,
                    'exists': False,
                    'status': 'clean',
                    'message': 'Кошелек не существует',
                    'raw': result
                }
            
            # 3. Ошибка limit_exceeded - кошелек существует, но превышен лимит
            if error == 'limit_exceeded':
                return {
                    'phone': normalized,
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Кошелек существует (лимит превышен)',
                    'raw': result
                }
            
            # 4. Статус success - нужно проверить дальше
            if status == 'success':
                # Проверяем есть ли request_id
                if 'request_id' in result:
                    # Пробуем process-payment для уточнения
                    return self._check_process_payment(normalized, result['request_id'])
                
                # Если нет request_id но статус success - скорее всего кошелек есть
                return {
                    'phone': normalized,
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Кошелек найден (success без request_id)',
                    'raw': result
                }
            
            # 5. Любая другая ошибка - по умолчанию считаем что кошелька нет
            # (но логируем для анализа)
            return {
                'phone': normalized,
                'exists': False,
                'status': 'clean',
                'message': f'Неизвестный статус: {status}, ошибка: {error}',
                'raw': result
            }
            
        except Exception as e:
            return {
                'phone': normalized,
                'exists': None,
                'status': 'error',
                'message': str(e)
            }
    
    def _check_process_payment(self, phone: str, request_id: str) -> Dict:
        """
        Дополнительная проверка через process-payment
        """
        try:
            url = "https://yoomoney.ru/api/process-payment"
            data = {
                'request_id': request_id,
                'money_source': 'wallet'
            }
            
            response = self.session.post(url, data=data, timeout=15)
            
            if response.status_code != 200:
                return {
                    'phone': phone,
                    'exists': True,  # Если не удалось проверить, считаем что есть
                    'status': 'occupied',
                    'message': 'Не удалось проверить через process-payment'
                }
            
            result = response.json()
            error = result.get('error', '')
            
            # Ошибки указывающие на отсутствие кошелька
            if error in ['payee_not_found', 'illegal_params']:
                return {
                    'phone': phone,
                    'exists': False,
                    'status': 'clean',
                    'message': 'Кошелек не существует (process-payment)',
                    'raw': result
                }
            
            # Ошибки указывающие на существование кошелька
            if error in ['limit_exceeded', 'not_enough_funds', 'authorization_reject']:
                return {
                    'phone': phone,
                    'exists': True,
                    'status': 'occupied',
                    'message': f'Кошелек существует (ошибка: {error})',
                    'raw': result
                }
            
            # Если статус success - кошелек точно есть
            if result.get('status') == 'success':
                return {
                    'phone': phone,
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Кошелек существует (process-payment success)',
                    'raw': result
                }
            
            # По умолчанию
            return {
                'phone': phone,
                'exists': True,
                'status': 'occupied',
                'message': f'Неизвестный ответ process-payment: {error}',
                'raw': result
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
            'message': result['message'],
            'debug': result.get('raw', {})
        }
