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
        normalized = self.normalize_phone(phone)
        
        try:
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
            
            # Проверяем ошибки
            if result.get('status') == 'error':
                errors = result.get('errors', {})
                phone_errors = errors.get('phone', {})
                error_code = phone_errors.get('code', '')
                
                block_indicators = ['blocked', 'fraud', 'limit_exceeded', 'restricted']
                is_blocked = any(ind in error_code.lower() for ind in block_indicators)
                
                if is_blocked:
                    return {
                        'exists': True,
                        'blocked': True,
                        'block_reason': error_code,
                        'status': 'blocked',
                        'message': f'Номер заблокирован: {error_code}',
                        'raw': result
                    }
                
                if 'occupied' in str(phone_errors):
                    return {
                        'exists': True,
                        'blocked': False,
                        'status': 'occupied',
                        'message': 'Yandex ID существует',
                        'raw': result
                    }
            
            # Проверка через accountInformation
            url2 = "https://passport.yandex.ru/registration/validations/accountInformation"
            response2 = self.session.post(url2, data={'phone': normalized}, headers=headers, timeout=10)
            result2 = response2.json() if response2.text else {}
            
            if result2.get('status') == 'ok' or result2.get('login'):
                return {
                    'exists': True,
                    'blocked': False,
                    'status': 'occupied',
                    'message': 'Yandex ID найден',
                    'raw': {
                        'validation': result,
                        'account_info': result2
                    }
                }
            
            return {
                'exists': False,
                'blocked': False,
                'status': 'clean',
                'message': 'Yandex ID не найден',
                'raw': {
                    'validation': result,
                    'account_info': result2
                }
            }
            
        except Exception as e:
            return {
                'exists': False,
                'blocked': False,
                'status': 'error',
                'message': f'Ошибка проверки: {str(e)}',
                'raw': {}
            }
    
    def check_card_eligibility(self, phone):
        """
        Проверка возможности открытия карты Yandex Pay
        """
        normalized = self.normalize_phone(phone)
        
        # Собираем все признаки
        yandex_id = self.check_yandex_id(phone)
        yoomoney = self.check_yoomoney(phone)
        
        eligibility = {
            'can_open_card': True,
            'risk_level': 'low',
            'risk_score': 0,
            'warnings': [],
            'recommendation': '',
            'details': {
                'yandex_id_exists': yandex_id['exists'],
                'yandex_id_blocked': yandex_id.get('blocked', False),
                'yoomoney_exists': yoomoney['exists'],
                'clean_slate': not yandex_id['exists'] and not yoomoney['exists']
            }
        }
        
        # Факторы риска
        if yandex_id.get('blocked'):
            eligibility['can_open_card'] = False
            eligibility['risk_level'] = 'blocked'
            eligibility['risk_score'] = 100
            eligibility['warnings'].append(f"Номер заблокирован: {yandex_id.get('block_reason', 'неизвестно')}")
        
        if yandex_id['exists'] and yoomoney['exists']:
            eligibility['risk_score'] += 30
            eligibility['warnings'].append("Есть и Yandex ID, и ЮMoney — возможно, старый аккаунт")
        
        # Определяем рекомендацию
        if eligibility['risk_level'] == 'blocked':
            eligibility['recommendation'] = "❌ НЕ ПОКУПАТЬ: номер в блоке Яндекса"
        elif eligibility['details']['clean_slate']:
            eligibility['recommendation'] = "✅ ОТЛИЧНО: чистый номер, идеален для новой карты"
        elif not yandex_id['exists'] and not yoomoney['exists']:
            eligibility['recommendation'] = "✅ ХОРОШО: можно регистрировать новый аккаунт"
        elif yandex_id['exists'] and not yandex_id.get('blocked'):
            eligibility['risk_score'] += 20
            eligibility['risk_level'] = 'medium'
            eligibility['recommendation'] = "⚠️ СРЕДНИЙ РИСК: аккаунт существует, нужна проверка"
        else:
            eligibility['recommendation'] = "ℹ️ ТРЕБУЕТ ВНИМАНИЯ: неоднозначная ситуация"
        
        # Итоговый риск
        if eligibility['risk_score'] >= 70:
            eligibility['risk_level'] = 'high'
        elif eligibility['risk_score'] >= 30:
            eligibility['risk_level'] = 'medium'
        
        return eligibility
    
    def check_wallet_exists(self, phone):
        normalized = self.normalize_phone(phone)
        
        yandex_id = self.check_yandex_id(phone)
        yoomoney = self.check_yoomoney(phone)
        eligibility = self.check_card_eligibility(phone)
        
        is_occupied = yandex_id['exists'] or yoomoney['exists'] or yandex_id.get('blocked', False)
        
        return {
            'phone': normalized,
            'exists': is_occupied,
            'blocked': yandex_id.get('blocked', False),
            'status': 'blocked' if yandex_id.get('blocked') else ('occupied' if is_occupied else 'clean'),
            'eligibility': eligibility,
            'yandex_id': yandex_id,
            'yoomoney': yoomoney,
            'raw': {
                'yandex_id': yandex_id.get('raw', {}),
                'yoomoney': yoomoney.get('raw', {})
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
        'is_blocked': result['blocked'],
        'can_open_card': result['eligibility']['can_open_card'],
        'risk_level': result['eligibility']['risk_level'],
        'risk_score': result['eligibility']['risk_score'],
        'recommendation': result['eligibility']['recommendation'],
        'has_yandex_id': result['yandex_id']['exists'],
        'has_yoomoney': result['yoomoney']['exists'],
        'warnings': result['eligibility']['warnings'],
        'details': result['eligibility']['details'],
        'status': result['status'],
        'message': result['yandex_id']['message'],
        'yoomoney_message': result['yoomoney']['message'],
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
            'is_blocked': result['blocked'],
            'can_open_card': result['eligibility']['can_open_card'],
            'risk_level': result['eligibility']['risk_level'],
            'risk_score': result['eligibility']['risk_score'],
            'recommendation': result['eligibility']['recommendation'],
            'has_yandex_id': result['yandex_id']['exists'],
            'has_yoomoney': result['yoomoney']['exists'],
            'warnings': result['eligibility']['warnings'],
            'details': result['eligibility']['details'],
            'status': result['status'],
            'message': result['yandex_id']['message'],
            'yoomoney_message': result['yoomoney']['message'],
            'debug': result['raw']
        })
    
    clean_count = sum(1 for r in results if r.get('is_clean') is True)
    blocked_count = sum(1 for r in results if r.get('is_blocked') is True)
    risky_count = sum(1 for r in results if r.get('risk_level') in ['medium', 'high'])
    
    return jsonify({
        'total': len(results),
        'clean': clean_count,
        'blocked': blocked_count,
        'risky': risky_count,
        'results': results
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
