from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import re
import os

app = Flask(__name__)
CORS(app)

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
    
    def normalize_phone(self, phone):
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return '+' + digits
    
    def check_yoomoney(self, phone):
        """Проверка кошелька ЮMoney"""
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
                    'exists': None,
                    'status': 'error',
                    'message': f'HTTP {response.status_code}',
                    'raw': {}
                }
            
            result = response.json()
            status = result.get('status', '')
            error = result.get('error', '')
            
            raw_response = {
                'status': status,
                'error': error,
                'has_contract_amount': 'contract_amount' in result,
                'has_request_id': 'request_id' in result,
                'full_response': result
            }
            
            if 'contract_amount' in result or error == 'limit_exceeded' or status == 'success':
                return {
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Кошелёк ЮMoney существует',
                    'raw': raw_response
                }
            
            if error == 'payee_not_found':
                return {
                    'exists': False,
                    'status': 'clean',
                    'message': 'Кошелёк не существует',
                    'raw': raw_response
                }
            
            return {
                'exists': False,
                'status': 'unknown',
                'message': f'Неизвестно: {error}',
                'raw': raw_response
            }
            
        except Exception as e:
            return {
                'exists': None,
                'status': 'error',
                'message': str(e),
                'raw': {}
            }
    
    def check_yandex_id(self, phone):
        """
        Проверка Yandex ID (аккаунта Яндекса) по номеру телефона
        """
        normalized = self.normalize_phone(phone)
        
        try:
            # Метод 1: Проверка через API паспорта (регистрация)
            url = "https://passport.yandex.ru/registration/validations/phone"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://passport.yandex.ru',
                'Referer': 'https://passport.yandex.ru/',
            }
            
            data = {
                'phone': normalized,
                'track_id': '',
                'csrf_token': ''
            }
            
            response = self.session.post(url, data=data, headers=headers, timeout=10)
            result = response.json() if response.text else {}
            
            # Если номер уже занят (привязан к аккаунту)
            if result.get('status') == 'error':
                errors = result.get('errors', {})
                if 'phone' in errors and 'occupied' in str(errors['phone']):
                    return {
                        'exists': True,
                        'status': 'occupied',
                        'message': 'Yandex ID существует (номер занят)',
                        'raw': result
                    }
            
            # Метод 2: Проверка через API account information
            url2 = "https://passport.yandex.ru/registration/validations/accountInformation"
            response2 = self.session.post(url2, data={'phone': normalized}, headers=headers, timeout=10)
            result2 = response2.json() if response2.text else {}
            
            # Если аккаунт существует (есть login)
            if result2.get('status') == 'ok' or result2.get('login'):
                return {
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Yandex ID найден',
                    'raw': result2
                }
            
            # Метод 3: Проверка через API восстановления пароля
            url3 = "https://passport.yandex.ru/restoration/login-or-phone"
            response3 = self.session.post(url3, data={'phone': normalized}, headers=headers, timeout=10)
            result3 = response3.json() if response3.text else {}
            
            if result3.get('status') == 'ok' or result3.get('logins'):
                return {
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Yandex ID найден (через восстановление)',
                    'raw': result3
                }
            
            return {
                'exists': False,
                'status': 'clean',
                'message': 'Yandex ID не найден',
                'raw': {
                    'validation': result,
                    'account_info': result2,
                    'restoration': result3
                }
            }
            
        except Exception as e:
            return {
                'exists': False,
                'status': 'error',
                'message': f'Ошибка проверки: {str(e)}',
                'raw': {}
            }
    
    def check_yandex_pay(self, phone):
        """
        Проверка Yandex Pay карты
        """
        normalized = self.normalize_phone(phone)
        
        try:
            # Проверяем через API Yandex Pay
            url = "https://pay.yandex.ru/api/v1/phone/check"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Content-Type': 'application/json',
                'Origin': 'https://pay.yandex.ru',
                'Referer': 'https://pay.yandex.ru/',
            }
            
            data = {
                'phone': normalized,
                'type': 'card_check'
            }
            
            response = self.session.post(url, json=data, headers=headers, timeout=10)
            result = response.json() if response.text else {}
            
            # Если Yandex ID существует, проверяем есть ли карта
            yandex_id = self.check_yandex_id(phone)
            
            # Если аккаунт есть, предполагаем что может быть карта
            # (точная проверка требует авторизации)
            if yandex_id['exists']:
                return {
                    'exists': True,  # Предполагаем наличие
                    'status': 'occupied',
                    'message': 'Возможна Yandex Pay карта (аккаунт существует)',
                    'raw': {
                        'pay_api': result,
                        'yandex_id': yandex_id
                    }
                }
            
            return {
                'exists': False,
                'status': 'clean',
                'message': 'Yandex Pay карты нет (нет аккаунта)',
                'raw': {
                    'pay_api': result,
                    'yandex_id': yandex_id
                }
            }
            
        except Exception as e:
            yandex_id = self.check_yandex_id(phone)
            return {
                'exists': yandex_id.get('exists', False),
                'status': 'error' if not yandex_id.get('exists') else 'occupied',
                'message': 'Проверка через Yandex ID',
                'raw': {'error': str(e), 'yandex_id': yandex_id}
            }
    
    def check_wallet_exists(self, phone):
        """
        Комплексная проверка: Yandex ID + ЮMoney + Yandex Pay
        """
        normalized = self.normalize_phone(phone)
        
        # Проверяем все три сервиса
        yandex_id_result = self.check_yandex_id(phone)
        yoomoney_result = self.check_yoomoney(phone)
        yandex_pay_result = self.check_yandex_pay(phone)
        
        # Определяем общий статус
        # ЗАНЯТ если есть хотя бы один из сервисов
        is_occupied = (
            yandex_id_result['exists'] or 
            yoomoney_result['exists'] or 
            yandex_pay_result['exists']
        )
        
        # Формируем сообщение
        services = []
        if yandex_id_result['exists']:
            services.append('Yandex ID')
        if yoomoney_result['exists']:
            services.append('ЮMoney')
        if yandex_pay_result['exists']:
            services.append('Yandex Pay')
        
        if services:
            final_message = f"Найдены: {', '.join(services)}"
        else:
            final_message = 'Чистый номер'
        
        return {
            'phone': normalized,
            'exists': is_occupied,
            'status': 'occupied' if is_occupied else 'clean',
            'message': final_message,
            'yandex_id': yandex_id_result,
            'yoomoney': yoomoney_result,
            'yandex_pay': yandex_pay_result,
            'raw': {
                'yandex_id': yandex_id_result.get('raw', {}),
                'yoomoney': yoomoney_result.get('raw', {}),
                'yandex_pay': yandex_pay_result.get('raw', {})
            }
        }

