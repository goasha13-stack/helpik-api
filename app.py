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
    
    def normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return '+' + digits
    
    def check_wallet_exists(self, phone: str):
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
                return {'phone': normalized, 'exists': None, 'status': 'error', 'message': f'HTTP {response.status_code}'}
            
            result = response.json()
            print(f"DEBUG: {normalized} -> {result}")
            
            status = result.get('status', '')
            error = result.get('error', '')
            
            if 'contract_amount' in result:
                return {'phone': normalized, 'exists': True, 'status': 'occupied', 'message': 'Кошелек существует'}
            
            if error == 'payee_not_found':
                return {'phone': normalized, 'exists': False, 'status': 'clean', 'message': 'Кошелек не существует'}
            
            if error == 'limit_exceeded':
                return {'phone': normalized, 'exists': True, 'status': 'occupied', 'message': 'Кошелек существует (лимит)'}
            
            if status == 'success':
                return {'phone': normalized, 'exists': True, 'status': 'occupied', 'message': 'Кошелек найден'}
            
            return {'phone': normalized, 'exists': False, 'status': 'clean', 'message': f'Неизвестно: {error}'}
            
        except Exception as e:
            return {'phone': normalized, 'exists': None, 'status': 'error', 'message': str(e)}

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
        'is_clean': not result['exists'] if result['exists'] is not None else None,
        'has_yoomoney': result['exists'],
        'has_yandex_pay': result['exists'],
        'status': result['status'],
        'message': result['message']
    })

@app.route('/api/check-batch', methods=['POST'])
def check_batch():
    phones = request.json.get('phones', [])
    results = []
    
    for phone in phones:
        result = checker.check_wallet_exists(phone)
        results.append({
            'phone': result['phone'],
            'is_clean': not result['exists'] if result['exists'] is not None else None,
            'has_yoomoney': result['exists'],
            'has_yandex_pay': result['exists'],
            'status': result['status'],
            'message': result['message']
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
