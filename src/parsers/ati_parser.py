# -*- coding: utf-8 -*-
"""
ATI.SU Loads Parser – стабильная версия с унификацией способов погрузки/разгрузки.

Ключевые правки:
- Нормализация loading/unloading (load/unload) + флаги растентовки/оснащения.
- Добавлены поля:
    loading_unloading_raw
    loading_methods_norm / unloading_methods_norm
    full_tent
    equipments
    loading_methods_human / unloading_methods_human
- Сохранена совместимость со старым полем 'loading_method' и существующей структурой.
- Логика и поведение парсера (авторизация, профили, фильтры, пагинация, парсинг карточек,
  сохранение, логи, перезапуски) — без изменений.

Основа: ваш стабильный ati_parser.py (см. аналогичные функции _load_cards_on_page/_extract_from_card/parse_page,
применение фильтра и т.д.). Вставки помечены комментариями "UNIFY LOADING/UNLOADING".
"""

from __future__ import annotations

import os
import re
import gc
import sys
import json
import time
import math
import queue
import pickle
import random
import shutil
import hashlib
import logging
import tempfile
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime, timezone

# =============================================================================
# Selenium
# =============================================================================
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service  # Selenium Manager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

# =============================================================================
# Логирование
# =============================================================================
APP_NAME = "ATI_Freights"
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.handlers.clear()
logger.addHandler(_handler)

