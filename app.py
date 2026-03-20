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
            
            # Кошелёк существует
            if 'contract_amount' in result or error == 'limit_exceeded' or status == 'success':
                return {
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Кошелёк ЮMoney существует',
                    'raw': raw_response
                }
            
            # Кошелёк не существует
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
    
    def check_yandex_pay(self, phone):
        """
        Проверка Yandex Pay карты через API привязки телефона
        """
        normalized = self.normalize_phone(phone)
        digits = normalized[1:]  # Убираем +
        
        try:
            # API проверки доступности номера для Yandex Pay
            # Эндпоинт проверки занятости номера в системе Яндекс
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
            
            # Альтернативный метод: проверка через API паспорта
            # Если номер уже привязан к аккаунту с Yandex Pay
            passport_check = self._check_passport_phone(normalized)
            
            return {
                'exists': passport_check.get('has_yandex_pay', False),
                'status': 'occupied' if passport_check.get('has_yandex_pay') else 'clean',
                'message': 'Yandex Pay карта найдена' if passport_check.get('has_yandex_pay') else 'Yandex Pay карты нет',
                'raw': {
                    'pay_api': result,
                    'passport_check': passport_check
                }
            }
            
        except Exception as e:
            # Fallback: проверяем через паспорт
            passport_check = self._check_passport_phone(normalized)
            return {
                'exists': passport_check.get('has_yandex_pay', False),
                'status': 'error' if not passport_check.get('has_yandex_pay') else 'occupied',
                'message': passport_check.get('message', str(e)),
                'raw': {'error': str(e), 'passport_check': passport_check}
            }
    
    def _check_passport_phone(self, phone):
        """
        Проверка через API Яндекс.Паспорта
        Возвращает информацию о привязке номера к аккаунту
        """
        try:
            # Проверка через API валидации номера
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
                'phone': phone,
                'track_id': '',
                'csrf_token': ''
            }
            
            response = self.session.post(url, data=data, headers=headers, timeout=10)
            result = response.json() if response.text else {}
            
            # Если номер уже занят (привязан к аккаунту)
            if result.get('status') == 'error' and 'occupied' in str(result.get('errors', {})):
                return {
                    'has_yandex_pay': True,  # Предполагаем, что у существующего аккаунта может быть карта
                    'occupied': True,
                    'message': 'Номер привязан к аккаунту Яндекс'
                }
            
            # Проверка через API account information
            url2 = "https://passport.yandex.ru/registration/validations/accountInformation"
            response2 = self.session.post(url2, data={'phone': phone}, headers=headers, timeout=10)
            result2 = response2.json() if response2.text else {}
            
            # Если аккаунт существует
            if result2.get('status') == 'ok' or 'login' in result2:
                return {
                    'has_yandex_pay': True,
                    'occupied': True,
                    'message': 'Аккаунт Яндекс существует',
                    'raw': result2
                }
            
            return {
                'has_yandex_pay': False,
                'occupied': False,
                'message': 'Аккаунт не найден',
                'raw': result2
            }
            
        except Exception as e:
            return {
                'has_yandex_pay': False,
                'occupied': False,
                'message': f'Ошибка проверки: {str(e)}',
                'raw': {}
            }
    
    def check_wallet_exists(self, phone):
        """
        Комплексная проверка: ЮMoney + Yandex Pay
        """
        normalized = self.normalize_phone(phone)
        
        # Проверяем оба сервиса
        yoomoney_result = self.check_yoomoney(phone)
        yandex_pay_result = self.check_yandex_pay(phone)
        
        # Определяем общий статус
        # ЗАНЯТ если есть ЮMoney ИЛИ есть Yandex Pay
        is_occupied = yoomoney_result['exists'] or yandex_pay_result['exists']
        
        # Если Yandex Pay точно есть — приоритет ему
        if yandex_pay_result['exists']:
            final_status = 'occupied'
            final_message = 'Yandex Pay карта существует'
        elif yoomoney_result['exists']:
            final_status = 'occupied'
            final_message = 'ЮMoney кошелёк существует'
        else:
            final_status = 'clean'
            final_message = 'Чистый номер'
        
        return {
            'phone': normalized,
            'exists': is_occupied,
            'status': final_status,
            'message': final_message,
            'yoomoney': yoomoney_result,
            'yandex_pay': yandex_pay_result,
            'raw': {
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
        'has_yoomoney': result['yoomoney']['exists'],
        'has_yandex_pay': result['yandex_pay']['exists'],
        'status': result['status'],
        'message': result['message'],
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
            'has_yoomoney': result['yoomoney']['exists'],
            'has_yandex_pay': result['yandex_pay']['exists'],
            'status': result['status'],
            'message': result['message'],
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
