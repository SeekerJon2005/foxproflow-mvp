# -*- coding: utf-8 -*-
"""
ATI TRUCKS Parser (транспорт) — стабильная версия с раздельным профилем Chrome.
Повторяет рабочую логику парсера грузов (ati_parser.py), но под разметку trucks.ati.su.

Ключевые моменты:
- Отдельный профиль Chrome: chrome_profile_transport
- Точечная зачистка Chrome по пути профиля (не трогаем грузовой браузер)
- Сохранение произвольного фильтра (любой маршрут/тип ТС) и парсинг по нему
- Отдельные файлы прогресса: для фильтра и для авто‑обхода регионов
- Redis‑дедупликация с безопасным фолбэком на сеансовый set
- Жёсткий рестарт драйвера с восстановлением состояния до целевой страницы

Селекторы и структура карточек/пагинации — из ваших примеров по trucks.ati.su.
"""

from __future__ import annotations

import os
import re
import gc
import sys
import json
import time
import psutil
import random
import signal
import hashlib
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

# -----------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# -----------------------------------------------------------------------------
# REDIS MANAGER (с фолбэком)
# -----------------------------------------------------------------------------
class _RedisStub:
    """Заглушка RedisManager — одинаковый интерфейс, никаких исключений наружу."""
    def is_redis_available(self) -> bool:
        return False
    def is_duplicate(self, key: str, ttl: int = 24 * 3600) -> bool:
        return False
    def check_and_set(self, key: str, ttl: int = 24 * 3600) -> bool:
        return True
    def set_if_not_exists(self, key: str, ttl: int = 24 * 3600) -> bool:
        return True

def _import_redis_manager() -> Any:
    candidates = [
        "src.data_layer.redis_manager",
        "data_layer.redis_manager",
        "redis_manager",
    ]
    for mod in candidates:
        try:
            module = __import__(mod, fromlist=["redis_manager"])
            rm = getattr(module, "redis_manager", None)
            if rm and getattr(rm, "is_redis_available", None):
                if rm.is_redis_available():
                    logging.info("✅ RedisManager успешно импортирован и подключен")
                else:
                    logging.warning("RedisManager импортирован, но Redis недоступен")
                return rm
        except Exception as e:
            continue
    logging.warning("❌ RedisManager не доступен, используется заглушка")
    return _RedisStub()

redis_manager = _import_redis_manager()
REDIS_ON = bool(getattr(redis_manager, "is_redis_available", lambda: False)())

# -----------------------------------------------------------------------------
# КОНСТАНТЫ/ПУТИ/ПРОФИЛЬ
# -----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ВАЖНО: у транспорта — свой профиль. Не совпадает с грузовым!
PROFILE_PATH = os.path.join(SCRIPT_DIR, "chrome_profile_transport")

