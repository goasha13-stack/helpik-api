# config_logic.py
# Логика проверки номеров для Helpik
# Определяет правила интерпретации результатов

class CheckLogic:
    """
    Логика определения статуса номера:
    
    Параметры проверки:
    - id (bool): Есть ли Yandex ID (аккаунт в Яндексе)
    - pay (bool): Есть ли открытая карта Yandex Pay
    - gu_verified (bool): Подтверждено ли в Госуслугах (по наличию даты рождения)
    - birth_date (str): Дата рождения ДД.ММ.ГГГГ или None
    - blocked (bool): Есть ли блокировка/ограничения
    
    Ключевое правило:
    - ВЕРИФИЦИРОВАН = есть Pay карта + найдена дата в Госуслугах
    - НЕ ВЕРИФИЦИРОВАН = есть Pay карта, но дата в Госуслугах НЕ найдена
    - ЧИСТЫЙ = нет Pay карты И нет Yandex ID
    
    ДАТА РОЖДЕНИЯ: Ищется для ВСЕХ номеров, кроме чистых (где нет ID и нет Pay)
    """
    
    # Приоритеты статусов (для отображения)
    STATUS_PRIORITY = {
        'blocked': 0,      # Высший приоритет - всегда показываем блок
        'pay_verif': 1,    # Хороший номер с верификацией
        'pay_no_verif': 2, # Нужна верификация
        'id_no_pay': 3,    # Только ID, нет Pay
        'clean': 4,        # Чистый номер
        'unknown': 5       # Неопределённый
    }
    
    # Иконки для отображения
    ICONS = {
        'yes': '✅',
        'no': '❌',
        'warning': '⚠️',
        'stop': '🛑',
        'clean': '✨',
        'unknown': '❓'
    }
    
    # Рекомендации по статусам
    RECOMMENDATIONS = {
        'clean': {
            'text': 'ЧИСТЫЙ — нет ID, нет Pay. Рекомендуем к покупке (идеальный номер)',
            'icon': '✨',
            'color': '#28a745',
            'buy': True,
            'priority': 'high'
        },
        'pay_verif': {
            'text': 'ХОРОШИЙ — Pay карта + подтверждено Госуслугами. Рекомендуем к покупке',
            'icon': '✅',
            'color': '#28a745',
            'buy': True,
            'priority': 'high'
        },
        'pay_no_verif': {
            'text': 'НУЖНА ВЕРИФИКАЦИЯ — Pay есть, но Госуслуги не подтверждены. Купить можно, требуется верификация по дате рождения',
            'icon': '⚠️',
            'color': '#ffc107',
            'buy': True,
            'priority': 'medium'
        },
        'blocked': {
            'text': 'СТОП — номер заблокирован. НЕ ПОКУПАТЬ',
            'icon': '🛑',
            'color': '#dc3545',
            'buy': False,
            'priority': 'stop'
        },
        'id_no_pay': {
            'text': 'Только ID — есть аккаунт Яндекса, но нет Pay карты. Нейтральный статус',
            'icon': '❓',
            'color': '#6c757d',
            'buy': None,
            'priority': 'low'
        },
        'unknown': {
            'text': 'Не удалось определить статус',
            'icon': '❓',
            'color': '#6c757d',
            'buy': None,
            'priority': 'low'
        }
    }
    
    @classmethod
    def determine_status(cls, id_exists, pay_exists, gu_verified, blocked, birth_date):
        """
        Определение статуса номера по параметрам
        
        Args:
            id_exists (bool): Есть ли Yandex ID
            pay_exists (bool): Есть ли открытая карта Pay
            gu_verified (bool): Подтверждено ли в Госуслугах (дата найдена)
            blocked (bool): Есть ли блокировка
            birth_date (str or None): Дата рождения
            
        Returns:
            str: Статус номера
        """
        # Приоритет 1: Блокировка (если есть блок - всё остальное не важно)
        if blocked:
            return 'blocked'
        
        # Приоритет 2: Нет ID и нет Pay = чистый номер (идеальный для покупки)
        if not id_exists and not pay_exists:
            return 'clean'
        
        # Приоритет 3: Есть Pay карта
        if pay_exists:
            if gu_verified and birth_date:
                # Pay есть + дата найдена в Госуслугах = верифицирован
                return 'pay_verif'
            else:
                # Pay есть, но дата не найдена = не верифицирован
                return 'pay_no_verif'
        
        # Приоритет 4: Есть только ID, нет Pay карты
        if id_exists and not pay_exists:
            return 'id_no_pay'
        
        # Fallback
        return 'unknown'
    
    @classmethod
    def need_birth_date_search(cls, id_exists, pay_exists):
        """
        Определяет, нужно ли искать дату рождения в Госуслугах
        
        Дата ищется для ВСЕХ номеров, кроме чистых (где нет ID и нет Pay)
        
        Returns:
            bool: True если нужно искать дату, False если не нужно
        """
        # Не ищем дату только для чистых номеров (нет ID и нет Pay)
        if not id_exists and not pay_exists:
            return False
        
        # Для всех остальных ищем дату:
        # - Есть Pay (независимо от верификации)
        # - Есть только ID без Pay
        # - Есть блокировка
        return True
    
    @classmethod
    def get_recommendation(cls, status):
        """Получить рекомендацию по статусу"""
        return cls.RECOMMENDATIONS.get(status, cls.RECOMMENDATIONS['unknown'])
    
    @classmethod
    def format_output_line(cls, number, id_exists, pay_exists, gu_verified, 
                          birth_date, blocked, status):
        """
        Форматирование строки вывода
        
        Формат: номер, id [✅/❌], pay [✅/❌], гу [✅/❌], дд.мм.гггг, [🛑], — комментарий
        """
        id_icon = cls.ICONS['yes'] if id_exists else cls.ICONS['no']
        pay_icon = cls.ICONS['yes'] if pay_exists else cls.ICONS['no']
        gu_icon = cls.ICONS['yes'] if gu_verified else cls.ICONS['no']
        
        parts = [f"{number}, id {id_icon}, pay {pay_icon}, гу {gu_icon}"]
        
        # Добавляем дату если есть (для всех кроме чистых)
        if birth_date:
            parts.append(f", {birth_date}")
        
        # Добавляем блок если есть
        if blocked:
            parts.append(f", блок {cls.ICONS['stop']}")
        
        # Добавляем комментарий-рекомендацию
        rec = cls.get_recommendation(status)
        parts.append(f" — {rec['text']}")
        
        return ''.join(parts)
    
    @classmethod
    def get_stats_summary(cls, results):
        """Получить сводку статистики"""
        total = len(results)
        
        stats = {
            'total': total,
            'clean': 0,
            'pay_verif': 0,
            'pay_no_verif': 0,
            'blocked': 0,
            'id_no_pay': 0,
            'unknown': 0
        }
        
        buy_recommended = 0      # Идеальные + хорошие (clean + pay_verif)
        buy_with_work = 0        # Нужна работа (pay_no_verif)
        do_not_buy = 0           # Блокировки
        
        for r in results:
            status = r.get('status', 'unknown')
            stats[status] = stats.get(status, 0) + 1
            
            rec = cls.get_recommendation(status)
            if rec['buy'] is True:
                if status in ['clean', 'pay_verif']:
                    buy_recommended += 1
                elif status == 'pay_no_verif':
                    buy_with_work += 1
            elif rec['buy'] is False:
                do_not_buy += 1
        
        return {
            'by_status': stats,
            'buy_recommended': buy_recommended,  # Идеальные + хорошие
            'buy_with_work': buy_with_work,      # Нужна верификация
            'do_not_buy': do_not_buy,            # Блокировки
            'neutral': stats['id_no_pay'] + stats['unknown']
        }