# По умолчанию ещё пишем в файл
file_handler = logging.FileHandler("ati_parser.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

# =============================================================================
# Глобальные настройки/пути
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(SCRIPT_DIR, "chrome_profile")  # постоянный профиль
COOKIES_FILE = os.path.join(SCRIPT_DIR, "ati_cookies.json")
FILTER_CONFIG = os.path.join(SCRIPT_DIR, "filter_config.pkl")
REGION_FILTERS_DIR = os.path.join(SCRIPT_DIR, "region_filters")
REGIONS_DATA_DIR = os.path.join(SCRIPT_DIR, "regions_data")
os.makedirs(REGION_FILTERS_DIR, exist_ok=True)
os.makedirs(REGIONS_DATA_DIR, exist_ok=True)

ATI_LOADS_URL = "https://loads.ati.su/?utm_source=header&utm_campaign=new_header"
ATI_LOGIN_URL = "https://ati.su/login"
BASE_URL = "https://ati.su"
FREIGHT_URL = "https://loads.ati.su/"

EXPECTED_USERNAME = "Ангелевская Оксана"
EXPECTED_USERNAME_VARIANTS = [
    "Ангелевская Оксана",
    "Ангелевская Оксана Сергеевна",
]

STOP_FILE = os.path.join(SCRIPT_DIR, "stop.txt")
SELENIUM_EXPLICIT_TIMEOUT = 20
PAGE_STABILIZE_SLEEP = 0.6
MEMORY_LIMIT_MB = 12000
JS_HEAP_LIMIT = 49152

# Восстановление/перезапуски
MAX_DRIVER_RECOVERY_ATTEMPTS = 3
MAX_CONSECUTIVE_ERRORS = 5
DRIVER_REBOOT_INTERVAL = 2  # каждые N регионов профилактический перезапуск

# Сеансовый набор увиденных хэшей — защита от повторов при сбоях Redis
SESSION_SEEN_HASHES: Set[str] = set()

# =============================================================================
# RedisManager (с фолбэком)
# =============================================================================
REDIS_AVAILABLE = False
redis_manager_instance = None
try:
    from src.data_layer.redis_manager import redis_manager as imported_redis_manager  # type: ignore
    redis_manager_instance = imported_redis_manager
    if redis_manager_instance.is_redis_available():
        REDIS_AVAILABLE = True
        logger.info("✅ RedisManager успешно импортирован и подключен")
    else:
        logger.warning("RedisManager импортирован, но Redis недоступен")
except Exception as import_error:
    try:
        from .data_layer.redis_manager import redis_manager as imported_redis_manager  # type: ignore
        redis_manager_instance = imported_redis_manager
        if redis_manager_instance.is_redis_available():
            REDIS_AVAILABLE = True
            logger.info("✅ RedisManager успешно импортирован (относительный путь)")
        else:
            logger.warning("RedisManager импортирован, но Redis недоступен")
    except Exception as inner_error:
        logger.warning(f"❌ RedisManager не доступен: {inner_error}")
        imported_redis_manager = None

if not REDIS_AVAILABLE or redis_manager_instance is None:
    class RedisManagerStub:
        @staticmethod
        def is_duplicate(*_, **__): return False
        @staticmethod
        def cache_data(*_, **__): pass
        @staticmethod
        def get_cached_data(*_, **__): return None
        @staticmethod
        def is_redis_available(): return False
    redis_manager_instance = RedisManagerStub()
    logger.info("ℹ️  RedisManager не используется (локальный режим)")

# =============================================================================
# Утилиты
# =============================================================================
def random_delay(a: float = 0.2, b: float = 0.5) -> None:
    time.sleep(random.uniform(a, b))

def clean_text(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())

def clean_float(x: Optional[str]) -> Optional[float]:
    if not x:
        return None
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", x.replace("\xa0", " "))
    if not m:
        return None
    return float(m.group(0).replace(",", "."))

def clean_int(x: Optional[str]) -> Optional[int]:
    if not x:
        return None
    m = re.search(r"\d[\d\s\xa0]*", x)
    if not m:
        return None
    return int(re.sub(r"[\s\xa0]", "", m.group(0)))

def mem_usage_mb() -> float:
    try:
        import psutil  # type: ignore
        proc = psutil.Process(os.getpid())
        return proc.memory_info().rss / (1024 ** 2)
    except Exception:
        return 0.0

# =============================================================================
# UNIFY LOADING/UNLOADING — нормализация «загрузка/выгрузка/растентовка»
# =============================================================================
HUMAN_MAP = {"rear": "задняя", "side": "боковая", "top": "верхняя"}

def _extract_dirs_from_text(txt: str) -> Set[str]:
    """Вернёт множество {'rear','side','top'} по любым вариантам в тексте."""
    t = " " + (txt or "").lower().replace("ё", "е") + " "
    t = re.sub(r"[\.,:;]+", " ", t)
    dirs: Set[str] = set()
    # задняя
    if re.search(r"(задн\w*|через\s+зад|сзад[иа]?)", t):
        dirs.add("rear")
    # боковая
    if re.search(r"(бок\w*|бортов\w*|через\s+бок)", t):
        dirs.add("side")
    # верхняя
    if re.search(r"(верх\w*|крыш\w*|через\s+верх)", t):
        dirs.add("top")
    return dirs

def parse_loading_unloading(raw: Optional[str]) -> Dict[str, Any]:
    """
    Унифицирует строку/фрагмент карточки: 'задн.', 'верх. бок.', 'загр:задн.', 'загр/выгр: задн.',
    'полная растентовка', 'гидроборт', 'рампа', 'манипулятор', 'кран-борт' и т. п.

    Возвращает структуру:
      {
        'raw': исходная_строка,
        'loading_methods_norm': [...],
        'unloading_methods_norm': [...],
        'full_tent': bool,
        'equipments': [...],
        'loading_methods_human': [...],
        'unloading_methods_human': [...]
      }
    """
    src = (raw or "").strip()
    text = src.lower().replace("ё", "е")

    # 1) Определяем области загр/выгр/общие
    def cut(pattern: str) -> Optional[str]:
        m = re.search(pattern, text)
        return m.group(1) if m else None

    both = cut(r"(?:загр\s*[/+]\s*выгр|загр/выгр|погр\s*[/+]\s*разгр)\s*[:\-]?\s*([^\|;\n]+)")
    only_load = cut(r"(?:загр(?:узка)?|погр(?:узка)?)\s*[:\-]?\s*([^\|;\n]+)")
    only_unload = cut(r"(?:выгр(?:узка)?|разгр(?:узка)?)\s*[:\-]?\s*([^\|;\n]+)")

    common = None
    if not any([both, only_load, only_unload]):
        # Не нашли явных маркировок — извлечём «подстроку» со словами
        m = re.search(r"(?:загр|выгр|растент|гидроборт|рампа|манипулятор|кран[\-\s]?борт)[^|]+", text)
        if m:
            common = m.group(0)
        else:
            common = text  # как есть (последний шанс)

    # 2) Наполняем множества направлений
    load_dirs: Set[str] = set()
    unload_dirs: Set[str] = set()
    if both:
        d = _extract_dirs_from_text(both)
        load_dirs |= d
        unload_dirs |= d
    if only_load:
        load_dirs |= _extract_dirs_from_text(only_load)
    if only_unload:
        unload_dirs |= _extract_dirs_from_text(only_unload)
    if (not both) and (not only_load) and (not only_unload) and common:
        d = _extract_dirs_from_text(common)
        load_dirs |= d
        unload_dirs |= d

    # 3) Растентовка и оснащение
    full_tent = bool(re.search(r"(полная\s+растентовка|полностью\s+растентов|full[-\s]*tent)", text))
    # (частичная/по сторонам — не сохраняем, т.к. в требованиях есть только full_tent)

    equipments: List[str] = []
    if re.search(r"гидро\s*борт|tail\s*lift", text):
        equipments.append("tail_lift")
    if re.search(r"рамп[аы]|dock|пандус", text):
        equipments.append("ramp")
    if re.search(r"манипулятор|кран[\-\s]*борт", text):
        equipments.append("crane")

    loading_human = [HUMAN_MAP[d] for d in sorted(load_dirs)]
    unloading_human = [HUMAN_MAP[d] for d in sorted(unload_dirs)]

    return {
        "raw": src,
        "loading_methods_norm": sorted(list(load_dirs)),
        "unloading_methods_norm": sorted(list(unload_dirs)),
        "full_tent": full_tent,
        "equipments": equipments,
        "loading_methods_human": loading_human,
        "unloading_methods_human": unloading_human,
    }

# =============================================================================
# Модели данных (минимально — как у вас)
# =============================================================================
@dataclass
class PriceInfo:
    amount_rub: Optional[int] = None
    per_km: Optional[float] = None
    vat_included: Optional[bool] = None  # True: "с НДС", False: "без НДС", None: не указано

@dataclass
class LoadingInfoCompat:
    """Совместимость со старой структурой (если она уже используется)."""
    raw: Optional[str] = None
    load: List[str] = field(default_factory=list)
    unload: List[str] = field(default_factory=list)
    tarpaulin_full: bool = False
    tarpaulin_partial: bool = False
    normalized_ru: str = ""

# =============================================================================
# Chrome
# =============================================================================
def init_driver(headless: bool = False, profile_path: Optional[str] = PROFILE_PATH) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")

    if profile_path:
        os.makedirs(profile_path, exist_ok=True)
        options.add_argument(f"--user-data-dir={os.path.abspath(profile_path)}")
        options.add_argument("--profile-directory=Default")

    # Selenium Manager сам подберёт chromedriver (решает WinError 193)
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)

    # Сохраним PID, чтобы уметь мягко закрыть «наш» Chrome
    try:
        with open(os.path.join(SCRIPT_DIR, "chrome_pid.txt"), "w", encoding="utf-8") as f:
            f.write(str(driver.service.process.pid if driver.service and driver.service.process else ""))
    except Exception:
        pass

    logger.info("Инициализация нового драйвера Chrome")
    return driver

