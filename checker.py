import requests
import re
import time
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
    
    def check_method_1(self, phone: str) -> Dict:
        """Метод 1: request-payment API"""
        try:
            url = "https://yoomoney.ru/api/request-payment"
            data = {
                'pattern_id': 'p2p',
                'to': phone,
                'amount': '1.00',
                'test_payment': 'true'
            }
            response = self.session.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                
                # Точные признаки
                if 'contract_amount' in result:
                    return {'exists': True, 'confidence': 'high', 'method': 'contract_amount'}
                
                if result.get('error') == 'payee_not_found':
                    return {'exists': False, 'confidence': 'high', 'method': 'payee_not_found'}
                
                if result.get('status') == 'success':
                    return {'exists': True, 'confidence': 'medium', 'method': 'success_status'}
                
                return {'exists': None, 'confidence': 'low', 'raw': result}
            
            return {'exists': None, 'confidence': 'low', 'error': f'HTTP {response.status_code}'}
            
        except Exception as e:
            return {'exists': None, 'confidence': 'low', 'error': str(e)}
    
    def check_method_2(self, phone: str) -> Dict:
        """Метод 2: Проверка через форму перевода"""
        try:
            url = "https://yoomoney.ru/transfer"
            params = {'to': phone}
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                text = response.text.lower()
                
                # Если есть форма для ввода суммы - кошелек существует
                if 'amount' in text or 'сумма' in text or 'перевод' in text:
                    return {'exists': True, 'confidence': 'medium', 'method': 'transfer_form'}
                
                # Если ошибка "не найден"
                if 'не найден' in text or 'not found' in text:
                    return {'exists': False, 'confidence': 'medium', 'method': 'not_found_page'}
                
                return {'exists': None, 'confidence': 'low'}
            
            return {'exists': None, 'confidence': 'low', 'error': f'HTTP {response.status_code}'}
            
        except Exception as e:
            return {'exists': None, 'confidence': 'low', 'error': str(e)}
    
    def check_method_3(self, phone: str) -> Dict:
        """Метод 3: Проверка через process-payment"""
        try:
            # Сначала получаем request_id
            url1 = "https://yoomoney.ru/api/request-payment"
            data = {
                'pattern_id': 'p2p',
                'to': phone,
                'amount': '1.00'
            }
            response1 = self.session.post(url1, data=data, timeout=10)
            
            if response1.status_code != 200:
                return {'exists': None, 'confidence': 'low'}
            
            result1 = response1.json()
            request_id = result1.get('request_id')
            
            if not request_id:
                return {'exists': None, 'confidence': 'low'}
            
            # Пробуем process-payment
            url2 = "https://yoomoney.ru/api/process-payment"
            data2 = {'request_id': request_id}
            response2 = self.session.post(url2, data=data2, timeout=10)
            
            if response2.status_code == 200:
                result2 = response2.json()
                error = result2.get('error', '')
                
                if 'payee' in error or 'получатель' in error:
                    return {'exists': False, 'confidence': 'high', 'method': 'process_payee_error'}
                
                if error in ['limit_exceeded', 'not_enough_funds']:
                    return {'exists': True, 'confidence': 'high', 'method': 'process_limit_error'}
                
                return {'exists': True, 'confidence': 'medium', 'method': 'process_other'}
            
            return {'exists': None, 'confidence': 'low'}
            
        except Exception as e:
            return {'exists': None, 'confidence': 'low', 'error': str(e)}
    
    def check_wallet_exists(self, phone: str) -> Dict:
        """
        Комплексная проверка всеми методами
        """
        normalized = self.normalize_phone(phone)
        
        # Пробуем методы по очереди
        results = []
        
        # Метод 1 (самый точный)
        r1 = self.check_method_1(normalized)
        results.append(r1)
        
        if r1['confidence'] == 'high':
            return {
                'phone': normalized,
                'exists': r1['exists'],
                'method': r1['method'],
                'confidence': 'high'
            }
        
        # Метод 2
        r2 = self.check_method_2(normalized)
        results.append(r2)
        
        if r2['confidence'] == 'high':
            return {
                'phone': normalized,
                'exists': r2['exists'],
                'method': r2['method'],
                'confidence': 'high'
            }
        
        # Метод 3
        r3 = self.check_method_3(normalized)
        results.append(r3)
        
        if r3['confidence'] == 'high':
            return {
                'phone': normalized,
                'exists': r3['exists'],
                'method': r3['method'],
                'confidence': 'high'
            }
        
        # Если есть совпадение средних confidence
        exists_count = sum(1 for r in results if r.get('exists') is True)
        not_exists_count = sum(1 for r in results if r.get('exists') is False)
        
        if exists_count > not_exists_count:
            return {
                'phone': normalized,
                'exists': True,
                'method': 'majority_vote',
                'confidence': 'medium',
                'details': results
            }
        elif not_exists_count > exists_count:
            return {
                'phone': normalized,
                'exists': False,
                'method': 'majority_vote',
                'confidence': 'medium',
                'details': results
            }
        
        # По умолчанию - неизвестно (но для безопасности считаем что нет)
        return {
            'phone': normalized,
            'exists': False,
            'method': 'default_unknown',
            'confidence': 'low',
            'details': results
        }
    
    def full_check(self, phone: str) -> Dict:
        result = self.check_wallet_exists(phone)
        
        return {
            'phone': result['phone'],
            'is_clean': not result['exists'] if result['exists'] is not None else None,
            'has_yoomoney': result['exists'],
            'has_yandex_pay': result['exists'],
            'confidence': result['confidence'],
            'method': result['method']
        }
