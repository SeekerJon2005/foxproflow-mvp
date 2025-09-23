import os
import json
import time
import shutil
import tempfile
import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

# ---------------------------
# НАСТРОЙКИ
# ---------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "https://ati.su"
PROFILE_PATH = os.path.join(SCRIPT_DIR, "chrome_profile")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "ati_cookies.json")

EXPECTED_USERNAME = "Ангелевская Оксана"
EXPECTED_USERNAME_VARIANTS = [
    "Ангелевская Оксана",
    "Ангелевская Оксана Сергеевна"
]

# ---------------------------
# ДРАЙВЕР
# ---------------------------
def init_driver(headless: bool = False, profile_path: Optional[str] = None) -> webdriver.Chrome:
    chrome_options = Options()

    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--lang=ru-RU")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

    if headless:
        chrome_options.add_argument("--headless=new")

    temp_profile = tempfile.mkdtemp()
    if profile_path and os.path.exists(profile_path):
        try:
            shutil.copytree(
                profile_path,
                temp_profile,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('Singleton*', 'SingletonLock')
            )
            logging.info(f"Профиль {profile_path} скопирован во временную папку: {temp_profile}")
        except Exception as e:
            logging.error(f"Ошибка копирования профиля: {str(e)}")

    chrome_options.add_argument(f"--user-data-dir={temp_profile}")

    logging.info("Инициализация драйвера Chrome для авторизации ATI")
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(10)
    driver.set_script_timeout(10)
    driver.implicitly_wait(2)
    return driver

# ---------------------------
# СЕССИЯ / COOKIES
# ---------------------------
def save_cookies(driver: webdriver.Chrome) -> bool:
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:  # type: ignore[arg-type]
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logging.info(f"Cookies ATI сохранены ({len(cookies)} шт.)")
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения cookies ATI: {e}")
        return False

def load_session(driver: webdriver.Chrome) -> bool:
    if os.path.exists(COOKIES_FILE):
        try:
            driver.get(BASE_URL)
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            driver.delete_all_cookies()
            for cookie in cookies:
                try:
                    if 'domain' in cookie and cookie['domain'].startswith('.'):
                        cookie['domain'] = cookie['domain'][1:]
                    driver.add_cookie(cookie)
                except Exception as cookie_error:
                    logging.warning(f"Ошибка добавления cookie {cookie.get('name')}: {cookie_error}")
            logging.info(f"Загружено {len(cookies)} cookies ATI")
            driver.refresh()
            time.sleep(0.5)
            return True
        except Exception as e:
            logging.error(f"Ошибка загрузки cookies ATI: {e}")
    else:
        logging.warning("Файл cookies ATI не найден")
    return False

# ---------------------------
# ПРОВЕРКА АВТОРИЗАЦИИ
# ---------------------------
def is_logged_in(driver: webdriver.Chrome) -> bool:
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "header")))
        page_source = driver.page_source
        for variant in EXPECTED_USERNAME_VARIANTS:
            if variant in page_source:
                logging.info(f"Авторизация ATI подтверждена: {variant}")
                return True
        logging.warning(f"Имя пользователя не совпадает. Ожидалось: {EXPECTED_USERNAME}")
        return False
    except TimeoutException:
        logging.error("Таймаут проверки авторизации ATI")
        return False
    except WebDriverException as e:
        logging.error(f"Ошибка проверки авторизации ATI: {e}")
        return False

# ---------------------------
# РУЧНАЯ АВТОРИЗАЦИЯ
# ---------------------------
def manual_login() -> bool:
    os.makedirs(PROFILE_PATH, exist_ok=True)
    try:
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
    except Exception as e:
        logging.error(f"Ошибка запуска драйвера ATI: {e}")
        return False
    try:
        logging.info("=== РУЧНАЯ АВТОРИЗАЦИЯ ATI ===")
        driver.get(BASE_URL)
        print("\n=== ИНСТРУКЦИЯ ===")
        print("1. В открывшемся браузере выполните вход в аккаунт ATI")
        print(f"2. Убедитесь, что справа вверху указано: {EXPECTED_USERNAME}")
        print("3. Вернитесь в консоль и нажмите Enter\n")
        input("Нажмите Enter после авторизации >>> ")
        if is_logged_in(driver):
            save_cookies(driver)
            return True
        return False
    except Exception as e:
        logging.error(f"Критическая ошибка авторизации ATI: {e}")
        return False
    finally:
        try:
            driver.quit()
        except Exception:
            pass