# =============================================================================
# Авторизация / Cookies
# =============================================================================
def is_logged_in(driver: webdriver.Chrome) -> bool:
    try:
        driver.get(ATI_LOADS_URL)
        WebDriverWait(driver, 10).until(lambda d: "ati" in d.current_url.lower())
        time.sleep(0.5)
        txt = driver.page_source
        for name in EXPECTED_USERNAME_VARIANTS:
            if name in txt:
                return True
        # дополнительно: есть личный кабинет и т.п.
        return "Выйти" in txt or "Мой профиль" in txt
    except Exception:
        return False

def save_session(driver: webdriver.Chrome) -> None:
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info(f"Cookies успешно сохранены ({len(cookies)} записей)")
    except Exception as e:
        logger.warning(f"Не удалось сохранить cookies: {e}")

def load_session(driver: webdriver.Chrome) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        driver.get(BASE_URL)
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            # домен иногда ругается — перехватываем
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.get(ATI_LOADS_URL)
        return True
    except Exception as e:
        logger.warning(f"Не удалось подлить cookies: {e}")
        return False

# =============================================================================
# Фильтры (запись/применение) — как у вас, без изменения логики
# =============================================================================
def record_filter(driver: webdriver.Chrome) -> List[Tuple[str, str]]:
    logger.info("Откройте страницу с нужным фильтром, затем нажмите Enter в консоли…")
    input("…Ожидаю Enter: ")
    actions: List[Tuple[str, str]] = []
    filtered_url = driver.current_url
    actions.append(("get", filtered_url))
    with open(FILTER_CONFIG, "wb") as f:
        pickle.dump(actions, f)
    logger.info(f"Конфигурация фильтра сохранена: {FILTER_CONFIG}")
    return actions