COOKIES_FILE = os.path.join(SCRIPT_DIR, "ati_cookies.json")  # общая авторизация пойдёт обоим парсерам
FILTERS_DIR = os.path.join(SCRIPT_DIR, "car_region_filters")  # фильтры для авто‑обхода регионов
DATA_DIR = os.path.join(SCRIPT_DIR, "cars_data")
os.makedirs(FILTERS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# прогрессы разделены:
PROGRESS_FILTER_FILE = os.path.join(SCRIPT_DIR, "car_saved_filter_progress.json")   # пункт 3
PROGRESS_REGIONS_FILE = os.path.join(SCRIPT_DIR, "car_region_progress.json")        # пункт 4

# базовые адреса для транспорта
TRUCKS_BASE = "https://trucks.ati.su/?utm_source=header&utm_campaign=new_header"  # стартовая страница фильтра
EXPECTED_USERNAME = "Ангелевская Оксана"  # для check_login()

# лимиты
JS_HEAP_LIMIT_MB = 48 * 1024
CRITICAL_TIMEOUT = 10  # секунды
DRIVER_RESTART_EVERY_N_PAGES = 10  # как у грузов — жёсткий рестарт раз в N страниц

# сеансовые штуки
SESSION_SEEN_HASHES: Set[str] = set()
current_driver: Optional[webdriver.Chrome] = None
stop_requested: bool = False


# -----------------------------------------------------------------------------
# СПРАВОЧНИК РЕГИОНОВ
# -----------------------------------------------------------------------------
RUSSIAN_REGIONS = [
    "Республика Адыгея", "Республика Алтай", "Республика Башкортостан", "Республика Бурятия",
    "Республика Дагестан", "Республика Ингушетия", "Кабардино-Балкарская Республика",
    "Республика Калмыкия", "Карачаево-Черкесская Республика", "Республика Карелия", "Республика Коми",
    "Республика Крым", "Республика Марий Эл", "Республика Мордовия", "Республика Саха (Якутия)",
    "Республика Северная Осетия-Алания", "Республика Татарстан", "Республика Тыва", "Удмуртская Республика",
    "Республика Хакасия", "Чеченская Республика", "Чувашская Республика", "Алтайский край",
    "Забайкальский край", "Камчатский край", "Краснодарский край", "Красноярский край", "Пермский край",
    "Приморский край", "Ставропольский край", "Хабаровский край", "Амурская область", "Архангельская область",
    "Астраханская область", "Белгородская область", "Брянская область", "Владимирская область",
    "Волгоградская область", "Вологодская область", "Воронежская область", "Ивановская область",
    "Иркутская область", "Калининградская область", "Калужская область", "Кемеровская область",
    "Кировская область", "Костромская область", "Курганская область", "Курская область",
    "Ленинградская область", "Липецкая область", "Магаданская область", "Мурманская область",
    "Нижегородская область", "Новгородская область", "Новосибирская область", "Омская область",
    "Оренбургская область", "Орловская область", "Пензенская область", "Псковская область",
    "Ростовская область", "Рязанская область", "Самарская область", "Саратовская область",
    "Сахалинская область", "Свердловская область", "Смоленская область", "Тамбовская область",
    "Тверская область", "Томская область", "Тульская область", "Тюменская область",
    "Ульяновская область", "Челябинская область", "Ярославская область", "Санкт-Петербург",
    "Еврейская автономная область", "Ненецкий автономный округ",
    "Ханты-Мансийский автономный округ — Югра", "Чукотский автономный округ",
    "Ямало-Ненецкий автономный округ"
]

MOSCOW_OBLAST_COMBINATIONS = [
    "Московская область - Республика Адыгея", "Московская область - Республика Алтай",
    "Московская область - Республика Башкортостан", "Московская область - Республика Бурятия",
    "Московская область - Республика Дагестан", "Московская область - Республика Ингушетия",
    "Московская область - Кабардино-Балкарская Республика", "Московская область - Республика Калмыкия",
    "Московская область - Карачаево-Черкесская Республика", "Московская область - Республика Карелия",
    "Московская область - Республика Коми", "Московская область - Республика Крым",
    "Московская область - Республика Марий Эл", "Московская область - Республика Мордовия",
    "Московская область - Республика Саха (Якутия)", "Московская область - Республика Северная Осетия-Алания",
    "Московская область - Республика Татарстан", "Московская область - Республика Тыва",
    "Московская область - Удмуртская Республика", "Московская область - Республика Хакасия",
    "Московская область - Чеченская Республика", "Московская область - Чувашская Республика",
    "Московская область - Алтайский край", "Московская область - Забайкальский край",
    "Московская область - Камчатский край", "Московская область - Краснодарский край",
    "Московская область - Красноярский край", "Московская область - Пермский край",
    "Московская область - Приморский край", "Московская область - Ставропольский край",
    "Московская область - Хабаровский край", "Московская область - Амурская область",
    "Московская область - Архангельская область", "Московская область - Астраханская область",
    "Московская область - Белгородская область", "Московская область - Брянская область",
    "Московская область - Владимирская область", "Московская область - Волгоградская область",
    "Московская область - Вологодская область", "Московская область - Воронежская область",
    "Московская область - Ивановская область", "Московская область - Иркутская область",
    "Московская область - Калининградская область", "Московская область - Калужская область",
    "Московская область - Кемеровская область", "Московская область - Кировская область",
    "Московская область - Костромская область", "Московская область - Курганская область",
    "Московская область - Курская область", "Московская область - Ленинградская область",
    "Московская область - Липецкая область", "Московская область - Магаданская область",
    "Московская область - Мурманская область", "Московская область - Нижегородская область",
    "Московская область - Новгородская область", "Московская область - Новосибирская область",
    "Московская область - Омская область", "Московская область - Оренбургская область",
    "Московская область - Орловская область", "Московская область - Пензенская область",
    "Московская область - Псковская область", "Московская область - Ростовская область",
    "Московская область - Рязанская область", "Московская область - Самарская область",
    "Московская область - Саратовская область", "Московская область - Сахалинская область",
    "Московская область - Свердловская область", "Московская область - Смоленская область",
    "Московская область - Тамбовская область", "Московская область - Тверская область",
    "Московская область - Томская область", "Московская область - Тульская область",
    "Московская область - Тюменская область", "Московская область - Ульяновская область",
    "Московская область - Челябинская область", "Московская область - Ярославская область",
    "Московская область - Санкт-Петербург", "Московская область - Еврейская автономная область",
    "Московская область - Ненецкий автономный округ",
    "Московская область - Ханты-Мансийский автономный округ — Югра",
    "Московская область - Чукотский автономный округ",
    "Московская область - Ямало-Ненецкий автономный округ"
]

# -----------------------------------------------------------------------------
# СИГНАЛЫ/СТОП
# -----------------------------------------------------------------------------
def _signal_handler(_sig: int, _frame: Any) -> None:
    global stop_requested, current_driver
    stop_requested = True
    logging.info("Получен сигнал остановки. Закрываем драйвер...")
    try:
        if current_driver:
            current_driver.quit()
    finally:
        os._exit(0)

signal.signal(signal.SIGINT, _signal_handler)

# -----------------------------------------------------------------------------
# УТИЛИТЫ
# -----------------------------------------------------------------------------
def _sleep(a: float = 0.05, b: float = 0.18) -> None:
    time.sleep(random.uniform(a, b))

def _hash_dict(d: Dict[str, Any]) -> str:
    try:
        js = json.dumps(d, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(js.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(str(d).encode("utf-8")).hexdigest()

def _is_dup(h: str, ttl: int = 7 * 24 * 3600) -> bool:
    """Безопасный dedup: Redis → фолбэк на сеанс."""
    if h in SESSION_SEEN_HASHES:
        return True
    try:
        # основная сигнатура
        if hasattr(redis_manager, "is_duplicate"):
            try:
                if redis_manager.is_duplicate(h, ttl):
                    return True
            except TypeError:
                if redis_manager.is_duplicate(h):
                    return True
        elif hasattr(redis_manager, "check_and_set"):
            created = bool(redis_manager.check_and_set(h, ttl))
            if not created:
                return True
        elif hasattr(redis_manager, "set_if_not_exists"):
            created = bool(redis_manager.set_if_not_exists(h, ttl))
            if not created:
                return True
    except Exception:
        pass
    SESSION_SEEN_HASHES.add(h)
    return False

# -----------------------------------------------------------------------------
# CHROME: запуск и точечная зачистка по профилю
# -----------------------------------------------------------------------------
def _kill_chrome_by_profile(profile_path: str, timeout: float = 4.0) -> None:
    victims: List[psutil.Process] = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or [])
            if ("chrome" in name or "chromium" in name) and profile_path in cmd:
                victims.append(p)
                victims.extend(p.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for proc in victims:
        try:
            proc.terminate()
        except Exception:
            pass
    _, alive = psutil.wait_procs(victims, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except Exception:
            pass
    psutil.wait_procs(alive, timeout=timeout)

    # снять lock-файлы профиля (чтобы следующий запуск прошёл без конфликтов)
    for fn in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        fp = os.path.join(profile_path, fn)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass

def init_driver(headless: bool = False) -> webdriver.Chrome:
    global current_driver
    os.makedirs(PROFILE_PATH, exist_ok=True)

    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_PATH}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--lang=ru-RU")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--disable-features=Translate,BackForwardCache")
    opts.add_argument(f"--js-flags=--max_old_space_size={JS_HEAP_LIMIT_MB}")
    if headless:
        opts.add_argument("--headless=new")

    logging.info(f"[Chrome] запуск на профиле: {PROFILE_PATH}")
    driver = webdriver.Chrome(service=Service(), options=opts)
    driver.set_page_load_timeout(CRITICAL_TIMEOUT)
    driver.set_script_timeout(CRITICAL_TIMEOUT)
    driver.implicitly_wait(2)
    current_driver = driver
    return driver

def restart_driver(last_url: Optional[str] = None) -> webdriver.Chrome:
    global current_driver
    try:
        if current_driver:
            try:
                current_driver.quit()
            except Exception:
                pass
    finally:
        _kill_chrome_by_profile(PROFILE_PATH)

    for attempt in range(1, 4):
        try:
            logging.info(f"Перезапуск драйвера (попытка {attempt}/3)…")
            drv = init_driver()
            if last_url:
                try:
                    drv.get(last_url)
                except Exception:
                    pass
            current_driver = drv
            return drv
        except Exception as e:
            _sleep(0.5, 1.2)
    raise RuntimeError("Не удалось перезапустить драйвер")

# -----------------------------------------------------------------------------
# COOKIE/AUTH
# -----------------------------------------------------------------------------
def _load_cookies(driver: webdriver.Chrome) -> None:
    if not os.path.exists(COOKIES_FILE):
        return
    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        driver.get("https://ati.su/")
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        logging.info("Загружено %d cookies ATI", len(cookies))
    except Exception as e:
        logging.error("Ошибка загрузки cookies: %s", e)

def _save_cookies(driver: webdriver.Chrome) -> None:
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logging.info("Cookies ATI сохранены (%d шт.)", len(cookies))
    except Exception as e:
        logging.error("Ошибка сохранения cookies ATI: %s", e)

def check_login(driver: webdriver.Chrome) -> bool:
    """Простая проверка авторизации: ищем имя пользователя на ati.su."""
    try:
        driver.get("https://ati.su/")
        _sleep(0.2, 0.4)
        page = driver.page_source
        return EXPECTED_USERNAME in page
    except Exception:
        return False

def ensure_session(driver: webdriver.Chrome) -> None:
    """Подливаем куки и убеждаемся, что мы залогинены под ожидаемым пользователем."""
    if not check_login(driver):
        _load_cookies(driver)
    # повторная проверка
    if not check_login(driver):
        logging.info("=== РУЧНАЯ АВТОРИЗАЦИЯ ATI ===\n\n"
                     "1) В открывшемся браузере войдите в аккаунт ATI\n"
                     f"2) Убедитесь, что справа вверху указано: {EXPECTED_USERNAME}\n"
                     "3) Вернитесь в консоль и нажмите Enter\n")
        input("Нажмите Enter после авторизации >>> ")
        if not check_login(driver):
            raise RuntimeError("Авторизация не подтверждена")
        _save_cookies(driver)
    else:
        logging.info("Авторизация ATI подтверждена: %s", EXPECTED_USERNAME)

# -----------------------------------------------------------------------------
# ПРОЧЕЕ I/O (прогрессы/фильтры)
# -----------------------------------------------------------------------------
def _load_json(path: str, default: Any) -> Any:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _save_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# -----------------------------------------------------------------------------
# ПАГИНАЦИЯ trucks.ati.su
# -----------------------------------------------------------------------------
def get_current_and_total_pages(driver: webdriver.Chrome) -> Tuple[int, int]:
    """
    Читаем верхнюю пагинацию (data-qa="top-pagination"):
      - текущее значение в <input value="…">
      - всего страниц в <button class="total-index_…">N</button>
    """
    try:
        # контейнер пагинации
        container = driver.find_element(By.CSS_SELECTOR, '[data-qa="top-pagination"]')
        # input
        inp = container.find_element(By.CSS_SELECTOR, '[data-qa="input-field"] input')
        current = int(inp.get_attribute("value") or "1")

        # total
        total_btn = container.find_element(By.CSS_SELECTOR, 'button[class*="total-index_"]')
        total = int(total_btn.text.strip())
        return current, total
    except Exception:
        return 1, 1

def click_next_page(driver: webdriver.Chrome) -> bool:
    """
    Нажимаем «вперёд». Возвращаем True, если страница переключилась,
    False — если кнопка «дальше» неактивна/мы на последней странице.
    """
    try:
        container = driver.find_element(By.CSS_SELECTOR, '[data-qa="top-pagination"]')
        next_btn = container.find_element(By.CSS_SELECTOR, 'button[class*="next_"]')
        cls = next_btn.get_attribute("class") or ""
        # иногда на последней странице кнопка есть, но disabled/не кликается
        if "disabled" in cls or "hide" in cls.lower():
            return False
        next_btn.click()
        _sleep(0.15, 0.35)
        return True
    except NoSuchElementException:
        return False
    except WebDriverException:
        return False

def go_to_page(driver: webdriver.Chrome, target_page: int) -> None:
    """Перелистываем вперёд до нужной страницы (для восстановления после рестарта)."""
    cur, total = get_current_and_total_pages(driver)
    if target_page <= cur:
        return
    for _ in range(cur, min(total, target_page)):
        if not click_next_page(driver):
            break

# -----------------------------------------------------------------------------
# ПАРСИНГ КАРТОЧКИ
# -----------------------------------------------------------------------------
def _text_safe(el) -> str:
    try:
        return el.text.strip()
    except Exception:
        return ""

def parse_card(card) -> Dict[str, Any]:
    """
    Парсим карточку транспорта (разметка по вашим примерам data-qa=...).
    """
    data: Dict[str, Any] = {
        "source": "trucks.ati.su",
        "scraped_at": datetime.utcnow().isoformat(),
    }

    try:
        # id карточки
        qa = card.get_attribute("data-qa") or ""
        # обычно выглядит как truck-card-<uuid>
        data["id"] = qa.replace("truck-card-", "") if "truck-card-" in qa else qa

        # блок "transport"
        try:
            transport = card.find_element(By.CSS_SELECTOR, '[data-qa="transport"]')
            info = transport.find_element(By.CSS_SELECTOR, '[data-qa="truck-info"]')
            data["truck_info"] = _text_safe(info)

            # вес/объём/габариты
            try:
                data["weight"] = _text_safe(transport.find_element(By.CSS_SELECTOR, '[data-qa="truck-weight"]'))
            except Exception:
                data["weight"] = ""
            try:
                data["volume"] = _text_safe(transport.find_element(By.CSS_SELECTOR, '[data-qa="truck-volume"]'))
            except Exception:
                data["volume"] = ""
            try:
                data["dimensions"] = _text_safe(transport.find_element(By.CSS_SELECTOR, '[data-qa="truck-dimensions"]'))
            except Exception:
                data["dimensions"] = ""

            try:
                data["loading_params"] = _text_safe(transport.find_element(By.CSS_SELECTOR, '[data-qa="truck-loading-params"]'))
            except Exception:
                data["loading_params"] = ""
        except Exception:
            pass

        # блок погрузки
        try:
            load_td = card.find_element(By.CSS_SELECTOR, '[data-qa="loading-point"]')
            data["loading_city"] = _text_safe(load_td.find_element(By.CSS_SELECTOR, '[data-qa="loading-city"]'))
            try:
                data["loading_distance"] = _text_safe(load_td.find_element(By.CSS_SELECTOR, '[data-qa="loading-car-location"]'))
            except Exception:
                data["loading_distance"] = ""
            try:
                data["loading_periodicity"] = _text_safe(load_td.find_element(By.CSS_SELECTOR, '[data-qa="loading-periodicity"]'))
            except Exception:
                data["loading_periodicity"] = ""
        except Exception:
            pass

        # блок разгрузки
        try:
            unloads = card.find_element(By.CSS_SELECTOR, '[data-qa="unloadings"]')
            data["main_unloading"] = _text_safe(unloads.find_element(By.CSS_SELECTOR, '[data-qa="main-unloading-point-name"]'))

            # дополнительные варианты / с тарифами
            variants = []
            for el in unloads.find_elements(By.CSS_SELECTOR, '[data-qa^="unloading-point-"]'):
                txt = _text_safe(el)
                if txt:
                    variants.append(txt)
            data["unloading_variants"] = variants
        except Exception:
            data["main_unloading"] = ""
            data["unloading_variants"] = []

        # тарифы
        prices = {"cash": "", "wout_nds": "", "with_nds": "", "bargain": False}
        try:
            rate_div = card.find_element(By.CSS_SELECTOR, '[data-qa="rate"]')
            raw = _text_safe(rate_div)
            # простая эвристика:
            m_cash = re.search(r"(\d[\d\s ]*\d)\s*руб.*налич", raw, flags=re.I)
            m_wo = re.search(r"(\d[\d\s ]*\d)\s*руб.*без\s*НДС", raw, flags=re.I)
            m_w = re.search(r"(\d[\d\s ]*\d)\s*руб.*с\s*НДС", raw, flags=re.I)
            prices["cash"] = (m_cash.group(1) if m_cash else "").replace(" ", " ").replace(" ", "")
            prices["wout_nds"] = (m_wo.group(1) if m_wo else "").replace(" ", " ").replace(" ", "")
            prices["with_nds"] = (m_w.group(1) if m_w else "").replace(" ", " ").replace(" ", "")
            prices["bargain"] = ("торг" in raw.lower())
        except Exception:
            pass
        data["prices"] = prices

    except Exception as e:
        data["parse_error"] = str(e)

    data["hash"] = _hash_dict({
        "truck_info": data.get("truck_info"),
        "loading_city": data.get("loading_city"),
        "main_unloading": data.get("main_unloading"),
        "loading_periodicity": data.get("loading_periodicity"),
        "prices": data.get("prices"),
        "dimensions": data.get("dimensions"),
    })
    return data

# -----------------------------------------------------------------------------
# ПАРСИНГ СТРАНИЦЫ
# -----------------------------------------------------------------------------
def parse_page(driver: webdriver.Chrome) -> Tuple[int, int]:
    """
    Возвращаем: (сохранено, дубликатов)
    """
    saved = 0
    dups = 0
    cards = driver.find_elements(By.CSS_SELECTOR, '[data-qa^="truck-card-"]')
    for c in cards:
        item = parse_card(c)
        h = item.get("hash") or _hash_dict(item)
        if _is_dup(h):
            dups += 1
            continue
        # пишем JSONL (режим без БД)
        out = os.path.join(DATA_DIR, "cars.jsonl")
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        saved += 1
    return saved, dups

# -----------------------------------------------------------------------------
# ОБЩИЕ ПОМОЩНИКИ
# -----------------------------------------------------------------------------
def soft_cleanup(driver: webdriver.Chrome) -> None:
    try:
        logging.info("Мягкая очистка памяти")
        gc.collect()
        try:
            driver.execute_script("window.gc && window.gc()")
        except Exception:
            pass
        logging.info("Мягкая очистка памяти выполнена")
    except Exception:
        pass

def recover_and_apply_url(target_page: int, url: str) -> webdriver.Chrome:
    """Жёсткий рестарт и восстановление на нужной странице."""
    drv = restart_driver()
    ensure_session(drv)
    drv.get(url)
    _sleep(0.25, 0.5)
    go_to_page(drv, target_page)
    return drv

# -----------------------------------------------------------------------------
# ПУНКТ 1 — Авторизация/куки
# -----------------------------------------------------------------------------
def cmd_login() -> None:
    drv = init_driver()
    try:
        drv.get("https://ati.su/")
        ensure_session(drv)
        _save_cookies(drv)
    finally:
        try:
            drv.quit()
        except Exception:
            pass

# -----------------------------------------------------------------------------
# ПУНКТ 2 — Запись параметров фильтра (произвольный)
# -----------------------------------------------------------------------------
def cmd_save_ad_hoc_filter() -> None:
    name = input("Введите имя фильтра (например: 'Москва → Екатеринбург, 20т тент'): ").strip()
    if not name:
        logging.error("Имя фильтра пусто — отмена.")
        return

    drv = init_driver()
    try:
        ensure_session(drv)
        drv.get(TRUCKS_BASE)
        print("\nОткройте/настройте фильтр на trucks.ati.su, затем нажмите Enter для сохранения URL…")
        input("> ")

        url = drv.current_url
        if not url or "trucks.ati.su" not in url:
            logging.error("Кажется, вы не на странице trucks.ati.su — фильтр не сохранён.")
            return

        filters = _load_json(PROGRESS_FILTER_FILE, {"filters": {}, "progress": {}})
        filters["filters"][name] = url
        filters["progress"][name] = 1  # сбрасываем прогресс фильтра
        _save_json(PROGRESS_FILTER_FILE, filters)
        print(f"\n✓ Фильтр '{name}' сохранён. Прогресс по фильтру сброшен на 1.\n")

    finally:
        try: drv.quit()
        except Exception: pass

# -----------------------------------------------------------------------------
# ПУНКТ 3 — Парсинг транспорта по сохранённому фильтру
# -----------------------------------------------------------------------------
def cmd_parse_saved_filter() -> None:
    meta = _load_json(PROGRESS_FILTER_FILE, {"filters": {}, "progress": {}})
    filters: Dict[str, str] = meta.get("filters", {})
    progress: Dict[str, int] = meta.get("progress", {})

    if not filters:
        logging.error("Нет сохранённых фильтров. Сначала выполните пункт 2.")
        return

    # берём единственный или спрашиваем имя
    if len(filters) == 1:
        name = list(filters.keys())[0]
    else:
        print("Сохранённые фильтры:")
        for i, k in enumerate(filters.keys(), 1):
            print(f"{i}. {k}")
        name = input("Имя фильтра для парсинга: ").strip()

    url = filters.get(name)
    if not url:
        logging.error("Фильтр '%s' не найден.", name)
        return

    start_page = int(progress.get(name, 1))
    drv = init_driver()
    try:
        ensure_session(drv)
        drv.get(url)
        _sleep(0.2, 0.4)

        # доходим до страницы прогресса
        go_to_page(drv, start_page)
        cur, total = get_current_and_total_pages(drv)
        logging.info("ОБЩЕЕ КОЛИЧЕСТВО СТРАНИЦ: %d", total)

        pages_done = 0
        while True:
            if stop_requested:
                break
            logging.info("Перед парсингом страницы %d. Использование памяти: ~", cur)
            saved, dups = parse_page(drv)
            logging.info("Страница %d/%d: обработано %d, сохранено %d, дубликатов %d",
                         cur, total, saved + dups, saved, dups)

            # прогресс по фильтру
            progress[name] = cur
            _save_json(PROGRESS_FILTER_FILE, {"filters": filters, "progress": progress})

            pages_done += 1
            if pages_done % DRIVER_RESTART_EVERY_N_PAGES == 0 and cur < total:
                logging.info("Жёсткая перезагрузка после страницы %d", cur)
                drv = recover_and_apply_url(cur, url)  # восстановимся на текущей
            else:
                if not click_next_page(drv):
                    logging.info("Кнопка 'Далее' неактивна — последняя страница")
                    break

            cur, total = get_current_and_total_pages(drv)

        logging.info("[DONE] Парсинг по фильтру '%s' завершён.", name)

    finally:
        try: drv.quit()
        except Exception: pass

# -----------------------------------------------------------------------------
# ПУНКТ 6 — Мастер сохранения фильтров для авто‑обхода
# -----------------------------------------------------------------------------
def cmd_save_filters_for_all_regions() -> None:
    print("================================================================")
    print("МАСТЕР СОХРАНЕНИЯ ФИЛЬТРОВ ДЛЯ АВТОПАРСИНГА (trucks.ati.su)")
    print("================================================================")
    print("1 - Только RUSSIAN_REGIONS")
    print("2 - Только MOSCOW_OBLAST_COMBINATIONS")
    print("3 - Оба списка (всё)")
    pick = input("> Выбор набора (Enter=3): ").strip() or "3"
    start_idx_str = input("> Стартовый индекс (Enter=0): ").strip() or "0"

    try:
        start_idx = max(0, int(start_idx_str))
    except ValueError:
        start_idx = 0

    if pick == "1":
        regions = RUSSIAN_REGIONS
    elif pick == "2":
        regions = MOSCOW_OBLAST_COMBINATIONS
    else:
        regions = RUSSIAN_REGIONS + MOSCOW_OBLAST_COMBINATIONS

    print(f"\nВыбрано: {('RUSSIAN_REGIONS' if pick=='1' else 'MOSCOW' if pick=='2' else 'Оба списка (всё)')}. "
          f"Всего регионов: {len(regions)}. Начинаем с idx={start_idx}.\n")

    drv = init_driver()
    try:
        ensure_session(drv)
        stored = _load_json(FILTERS_DIR + "/car_region_filters.json", {})

        for i, region in enumerate(regions[start_idx:], start=start_idx + 1):
            print("----------------------------------------------------------------")
            print(f"[{i}/{len(regions)}] Регион: {region}")
            drv.get(TRUCKS_BASE)
            print("Открыл страницу транспорта. Настройте фильтр вручную (даты/типы/маршруты),")
            print("затем вернитесь в терминал и нажмите Enter для сохранения.")
            print("Введите 's' чтобы пропустить этот регион, 'q' чтобы завершить мастер.")
            cmd = input("> (Enter=сохранить / s=пропустить / q=выход): ").strip().lower()
            if cmd == "q":
                break
            if cmd == "s":
                continue

            try:
                url = current_driver.current_url
                if not url or "trucks.ati.su" not in url:
                    raise RuntimeError("URL пуст или не trucks.ati.su")
                stored[region] = url
                _save_json(FILTERS_DIR + "/car_region_filters.json", stored)
                print(f"✓ Фильтр для региона '{region}' сохранён.")
            except Exception as e:
                logging.warning("[Filter] ошибка сохранения фильтра: %s", e)
                print("! Не удалось сохранить (URL пуст?). Попробуйте ещё раз для этого региона.")
                if input("> Повторить сохранение? (y/N): ").strip().lower() == "y":
                    continue

    finally:
        try: drv.quit()
        except Exception: pass

# -----------------------------------------------------------------------------
# ПУНКТ 4 — Автоматический парсинг всех регионов
# -----------------------------------------------------------------------------
def cmd_auto_parse_all_regions() -> None:
    filters_path = FILTERS_DIR + "/car_region_filters.json"
    region_filters: Dict[str, str] = _load_json(filters_path, {})
    if not region_filters:
        logging.error("Фильтры регионов не найдены. Сначала выполните пункт 6.")
        return

    progress = _load_json(PROGRESS_REGIONS_FILE, {"region": None, "page": 1})
    resume_region = progress.get("region")
    resume_page = int(progress.get("page") or 1)

    drv = init_driver()
    try:
        ensure_session(drv)

        regions = list(region_filters.keys())
        start_index = 0
        if resume_region in region_filters:
            start_index = regions.index(resume_region)

        page_counter = 0
        for idx in range(start_index, len(regions)):
            if stop_requested:
                break

            region = regions[idx]
            url = region_filters[region]
            logging.info("Начало обработки региона %s (%d/%d)", region, idx + 1, len(regions))

            drv.get(url)
            _sleep(0.2, 0.4)

            # восстановление страницы
            target_page = resume_page if (resume_region == region) else 1
            go_to_page(drv, target_page)

            cur, total = get_current_and_total_pages(drv)
            logging.info("ОБЩЕЕ КОЛИЧЕСТВО СТРАНИЦ: %d", total)

            while True:
                if stop_requested:
                    break

                saved, dups = parse_page(drv)
                logging.info("Страница %d/%d: обработано %d, сохранено %d, дубликатов %d",
                             cur, total, saved + dups, saved, dups)

                # обновим прогресс регионов
                _save_json(PROGRESS_REGIONS_FILE, {"region": region, "page": cur})

                page_counter += 1
                if page_counter % DRIVER_RESTART_EVERY_N_PAGES == 0 and cur < total:
                    logging.info("Жёсткая перезагрузка после страницы %d", cur)
                    drv = recover_and_apply_url(cur, url)
                else:
                    if not click_next_page(drv):
                        logging.info("Кнопка 'Далее' неактивна — последняя страница")
                        break

                cur, total = get_current_and_total_pages(drv)

            # регион завершён — сбросим страницу на 1, подготовимся к следующему
            _save_json(PROGRESS_REGIONS_FILE, {"region": region, "page": 1})
            # пауза между регионами
            _sleep(0.8, 1.6)

    finally:
        try: drv.quit()
        except Exception: pass

# -----------------------------------------------------------------------------
# ПУНКТ 5 — Создать stop.txt
# -----------------------------------------------------------------------------
def cmd_create_stop_file() -> None:
    with open(os.path.join(SCRIPT_DIR, "stop.txt"), "w", encoding="utf-8") as f:
        f.write("stop")
    print("✓ stop.txt создан рядом со скриптом.")

# -----------------------------------------------------------------------------
# МЕНЮ
# -----------------------------------------------------------------------------
def interactive_menu() -> None:
    print("==========================================================")
    print("ПОИСК ТРАНСПОРТА (trucks.ati.su)")
    print("==========================================================")
    print("Выберите действие:")
    print("1 - Авторизация (общая, cookies)")
    print("2 - Запись параметров фильтра (произвольный)")
    print("3 - Парсинг транспорта по сохранённому фильтру")
    print("4 - Автоматический парсинг всех регионов")
    print("5 - Создать файл остановки (stop.txt)")
    print("6 - Настройка фильтров для всех регионов")
    print("7 - Выход")
    choice = input("> ").strip()

    if choice == "1":
        cmd_login()
    elif choice == "2":
        cmd_save_ad_hoc_filter()
    elif choice == "3":
        cmd_parse_saved_filter()
    elif choice == "4":
        cmd_auto_parse_all_regions()
    elif choice == "5":
        cmd_create_stop_file()
    elif choice == "6":
        cmd_save_filters_for_all_regions()
    else:
        print("Выход.")

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main(argv: List[str]) -> None:
    if not argv:
        interactive_menu()
        return
    cmd = argv[0].lower()
    if cmd == "login":
        cmd_login()
    elif cmd == "save_filter":
        cmd_save_ad_hoc_filter()
    elif cmd == "parse_filter":
        cmd_parse_saved_filter()
    elif cmd == "parse_all":
        cmd_auto_parse_all_regions()
    elif cmd == "mkstop":
        cmd_create_stop_file()
    else:
        print("Использование:\n"
              "  python ati_cars_parser.py login\n"
              "  python ati_cars_parser.py save_filter\n"
              "  python ati_cars_parser.py parse_filter\n"
              "  python ati_cars_parser.py parse_all\n"
              "  python ati_cars_parser.py mkstop\n")

if __name__ == "__main__":
    main(sys.argv[1:])
