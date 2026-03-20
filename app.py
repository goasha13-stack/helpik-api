@app.route('/api/check', methods=['POST'])
def check_phone():
    phone = request.json.get('phone', '')
    if not phone:
        return jsonify({'error': 'Номер не указан'}), 400
    
    # Получаем детальную информацию
    result = checker.full_check(phone)
    
    # Добавляем отладочную информацию
    return jsonify({
        'phone': result['phone'],
        'is_clean': result['is_clean'],
        'has_yoomoney': result['has_yoomoney'],
        'debug': result.get('debug_info', {}),  # Покажем что вернул API
        'raw_methods': result.get('methods', {})
    })