def apply_recorded_filter(driver: webdriver.Chrome) -> bool:
    if not os.path.exists(FILTER_CONFIG):
        logger.error("Конфигурация фильтра не найдена. Сначала выполните запись фильтра.")
        return False
    try:
        with open(FILTER_CONFIG, "rb") as f:
            actions = pickle.load(f)
        for action in actions:
            if action[0] == "get":
                driver.get(action[1])
                logger.info(f"Применение фильтров: {action[1]}")
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, "section[data-load-id]") or
                                  d.find_elements(By.CSS_SELECTOR, "div.FreightList_list__pB6Hh") or
                                  d.find_elements(By.CSS_SELECTOR, "div.no-results")
                    )
                except TimeoutException:
                    logger.warning("Первая попытка неудачна, обновляем страницу.")
                    driver.refresh()
                    WebDriverWait(driver, 20).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, "section[data-load-id]") or
                                  d.find_elements(By.CSS_SELECTOR, "div.FreightList_list__pB6Hh") or
                                  d.find_elements(By.CSS_SELECTOR, "div.no-results")
                    )
        set_display_rows(driver)
        return True
    except Exception as e:
        logger.error(f"Ошибка применения фильтра: {str(e)}")
        return False

def apply_region_filter(driver: webdriver.Chrome, region_name: str) -> bool:
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in region_name)
    filter_file = os.path.join(REGION_FILTERS_DIR, f"{safe_name}.pkl")
    if not os.path.exists(filter_file):
        logger.error(f"[Filter] не найден файл фильтра для региона: {region_name}")
        return False
    try:
        with open(filter_file, "rb") as f:
            filter_state = pickle.load(f)
        driver.get(filter_state["url"])
        logger.info(f"Применен фильтр для региона: {region_name}")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
            )
        except TimeoutException:
            logger.warning("Первая попытка неудачна, обновляем страницу.")
            driver.refresh()
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
            )
        random_delay(0.1, 0.3)
        set_display_rows(driver)
        return True
    except Exception as e:
        logger.error(f"Ошибка региона {region_name}: {e}")
        return False

def set_display_rows(driver: webdriver.Chrome, rows: int = 100) -> None:
    """
    Устанавливаем «100» строк (селект на странице).
    """
    try:
        # основной вариант: селект рядом с пагинацией
        combo = None
        for css in [
            'div[data-qa="pageSizeSelect"] select',
            "select.page-size",
            "div.PageSize select",
            "select[data-qa='page-size-select']",
        ]:
            try:
                combo = driver.find_element(By.CSS_SELECTOR, css)
                break
            except Exception:
                continue
        if not combo:
            return
        val = combo.get_attribute("value") or ""
        if str(val) == str(rows):
            logger.info(f"Уже установлено значение: {rows}")
            return
        combo.click()
        combo.send_keys(str(rows))
        combo.send_keys(Keys.ENTER)
        time.sleep(0.5)
        logger.info("Успешно установлено отображение 100 строк")
    except Exception:
        pass

