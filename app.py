from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import re
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

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
        self.driver = None
    
    def normalize_phone(self, phone):
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return digits
    
    def init_selenium(self):
        if self.driver:
            return self.driver
            
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return self.driver
        except:
            return None
    
    def check_gosuslugi_date(self, phone):
        """Получение даты рождения через Госуслуги"""
        normalized = self.normalize_phone(phone)
        driver = self.init_selenium()
        
        if not driver:
            return None
        
        try:
            driver.delete_all_cookies()
            driver.get('https://www.gosuslugi.ru/')
            time.sleep(2)
            
            wait = WebDriverWait(driver, 15)
            
            try:
                login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Войти')]")))
                login_btn.click()
            except:
                pass
            
            time.sleep(2)
            
            try:
                phone_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Телефон')]")))
                phone_tab.click()
            except:
                pass
            
            time.sleep(1)
            
            phone_input = wait.until(EC.presence_of_element_located((By.NAME, "mobile")))
            phone_input.clear()
            phone_input.send_keys('+' + normalized)
            
            time.sleep(1)
            
            try:
                submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Получить') or contains(text(), 'Продолжить')]")
                submit_btn.click()
            except:
                phone_input.submit()
            
            time.sleep(4)
            
            page_text = driver.page_source
            
            # Ищем дату ДД.ММ.ГГГГ
            match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', page_text)
            if match:
                return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
            
            return None
            
        except:
            return None
    
    def check_yandex(self, phone):
        """Проверка Yandex ID, Pay, блокировки"""
        normalized = self.normalize_phone(phone)
        
        result = {
            'id': False,
            'pay': False,
            'blocked': False
        }
        
        # Проверка Yandex ID и блокировки
        try:
            url = "https://passport.yandex.ru/registration/validations/phone"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://passport.yandex.ru',
            }
            
            response = self.session.post(url, data={'phone': '+' + normalized}, headers=headers, timeout=10)
            data = response.json() if response.text else {}
            
            if data.get('status') == 'error':
                errors = data.get('errors', {}).get('phone', {})
                error_str = str(errors).lower()
                
                if 'blocked' in error_str or 'fraud' in error_str or 'limit' in error_str:
                    result['blocked'] = True
                    result['id'] = True
                elif 'occupied' in error_str:
                    result['id'] = True
            
            # Дополнительная проверка accountInformation
            url2 = "https://passport.yandex.ru/registration/validations/accountInformation"
            response2 = self.session.post(url2, data={'phone': '+' + normalized}, headers=headers, timeout=10)
            data2 = response2.json() if response2.text else {}
            
            if data2.get('status') == 'ok' or data2.get('login'):
                result['id'] = True
                
        except:
            pass
        
        # Проверка Yandex Pay
        try:
            url = "https://pay.yandex.ru/api/v1/phone/check"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://pay.yandex.ru',
            }
            
            response = self.session.post(url, json={'phone': '+' + normalized, 'type': 'card_check'}, headers=headers, timeout=10)
            data = response.json() if response.text else {}
            
            if data.get('has_card') or data.get('card_available'):
                result['pay'] = True
            
            # Проверка через статус
            url2 = "https://pay.yandex.ru/api/v1/user/status"
            response2 = self.session.post(url2, json={'phone': '+' + normalized}, headers=headers, timeout=10)
            data2 = response2.json() if response2.text else {}
            
            if data2.get('has_active_card') or data2.get('card_status') == 'active':
                result['pay'] = True
                
        except:
            pass
        
        # Косвенная проверка Pay через ЮMoney если есть ID
        if result['id'] and not result['pay']:
            try:
                url = "https://yoomoney.ru/api/request-payment"
                data = {
                    'pattern_id': 'p2p',
                    'to': '+' + normalized,
                    'amount': '1.00'
                }
                response = self.session.post(url, data=data, timeout=10)
                result_data = response.json() if response.text else {}
                
                # Если есть кошелек, может быть и Pay
                if 'contract_amount' in result_data or result_data.get('status') == 'success':
                    # Проверяем дополнительно
                    pass
            except:
                pass
        
        return result
    
    def check_number(self, phone):
        """Полная проверка одного номера"""
        normalized = self.normalize_phone(phone)
        
        # Сначала проверяем Яндекс (ID, Pay, блок)
        yandex = self.check_yandex(phone)
        
        # Если нет ID и нет Pay — номер чистый, Госуслуги не ищем
        if not yandex['id'] and not yandex['pay']:
            return {
                'number': normalized,
                'id': False,
                'pay': False,
                'gu': False,
                'birth_date': None,
                'blocked': False,
                'status': 'clean'
            }
        
        # Если есть Pay (или ID) — ищем дату рождения в Госуслугах
        birth_date = self.check_gosuslugi_date(phone)
        
        # "гу ✅" = нашли дату рождения
        gu_found = birth_date is not None
        
        return {
            'number': normalized,
            'id': yandex['id'],
            'pay': yandex['pay'],
            'gu': gu_found,
            'birth_date': birth_date,
            'blocked': yandex['blocked'],
            'status': 'pay_with_date' if birth_date else 'pay_no_date'
        }
    
    def format_output(self, result):
        """Форматирование строки результата"""
        n = result['number']
        id_icon = '✅' if result['id'] else '❌'
        pay_icon = '✅' if result['pay'] else '❌'
        gu_icon = '✅' if result['gu'] else '❌'
        
        # Базовая строка
        line = f"{n}, id {id_icon}, pay {pay_icon}, гу {gu_icon}"
        
        # Добавляем дату если есть
        if result['birth_date']:
            line += f", {result['birth_date']}"
        
        # Добавляем блок если есть
        if result['blocked']:
            line += ", блок ✅"
        
        # Добавляем примечание только для чистых
        if result['status'] == 'clean':
            line += " — чист"
        
        return line
    
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

checker = YandexPayChecker()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check-batch', methods=['POST'])
def check_batch():
    phones = request.json.get('phones', [])
    
    if not phones:
        return jsonify({'error': 'Номера не указаны'}), 400
    
    results = []
    output_lines = []
    
    try:
        for i, phone in enumerate(phones):
            # Пересоздаем драйвер каждые 3 номера
            if i > 0 and i % 3 == 0:
                checker.close()
                time.sleep(2)
            
            result = checker.check_number(phone)
            formatted = checker.format_output(result)
            
            results.append({
                'number': result['number'],
                'id': result['id'],
                'pay': result['pay'],
                'gu': result['gu'],
                'birth_date': result['birth_date'],
                'blocked': result['blocked'],
                'status': result['status'],
                'formatted': formatted
            })
            
            output_lines.append(formatted)
            
            # Задержка между запросами
            if i < len(phones) - 1:
                time.sleep(3)
        
        return jsonify({
            'total': len(results),
            'results': results,
            'text_output': '\n'.join(output_lines)
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'results': results}), 500
    finally:
        checker.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