checker = YandexPayChecker()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check', methods=['POST'])
def check_phone():
    phone = request.json.get('phone', '')
    if not phone:
        return jsonify({'error': 'Номер не указан'}), 400
    
    result = checker.check_wallet_exists(phone)
    
    return jsonify({
        'phone': result['phone'],
        'is_clean': not result['exists'],
        'has_yandex_id': result['yandex_id']['exists'],
        'has_yoomoney': result['yoomoney']['exists'],
        'has_yandex_pay': result['yandex_pay']['exists'],
        'status': result['status'],
        'message': result['message'],
        'yandex_id_message': result['yandex_id']['message'],
        'yoomoney_message': result['yoomoney']['message'],
        'yandex_pay_message': result['yandex_pay']['message'],
        'debug': result['raw']
    })

@app.route('/api/check-batch', methods=['POST'])
def check_batch():
    phones = request.json.get('phones', [])
    results = []
    
    for phone in phones:
        result = checker.check_wallet_exists(phone)
        results.append({
            'phone': result['phone'],
            'is_clean': not result['exists'],
            'has_yandex_id': result['yandex_id']['exists'],
            'has_yoomoney': result['yoomoney']['exists'],
            'has_yandex_pay': result['yandex_pay']['exists'],
            'status': result['status'],
            'message': result['message'],
            'yandex_id_message': result['yandex_id']['message'],
            'yoomoney_message': result['yoomoney']['message'],
            'yandex_pay_message': result['yandex_pay']['message'],
            'debug': result['raw']
        })
    
    clean_count = sum(1 for r in results if r.get('is_clean') is True)
    occupied_count = sum(1 for r in results if r.get('is_clean') is False)
    
    return jsonify({
        'total': len(results),
        'clean': clean_count,
        'occupied': occupied_count,
        'results': results
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