# =============================================================================
# Парсинг карточек/страницы
# =============================================================================
def _load_cards_on_page(driver: webdriver.Chrome) -> List[Any]:
    """
    Ищем карточки и даём им «стабилизироваться».
    """
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "section[data-load-id]") or
                      d.find_elements(By.CSS_SELECTOR, "div.FreightList_list__pB6Hh") or
                      d.find_elements(By.CSS_SELECTOR, "div.no-results")
        )
    except TimeoutException:
        return []
    cards = driver.find_elements(By.CSS_SELECTOR, "section[data-load-id]")
    if not cards:
        cards = driver.find_elements(By.CSS_SELECTOR, "div.FreightList_list__pB6Hh section[data-load-id]")
    return cards

def _find_loading_raw(card) -> str:
    """
    Пытаемся вытащить «сырой» блок по загрузке/выгрузке/растентовке так,
    как он отображается на сайте (строку). Фолбэком возьмём всю карточку.
    """
    # Часто это короткие подписи/бейджи. Берём первое совпадение.
    txt_candidates: List[str] = []
    try:
        # бэйджи / строки с ключевыми словами
        nodes = card.find_elements(
            By.XPATH,
            ".//*[contains(translate(., 'ЗАГРВЫГРТЕНТОПОЛНЯБОРТРампМАНИПУЛЯТОРКРАН',\
                                     'загрвыгртентополнябортрампманипуляторкран'),\
                        'загр') or \
               contains(translate(., 'ВЫГР', 'выгр'), 'выгр') or \
               contains(translate(., 'РАСТЕН', 'растен'), 'растент') or \
               contains(translate(., 'ГИДРОБОРТ', 'гидроборт'), 'гидроборт') or \
               contains(translate(., 'МАНИПУЛЯТОР', 'манипулятор'), 'манипулятор') or \
               contains(translate(., 'КРАН', 'кран'), 'кран') or \
               contains(translate(., 'РАМП', 'рамп'), 'рамп')]"
        )
        for n in nodes[:3]:
            t = clean_text(n.text)
            if t:
                txt_candidates.append(t)
    except Exception:
        pass
    if not txt_candidates:
        return clean_text(card.text)
    # склеим, чтобы ничего не потерять
    return "; ".join(dict.fromkeys(txt_candidates))

