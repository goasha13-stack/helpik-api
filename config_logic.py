# config_logic.py
# Логика проверки номеров для Helpik

class CheckLogic:
    """
    Логика определения статуса номера:
    
    СТАТУСЫ:
    1. clean (чистый) - нет ID, нет Pay карты. Дату не ищем. Рекомендуем к покупке.
    2. pay_verif (хороший) - есть Pay карта + дата рождения найдена. Рекомендуем к покупке.
    3. pay_no_verif (нужна верификация) - есть Pay карта, но даты нет. Купить можно, нужна верификация.
    4. blocked (стоп) - номер заблокирован. НЕ ПОКУПАТЬ.
    5. id_no_pay (только ID) - есть ID, но нет Pay карты. Нейтральный статус.
    """
    
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
        
        Приоритет:
        1. Блокировка (всегда первый приоритет)
        2. Чистый номер (нет ID и нет Pay)
        3. Есть Pay карта (с верификацией или без)
        4. Только ID без Pay
        """
        # Приоритет 1: Блокировка
        if blocked:
            return 'blocked'
        
        # Приоритет 2: Чистый номер (нет ID и нет Pay)
        if not id_exists and not pay_exists:
            return 'clean'
        
        # Приоритет 3: Есть Pay карта
        if pay_exists:
            if gu_verified and birth_date:
                return 'pay_verif'
            else:
                return 'pay_no_verif'
        
        # Приоритет 4: Есть только ID, нет Pay
        if id_exists and not pay_exists:
            return 'id_no_pay'
        
        return 'unknown'
    
    @classmethod
    def format_output_line(cls, number, id_exists, pay_exists, gu_verified, 
                          birth_date, blocked, status):
        """
        Форматирование строки вывода по твоему шаблону:
        
        79113725286, id нет, pay не открыта,  — , значит нет ни id, ни pay, дальше ничего не нужно искать к этому номеру.. значит это чистый номер . рекомендуем купить (идеальный  номер)
        
        79222909198, id есть, pay открыта, не вериф, (день,месяц,год рождения цифрами в формате дд.мм.гггг ) это значит найти дату,  это значит есть id,есть карта pay, но не прошла вериф гос услуг, . это значит купить можно то нужно верифицировать
        """
        
        # Формируем части строки
        parts = [number]
        
        # ID статус
        if id_exists:
            parts.append("id есть")
        else:
            parts.append("id нет")
        
        # Pay статус
        if pay_exists:
            parts.append("pay открыта")
        else:
            parts.append("pay не открыта")
        
        # Верификация Госуслуг / дата рождения
        if blocked:
            parts.append("блок")
            if birth_date:
                parts.append(f"({birth_date})")
        elif not id_exists and not pay_exists:
            # Чистый номер - дату не показываем
            parts.append("—")
        elif pay_exists:
            if gu_verified and birth_date:
                parts.append(f"гу верифицированы, ({birth_date})")
            else:
                parts.append(f"не вериф, ({birth_date if birth_date else 'дата не найдена'})")
        elif id_exists and not pay_exists:
            # Только ID
            if birth_date:
                parts.append(f"({birth_date})")
            else:
                parts.append("—")
        
        # Добавляем итоговое описание
        rec = cls.get_recommendation(status)
        
        if status == 'clean':
            parts.append(f"значит нет ни id, ни pay, дальше ничего не нужно искать к этому номеру.. значит это чистый номер. {rec['text']}")
        elif status == 'pay_verif':
            parts.append(f"итог это значит есть id,есть карта pay и прошла вериф, {rec['text']}")
        elif status == 'pay_no_verif':
            parts.append(f"это значит найти дату, это значит есть id,есть карта pay, но не прошла вериф гос услуг, это значит купить можно то нужно верифицировать")
        elif status == 'blocked':
            parts.append(f"это значит найти дату рождения ({birth_date if birth_date else 'не найдена'}), блок там это значит есть id,есть карта pay,прошла вериф,но заблокирована. пометить значком стоп")
        elif status == 'id_no_pay':
            parts.append(f"это значит есть id, но нет pay карты. {rec['text']}")
        
        return ", ".join(parts)
    
    @classmethod
    def get_recommendation(cls, status):
        """Получить рекомендацию по статусу"""
        return cls.RECOMMENDATIONS.get(status, cls.RECOMMENDATIONS['unknown'])
    
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
            'buy_recommended': buy_recommended,
            'buy_with_work': buy_with_work,
            'do_not_buy': do_not_buy,
            'neutral': stats['id_no_pay'] + stats['unknown']
        }


# Тестовые кейсы для проверки логики
TEST_CASES = [
    # (номер, id, pay, gu_verified, birth_date, blocked, ожидаемый_статус)
    ("79113725286", False, False, False, None, False, "clean"),
    ("79222909198", True, True, False, None, False, "pay_no_verif"),
    ("79222991829", True, True, False, "15.03.1985", False, "pay_no_verif"),
    ("79222996301", True, True, True, "10.11.1988", False, "pay_verif"),
    ("79133484680", True, True, True, "05.09.1992", True, "blocked"),
    ("79326374121", True, True, True, "18.01.1980", True, "blocked"),
    ("79326379039", True, True, True, "30.06.1995", True, "blocked"),
    ("79001234567", True, False, False, "15.05.1985", False, "id_no_pay"),
]

if __name__ == "__main__":
    # Тестирование логики
    print("Тестирование логики проверки номеров:\n")
    
    for case in TEST_CASES:
        number, id_ok, pay_ok, gu_ok, birth, block, expected = case
        
        status = CheckLogic.determine_status(id_ok, pay_ok, gu_ok, block, birth)
        line = CheckLogic.format_output_line(number, id_ok, pay_ok, gu_ok, birth, block, status)
        
        check = "✓" if status == expected else f"✗ (ожидалось {expected})"
        print(f"{check} {line}\n")
