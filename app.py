from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import re
import os
import time
import logging
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Импорт логики
from config_logic import CheckLogic

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


class YandexPayChecker:
    """
    Проверка номеров на:
    - Наличие Yandex ID (аккаунт в Яндексе)
    - Наличие открытой карты Yandex Pay
    - Подтверждение в Госуслугах (по наличию даты рождения)
    - Блокировки/ограничения
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://yoomoney.ru',
            'Referer': 'https://yoomoney.ru/',
            'X-Requested-With': 'XMLHttpRequest'
        })
        self.driver = None
    
    def normalize_phone(self, phone):
        """Нормализация номера телефона к формату 7XXXXXXXXXX"""
        digits = re.sub(r'\D', '', phone)
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '7' + digits
        return digits
    
    def init_selenium(self):
        """Инициализация Selenium WebDriver"""
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
            logger.info("Selenium WebDriver инициализирован")
            return self.driver
        except Exception as e:
            logger.error(f"Ошибка инициализации Selenium: {e}")
            return None
    
    def check_gosuslugi_date(self, phone):
        """
        Получение даты рождения через Госуслуги.
        Returns: str: Дата в формате ДД.ММ.ГГГГ или None
        """
        normalized = self.normalize_phone(phone)
        driver = self.init_selenium()
        
        if not driver:
            logger.warning("WebDriver не доступен, пропускаем проверку Госуслуг")
            return None
        
        try:
            driver.delete_all_cookies()
            driver.get('https://www.gosuslugi.ru/')
            time.sleep(2)
            
            wait = WebDriverWait(driver, 15)
            
            # Кликаем "Войти"
            try:
                login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Войти')]")))
                login_btn.click()
            except:
                pass
            
            time.sleep(2)
            
            # Выбираем вход по телефону
            try:
                phone_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Телефон')]")))
                phone_tab.click()
            except:
                pass
            
            time.sleep(1)
            
            # Вводим номер
            phone_input = wait.until(EC.presence_of_element_located((By.NAME, "mobile")))
            phone_input.clear()
            phone_input.send_keys('+' + normalized)
            
            time.sleep(1)
            
            # Нажимаем продолжить
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
                date_str = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
                logger.info(f"Найдена дата рождения: {date_str}")
                return date_str
            
            logger.info("Дата рождения не найдена")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при проверке Госуслуг: {e}")
            return None
    
    def check_yandex_id(self, phone):
        """
        Проверка наличия Yandex ID и блокировки
        Returns: dict с ключами 'exists' (bool), 'blocked' (bool)
        """
        normalized = self.normalize_phone(phone)
        result = {'exists': False, 'blocked': False}
        
        try:
            # Проверка через паспорт Яндекса
            url = "https://passport.yandex.ru/registration/validations/phone"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://passport.yandex.ru',
                'Referer': 'https://passport.yandex.ru/',
            }
            
            response = self.session.post(
                url, 
                data={'phone': '+' + normalized}, 
                headers=headers, 
                timeout=10
            )
            
            logger.info(f"Yandex ID check response: {response.text}")
            
            try:
                data = response.json()
            except:
                data = {}
            
            # Анализируем ответ
            if data.get('status') == 'error':
                errors = data.get('errors', {})
                phone_errors = errors.get('phone', {}) if isinstance(errors, dict) else {}
                
                if isinstance(phone_errors, dict):
                    error_keys = list(phone_errors.keys())
                    error_str = str(phone_errors).lower()
                    
                    # Проверяем блокировку
                    if any(x in error_str for x in ['blocked', 'fraud', 'limit', 'banned']):
                        result['blocked'] = True
                        result['exists'] = True
                        logger.info(f"Номер {normalized}: заблокирован")
                    # Проверяем занятость (есть ID)
                    elif any(x in error_str for x in ['occupied', 'exists', 'registered']):
                        result['exists'] = True
                        logger.info(f"Номер {normalized}: ID существует")
                        
            elif data.get('status') == 'ok':
                # Номер свободен - нет ID
                logger.info(f"Номер {normalized}: свободен (нет ID)")
                
        except Exception as e:
            logger.error(f"Ошибка проверки Yandex ID: {e}")
            
        return result
    
    def check_yandex_pay(self, phone):
        """
        Проверка наличия открытой карты Yandex Pay
        Returns: bool
        """
        normalized = self.normalize_phone(phone)
        
        try:
            # Пробуем разные endpoints
            endpoints = [
                "https://pay.yandex.ru/api/v1/phone/check",
                "https://pay.yandex.ru/api/v1/user/status",
            ]
            
            for url in endpoints:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Origin': 'https://pay.yandex.ru',
                    }
                    
                    response = self.session.post(
                        url, 
                        json={'phone': '+' + normalized}, 
                        headers=headers, 
                        timeout=10
                    )
                    
                    logger.info(f"Yandex Pay check ({url}): {response.text}")
                    
                    try:
                        data = response.json()
                    except:
                        continue
                    
                    # Проверяем наличие карты
                    if any([
                        data.get('has_card'),
                        data.get('card_available'),
                        data.get('has_active_card'),
                        data.get('card_status') == 'active',
                        data.get('status') == 'active'
                    ]):
                        logger.info(f"Номер {normalized}: Pay карта найдена")
                        return True
                        
                except Exception as e:
                    logger.error(f"Ошибка endpoint {url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Ошибка проверки Yandex Pay: {e}")
            
        logger.info(f"Номер {normalized}: Pay карта не найдена")
        return False
    
    def check_number(self, phone):
        """
        Полная проверка одного номера с корректной логикой
        """
        normalized = self.normalize_phone(phone)
        logger.info(f"\n{'='*50}")
        logger.info(f"Проверка номера: {normalized}")
        logger.info(f"{'='*50}")
        
        # Шаг 1: Проверяем Yandex ID и блокировку
        yandex_id = self.check_yandex_id(phone)
        id_exists = yandex_id['exists']
        blocked = yandex_id['blocked']
        
        logger.info(f"ID exists: {id_exists}, Blocked: {blocked}")
        
        # Шаг 2: Проверяем Pay карту (только если нет блокировки или есть ID)
        pay_exists = False
        if not blocked or id_exists:
            pay_exists = self.check_yandex_pay(phone)
            logger.info(f"Pay exists: {pay_exists}")
        
        # Шаг 3: Определяем, нужно ли искать дату рождения
        # Ищем дату если: есть ID ИЛИ есть Pay ИЛИ есть блокировка
        need_birth_date = id_exists or pay_exists or blocked
        
        birth_date = None
        gu_verified = False
        
        if need_birth_date:
            logger.info("Ищем дату рождения в Госуслугах...")
            birth_date = self.check_gosuslugi_date(phone)
            gu_verified = pay_exists and birth_date is not None
            logger.info(f"Birth date: {birth_date}, GU verified: {gu_verified}")
        else:
            logger.info("Дату рождения не ищем (чистый номер)")
        
        # Шаг 4: Определяем статус
        status = CheckLogic.determine_status(
            id_exists=id_exists,
            pay_exists=pay_exists,
            gu_verified=gu_verified,
            blocked=blocked,
            birth_date=birth_date
        )
        
        result = {
            'number': normalized,
            'id': id_exists,
            'pay': pay_exists,
            'gu_verified': gu_verified,
            'birth_date': birth_date,
            'blocked': blocked,
            'status': status
        }
        
        logger.info(f"Результат: {result}")
        return result
    
    def format_output(self, result):
        """Форматирование строки результата через логику"""
        return CheckLogic.format_output_line(
            number=result['number'],
            id_exists=result['id'],
            pay_exists=result['pay'],
            gu_verified=result['gu_verified'],
            birth_date=result['birth_date'],
            blocked=result['blocked'],
            status=result['status']
        )
    
    def close(self):
        """Закрытие WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver закрыт")
            except:
                pass
            self.driver = None