def _extract_from_card(driver: webdriver.Chrome, card, region: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Стараемся собрать максимум, но при любой недостающей детали карточку не отбрасываем.
    Унификация loading/unloading — через parse_loading_unloading() (без изменения остальной логики).
    """
    try:
        # Идентификаторы
        load_id = card.get_attribute("data-load-id") or ""
        load_uuid = card.get_attribute("data-uuid") or ""

        # URL
        url = None
        try:
            a = card.find_element(By.CSS_SELECTOR, 'a[href*="/freights/"], a[href*="/loads/"], a[href^="https://loads.ati.su/"]')
            url = a.get_attribute("href")
        except Exception:
            pass

        # Маршрут
        route_from, route_to = None, None
        try:
            route_node = card.find_element(By.CSS_SELECTOR, '[data-qa="route"], .route_kNB7w, .Ub5YU')
            txt = clean_text(route_node.text)
            parts = re.split(r"\s+[-–—>→]\s+", txt)
            if len(parts) >= 2:
                route_from, route_to = parts[0], parts[1]
        except Exception:
            txt = clean_text(card.text)
            cities = re.findall(r"[A-ЯЁA-Z][A-ЯЁA-Za-z\-\.\s]+", txt)
            if len(cities) >= 2:
                route_from, route_to = cities[0], cities[1]

        # Вес/объём (часто идут рядом — вида "20 / 82")
        weight_t = None
        volume_m3 = None
        try:
            txt = clean_text(card.text)
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*[тt]\s*/\s*(\d+(?:[.,]\d+)?)\s*(?:м3|m3)", txt, re.I)
            if m:
                weight_t = float(m.group(1).replace(",", "."))
                volume_m3 = float(m.group(2).replace(",", "."))
        except Exception:
            pass

        # Готовность/дистанция (опционально)
        ready = None
        distance_km = None
        try:
            txt = clean_text(card.text)
            m = re.search(r"(готов[^;,\n]+)", txt, re.I)
            if m: ready = m.group(1)
            m = re.search(r"(\d+)\s*км", txt, re.I)
            if m: distance_km = int(m.group(1))
        except Exception:
            pass

        # Тип кузова/FTL/документы/торг/гарантия/приоритет — оставляем как в вашей версии (эвристики)
        body_type, ftl, docs, trade, guarantee_ati_at, priority_atis = None, False, None, None, None, None
        try:
            txt = clean_text(card.text).lower()
            if "отд. машина" in txt or "отд.машина" in txt or "ftl" in txt:
                ftl = True
            if "тент" in txt:
                body_type = "тент"
            if "по ттн" in txt:
                docs = "по ттн"
            if "без торга" in txt:
                trade = "без торга"
            m = re.search(r"гарант\w*\s+ati\W+(\d+)", txt)
            if m: guarantee_ati_at = int(m.group(1))
            m = re.search(r"приор\w*\s+(\d+(?:[.,]\d+)?)", txt)
            if m: priority_atis = float(m.group(1).replace(",", "."))
        except Exception:
            pass

        # Цена (упрощённо — как и было: основное число; валюту выносим в amount_rub/переприсвоить при необходимости)
        price = None
        try:
            txt = clean_text(card.text)
            # символы валют
            curr = "RUB"
            if "€" in txt or "евро" in txt: curr = "EUR"
            if "$" in txt or "usd" in txt:  curr = "USD"
            m = re.search(r"(\d[\d\s\xa0]{2,})", txt)
            if m:
                amount = int(re.sub(r"[\s\xa0]", "", m.group(1)))
                price = {"amount": amount, "currency": curr}
        except Exception:
            pass

        # --- UNIFY LOADING/UNLOADING ---
        loading_raw_str = _find_loading_raw(card)  # как на карточке
        # Старую совместимую структуру ('loading' в вашей модели) мы продолжаем заполнять безопасно
        norm = parse_loading_unloading(loading_raw_str)
        loading_struct_compat = LoadingInfoCompat(
            raw=norm["raw"],
            load=norm["loading_methods_norm"],
            unload=norm["unloading_methods_norm"],
            tarpaulin_full=bool(norm["full_tent"]),
            tarpaulin_partial=False,
            normalized_ru=" | ".join(filter(None, [
                ("погрузка: " + ", ".join([HUMAN_MAP[c] for c in norm["loading_methods_norm"]])) if norm["loading_methods_norm"] else "",
                ("выгрузка: " + ", ".join([HUMAN_MAP[c] for c in norm["unloading_methods_norm"]])) if norm["unloading_methods_norm"] else "",
                ("тент: полная") if norm["full_tent"] else "",
            ]))
        )

        item: Dict[str, Any] = {
            "id": load_id or None,
            "uuid": load_uuid or None,
            "url": url,
            "route_from": route_from,
            "route_to": route_to,
            "ready": ready,
            "distance_km": distance_km,
            "body_type": body_type,
            "ftl": ftl,
            "cargo": None,                 # как и прежде — если в тексте найдёте «ТНП/продукты», можно сюда
            "weight_t": weight_t,
            "volume_m3": volume_m3,
            "docs": docs,
            "prices": price or None,
            "trade": trade,
            "guarantee_ati_at": guarantee_ati_at,
            "priority_atis": priority_atis,

            # Совместимость — старое поле:
            "loading_method": norm["raw"] or None,

            # Совместимая вложенная структура (как была у вас):
            "loading": {
                "raw": loading_struct_compat.raw,
                "load": loading_struct_compat.load,
                "unload": loading_struct_compat.unload,
                "tarpaulin_full": loading_struct_compat.tarpaulin_full,
                "tarpaulin_partial": loading_struct_compat.tarpaulin_partial,
                "normalized_ru": loading_struct_compat.normalized_ru,
            },

            # Новые поля (требования задачи):
            "loading_unloading_raw": norm["raw"],
            "loading_methods_norm": norm["loading_methods_norm"],
            "unloading_methods_norm": norm["unloading_methods_norm"],
            "full_tent": bool(norm["full_tent"]),
            "equipments": norm["equipments"],
            "loading_methods_human": norm["loading_methods_human"],
            "unloading_methods_human": norm["unloading_methods_human"],

            "region": region,
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
        }

        # Минимальный ключ дедупликации — uuid|id|url
        dedup_key = item.get("uuid") or item.get("id") or item.get("url")
        if not dedup_key:
            dedup_key = hashlib.md5(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            item["_hash"] = dedup_key

        return item

    except Exception as e:
        logger.debug(f"extract card err: {e}")
        return None

def parse_page(driver: webdriver.Chrome, region: Optional[str]) -> Tuple[List[Dict[str, Any]], int]:
    cards = _load_cards_on_page(driver)
    total = len(cards)
    items: List[Dict[str, Any]] = []
    for c in cards:
        it = _extract_from_card(driver, c, region=region)
        if not it:
            continue
        key = it.get("uuid") or it.get("id") or it.get("url")
        is_dup = False
        try:
            if key:
                is_dup = bool(redis_manager_instance.is_duplicate("ati_loads", key))  # type: ignore
        except Exception:
            is_dup = False
        if is_dup:
            continue
        items.append(it)
    return items, total

# =============================================================================
# Пагинация / страницы / регионы
# =============================================================================
def get_total_pages(driver: webdriver.Chrome) -> int:
    """
    Аккуратно определяем количество страниц.
    """
    try:
        # Популярный вариант: пагинация с кнопкой «Последняя»
        pagers = driver.find_elements(By.CSS_SELECTOR, "nav[aria-label*='pagination'], ul.pagination, div.Pagination")
        txt = clean_text(driver.page_source)
        # Если найдена «Найдено XXX» — делим на 100
        m = re.search(r"Найдено\s+(\d[\d\s\xa0]*)", txt, re.I)
        if m:
            total = int(re.sub(r"[\s\xa0]", "", m.group(1)))
            return max(1, math.ceil(total / 100))
        # иначе — считаем видимые номера страниц
        nums = re.findall(r">\s*(\d+)\s*<", driver.page_source)
        if nums:
            return int(sorted({int(n) for n in nums})[-1])
    except Exception:
        pass
    return 1

def make_outfile(region: Optional[str]) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if region:
        name = f"{region}_{ts}.jsonl"
    else:
        name = f"ati_{ts}.jsonl"
    return os.path.join(REGIONS_DATA_DIR, name)

def append_jsonl(filename: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with open(filename, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def handle_pagination(driver: webdriver.Chrome, region: Optional[str]) -> None:
    total_pages = get_total_pages(driver)
    out_file = make_outfile(region)
    for page_idx in range(1, total_pages + 1):
        if os.path.exists(STOP_FILE):
            logger.info("Получен сигнал остановки. Сохранение данных…")
            break
        logger.info(f"Перед парсингом страницы {page_idx}. Использование памяти: {mem_usage_mb():.2f} MB")
        items, found = parse_page(driver, region)
        saved = len(items)
        append_jsonl(out_file, items)
        logger.info(f"Страница {page_idx}/{total_pages}: найдено {found}, сохранено {saved}")

# =============================================================================
# Основные сценарии
# =============================================================================
def authorize_flow(driver: webdriver.Chrome) -> None:
    """
    Ручная авторизация один раз: открываем логин-страницу, ждём входа, сохраняем куки.
    """
    driver.get(ATI_LOGIN_URL)
    logger.info("Открыл страницу логина. Выполните вход вручную, затем вернитесь в консоль.")
    input("Нажмите Enter после успешного входа: ")
    if is_logged_in(driver):
        save_session(driver)
        # Скриншот успеха — опционально
        try:
            driver.save_screenshot(os.path.join(SCRIPT_DIR, "auth_success.png"))
        except Exception:
            pass
        logger.info("Авторизация успешна! Теперь можно использовать другие пункты.")
    else:
        logger.error("Не удалось подтвердить авторизацию. Проверьте вход и повторите.")

def parse_with_saved_filter(driver: webdriver.Chrome) -> None:
    if not (load_session(driver) and is_logged_in(driver)):
        logger.error("❌ Не удалось восстановить сессию. Сначала выполните авторизацию (п.1).")
        return
    if not apply_recorded_filter(driver):
        logger.error("❌ Не удалось применить сохранённый фильтр.")
        return
    handle_pagination(driver, region=None)

def setup_all_region_filters(driver: webdriver.Chrome) -> None:
    """
    Псевдо-режим: вы по очереди открываете фильтр нужного региона → Enter.
    Файл с URL сохраняется в region_filters/<Регион>.pkl
    """
    logger.info("Режим записи фильтров по регионам. На каждом шаге откройте нужный регион и жмите Enter.")
    while True:
        region_name = input("Название региона (или пусто для выхода): ").strip()
        if not region_name:
            break
        input("Откройте страницу с нужным фильтром региона и нажмите Enter… ")
        url = driver.current_url
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in region_name)
        with open(os.path.join(REGION_FILTERS_DIR, f"{safe}.pkl"), "wb") as f:
            pickle.dump({"url": url}, f)
        logger.info(f"Сохранён фильтр региона: {region_name}")

def auto_parse_all_regions(driver: webdriver.Chrome) -> None:
    if not (load_session(driver) and is_logged_in(driver)):
        logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1.")
        return
    logger.info("✅ Сессия восстановлена! Начинаем автоматический парсинг регионов…")

    region_files = [f for f in os.listdir(REGION_FILTERS_DIR) if f.endswith(".pkl")]
    region_names = [os.path.splitext(f)[0] for f in region_files]
    if not region_names:
        logger.error("Нет сохранённых региональных фильтров. Используйте пункт 6.")
        return

    for idx, name in enumerate(region_names, 1):
        logger.info(f"Начало обработки региона {name} ({idx}/{len(region_names)}) Использование памяти: {mem_usage_mb():.2f} MB")
        if not apply_region_filter(driver, name):
            logger.error(f"Ошибка региона {name}: Не удалось применить фильтр региона")
            # Перезапустим драйвер и попробуем следующий
            try:
                driver.quit()
            except Exception:
                pass
            driver = init_driver(headless=False, profile_path=PROFILE_PATH)
            if not (load_session(driver) and is_logged_in(driver)):
                logger.error("❌ Не удалось восстановить сессию после перезапуска драйвера.")
                break
            continue

        handle_pagination(driver, region=name)

        if idx % DRIVER_REBOOT_INTERVAL == 0:
            logger.info("Профилактический перезапуск драйвера…")
            try:
                driver.quit()
            except Exception:
                pass
            driver = init_driver(headless=False, profile_path=PROFILE_PATH)
            if not (load_session(driver) and is_logged_in(driver)):
                logger.error("❌ Не удалось восстановить сессию после перезапуска драйвера.")
                break

# =============================================================================
# Меню
# =============================================================================
def main() -> None:
    logger.info("==================================================")
    logger.info("ПАРСЕР ATI.SU - ГИБРИДНАЯ СТАБИЛЬНАЯ ВЕРСИЯ")
    logger.info("==================================================")
    print("Выберите действие:")
    print("1 - Авторизация (требуется при первом запуске)")
    print("2 - Запись параметров фильтра")
    print("3 - Парсинг грузов с применением сохраненного фильтра")
    print("4 - Автоматический парсинг всех регионов")
    print("5 - Создать файл остановки (stop.txt)")
    print("6 - Настройка фильтров для всех регионов (псевдо-режим — аналог п.2 многократно)")
    print("7 - Выход")
    choice = input(">").strip()

    if choice == "1":
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        try:
            authorize_flow(driver)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    elif choice == "2":
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        try:
            if not (load_session(driver) and is_logged_in(driver)):
                logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1")
                return
            record_filter(driver)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    elif choice == "3":
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        try:
            parse_with_saved_filter(driver)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    elif choice == "4":
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        try:
            auto_parse_all_regions(driver)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    elif choice == "5":
        try:
            with open(STOP_FILE, "w", encoding="utf-8") as f:
                f.write("1\n")
            logger.info("Файл остановки создан. Парсинг остановится после завершения текущей страницы.")
        except Exception as e:
            logger.error(f"❌ Ошибка создания файла: {e}")

    elif choice == "6":
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        try:
            if not (load_session(driver) and is_logged_in(driver)):
                logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1")
                return
            logger.info("✅ Сессия восстановлена! Начинаем настройку фильтров регионов…")
            setup_all_region_filters(driver)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    elif choice == "7":
        logger.info("Выход…")
        return
    else:
        logger.warning("❌ Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()