# Примеры для тестирования (по вашим данным)
TEST_CASES = [
    # (номер, id, pay, gu_verified, birth_date, blocked, ожидаемый_статус)
    ("79113725286", False, False, False, None, False, "clean"),           # Нет ID, нет Pay = чистый (дату не ищем)
    ("79222909198", True, True, False, None, False, "pay_no_verif"),       # Pay есть, даты нет = не вериф (дату ищем)
    ("79222991829", True, True, False, None, False, "pay_no_verif"),       # Pay есть, даты нет = не вериф (дату ищем)
    ("79222996301", True, True, True, "10.11.1988", False, "pay_verif"),   # Pay есть + дата = вериф (дату ищем)
    ("79133484680", True, True, True, "05.09.1992", True, "blocked"),      # Блок = стоп (дату ищем)
    ("79326374121", True, True, True, "18.01.1980", True, "blocked"),      # Блок = стоп (дату ищем)
    ("79326379039", True, True, True, "30.06.1995", True, "blocked"),      # Блок = стоп (дату ищем)
    ("79001234567", True, False, False, "15.05.1985", False, "id_no_pay"), # Только ID, нет Pay (дату ищем)
]

if __name__ == "__main__":
    # Тестирование логики
    print("Тестирование логики проверки номеров:\n")
    
    for case in TEST_CASES:
        number, id_ok, pay_ok, gu_ok, birth, block, expected = case
        
        # Проверяем нужно ли искать дату
        need_search = CheckLogic.need_birth_date_search(id_ok, pay_ok)
        
        status = CheckLogic.determine_status(id_ok, pay_ok, gu_ok, block, birth)
        line = CheckLogic.format_output_line(number, id_ok, pay_ok, gu_ok, birth, block, status)
        
        check = "✓" if status == expected else f"✗ (ожидалось {expected})"
        date_info = "дату ищем" if need_search else "дату НЕ ищем"
        print(f"{check} [{date_info}] {line}")
    
    print("\n" + "="*70)
    print("Легенда статусов:")
    for status, rec in CheckLogic.RECOMMENDATIONS.items():
        print(f"  {rec['icon']} {status}: {rec['text']}")
    
    print("\n" + "="*70)
    print("Правило поиска даты рождения:")
    print("  Дата ищется для ВСЕХ номеров, КРОМЕ чистых (где нет ID и нет Pay)")
    print("  То есть ищем если: есть Pay ИЛИ есть ID ИЛИ есть блокировка")
