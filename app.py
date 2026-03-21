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
        return '+' + digits
    
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
        except Exception as e:
            print(f"Selenium init error: {e}")
            return None
    
    def check_gosuslugi_selenium(self, phone):
        normalized = self.normalize_phone(phone)
        driver = self.init_selenium()
        
        if not driver:
            return self.check_gosuslugi_api(phone)
        
        try:
            driver.delete_all_cookies()
            driver.get('https://www.gosuslugi.ru/')
            time.sleep(2)
            
            wait = WebDriverWait(driver, 15)
            
            try:
                login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Войти') or contains(@class, 'login')]")))
                login_btn.click()
            except:
                login_btn = driver.find_element(By.CSS_SELECTOR, "a[href*='login'], button[data-testid='login']")
                login_btn.click()
            
            time.sleep(2)
            
            try:
                phone_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Телефон') or contains(text(), 'телефону')]")))
                phone_tab.click()
            except:
                pass
            
            time.sleep(1)
            
            phone_input = wait.until(EC.presence_of_element_located((By.NAME, "mobile")))
            phone_input.clear()
            phone_input.send_keys(normalized)
            
            time.sleep(1)
            
            try:
                submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Получить') or contains(text(), 'Продолжить') or contains(@type, 'submit')]")
                submit_btn.click()
            except:
                phone_input.submit()
            
            time.sleep(4)
            
            page_text = driver.page_source
            
            patterns = [
                r'(\d{2})\.(\d{2})\.(\d{4})\s*г\.р\.',
                r'(\d{2})\s+([а-яё]+)\s+(\d{4})\s*г\.р?',
                r'дата\s+рождения[:\s]*(\d{2})\.(\d{2})\.(\d{4})',
                r'(\d{2})\.(\d{2})\.(\d{4})',
            ]
            
            birth_date = None
            full_hint = None
            
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) >= 3:
                        day, month, year = groups[0], groups[1], groups[2]
                        
                        month_map = {
                            'января': '01', 'февраля': '02', 'марта': '03',
                            'апреля': '04', 'мая': '05', 'июня': '06',
                            'июля': '07', 'августа': '08', 'сентября': '09',
                            'октября': '10', 'ноября': '11', 'декабря': '12'
                        }
                        month = month_map.get(month.lower(), month)
                        
                        birth_date = {
                            'day': day,
                            'month': month,
                            'year': year,
                            'formatted': f"{day}.{month}.{year}"
                        }
                        full_hint = match.group(0)
                        break
            
            name_patterns = [
                r'([А-ЯЁ][а-яё]+)\s+[А-ЯЁ]\.[А-ЯЁ]\.',
                r'([А-ЯЁ][а-яё]+)\s+[А-ЯЁ]\.',
                r'учётная\s+запись\s+([А-ЯЁ][а-яё]+)',
            ]
            
            name = None
            for pattern in name_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    name = match.group(1)
                    break
            
            has_account = (
                'учётная запись' in page_text.lower() or
                'привязан' in page_text.lower() or
                'владелец' in page_text.lower() or
                birth_date is not None
            )
            
            if birth_date:
                return {
                    'exists': True,
                    'full_hint': full_hint,
                    'name': name,
                    'birth_date': birth_date,
                    'has_full_data': True,
                    'message': f'✅ Найдена: {name or "Владелец"} {birth_date["formatted"]}',
                    'method': 'selenium',
                    'raw': {'page_snippet': page_text[page_text.find('г.р.')-50:page_text.find('г.р.')+50] if 'г.р.' in page_text else ''}
                }
            elif has_account:
                return {
                    'exists': True,
                    'full_hint': None,
                    'name': name,
                    'birth_date': None,
                    'has_full_data': False,
                    'message': '⚠️ Аккаунт найден, дата не определена',
                    'method': 'selenium',
                    'raw': {'page_snippet': page_text[:500]}
                }
            else:
                return {
                    'exists': False,
                    'full_hint': None,
                    'name': None,
                    'birth_date': None,
                    'has_full_data': False,
                    'message': '❌ Учётная запись не найдена',
                    'method': 'selenium',
                    'raw': {}
                }
                
        except Exception as e:
            return {
                'exists': None,
                'full_hint': None,
                'name': None,
                'birth_date': None,
                'has_full_data': False,
                'message': f'⚠️ Ошибка Selenium: {str(e)}',
                'method': 'selenium',
                'raw': {}
            }
    
    def check_gosuslugi_api(self, phone):
        normalized = self.normalize_phone(phone)
        
        try:
            url = "https://esia.gosuslugi.ru/aas/oauth2/api/anonymous/check-identifier"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://gosuslugi.ru',
                'Referer': 'https://www.gosuslugi.ru/',
            }
            
            data = {'identifier': normalized, 'type': 'mobile'}
            response = self.session.post(url, json=data, headers=headers, timeout=10)
            result = response.json() if response.text else {}
            
            if result.get('exists') or result.get('accountExists'):
                year = result.get('birthYear', '')
                return {
                    'exists': True,
                    'full_hint': None,
                    'name': result.get('maskedName', ''),
                    'birth_date': {
                        'day': None,
                        'month': None,
                        'year': year,
                        'formatted': f"??.??.{year}" if year else "??.??.????"
                    } if year else None,
                    'has_full_data': False,
                    'message': f'Найдена (только год): {year}' if year else 'Найдена, год неизвестен',
                    'method': 'api',
                    'raw': result
                }
            
            return {
                'exists': False,
                'full_hint': None,
                'name': None,
                'birth_date': None,
                'has_full_data': False,
                'message': 'Не найдена',
                'method': 'api',
                'raw': result
            }
            
        except Exception as e:
            return {
                'exists': None,
                'full_hint': None,
                'name': None,
                'birth_date': None,
                'has_full_data': False,
                'message': f'Ошибка API: {str(e)}',
                'method': 'api',
                'raw': {}
            }
    
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
            result = response.json() if response.text else {}
            
            status = result.get('status', '')
            error = result.get('error', '')
            
            if 'contract_amount' in result or error == 'limit_exceeded' or status == 'success':
                return {
                    'exists': True,
                    'status': 'occupied',
                    'message': 'Кошелёк существует',
                    'raw': result
                }
            
            if error == 'payee_not_found':
                return {
                    'exists': False,
                    'status': 'clean',
                    'message': 'Кошелёк не существует',
                    'raw': result
                }
            
            return {
                'exists': False,
                'status': 'unknown',
                'message': f'Неизвестно: {error}',
                'raw': result
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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://passport.yandex.ru',
                'Referer': 'https://passport.yandex.ru/',
            }
            
            data = {'phone': normalized, 'track_id': '', 'csrf_token': ''}
            response = self.session.post(url, data=data, headers=headers, timeout=10)
            result = response.json() if response.text else {}
            
            if result.get('status') == 'error':
                errors = result.get('errors', {})
                phone_errors = errors.get('phone', {})
                
                if 'blocked' in str(phone_errors).lower() or 'fraud' in str(phone_errors).lower():
                    return {
                        'exists': True,
                        'blocked': True,
                        'status': 'blocked',
                        'message': f'Номер заблокирован: {phone_errors.get("code", "unknown")}',
                        'raw': result
                    }
                
                if 'occupied' in str(phone_errors).lower():
                    return {
                        'exists': True,
                        'blocked': False,
                        'status': 'occupied',
                        'message': 'Yandex ID существует',
                        'raw': result
                    }
            
            url2 = "https://passport.yandex.ru/registration/validations/accountInformation"
            response2 = self.session.post(url2, data={'phone': normalized}, headers=headers, timeout=10)
            result2 = response2.json() if response2.text else {}
            
            if result2.get('status') == 'ok' or result2.get('login'):
                return {
                    'exists': True,
                    'blocked': False,
                    'status': 'occupied',
                    'message': 'Yandex ID найден',
                    'raw': {'validation': result, 'account_info': result2}
                }
            
            return {
                'exists': False,
                'blocked': False,
                'status': 'clean',
                'message': 'Yandex ID не найден',
                'raw': {'validation': result, 'account_info': result2}
            }
            
        except Exception as e:
            return {
                'exists': False,
                'blocked': False,
                'status': 'error',
                'message': f'Ошибка: {str(e)}',
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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://pay.yandex.ru',
                'Referer': 'https://pay.yandex.ru/',
            }
            
            data = {'phone': normalized, 'type': 'card_check'}
            
            try:
                response = self.session.post(url, json=data, headers=headers, timeout=10)
                result = response.json() if response.text else {}
            except:
                result = {}
            
            # Проверяем через альтернативный эндпоинт
            url2 = "https://pay.yandex.ru/api/v1/user/status"
            try:
                response2 = self.session.post(url2, json={'phone': normalized}, headers=headers, timeout=10)
                result2 = response2.json() if response2.text else {}
            except:
                result2 = {}
            
            # Определяем наличие карты
            has_card = (
                result.get('has_card') or 
                result.get('card_available') or
                result2.get('has_active_card') or
                result2.get('card_status') == 'active'
            )
            
            # Проверяем верификацию
            is_verified = result2.get('verified') or result.get('verified', False)
            
            # Если есть Yandex ID, предполагаем возможность карты
            yandex_id = self.check_yandex_id(phone)
            if yandex_id['exists'] and not has_card:
                # Проверяем через косвенные признаки
                has_card = self._check_yandex_pay_indirect(normalized)
            
            if has_card:
                return {
                    'exists': True,
                    'verified': is_verified,
                    'status': 'occupied',
                    'message': f'Yandex Pay карта есть {"(верифицирована)" if is_verified else "(не верифицирована)"}',
                    'raw': {'check_api': result, 'status_api': result2}
                }
            
            return {
                'exists': False,
                'verified': False,
                'status': 'clean',
                'message': 'Yandex Pay карты нет',
                'raw': {'check_api': result, 'status_api': result2}
            }
            
        except Exception as e:
            return {
                'exists': None,
                'verified': None,
                'status': 'error',
                'message': f'Ошибка: {str(e)}',
                'raw': {}
            }
    
    def _check_yandex_pay_indirect(self, phone):
        """Косвенная проверка через признаки"""
        try:
            # Проверка через quickpay ссылку
            url = f"https://yoomoney.ru/quickpay/confirm?receiver={phone.replace('+', '')}"
            response = self.session.head(url, timeout=10, allow_redirects=True)
            
            # Если редирект на страницу с ошибкой — карты нет
            if 'error' in response.url or response.status_code == 404:
                return False
            
            return None  # Неизвестно
        except:
            return None
    
    def check_wallet_exists(self, phone, use_selenium=True):
        normalized = self.normalize_phone(phone)
        
        # Все проверки
        if use_selenium:
            gosuslugi = self.check_gosuslugi_selenium(phone)
            if gosuslugi['exists'] is None:
                gosuslugi = self.check_gosuslugi_api(phone)
        else:
            gosuslugi = self.check_gosuslugi_api(phone)
        
        yandex_id = self.check_yandex_id(phone)
        yoomoney = self.check_yoomoney(phone)
        yandex_pay = self.check_yandex_pay(phone)
        
        # Статусы
        is_blocked = yandex_id.get('blocked', False)
        is_occupied = yandex_id['exists'] or yoomoney['exists'] or yandex_pay['exists'] or gosuslugi['exists']
        
        # Рекомендация
        if is_blocked:
            recommendation = "❌ НЕ ПОКУПАТЬ: номер заблокирован в Яндексе"
        elif yandex_pay['exists']:
            recommendation = f"💳 Yandex Pay: карта есть {'(верифицирована)' if yandex_pay.get('verified') else '(не верифицирована)'}"
        elif gosuslugi.get('birth_date', {}).get('day'):
            bd = gosuslugi['birth_date']
            recommendation = f"✅ ДАТА РОЖДЕНИЯ: {bd['formatted']} (можно верифицировать)"
        elif gosuslugi.get('birth_date', {}).get('year'):
            bd = gosuslugi['birth_date']
            recommendation = f"⚠️ Только год: {bd['year']}"
        elif is_occupied:
            recommendation = "⚠️ Есть привязки к сервисам Яндекса"
        else:
            recommendation = "✅ ЧИСТЫЙ: можно регистрировать"
        
        return {
            'phone': normalized,
            'exists': is_occupied,
            'blocked': is_blocked,
            'has_gosuslugi': gosuslugi['exists'] if gosuslugi['exists'] is not None else False,
            'birth_date': gosuslugi.get('birth_date'),
            'gosuslugi_name': gosuslugi.get('name'),
            'gosuslugi_method': gosuslugi.get('method', 'unknown'),
            'has_yandex_id': yandex_id['exists'],
            'yandex_blocked': yandex_id.get('blocked', False),
            'has_yoomoney': yoomoney['exists'],
            'has_yandex_pay': yandex_pay['exists'],
            'yandex_pay_verified': yandex_pay.get('verified', False),
            'status': 'blocked' if is_blocked else ('occupied' if is_occupied else 'clean'),
            'recommendation': recommendation,
            'gosuslugi': gosuslugi,
            'yandex_id': yandex_id,
            'yoomoney': yoomoney,
            'yandex_pay': yandex_pay,
            'raw': {
                'gosuslugi': gosuslugi.get('raw', {}),
                'yandex_id': yandex_id.get('raw', {}),
                'yoomoney': yoomoney.get('raw', {}),
                'yandex_pay': yandex_pay.get('raw', {})
            }
        }
    
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

