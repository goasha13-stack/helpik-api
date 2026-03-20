from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from checker import YandexPayChecker  # ← Импорт из checker.py
import os

app = Flask(__name__)
CORS(app)

# Создаём экземпляр чекера
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