# Глобальный экземпляр чекера
checker = YandexPayChecker()


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/check-batch', methods=['POST'])
def check_batch():
    """
    API для пакетной проверки номеров
    """
    phones = request.json.get('phones', [])
    
    if not phones:
        return jsonify({'error': 'Номера не указаны'}), 400
    
    results = []
    output_lines = []
    
    try:
        for i, phone in enumerate(phones):
            # Пересоздаем драйвер каждые 2 номера для стабильности
            if i > 0 and i % 2 == 0:
                checker.close()
                time.sleep(2)
            
            # Проверяем номер
            result = checker.check_number(phone)
            formatted = checker.format_output(result)
            
            # Добавляем рекомендацию в результат
            rec = CheckLogic.get_recommendation(result['status'])
            
            results.append({
                'number': result['number'],
                'id': result['id'],
                'pay': result['pay'],
                'gu_verified': result['gu_verified'],
                'birth_date': result['birth_date'],
                'blocked': result['blocked'],
                'status': result['status'],
                'recommendation': rec['text'],
                'buy': rec['buy'],
                'formatted': formatted
            })
            
            output_lines.append(formatted)
            
            # Задержка между запросами
            if i < len(phones) - 1:
                time.sleep(5)  # Увеличил задержку
        
        # Статистика
        stats = CheckLogic.get_stats_summary(results)
        
        return jsonify({
            'total': len(results),
            'results': results,
            'stats': stats,
            'text_output': '\n'.join(output_lines)
        })
        
    except Exception as e:
        logger.error(f"Ошибка при проверке: {e}")
        return jsonify({'error': str(e), 'results': results}), 500
    finally:
        checker.close()


@app.route('/api/logic-info', methods=['GET'])
def logic_info():
    """API для получения информации о логике проверки"""
    return jsonify({
        'statuses': CheckLogic.RECOMMENDATIONS,
        'icons': CheckLogic.ICONS,
        'test_cases': [
            {
                'number': '79113725286',
                'description': 'Чистый номер — нет ID, нет Pay карты (дату не ищем)',
                'expected_status': 'clean'
            },
            {
                'number': '79222909198',
                'description': 'Pay карта есть, но Госуслуги не подтверждены (дату ищем)',
                'expected_status': 'pay_no_verif'
            },
            {
                'number': '79222996301',
                'description': 'Pay карта + подтверждено Госуслугами (дату ищем)',
                'expected_status': 'pay_verif'
            },
            {
                'number': '79001234567',
                'description': 'Только ID, нет Pay карты (дату ищем)',
                'expected_status': 'id_no_pay'
            },
            {
                'number': '79133484680',
                'description': 'Pay карта + верификация, но заблокирован (дату ищем)',
                'expected_status': 'blocked'
            }
        ]
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
