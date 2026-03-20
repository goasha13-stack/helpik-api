from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from checker import YandexPayChecker
import os

app = Flask(__name__)
CORS(app)
checker = YandexPayChecker()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check', methods=['POST'])
def check_phone():
    phone = request.json.get('phone', '')
    if not phone:
        return jsonify({'error': 'Номер не указан'}), 400
    
    result = checker.full_check(phone)
    return jsonify(result)

@app.route('/api/check-batch', methods=['POST'])
def check_batch():
    phones = request.json.get('phones', [])
    results = []
    
    for phone in phones:
        result = checker.full_check(phone)
        results.append(result)
    
    clean_count = sum(1 for r in results if r.get('is_clean'))
    occupied_count = len(results) - clean_count
    
    return jsonify({
        'total': len(results),
        'clean': clean_count,
        'occupied': occupied_count,
        'results': results
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
