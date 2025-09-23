import os
import json
import time
import logging
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("record_regions.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Конфигурация
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(SCRIPT_DIR, "chrome_profile")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "ati_cookies.json")
FILTERS_DIR = os.path.join(SCRIPT_DIR, "region_filters")
BASE_URL = "https://ati.su"
FREIGHT_URL = "https://loads.ati.su/"
EXPECTED_USERNAME = "Ангелевская Оксана"

# Субъекты РФ
RUSSIAN_REGIONS = [
    "Республика Адыгея", "Республика Алтай", "Республика Башкортостан", "Республика Бурятия",
    "Республика Дагестан", "Республика Ингушетия", "Кабардино-Балкарская Республика",
    "Республика Калмыкия", "Карачаево-Черкесская Республика", "Республика Карелия",
    "Республика Коми", "Республика Крым", "Республика Марий Эл", "Республика Мордовия",
    "Республика Саха (Якутия)", "Республика Северная Осетия-Алания", "Республика Татарстан",
    "Республика Тыва", "Удмуртская Республика", "Республика Хакасия", "Чеченская Республика",
    "Чувашская Республика", "Алтайский край", "Забайкальский край", "Камчатский край",
    "Краснодарский край", "Красноярский край", "Пермский край", "Приморский край",
    "Ставропольский край", "Хабаровский край", "Амурская область", "Архангельская область",
    "Астраханская область", "Белгородская область", "Брянская область", "Владимирская область",
    "Волгоградская область", "Вологодская область", "Воронежская область", "Ивановская область",
    "Иркутская область", "Калининградская область", "Калужская область", "Кемеровская область",
    "Кировская область", "Костромская область", "Курганская область", "Курская область",
    "Ленинградская область", "Липецкая область", "Магаданская область", "Московская область",
    "Мурманская область", "Нижегородская область", "Новгородская область", "Новосибирская область",
    "Омская область", "Оренбургская область", "Орловская область", "Пензенская область",
    "Псковская область", "Ростовская область", "Рязанская область", "Самарская область",
    "Саратовская область", "Сахалинская область", "Свердловская область", "Смоленская область",
    "Тамбовская область", "Тверская область", "Томская область", "Тульская область",
    "Тюменская область", "Ульяновская область", "Челябинская область", "Ярославская область",
    "Москва", "Санкт-Петербург", "Севастополь", "Еврейская автономная область",
    "Ненецкий автономный округ", "Ханты-Мансийский автономный округ - Югра",
    "Чукотский автономный округ", "Ямало-Ненецкий автономный округ"
]

def init_driver(headless=False, profile=True):
    """Инициализация драйвера с настройками"""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless=new")
    else:
        chrome_options.add_argument("--start-maximized")
        
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--lang=ru-RU")
    
    # Использовать профиль браузера если доступен
    if profile and os.path.exists(PROFILE_PATH):
        chrome_options.add_argument(f"--user-data-dir={PROFILE_PATH}")
        chrome_options.add_argument("--profile-directory=Default")
        logging.info("Используется сохраненный профиль Chrome")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(45)
    return driver

def is_logged_in(driver):
    """Проверка авторизации по имени пользователя в шапке"""
    try:
        driver.get(BASE_URL)
        username_element = WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "span.UserInformation__name___JQyR5"))
        )
        if EXPECTED_USERNAME in username_element.text:
            logging.info(f"Авторизация подтверждена: {EXPECTED_USERNAME}")
            return True
        return False
    except Exception:
        return False

def load_session(driver):
    """Загрузка сохраненной сессии через cookies"""
    if os.path.exists(COOKIES_FILE):
        try:
            driver.get(BASE_URL)
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            driver.delete_all_cookies()
            for cookie in cookies:
                if 'domain' in cookie and cookie['domain'].startswith('.'):
                    cookie['domain'] = cookie['domain'][1:]
                if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                    cookie['sameSite'] = 'Lax'
                driver.add_cookie(cookie)
            driver.refresh()
            time.sleep(3)
            return True
        except Exception as e:
            logging.error(f"Ошибка загрузки cookies: {str(e)}")
    return False

def record_region_filter(driver, region_name):
    """Запись фильтра для конкретного региона"""
    # Создаем папку для фильтров, если ее нет
    os.makedirs(FILTERS_DIR, exist_ok=True)
    
    # Создаем безопасное имя файла
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in region_name)
    filter_file = os.path.join(FILTERS_DIR, f"{safe_name}.pkl")
    
    logging.info(f"=== НАСТРОЙКА ФИЛЬТРА ДЛЯ РЕГИОНА: {region_name} ===")
    print("\n=== ИНСТРУКЦИЯ ===")
    print(f"1. Настройте фильтр для региона: {region_name}")
    print("2. В поле 'Откуда' введите регион и выберите его из списка")
    print("3. Настройте другие параметры фильтра (вес, объем и т.д.)")
    print("4. Нажмите кнопку 'Поиск'")
    print("5. Дождитесь загрузки результатов поиска")
    print("6. После этого вернитесь сюда и нажмите Enter\n")
    
    # Переходим на страницу грузов
    driver.get(FREIGHT_URL)
    
    # Ожидаем загрузки страницы
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.Filters_container__3niLd"))
    )
    time.sleep(2)
    
    # Ждем завершения настройки пользователем
    input("Нажмите Enter после настройки фильтра и загрузки результатов >>> ")
    
    # Сохраняем текущий URL и состояние фильтров
    current_url = driver.current_url
    filter_state = {
        'region': region_name,
        'url': current_url,
        'timestamp': int(time.time())
    }
    
    # Сохраняем в файл
    with open(filter_file, 'wb') as f:
        pickle.dump(filter_state, f)
    
    logging.info(f"Фильтр для региона {region_name} сохранен в {filter_file}")
    logging.info(f"URL фильтра: {current_url}")
    
    # Делаем скриншот для подтверждения
    driver.save_screenshot(os.path.join(FILTERS_DIR, f"{safe_name}_confirmation.png"))
    logging.info(f"Скриншот сохранен: {safe_name}_confirmation.png")
    
    return filter_state

def main():
    logging.info("=== ЗАПУСК РЕЖИМА ЗАПИСИ РЕГИОНАЛЬНЫХ ФИЛЬТРОВ ===")
    driver = init_driver(headless=False, profile=True)
    
    try:
        if not load_session(driver) or not is_logged_in(driver):
            logging.error("Не удалось восстановить сессию. Выполните авторизацию в основном парсере.")
            return
        
        logging.info("Сессия успешно восстановлена! Начинаем запись фильтров...")
        
        # Записываем фильтры для каждого региона
        for region in RUSSIAN_REGIONS:
            record_region_filter(driver, region)
            logging.info(f"Фильтр для региона '{region}' записан. Переходим к следующему...")
            
            # Пауза перед следующим регионом
            input("Нажмите Enter для перехода к следующему региону >>> ")
            driver.get(FREIGHT_URL)  # Возвращаемся на чистую страницу
        
        logging.info("Все регионы обработаны! Фильтры сохранены в папке 'region_filters'")
        
    except Exception as e:
        logging.error(f"Критическая ошибка: {str(e)}")
    finally:
        driver.quit()
        logging.info("=== РАБОТА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    main()
