from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import re
import os
import time
import logging

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
    
    ЛОГИКА ВЕРИФИКАЦИИ:
    - Верифицирован = есть Pay карта + найдена дата рождения в Госуслугах
    - Не верифицирован = есть Pay карта, но дата в Госуслугах не найдена
    - Чистый = нет Pay карты И нет Yandex ID
    
    ПОИСК ДАТЫ РОЖДЕНИЯ:
    - Ищется для ВСЕХ номеров, кроме чистых (где нет ID и нет Pay)
    - То есть ищем если: есть Pay ИЛИ есть ID ИЛИ есть блокировка
    """
    
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
        
        ДАТА ИЩЕТСЯ ДЛЯ ВСЕХ НОМЕРОВ, КРОМЕ ЧИСТЫХ (где нет ID и нет Pay).
        
        ЭТО КЛЮЧЕВОЙ ПАРАМЕТР для определения верификации:
        - Если дата найдена → Госуслуги подтверждены → верификация пройдена
        - Если даты нет → Госуслуги не подтверждены → нужна верификация
        
        Дата рождения нужна для верификации номера через Госуслуги.
        Если при верификации указана неверная дата — вериф не пройдёт.
        
        Returns:
            str: Дата в формате ДД.ММ.ГГГГ или None
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
            
            logger.info("Дата рождения не найдена (Госуслуги не подтверждены)")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при проверке Госуслуг: {e}")
            return None
    
    def check_yandex(self, phone):
        """
        Проверка Yandex ID, Pay, блокировки
        
        Returns:
            dict: {'id': bool, 'pay': bool, 'blocked': bool}
        """
        normalized = self.normalize_phone(phone)
        
        result = {
            'id': False,
            'pay': False,
            'blocked': False
        }
        
        # Проверка Yandex ID и блокировки через паспорт
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
            elif data.get('status') == 'ok':
                # Номер свободен - ни ID ни блока
                pass
            
            # Дополнительная проверка accountInformation
            url2 = "https://passport.yandex.ru/registration/validations/accountInformation"
            response2 = self.session.post(url2, data={'phone': '+' + normalized}, headers=headers, timeout=10)
            data2 = response2.json() if response2.text else {}
            
            if data2.get('status') == 'ok' or data2.get('login'):
                result['id'] = True
                
        except Exception as e:
            logger.error(f"Ошибка проверки Yandex ID: {e}")
        
        # Проверка Yandex Pay (открыта ли карта)
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
            
            # Проверка через статус пользователя
            url2 = "https://pay.yandex.ru/api/v1/user/status"
            response2 = self.session.post(url2, json={'phone': '+' + normalized}, headers=headers, timeout=10)
            data2 = response2.json() if response2.text else {}
            
            if data2.get('has_active_card') or data2.get('card_status') == 'active':
                result['pay'] = True
                
        except Exception as e:
            logger.error(f"Ошибка проверки Yandex Pay: {e}")
        
        return result
    
    def check_number(self, phone):
        """
        Полная проверка одного номера
        
        ЛОГИКА:
        1. Проверяем Yandex (ID, Pay карта, блок)
        2. Если нет ID и нет Pay карты → ЧИСТЫЙ номер (не ищем дату рождения)
        3. Если есть ID ИЛИ Pay карта ИЛИ блок → ищем дату рождения в Госуслугах
        4. Если Pay карта есть:
           - Дата найдена → ВЕРИФИЦИРОВАН
           - Даты нет → НЕ ВЕРИФИЦИРОВАН (нужна дата бывшего владельца)
        
        Returns:
            dict: Результат проверки
        """
        normalized = self.normalize_phone(phone)
        logger.info(f"Проверка номера: {normalized}")
        
        # Шаг 1: Проверяем Яндекс (ID, Pay карта, блок)
        yandex = self.check_yandex(phone)
        
        # Шаг 2: Определяем нужно ли искать дату рождения
        need_birth_date = CheckLogic.need_birth_date_search(yandex['id'], yandex['pay'])
        
        # Шаг 3: Если номер чистый (нет ID и нет Pay) — сразу возвращаем результат
        if not need_birth_date:
            return {
                'number': normalized,
                'id': False,
                'pay': False,
                'gu_verified': False,
                'birth_date': None,
                'blocked': False,
                'status': 'clean'
            }
        
        # Шаг 4: Для всех остальных ищем дату рождения в Госуслугах
        birth_date = self.check_gosuslugi_date(phone)
        
        # Шаг 5: Определяем верификацию ГУ (только если есть Pay карта)
        # ВЕРИФИЦИРОВАН = Pay карта есть + дата рождения найдена
        gu_verified = yandex['pay'] and birth_date is not None
        
        # Шаг 6: Определяем финальный статус
        status = CheckLogic.determine_status(
            id_exists=yandex['id'],
            pay_exists=yandex['pay'],
            gu_verified=gu_verified,
            blocked=yandex['blocked'],
            birth_date=birth_date
        )
        
        return {
            'number': normalized,
            'id': yandex['id'],
            'pay': yandex['pay'],
            'gu_verified': gu_verified,
            'birth_date': birth_date,
            'blocked': yandex['blocked'],
            'status': status
        }
    
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
    
    Request: {"phones": ["79113725286", "79222909198", ...]}
    Response: {"total": N, "results": [...], "stats": {...}, "text_output": "..."}
    """
    phones = request.json.get('phones', [])
    
    if not phones:
        return jsonify({'error': 'Номера не указаны'}), 400
    
    results = []
    output_lines = []
    
    try:
        for i, phone in enumerate(phones):
            # Пересоздаем драйвер каждые 3 номера для стабильности
            if i > 0 and i % 3 == 0:
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
                time.sleep(3)
        
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