@app.route('/api/check', methods=['POST'])
def check_phone():
    phone = request.json.get('phone', '')
    use_selenium = request.json.get('use_selenium', True)
    
    if not phone:
        return jsonify({'error': 'Номер не указан'}), 400
    
    try:
        result = checker.check_wallet_exists(phone, use_selenium=use_selenium)
        
        return jsonify({
            'phone': result['phone'],
            'is_clean': not result['exists'] and not result['blocked'],
            'is_blocked': result['blocked'],
            'has_gosuslugi': result['has_gosuslugi'],
            'birth_date': result['birth_date'],
            'gosuslugi_name': result['gosuslugi_name'],
            'gosuslugi_method': result['gosuslugi_method'],
            'has_yandex_id': result['has_yandex_id'],
            'yandex_blocked': result['yandex_blocked'],
            'has_yoomoney': result['has_yoomoney'],
            'has_yandex_pay': result['has_yandex_pay'],
            'yandex_pay_verified': result['yandex_pay_verified'],
            'recommendation': result['recommendation'],
            'status': result['status'],
            'gosuslugi_message': result['gosuslugi']['message'],
            'yandex_id_message': result['yandex_id']['message'],
            'yoomoney_message': result['yoomoney']['message'],
            'yandex_pay_message': result['yandex_pay']['message'],
            'debug': result['raw']
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-batch', methods=['POST'])
def check_batch():
    phones = request.json.get('phones', [])
    use_selenium = request.json.get('use_selenium', True)
    
    if not phones:
        return jsonify({'error': 'Номера не указаны'}), 400
    
    results = []
    
    try:
        for i, phone in enumerate(phones):
            if use_selenium and i > 0 and i % 3 == 0:
                checker.close()
                time.sleep(2)
            
            result = checker.check_wallet_exists(phone, use_selenium=use_selenium)
            results.append({
                'phone': result['phone'],
                'is_clean': not result['exists'] and not result['blocked'],
                'is_blocked': result['blocked'],
                'has_gosuslugi': result['has_gosuslugi'],
                'birth_date': result['birth_date'],
                'gosuslugi_name': result['gosuslugi_name'],
                'gosuslugi_method': result['gosuslugi_method'],
                'has_yandex_id': result['has_yandex_id'],
                'yandex_blocked': result['yandex_blocked'],
                'has_yoomoney': result['has_yoomoney'],
                'has_yandex_pay': result['has_yandex_pay'],
                'yandex_pay_verified': result['yandex_pay_verified'],
                'recommendation': result['recommendation'],
                'status': result['status'],
                'gosuslugi_message': result['gosuslugi']['message'],
                'yandex_id_message': result['yandex_id']['message'],
                'yoomoney_message': result['yoomoney']['message'],
                'yandex_pay_message': result['yandex_pay']['message'],
                'debug': result['raw']
            })
            
            if use_selenium and i < len(phones) - 1:
                time.sleep(3)
        
        clean_count = sum(1 for r in results if r.get('is_clean') is True)
        blocked_count = sum(1 for r in results if r.get('is_blocked') is True)
        with_gosuslugi = sum(1 for r in results if r.get('has_gosuslugi') is True)
        with_full_date = sum(1 for r in results if r.get('birth_date', {}).get('day') is not None)
        with_yandex_pay = sum(1 for r in results if r.get('has_yandex_pay') is True)
        
        return jsonify({
            'total': len(results),
            'clean': clean_count,
            'blocked': blocked_count,
            'with_gosuslugi': with_gosuslugi,
            'with_full_date': with_full_date,
            'with_yandex_pay': with_yandex_pay,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'results': results}), 500
    finally:
        checker.close()

@app.route('/api/close-driver', methods=['POST'])
def close_driver():
    checker.close()
    return jsonify({'status': 'closed'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
