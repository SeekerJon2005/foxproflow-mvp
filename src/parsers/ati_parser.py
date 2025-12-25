# -*- coding: utf-8 -*-
"""
ATI Transport Parser (loads).
Гибридная стабильная версия с постоянным профилем, корректной пагинацией и нормализацией "загр/выгр/растентовка".

Что добавлено/уточнено (бережно, без поломки логики):
- Полный каталог регионов РФ + комбинации с Московской областью.
- Строгая навигация по страницам: читаем текущую стр. из поля ввода/активной кнопки, сверяем с целевой,
  при несоответствии переходим на нужную. Страницы считаются в рамках текущего фильтра.
- Нормализация способов загрузки/выгрузки/растентовки и оборудования (tail_lift, ramp, crane)
  с сохранением всех старых полей.
- Единоразовый лог Redis (без повторов), безопасный фолбэк.

© FoxProFlow MVP
"""

import os
import json
import logging
import time
import random
import pickle
import signal
import psutil
import gc
import traceback
import re
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Set

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException
)

# ---------------------------
# ЛОГИРОВАНИЕ
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ati_parser.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------
# REDIS MANAGER (с фолбэком, единоразовый лог)
# ---------------------------
REDIS_AVAILABLE = False
redis_manager_instance = None
try:
    # ваш путь к менеджеру redis
    from src.data_layer.redis_manager import redis_manager as imported_redis_manager  # type: ignore
    redis_manager_instance = imported_redis_manager
    if hasattr(redis_manager_instance, "is_redis_available") and redis_manager_instance.is_redis_available():
        REDIS_AVAILABLE = True
        logger.info("✅ Redis подключен (RedisManager)")
    else:
        logger.info("ℹ️  Redis недоступен — работаем без него (фолбэк в память процесса)")
except Exception as e:
    logger.info(f"ℹ️  RedisManager не найден/недоступен ({e}). Работаем без Redis.")
    imported_redis_manager = None

if not REDIS_AVAILABLE or redis_manager_instance is None:
    class RedisManagerStub:
        @staticmethod
        def is_duplicate(*_, **__):
            return False
        @staticmethod
        def cache_data(*_, **__):
            pass
        @staticmethod
        def get_cached_data(*_, **__):
            return None
        @staticmethod
        def is_redis_available():
            return False
    redis_manager_instance = RedisManagerStub()

# ---------------------------
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ/КОНСТАНТЫ
# ---------------------------
stop_parsing = False
current_driver: Optional[webdriver.Chrome] = None

# Сеансовый набор увиденных хэшей — защита от повторов при сбоях Redis
SESSION_SEEN_HASHES: Set[str] = set()

MAX_DRIVER_RECOVERY_ATTEMPTS = 3
MAX_CONSECUTIVE_ERRORS = 5
DRIVER_REBOOT_INTERVAL = 2  # регионов

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(SCRIPT_DIR, "chrome_profile")        # постоянный профиль
COOKIES_FILE = os.path.join(SCRIPT_DIR, "ati_cookies.json")
FILTER_CONFIG = os.path.join(SCRIPT_DIR, "filter_config.pkl")
REGION_FILTERS_DIR = os.path.join(SCRIPT_DIR, "region_filters")
BASE_URL = "https://ati.su"
FREIGHT_URL = "https://loads.ati.su/?utm_source=header&utm_campaign=new_header"

EXPECTED_USERNAME_VARIANTS = [
    "Ангелевская Оксана",
    "Ангелевская Оксана Сергеевна"
]

MEMORY_LIMIT_MB = 12000
JS_HEAP_LIMIT = 49152

REGIONS_DATA_DIR = os.path.join(SCRIPT_DIR, "regions_data")
REGION_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "region_progress.json")

CRITICAL_RECOVERY_TIMEOUT = 10
UNKNOWN_ERROR_TIMEOUT = 20

os.makedirs(REGIONS_DATA_DIR, exist_ok=True)
os.makedirs(REGION_FILTERS_DIR, exist_ok=True)
os.makedirs(PROFILE_PATH, exist_ok=True)

# ---------------------------
# СПРАВОЧНИК РЕГИОНОВ (полный)
# ---------------------------
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
    "Московская область - Чукотский автономный округ", "Московская область - Ямало-Ненецкий автономный округ"
]

# ---------------------------
# CTRL+C
# ---------------------------
def signal_handler(_sig: int, _frame: Any) -> None:
    global stop_parsing, current_driver
    logger.info("Получен сигнал остановки. Сохранение данных...")
    stop_parsing = True
    try:
        if current_driver is not None:
            try:
                with open("last_url.txt", "w", encoding="utf-8") as f:
                    f.write(current_driver.current_url)
                logger.info("Текущий URL сохранен")
            except (WebDriverException, AttributeError) as e:
                logger.warning(f"Драйвер недоступен: {str(e)}")
            try:
                current_driver.quit()
            except (WebDriverException, AttributeError) as e:
                logger.warning(f"Ошибка при закрытии драйвера: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка при завершении: {str(e)}")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ---------------------------
# УТИЛИТЫ
# ---------------------------
def log_memory_usage(message: str = "") -> None:
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / (1024 ** 2)
    logger.info(f"{message} Использование памяти: {mem:.2f} MB")

def check_stop_file() -> bool:
    global stop_parsing
    stop_file = os.path.join(SCRIPT_DIR, "stop.txt")
    if os.path.exists(stop_file):
        logger.info("Обнаружен файл остановки. Завершаем работу...")
        try:
            os.remove(stop_file)
        except OSError:
            pass
        stop_parsing = True
        return True
    return False

def random_delay(min_delay: float = 0.05, max_delay: float = 0.15) -> None:
    time.sleep(random.uniform(min_delay, max_delay))

def check_memory_usage() -> float:
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 * 1024)

def is_browser_responsive(driver: webdriver.Chrome) -> bool:
    try:
        ready = driver.execute_script("return document.readyState")
        _ = driver.execute_script("return Date.now()")
        return ready in ("interactive", "complete")
    except Exception:
        return False

def safe_current_url(driver: Optional[webdriver.Chrome], fallback: str = "about:blank") -> str:
    try:
        if driver is None:
            return fallback
        return driver.current_url
    except Exception:
        return fallback

# --- «Чистое» убийство Chrome по профилю + снятие локов Singleton* ---
def _kill_chrome_by_profile(profile_path: str, timeout: float = 5.0) -> None:
    victims = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (p.info['name'] or '').lower()
            cmd = ' '.join(p.info.get('cmdline') or [])
            if ('chrome' in name or 'chromium' in name) and profile_path in cmd:
                victims.append(p)
                victims.extend(p.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for p in victims:
        try: p.terminate()
        except Exception: pass
    _, alive = psutil.wait_procs(victims, timeout=timeout)

    for p in alive:
        try: p.kill()
        except Exception: pass
    psutil.wait_procs(alive, timeout=timeout)

    for fn in ('SingletonLock', 'SingletonCookie', 'SingletonSocket'):
        fp = os.path.join(profile_path, fn)
        if os.path.exists(fp):
            try: os.remove(fp)
            except Exception: pass

def kill_own_chrome_process() -> None:
    try:
        _kill_chrome_by_profile(PROFILE_PATH)
    except Exception as e:
        logger.debug(f"Ошибка при зачистке Chrome по профилю: {e}")

# ---------------------------
# НОРМАЛИЗАЦИЯ И ХЭШ
# ---------------------------
def _normalize_string(value: str) -> str:
    if not value:
        return ""
    normalized = re.sub(r'[^\w\s]', '', value.strip().lower())
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized

def _normalize_city_name(city_name: str) -> str:
    if not city_name:
        return ""
    normalized = re.sub(r'^(г\.?|гор\.?|город\s+)', '', city_name.strip().lower())
    normalized = _normalize_string(normalized)
    return normalized

def _normalize_weight_value(text: str) -> str:
    if not text:
        return '0.0'
    s = text.lower().replace(",", ".")
    # try tons
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:т|тонн?)\b', s)
    if m:
        try:
            return str(round(float(m.group(1)) * 1000.0, 1))
        except Exception:
            pass
    # try kg
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:кг|kg)\b', s)
    if m:
        try:
            return str(round(float(m.group(1)), 1))
        except Exception:
            pass
    # default: first number
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if m:
        try:
            return str(round(float(m.group(1)), 1))
        except Exception:
            pass
    return '0.0'

def _normalize_volume_value(text: str) -> str:
    if not text:
        return '0.0'
    s = text.lower().replace(",", ".")
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:м3|m3|куб)', s)
    if m:
        try:
            return str(round(float(m.group(1)), 1))
        except Exception:
            pass
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if m:
        try:
            return str(round(float(m.group(1)), 1))
        except Exception:
            pass
    return '0.0'

def _normalize_price_and_currency(prices: Dict[str, str]) -> str:
    price_value = prices.get('с_НДС') or prices.get('без_НДС') or prices.get('наличные')
    if not price_value:
        return '0'
    try:
        clean = re.sub(r'[^\d,\.]', '', price_value).replace(',', '.')
        val = float(clean)
        return str(round(val))
    except Exception:
        return '0'

def _normalize_freight_minimal(freight_data: dict) -> dict:
    # минимальный, безопасный набор (как был), + число вес/объём, цена
    normalized = {
        'loading_city': _normalize_city_name(', '.join(freight_data.get('loading_points', [])[:1])),
        'unloading_city': _normalize_city_name(', '.join(freight_data.get('unloading_points', [])[:1])),
        'cargo': _normalize_string(freight_data.get('cargo', '')),
        'body_type': _normalize_string(freight_data.get('body_type', '')),
        'loading_date': freight_data.get('loading_date', '')
    }
    normalized['weight'] = _normalize_weight_value(freight_data.get('weight', ''))
    normalized['volume'] = _normalize_volume_value(freight_data.get('volume', ''))
    normalized['price'] = _normalize_price_and_currency(freight_data.get('prices', {}))
    return normalized

def _generate_freight_hash(freight: Dict[str, Any]) -> str:
    """Стабильный хеш с учётом цены/условий — чтобы фиксировать обновления ставок/правил."""
    def _normpoint_list(xs):
        out = []
        for s in xs or []:
            if not isinstance(s, str):
                continue
            s1 = re.sub(r'[^\w\s]', '', s.strip().lower())
            s1 = re.sub(r'\s+', ' ', s1)
            out.append(s1)
        return out

    try:
        key_data = {
            "id": freight.get("id", ""),
            "loading_points": _normpoint_list(freight.get("loading_points", [])),
            "unloading_points": _normpoint_list(freight.get("unloading_points", [])),
            "loading_date": (freight.get("loading_date") or "").strip(),
            "cargo": (freight.get("cargo") or "").strip().lower(),
            "body_type": (freight.get("body_type") or "").strip().lower(),
            "weight": str(freight.get("weight") or "").strip(),
            "volume": str(freight.get("volume") or "").strip(),
            "prices": freight.get("prices", {}),
            "loading_method": (freight.get("loading_method") or "").strip().lower(),
            "possible_reload": (freight.get("possible_reload") or "").strip().lower(),
        }
        key_str = json.dumps(key_data, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()
    except Exception as e:
        logger.error(f"Ошибка генерации хеша: {e}")
        return hashlib.sha256(str(freight).encode("utf-8")).hexdigest()

# ---------------------------
# НОРМАЛИЗАЦИЯ "ЗАГР/ВЫГР/РАСТЕНТОВКА"
# ---------------------------
def _parse_loading_unloading(raw: str) -> Dict[str, Any]:
    """
    Преобразует "загр/выгр" строку в нормализованные признаки.
    Возвращает словарь:
      loading_unloading_raw, loading_methods_norm (rear/side/top), unloading_methods_norm,
      full_tent (bool), equipments (tail_lift/ramp/crane),
      loading_methods_human, unloading_methods_human.
    """
    if not raw:
        return {
            "loading_unloading_raw": "",
            "loading_methods_norm": [],
            "unloading_methods_norm": [],
            "full_tent": False,
            "equipments": [],
            "loading_methods_human": "",
            "unloading_methods_human": "",
        }
    s = str(raw).lower()
    s = re.sub(r"\s+", " ", s).strip()

    def find_methods(text: str) -> List[str]:
        found = set()
        if re.search(r"задн|сзади|задняя", text):
            found.add("rear")
        if re.search(r"бок|сбоку|боковая", text):
            found.add("side")
        if re.search(r"верх|верхняя", text):
            found.add("top")
        order = {"rear": 0, "side": 1, "top": 2}
        return sorted(found, key=lambda x: order[x])

    full_tent = bool(re.search(r"полн\w*\s+растент", s)) or "полная растентовка" in s

    equipments = []
    if "гидроборт" in s:
        equipments.append("tail_lift")
    if re.search(r"рамп|аппарел", s):
        equipments.append("ramp")
    if re.search(r"манипулятор|кран\s*-?\s*борт|кранборт", s):
        equipments.append("crane")

    load_methods: List[str] = []
    unload_methods: List[str] = []

    if re.search(r"загр\s*/\s*выгр\s*:", s):
        m = re.search(r"загр\s*/\s*выгр\s*:\s*([^|;]+)", s)
        segment = m.group(1) if m else s
        methods = find_methods(segment)
        load_methods = methods
        unload_methods = methods
    else:
        m1 = re.search(r"загр\s*:\s*([^|;]+)", s)
        if m1:
            load_methods = find_methods(m1.group(1))
        m2 = re.search(r"выгр\s*:\s*([^|;]+)", s)
        if m2:
            unload_methods = find_methods(m2.group(1))

    if not load_methods and not unload_methods:
        methods = find_methods(s)
        load_methods = methods
        unload_methods = methods

    human_map = {"rear": "задняя", "side": "боковая", "top": "верхняя"}
    loading_methods_human = "; ".join(human_map[m] for m in load_methods) if load_methods else ""
    unloading_methods_human = "; ".join(human_map[m] for m in unload_methods) if unload_methods else ""

    return {
        "loading_unloading_raw": s,
        "loading_methods_norm": load_methods,
        "unloading_methods_norm": unload_methods,
        "full_tent": full_tent,
        "equipments": equipments,
        "loading_methods_human": loading_methods_human,
        "unloading_methods_human": unloading_methods_human,
    }

# ---------------------------
# ДЕДУПЛИКАЦИЯ (с фолбэком)
# ---------------------------
def is_duplicate_with_fallback(freight_hash: str, ttl_seconds: int = 7*24*3600) -> bool:
    # Сначала — сеансовая память
    if freight_hash in SESSION_SEEN_HASHES:
        return True

    # Затем Redis (если доступен)
    try:
        if hasattr(redis_manager_instance, "is_duplicate"):
            try:
                result = redis_manager_instance.is_duplicate(freight_hash, ttl_seconds)
                if result:
                    return True
                SESSION_SEEN_HASHES.add(freight_hash)
                return False
            except TypeError:
                result = redis_manager_instance.is_duplicate(freight_hash)
                if result:
                    return True
                SESSION_SEEN_HASHES.add(freight_hash)
                return False

        if hasattr(redis_manager_instance, "check_and_set"):
            created = bool(redis_manager_instance.check_and_set(freight_hash, ttl_seconds))
            if not created:
                return True
            SESSION_SEEN_HASHES.add(freight_hash)
            return False

        if hasattr(redis_manager_instance, "set_if_not_exists"):
            created = bool(redis_manager_instance.set_if_not_exists(freight_hash, ttl_seconds))
            if not created:
                return True
            SESSION_SEEN_HASHES.add(freight_hash)
            return False
    except Exception:
        # молчим, уходим в фолбэк
        pass

    # Фолбэк: только память процесса
    SESSION_SEEN_HASHES.add(freight_hash)
    return False

# ---------------------------
# ДРАЙВЕР
# ---------------------------
def init_driver(headless: bool = False, profile_path: Optional[str] = None) -> webdriver.Chrome:
    global current_driver
    chrome_options = Options()

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheet": 2,
        "profile.managed_default_content_settings.fonts": 2,
        "profile.managed_default_content_settings.javascript": 1,
        "profile.managed_default_content_settings.plugins": 2,
        "profile.managed_default_content_settings.popups": 2,
        "profile.managed_default_content_settings.media_stream": 2,
        "profile.managed_default_content_settings.geolocation": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--lang=ru-RU")
    chrome_options.add_argument(f"--js-flags=--max_old_space_size={JS_HEAP_LIMIT}")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-features=Translate,BackForwardCache")

    if headless:
        chrome_options.add_argument("--headless=new")

    if profile_path is None:
        profile_path = PROFILE_PATH
    os.makedirs(profile_path, exist_ok=True)
    chrome_options.add_argument(f"--user-data-dir={profile_path}")
    chrome_options.add_argument("--profile-directory=Default")

    logger.info("Инициализация нового драйвера Chrome")
    service = Service()  # Selenium Manager подберёт chromedriver
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(CRITICAL_RECOVERY_TIMEOUT)
    driver.set_script_timeout(CRITICAL_RECOVERY_TIMEOUT)
    driver.implicitly_wait(2)
    current_driver = driver
    return driver

# ---------------------------
# МЯГКАЯ/ЖЁСТКАЯ ОЧИСТКА
# ---------------------------
def soft_memory_cleanup(driver: webdriver.Chrome) -> None:
    try:
        logger.info("Мягкая очистка памяти")
        gc.collect()
        try:
            driver.execute_script("window.gc && window.gc()")
        except Exception:
            pass
        logger.info("Мягкая очистка памяти выполнена")
    except Exception as e:
        logger.error(f"Ошибка мягкой очистки памяти: {e}")

def restart_driver(old_driver: Optional[webdriver.Chrome], last_successful_url: Optional[str] = None) -> Optional[webdriver.Chrome]:
    global current_driver
    try:
        if old_driver is not None:
            try:
                old_driver.quit()
            except Exception as e:
                logger.debug(f"Ошибка при закрытии драйвера: {e}")
    except Exception:
        pass

    kill_own_chrome_process()

    for attempt in range(3):
        time.sleep(1.0)
        logger.info(f"Перезапуск драйвера (попытка {attempt + 1}/3)...")
        try:
            new_driver = init_driver(headless=False, profile_path=PROFILE_PATH)
            time.sleep(0.3)
            if is_logged_in(new_driver):
                current_driver = new_driver
                logger.info("✅ Драйвер успешно перезапущен (сессия из профиля)")
            else:
                if not load_session(new_driver):
                    logger.error("Не удалось загрузить cookies")
                    new_driver.quit()
                    continue
                if not is_logged_in(new_driver):
                    logger.error("Авторизация не восстановлена")
                    new_driver.quit()
                    continue
                current_driver = new_driver
                logger.info("✅ Драйвер успешно перезапущен (сессия из cookies)")

            if last_successful_url:
                try:
                    new_driver.get(last_successful_url)
                    WebDriverWait(new_driver, CRITICAL_RECOVERY_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                    )
                except TimeoutException:
                    logger.warning("Таймаут при восстановлении URL")
            return new_driver
        except Exception as e:
            logger.error(f"Ошибка инициализации драйвера: {str(e)}")
        time.sleep(2)

    logger.critical("❌ Все попытки перезапуска драйвера провалились")
    return None

# ---------------------------
# АВТОРИЗАЦИЯ / СЕССИЯ
# ---------------------------
def is_logged_in(driver: webdriver.Chrome) -> bool:
    try:
        logger.info("Проверка авторизации...")
        driver.get(BASE_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "header")))
        page_source = driver.page_source
        for variant in EXPECTED_USERNAME_VARIANTS:
            if variant in page_source:
                logger.info(f"Авторизация подтверждена: {variant}")
                return True
        logger.warning("Имя пользователя не обнаружено в шапке (требуется вход)")
        return False
    except TimeoutException:
        logger.error("Таймаут при ожидании хедера")
        return False
    except WebDriverException as e:
        logger.error(f"Ошибка проверки авторизации: {str(e)}")
        return False

def save_cookies(driver: webdriver.Chrome) -> bool:
    try:
        random_delay(0.2, 0.4)
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info(f"Cookies успешно сохранены ({len(cookies)} записей)")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения cookies: {str(e)}")
        return False

def load_session(driver: webdriver.Chrome) -> bool:
    """
    1) Сначала пробуем профиль: если уже залогинены — возврат True.
    2) Если нет — подливаем куки из файла (без delete_all_cookies), затем refresh().
    """
    try:
        driver.get(BASE_URL)
        if is_logged_in(driver):
            logger.info("Профиль уже авторизован; загрузка cookies не требуется")
            return True
    except Exception:
        pass

    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            for cookie in cookies:
                try:
                    if 'domain' in cookie and cookie['domain'].startswith('.'):
                        cookie['domain'] = cookie['domain'][1:]
                    driver.add_cookie(cookie)
                except Exception as cookie_error:
                    logger.debug(f"Не удалось добавить cookie {cookie.get('name')}: {cookie_error}")
            logger.info(f"Загружено {len(cookies)} cookies (фолбэк)")
            driver.refresh()
            random_delay(0.3, 0.5)
            return True
        except Exception as e:
            logger.error(f"Ошибка загрузки cookies: {str(e)}")
    else:
        logger.warning("Файл cookies не найден")
    return False

def manual_login() -> bool:
    global current_driver
    os.makedirs(PROFILE_PATH, exist_ok=True)
    try:
        driver = init_driver(headless=False, profile_path=PROFILE_PATH)
    except Exception as e:
        logger.error(f"Ошибка инициализации драйвера: {str(e)}")
        return False
    try:
        logger.info("=== РУЧНАЯ АВТОРИЗАЦИЯ ===")
        driver.get(BASE_URL)
        print("\n=== ИНСТРУКЦИЯ ===")
        print("1. В открывшемся браузере выполните вход в аккаунт ATI")
        print("2. Убедитесь, что в правом верхнем углу отображается ваше имя")
        print("3. После успешной авторизации вернитесь сюда и нажмите Enter\n")
        input("Нажмите Enter после успешной авторизации >>> ")
        time.sleep(0.2)
        if is_logged_in(driver):
            save_cookies(driver)
            return True
        return False
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        return False
    finally:
        try:
            if driver is not None:
                driver.quit()
            current_driver = None
        except Exception:
            pass

# ---------------------------
# ФИЛЬТРЫ
# ---------------------------
def record_filter_actions(driver: webdriver.Chrome) -> List[tuple]:
    logger.info("=== РЕЖИМ ЗАПИСИ ФИЛЬТРА ===")
    print("\n=== ИНСТРУКЦИЯ ===")
    print("1. Настройте фильтры как нужно")
    print("2. После настройки дождитесь загрузки результатов и нажмите Enter")
    actions = []
    input("Нажмите Enter после настройки фильтров и загрузки результатов >>> ")
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
        )
    except TimeoutException:
        logger.error("Таймаут ожидания результатов поиска!")
    filtered_url = driver.current_url
    actions.append(('get', filtered_url))
    with open(FILTER_CONFIG, 'wb') as f:
        pickle.dump(actions, f)  # type: ignore[arg-type]
    logger.info(f"Конфигурация фильтра сохранена: {FILTER_CONFIG}")
    return actions

def apply_recorded_filter(driver: webdriver.Chrome) -> bool:
    if not os.path.exists(FILTER_CONFIG):
        logger.error("Конфигурация фильтра не найдена. Сначала выполните пункт 2 (Запись параметров фильтра).")
        return False
    try:
        with open(FILTER_CONFIG, 'rb') as f:
            actions = pickle.load(f)
        for action in actions:
            if stop_parsing:
                logger.info("Остановка по запросу пользователя при применении фильтра")
                return False
            if action[0] == 'get':
                driver.get(action[1])
                logger.info(f"Применение фильтров: {action[1]}")
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, "section[data-load-id]") or
                                  d.find_elements(By.CSS_SELECTOR, "div.FreightList_list__pB6Hh") or
                                  d.find_elements(By.CSS_SELECTOR, "div.no-results")
                    )
                except TimeoutException:
                    logger.warning("Первая попытка неудачна, обновляем страницу...")
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
    if stop_parsing:
        logger.info("Остановка по запросу пользователя при применении регионального фильтра")
        return False
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in region_name)
    filter_file = os.path.join(REGION_FILTERS_DIR, f"{safe_name}.pkl")
    if not os.path.exists(filter_file):
        logger.error(f"[Filter] не найден файл фильтра для региона: {region_name}")
        return False
    try:
        with open(filter_file, 'rb') as f:
            filter_state = pickle.load(f)
        driver.get(filter_state['url'])
        logger.info(f"Применен фильтр для региона: {region_name}")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
            )
        except TimeoutException:
            logger.warning("Первая попытка неудачна, обновляем страницу...")
            driver.refresh()
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
            )
        random_delay(0.1, 0.2)
        set_display_rows(driver)
        return True
    except WebDriverException as e:
        logger.error(f"Ошибка применения фильтра для региона {region_name}: {str(e)}")
        return False

def set_display_rows(driver: webdriver.Chrome, value: str = "100") -> bool:
    logger.info(f"Устанавливаем отображение {value} строк на странице")
    try:
        rows_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,
                "div.SearchResults_actionsContainer_top__0jnFb div.Field_container__UTlL4.SearchResults_sortFieldContainer__7hH7u"))
        )
        current_value_element = rows_container.find_element(By.CSS_SELECTOR, "span.input-text_409aff4f19")
        current_value = current_value_element.text.strip()
        if current_value == value:
            logger.info(f"Уже установлено значение: {value}")
            return True
        dropdown = rows_container.find_element(By.CSS_SELECTOR, "label.select-input_409aff4f19")
        driver.execute_script("arguments[0].click();", dropdown)
        WebDriverWait(driver, 7).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "div.suggestion-list-wrapper_ed973e084c"))
        )
        option_selector = f"button[data-value='{value}']"
        option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, option_selector))
        )
        driver.execute_script("arguments[0].click();", option)
        WebDriverWait(driver, 7).until(
            lambda d: d.find_element(
                By.CSS_SELECTOR,
                "div.SearchResults_actionsContainer_top__0jnFb span.input-text_409aff4f19"
            ).text.strip() == value
        )
        logger.info(f"Успешно установлено отображение {value} строк")
        return True
    except Exception as e:
        logger.error(f"Ошибка установки количества строк: {str(e)}")
        return False

# ---------------------------
# WHITE SCREEN DETECTION
# ---------------------------
def check_white_screen(driver: webdriver.Chrome) -> bool:
    try:
        page_text = driver.page_source
        if ("Опаньки" in page_text or "Out of Memory" in page_text or len(page_text) < 1000):
            logger.error("Обнаружен белый экран или ошибка памяти!")
            return True
        pagination = driver.find_elements(By.CSS_SELECTOR, "div[data-qa='pagination']")
        freights = driver.find_elements(By.CSS_SELECTOR, "section[data-app='pretty-load']")
        no_results = driver.find_elements(By.CSS_SELECTOR, "div.no-results")
        if not pagination and not freights and not no_results:
            logger.error("Белый экран: не найдены элементы пагинации, грузы или сообщение об отсутствии результатов")
            return True
    except Exception as e:
        logger.error(f"Ошибка при проверке белого экрана: {e}")
        return True
    return False

# ---------------------------
# ВОССТАНОВЛЕНИЕ СЕССИИ
# ---------------------------
def restore_session(region_name: Optional[str], target_page: int, is_filter: bool) -> Optional[webdriver.Chrome]:
    logger.info(f"Восстановление сессии: region={region_name}, target_page={target_page}, is_filter={is_filter}")
    new_driver = restart_driver(current_driver, None)
    if new_driver is None:
        return None
    try:
        if is_filter or not region_name or region_name == "filter":
            if not apply_recorded_filter(new_driver):
                logger.error("Не удалось применить записанный фильтр")
                return None
        else:
            if not apply_region_filter(new_driver, region_name):
                logger.error("Не удалось применить фильтр региона")
                return None
        set_display_rows(new_driver, "100")
        if not navigate_to_page(new_driver, target_page):
            logger.error(f"Не удалось перейти на страницу {target_page} после восстановления")
            return None
        cur = get_current_page_number(new_driver)
        if cur != target_page:
            logger.warning(f"После восстановления текущая страница {cur} != {target_page}")
            return None
        logger.info(f"Сессия восстановлена на странице {target_page}")
        return new_driver
    except Exception as e:
        logger.error(f"Ошибка restore_session: {e}")
        return None

# ---------------------------
# ПАГИНАЦИЯ / НАВИГАЦИЯ (точная)
# ---------------------------
def get_current_page_number(driver: webdriver.Chrome) -> int:
    # 1) активная кнопка
    try:
        active_button = driver.find_element(By.CSS_SELECTOR, "button.item_JqfSO.active_WLE-D")
        page_num = active_button.get_attribute("data-value")
        if page_num and page_num.isdigit():
            return int(page_num)
    except NoSuchElementException:
        pass
    # 2) поле ввода
    try:
        pagination_container = driver.find_element(By.CSS_SELECTOR, "div[data-qa='pagination']")
        input_field = pagination_container.find_element(By.CSS_SELECTOR, "div[data-qa='input-field'] input")
        value = input_field.get_attribute("value")
        if value and value.isdigit():
            return int(value)
    except NoSuchElementException:
        pass
    return 1

def get_total_pages(driver: webdriver.Chrome) -> int:
    # кнопка с "всего"
    try:
        total_button = driver.find_element(By.CSS_SELECTOR, "button.total-index_kjYkG")
        total_value = total_button.get_attribute("data-value")
        if total_value and total_value.isdigit():
            return int(total_value)
    except NoSuchElementException:
        pass
    # отображение "... из N"
    try:
        total_element = driver.find_element(By.CSS_SELECTOR, "span.total_5B9k1")
        numbers = re.findall(r'\d+', total_element.text)
        if numbers:
            return int(numbers[-1])
    except NoSuchElementException:
        pass
    # набор кнопок
    try:
        page_buttons = driver.find_elements(By.CSS_SELECTOR, "button.item_JqfSO")
        max_page = 1
        for btn in page_buttons:
            try:
                page_num = int(btn.get_attribute("data-value"))
                if page_num > max_page:
                    max_page = page_num
            except Exception:
                continue
        return max_page
    except Exception:
        return 1

def click_next_button(driver: webdriver.Chrome) -> Optional[bool]:
    """
    True  — успешно перешли на следующую,
    False — попытались перейти, но не получилось,
    None  — последняя страница (кнопки нет/скрыта).
    """
    try:
        next_btn = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button.next_FJXnH"))
        )
        if "hide_ilkOM" in next_btn.get_attribute("class"):
            return None
        current_page = get_current_page_number(driver)
        driver.execute_script("arguments[0].click();", next_btn)
        WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
            lambda d: get_current_page_number(d) != current_page
        )
        WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
        )
        return True
    except TimeoutException:
        return None
    except NoSuchElementException:
        return None
    except Exception:
        return False

def navigate_to_page(driver: webdriver.Chrome, target_page: int) -> bool:
    current_page = get_current_page_number(driver)
    if current_page == target_page:
        return True
    try:
        try:
            pagination_div = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.pagination_Nze-D.SearchResults_pagination__fsnZq"))
            )
        except TimeoutException:
            return target_page == 1

        # кнопка страницы
        try:
            page_button = pagination_div.find_element(By.CSS_SELECTOR, f'button.item_JqfSO[data-value="{target_page}"]')
            driver.execute_script("arguments[0].click();", page_button)
            WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
                lambda d: get_current_page_number(d) == target_page
            )
            WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
            )
            return True
        except NoSuchElementException:
            pass

        # поле ввода
        try:
            input_field = pagination_div.find_element(By.CSS_SELECTOR, "div[data-qa='input-field'] input")
            input_field.send_keys(Keys.CONTROL, 'a')
            input_field.send_keys(Keys.DELETE)
            time.sleep(0.1)
            input_field.send_keys(str(target_page))
            input_field.send_keys(Keys.ENTER)
            WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
                lambda d: get_current_page_number(d) == target_page
            )
            WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results"))
            )
            return True
        except NoSuchElementException:
            # последовательные клики "Далее" как фолбэк
            cur = get_current_page_number(driver)
            while cur < target_page:
                result = click_next_button(driver)
                if result is None:
                    break
                if not result:
                    return False
                cur = get_current_page_number(driver)
            return get_current_page_number(driver) == target_page
    except Exception as e:
        logger.error(f"Ошибка navigate_to_page({target_page}): {e}")
        return False

# ---------------------------
# ОБРАБОТКА ПАГИНАЦИИ
# ---------------------------
def handle_pagination(driver: webdriver.Chrome, region_name: str = "filter") -> webdriver.Chrome:
    global stop_parsing, current_driver
    total_pages = get_total_pages(driver)
    page_num = 1
    consecutive_errors = 0
    max_consecutive_errors = 2

    jsonl_filename = get_region_jsonl_filename(region_name)

    progress = load_region_progress()
    if progress and progress.get("region") == region_name:
        page_num = progress.get("page", 1)
        total_pages = progress.get("total_pages", total_pages)
        logger.info(f"Восстановление прогресса: регион {region_name}, страница {page_num}/{total_pages}")
        # важно: сверка и переход на нужную страницу
        if not navigate_to_page(driver, page_num):
            logger.error("Не удалось восстановить позицию. Начинаем с первой страницы.")
            page_num = 1
    else:
        page_num = 1

    if total_pages <= 1:
        total_pages = get_total_pages(driver)

    logger.info(f"ОБЩЕЕ КОЛИЧЕСТВО СТРАНИЦ: {total_pages}")

    try:
        while not stop_parsing and not check_stop_file():
            if check_white_screen(driver) or not is_browser_responsive(driver):
                logger.critical("Out of Memory или белый экран — жёсткий перезапуск браузера")
                restored = restore_session(region_name if region_name != "filter" else None,
                                           page_num,
                                           is_filter=(region_name == "filter"))
                if not restored:
                    logger.error("Не удалось восстановить после белого экрана/зависания")
                    break
                driver = restored
                total_pages = get_total_pages(driver)
                page_num = get_current_page_number(driver)

            if page_num % 5 == 0:
                soft_memory_cleanup(driver)

            mem_usage = check_memory_usage()
            if mem_usage > MEMORY_LIMIT_MB * 0.95:
                logger.critical(f"КРИТИЧЕСКОЕ ИСПОЛЬЗОВАНИЕ ПАМЯТИ: {mem_usage:.2f} MB — жёсткая перезагрузка")
                restored = restore_session(region_name if region_name != "filter" else None, page_num, is_filter=(region_name == "filter"))
                if not restored:
                    logger.error("Не удалось восстановить после критической памяти")
                    break
                driver = restored

            if page_num % 10 == 0:
                logger.info(f"Жёсткая перезагрузка после страницы {page_num}")
                restored = restore_session(region_name if region_name != "filter" else None, page_num, is_filter=(region_name == "filter"))
                if not restored:
                    logger.error("Не удалось выполнить жёсткую перезагрузку")
                    break
                driver = restored
                total_pages = get_total_pages(driver)
                page_num = get_current_page_number(driver)

            log_memory_usage(f"Перед парсингом страницы {page_num}.")
            try:
                freights, stats = parse_current_page(driver, page_num)
                logger.info(f"Страница {page_num}/{total_pages}: найдено {stats['found']}, обработано {stats['processed']}, сохранено {stats['saved']}, дубликатов {stats['duplicates']}")
                if stats.get("errors", 0) > 0:
                    logger.warning(f"На странице {page_num} пропущено карточек из-за ошибок: {stats['errors']}")
                if freights:
                    append_freights_to_jsonl(freights, jsonl_filename)
                else:
                    logger.warning(f"Нет новых данных на странице {page_num}")
                consecutive_errors = 0
            except (TimeoutException, WebDriverException, Exception) as e:
                consecutive_errors += 1
                logger.warning(f"Критическая ошибка при парсинге страницы {page_num} ({consecutive_errors}/{max_consecutive_errors}): {str(e)}")
                logger.critical("Зависание/неизвестная ошибка — жёсткий перезапуск браузера")
                restored = restore_session(region_name if region_name != "filter" else None,
                                           page_num,
                                           is_filter=(region_name == "filter"))
                if not restored:
                    logger.error("Не удалось восстановить позицию. Прерывание.")
                    break
                driver = restored
                consecutive_errors = 0
                total_pages = get_total_pages(driver)
                page_num = get_current_page_number(driver)
                continue

            save_region_progress(region_name, page_num, total_pages, safe_current_url(driver))

            next_result = click_next_button(driver)
            if next_result is None:
                logger.info("Кнопка 'Далее' неактивна — последняя страница")
                break
            elif next_result:
                page_num += 1
            else:
                next_page = page_num + 1
                if navigate_to_page(driver, next_page):
                    page_num = next_page
                else:
                    logger.error(f"Не удалось перейти на страницу {next_page}. Прерывание.")
                    break

            random_delay(0.2, 0.4)
            if page_num % 5 == 0:
                gc.collect()

    except WebDriverException as e:
        logger.error(f"Ошибка пагинации: {str(e)}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка в пагинации: {str(e)}")

    return driver

# ---------------------------
# ПАРСИНГ СТРАНИЦЫ
# ---------------------------
def parse_current_page(driver: webdriver.Chrome, page_num: int) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    if stop_parsing:
        return [], {"found": 0, "processed": 0, "saved": 0, "duplicates": 0, "errors": 0}

    WebDriverWait(driver, CRITICAL_RECOVERY_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-app='pretty-load']"))
    )

    items = driver.find_elements(By.CSS_SELECTOR, "section[data-app='pretty-load']")
    total_found = len(items)
    saved = 0
    duplicates = 0
    errors = 0
    freights: List[Dict[str, Any]] = []

    for item in items:
        if stop_parsing:
            break
        try:
            freight_data = driver.execute_script("""
                const item = arguments[0];
                const data = {
                    id: item.getAttribute('data-load-id') || 'N/A',
                    loading_points: [],
                    unloading_points: [],
                    distance: 'N/A',
                    cargo: 'Н/Д',
                    weight: 'Н/Д',
                    volume: 'Н/Д',
                    prices: {},
                    loading_date: 'Н/Д',
                    body_type: 'Н/Д',
                    loading_method: 'Н/Д',
                    loading_unloading_raw: '',
                    possible_reload: 'нет'
                };
                const compositeRoute = item.querySelector("div.PExKw");
                const directRoute = item.querySelector("div.NcNn7") && item.querySelector("div.OtkNo");
                try {
                    if (compositeRoute) {
                        const loadingPoint = compositeRoute.querySelector("div.Ha2A8 .yLMmR");
                        if (loadingPoint) {
                            const city = loadingPoint.textContent.replace('погрузка', '').replace('выгрузка', '').trim();
                            if (city) data.loading_points.push(city);
                        }
                        const unloadingPoints = compositeRoute.querySelectorAll("div.QnFJD .yLMmR");
                        unloadingPoints.forEach(point => {
                            const city = point.textContent.replace('погрузка', '').replace('выгрузка', '').trim();
                            if (city) data.unloading_points.push(city);
                        });
                    } else if (directRoute) {
                        const loadingBlock = item.querySelector("div.NcNn7");
                        if (loadingBlock) {
                            const cityElement = loadingBlock.querySelector(".BUBXM.h56vj, .BUBXM");
                            const regionElement = loadingBlock.querySelector(".VX7nr");
                            const city = cityElement ? cityElement.textContent.trim() : 'Н/Д';
                            const region = regionElement ? regionElement.textContent.trim() : 'Н/Д';
                            data.loading_points.push(`${city}, ${region}`);
                        }
                        const unloadingBlock = item.querySelector("div.OtkNo");
                        if (unloadingBlock) {
                            const cityElement = unloadingBlock.querySelector(".BUBXM.h56vj, .BUBXM");
                            const regionElement = unloadingBlock.querySelector(".VX7nr");
                            const city = cityElement ? cityElement.textContent.trim() : 'Н/Д';
                            const region = regionElement ? regionElement.textContent.trim() : 'Н/Д';
                            data.unloading_points.push(`${city}, ${region}`);
                        }
                    }
                } catch (e) {}

                try {
                    const dateElement = item.querySelector("span.qaQg4 .BUBXM");
                    if (dateElement) data.loading_date = dateElement.textContent.trim();
                } catch (e) {}

                try {
                    let distanceElement = item.querySelector("a.Laof2") || item.querySelector("a.G_fQk");
                    if (distanceElement) data.distance = distanceElement.textContent.replace('км', '').trim();
                } catch (e) {}

                try {
                    const cargoElement = item.querySelector("div.WZJ4F");
                    if (cargoElement) data.cargo = cargoElement.textContent.trim();
                } catch (e) {}

                try {
                    const bodyTypeElement = item.querySelector("div.Y_WwK span.wVNyD");
                    if (bodyTypeElement) data.body_type = bodyTypeElement.textContent.trim();
                } catch (e) {}

                try {
                    const loadingMethodContainer = item.querySelector("div.y7YtP");
                    if (loadingMethodContainer) {
                        const t = loadingMethodContainer.textContent || "";
                        data.loading_unloading_raw = t.replace(/\\s+/g, " ").trim();
                        data.loading_method = data.loading_unloading_raw.replace(/(загр\\/выгр|загр|выгр)\\s*:\\s*/gi, "").trim();
                    }
                } catch (e) {}

                try {
                    const weightVolumeElement = item.querySelector("div.h49FM");
                    if (weightVolumeElement) {
                        const text = weightVolumeElement.textContent.trim();
                        if (text.includes('/')) {
                            const parts = text.split('/');
                            data.weight = parts[0].trim();
                            data.volume = parts[1].trim();
                        } else {
                            data.weight = text || 'Н/Д';
                            data.volume = 'Н/Д';
                        }
                    }
                } catch (e) {}

                try {
                    const priceBlocks = item.querySelectorAll("div.eSeMX");
                    priceBlocks.forEach(block => {
                        const priceTypeElement = block.querySelector(".f3LPw");
                        const amountElement = block.querySelector(".BUBXM");
                        if (priceTypeElement && amountElement) {
                            const priceType = priceTypeElement.textContent.trim();
                            const amount = amountElement.textContent.trim();
                            if (priceType.includes('с НДС')) data.prices['с_НДС'] = amount;
                            else if (priceType.includes('без НДС')) data.prices['без_НДС'] = amount;
                            else if (priceType.includes('нал')) data.prices['наличные'] = amount;
                        }
                    });
                } catch (e) {}

                try {
                    const reloadElement = item.querySelector("div.ctSCk");
                    if (reloadElement) {
                        const text = reloadElement.textContent.toLowerCase();
                        if (text.includes('догруз') || text.includes('догр') || text.includes('возм.догруз')) {
                            data.possible_reload = 'да';
                        }
                    }
                } catch (e) {}

                return data;
            """, item)

            # Минимальная нормализация (как в стабильной версии)
            normalized = _normalize_freight_minimal(freight_data)

            # Добавляем новый блок нормализации "загр/выгр/растентовка" (НЕ ломая старые поля)
            extra_loading = _parse_loading_unloading(freight_data.get("loading_unloading_raw") or freight_data.get("loading_method") or "")
            normalized.update(extra_loading)

            # Сохраняем сырьевые поля, которые полезны для CRM/аналитики
            normalized["raw"] = {
                "id": freight_data.get("id"),
                "loading_points": freight_data.get("loading_points", []),
                "unloading_points": freight_data.get("unloading_points", []),
                "distance": freight_data.get("distance"),
                "cargo": freight_data.get("cargo"),
                "weight_text": freight_data.get("weight"),
                "volume_text": freight_data.get("volume"),
                "prices": freight_data.get("prices", {}),
                "loading_date_text": freight_data.get("loading_date"),
                "body_type_text": freight_data.get("body_type"),
                "loading_method_text": freight_data.get("loading_method"),
                "possible_reload": freight_data.get("possible_reload", "нет"),
            }

            # Хеш дубликата
            freight_hash = _generate_freight_hash(freight_data)
            normalized['hash'] = freight_hash

            if is_duplicate_with_fallback(freight_hash, 7 * 24 * 3600):
                duplicates += 1
                continue

            freights.append(normalized)
            saved += 1

        except StaleElementReferenceException:
            errors += 1
            continue
        except Exception as e:
            errors += 1
            if errors <= 3:
                logger.debug(f"Ошибка при обработке карточки: {e}")
            continue

    stats = {
        "found": total_found,
        "processed": saved + duplicates,
        "saved": saved,
        "duplicates": duplicates,
        "errors": errors,
    }
    return freights, stats

# ---------------------------
# ПРОГРЕСС
# ---------------------------
def get_region_jsonl_filename(region_name: str) -> str:
    safe_region_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in region_name)
    region_dir = os.path.join(REGIONS_DATA_DIR, safe_region_name)
    os.makedirs(region_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(region_dir, f"{safe_region_name}_{timestamp}.jsonl")

def append_freights_to_jsonl(freights: List[Dict[str, Any]], filename: str) -> None:
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            for freight in freights:
                freight_record = {**freight, 'parsed_at': datetime.now().isoformat()}
                f.write(json.dumps(freight_record, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"Ошибка сохранения результатов: {str(e)}")

def save_region_progress(region_name: str, page_num: int, total_pages: int, url: str, region_idx: Optional[int] = None) -> None:
    try:
        progress = {
            "region": region_name,
            "page": int(page_num),
            "total_pages": int(total_pages),
            "url": url,
            "timestamp": int(time.time())
        }
        if region_idx is not None:
            progress["region_idx"] = region_idx
        with open(REGION_PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения прогресса: {str(e)}")

def load_region_progress() -> Optional[Dict[str, Any]]:
    if os.path.exists(REGION_PROGRESS_FILE):
        try:
            with open(REGION_PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки прогресса: {e}")
    return None

def clear_region_progress() -> None:
    try:
        if os.path.exists(REGION_PROGRESS_FILE):
            os.remove(REGION_PROGRESS_FILE)
    except OSError as e:
        logger.error(f"Ошибка удаления файла прогресса: {e}")

# ---------------------------
# ВСЕ РЕГИОНЫ
# ---------------------------
def parse_all_regions(driver: webdriver.Chrome) -> webdriver.Chrome:
    """
    Учитываем сохранённый region_idx; переносим прогресс на следующий регион, используя safe_current_url().
    Полный каталог регионов встроен.
    """
    global stop_parsing
    os.makedirs(REGIONS_DATA_DIR, exist_ok=True)

    processed_regions = 0
    consecutive_errors = 0
    skipped_regions = []
    last_successful_url = None

    all_regions = RUSSIAN_REGIONS + MOSCOW_OBLAST_COMBINATIONS
    total_regions_count = len(all_regions)

    progress = load_region_progress()
    start_index = 0
    if progress and "region_idx" in progress:
        start_index = progress["region_idx"]
        logger.info(f"Восстановление с региона {progress.get('region')} (индекс {start_index})")

    for region_idx, region in enumerate(all_regions[start_index:], start=start_index):
        if stop_parsing or check_stop_file():
            logger.info("Остановка парсинга регионов по запросу пользователя")
            break

        log_memory_usage(f"Начало обработки региона {region} ({region_idx + 1}/{total_regions_count})")
        region_success = False
        region_attempts = 0

        while not region_success and region_attempts < MAX_DRIVER_RECOVERY_ATTEMPTS:
            region_attempts += 1
            try:
                try:
                    _ = driver.current_url
                except WebDriverException:
                    logger.warning("Драйвер не отвечает, пробуем восстановить...")
                    driver = restart_driver(driver, last_successful_url)
                    if not driver:
                        logger.error("Не удалось восстановить драйвер")
                        break

                if not apply_region_filter(driver, region):
                    if region_attempts == MAX_DRIVER_RECOVERY_ATTEMPTS:
                        logger.error(f"Не удалось применить фильтр для региона {region} после {MAX_DRIVER_RECOVERY_ATTEMPTS} попыток")
                        skipped_regions.append(region)
                    continue

                last_successful_url = safe_current_url(driver, last_successful_url or BASE_URL)
                save_region_progress(region, 1, 1, safe_current_url(driver, last_successful_url), region_idx)

                driver = handle_pagination(driver, region)

                region_success = True
                processed_regions += 1
                consecutive_errors = 0
                logger.info(f"Успешно обработан регион: {region}")

                next_idx = region_idx + 1
                if next_idx < total_regions_count:
                    next_region = all_regions[next_idx]
                    save_region_progress(next_region, 1, 1, safe_current_url(driver, last_successful_url), next_idx)
                else:
                    clear_region_progress()

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Ошибка при обработке региона {region} (попытка {region_attempts}/{MAX_DRIVER_RECOVERY_ATTEMPTS}): {str(e)}")
                logger.error(traceback.format_exc())
                gc.collect()
                if "не отвечает" in str(e).lower() or "connection" in str(e).lower():
                    driver = restart_driver(driver, last_successful_url)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"Превышен лимит последовательных ошибок ({MAX_CONSECUTIVE_ERRORS})")
                    break

        delay = min(15, 3 + processed_regions * 1)
        logger.info(f"Пауза перед следующим регионом: {delay} сек")
        time.sleep(delay)

        if processed_regions > 0 and processed_regions % DRIVER_REBOOT_INTERVAL == 0:
            logger.info("Профилактический перезапуск драйвера...")
            driver = restart_driver(driver, last_successful_url)
            if not driver:
                logger.error("Не удалось перезапустить драйвер. Прерывание парсинга.")
                break

    report = {
        "processed_regions": processed_regions,
        "skipped_regions": skipped_regions,
        "total_regions": total_regions_count,
        "success_rate": f"{(processed_regions / total_regions_count) * 100:.1f}%" if total_regions_count else "0%",
        "timestamp": datetime.now().isoformat(),
    }
    report_file = os.path.join(
        REGIONS_DATA_DIR,
        f"parsing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"Обработка завершена. Успешно: {processed_regions}, Пропущено: {len(skipped_regions)}")
    if skipped_regions:
        logger.info(f"Пропущенные регионы: {', '.join(skipped_regions)}")

    return driver

# ---------------------------
# НАСТРОЙКА ФИЛЬТРОВ ДЛЯ ВСЕХ РЕГИОНОВ
# ---------------------------
def setup_all_region_filters(driver: webdriver.Chrome) -> None:
    global stop_parsing
    print("\n=== НАСТРОЙКА ФИЛЬТРОВ РЕГИОНОВ ===")
    print("Инструкция: настройте фильтр для каждого региона и жмите Enter")

    if not is_logged_in(driver):
        logger.error("Требуется авторизация! Сначала выполните пункт 1")
        return

    driver.get(FREIGHT_URL)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.Filters_container__3niLd")))

    for region in RUSSIAN_REGIONS + MOSCOW_OBLAST_COMBINATIONS:
        if stop_parsing:
            logger.info("Остановка настройки по запросу пользователя")
            return
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in region)
        filter_file = os.path.join(REGION_FILTERS_DIR, f"{safe_name}.pkl")
        print(f"\n\n=== РЕГИОН: {region.upper()} ===")
        print(f"Файл фильтра: {filter_file}")
        action = input("Выберите действие [настроить/пропустить/готово]: ").strip().lower()
        if action in ["готово", "exit", "quit", "q"]:
            logger.info("Завершение настройки по запросу пользователя")
            return
        elif action in ["пропустить", "skip", "s"]:
            if os.path.exists(filter_file):
                print(f"Сохраненный фильтр для региона {region} не изменен")
            else:
                print(f"Регион {region} пропущен, фильтр не настроен")
            continue
        print(f"\nНастройте фильтр для региона: {region}")
        print("После настройки вернитесь сюда и нажмите Enter")
        try:
            input("Нажмите Enter после настройки фильтра >>> ")
            current_url = driver.current_url
            filter_state = {'region': region, 'url': current_url, 'timestamp': datetime.now().isoformat()}
            with open(filter_file, 'wb') as f:
                pickle.dump(filter_state, f)
            logger.info(f"Фильтр для региона '{region}' сохранен: {current_url}")
            try:
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-load-id], div.no-results")))
            except TimeoutException:
                logger.warning("Не удалось обнаружить результаты после настройки фильтра")
        except Exception as e:
            logger.error(f"Ошибка сохранения фильтра для региона {region}: {str(e)}")
        time.sleep(0.3)
    logger.info("Настройка фильтров для всех регионов завершена!")

# ---------------------------
# MAIN (меню) + AUTO CLI
# ---------------------------
def main() -> None:
    global stop_parsing, current_driver
    print("=" * 50)
    print("ПАРСЕР ATI.SU - ГИБРИДНАЯ СТАБИЛЬНАЯ ВЕРСИЯ")
    print("=" * 50)
    print("Выберите действие:")
    print("1 - Авторизация (требуется при первом запуске)")
    print("2 - Запись параметров фильтра (ручная настройка URL-фильтра на странице)")
    print("3 - Парсинг грузов с применением сохраненного фильтра (глобальный фильтр)")
    print("4 - Автоматический парсинг всех регионов")
    print("5 - Создать файл остановки (stop.txt)")
    print("6 - Настройка фильтров для всех регионов")
    print("7 - Выход")
    choice = input("> ").strip()

    if choice == "1":
        if manual_login():
            logger.info("✅ Авторизация успешна! Теперь можно использовать другие пункты")
        else:
            logger.error("❌ Авторизация не удалась. Повторите попытку")

    elif choice == "2":
        try:
            driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {str(e)}")
            return
        try:
            if not load_session(driver) or not is_logged_in(driver):
                logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1")
                return
            logger.info("✅ Сессия восстановлена! Переходим к странице грузов...")
            driver.get(FREIGHT_URL)
            WebDriverWait(driver, 16).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.Filters_container__3niLd")))
            random_delay(0.2, 0.4)
            record_filter_actions(driver)
            try:
                clear_region_progress()
                logger.info("✅ Прогресс страниц сброшен после записи фильтра")
            except Exception as _e:
                logger.warning(f"Не удалось сбросить прогресс: {_e}")
        except WebDriverException as e:
            logger.error(f"❌ Ошибка: {str(e)}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            current_driver = None

    elif choice == "3":
        try:
            driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {str(e)}")
            return
        try:
            if not load_session(driver) or not is_logged_in(driver):
                logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1")
                return
            logger.info("✅ Сессия восстановлена! Применяем сохраненный фильтр...")
            if not apply_recorded_filter(driver):
                logger.error("Нет сохранённого фильтра. Выполните пункт 2 для записи фильтра и повторите пункт 3.")
                return
            handle_pagination(driver)
        except WebDriverException as e:
            logger.error(f"❌ Ошибка в основном потоке: {str(e)}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException as e:
                    logger.warning(f"⚠️ Ошибка при закрытии драйвера: {e}")
            current_driver = None

    elif choice == "4":
        try:
            driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {str(e)}")
            return
        try:
            if not load_session(driver) or not is_logged_in(driver):
                logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1")
                return
            logger.info("✅ Сессия восстановлена! Начинаем автоматический парсинг регионов...")
            driver = parse_all_regions(driver)
        except WebDriverException as e:
            logger.error(f"❌ Ошибка в основном потоке: {str(e)}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException as e:
                    logger.warning(f"⚠️ Ошибка при закрытии драйвера: {e}")
            current_driver = None

    elif choice == "5":
        try:
            with open("stop.txt", "w") as f:
                f.write("stop")
            logger.info("✅ Файл stop.txt создан. Парсинг остановится после завершения текущей страницы.")
        except Exception as e:
            logger.error(f"❌ Ошибка создания файла: {e}")

    elif choice == "6":
        try:
            driver = init_driver(headless=False, profile_path=PROFILE_PATH)
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера: {str(e)}")
            return
        try:
            if not load_session(driver) or not is_logged_in(driver):
                logger.error("❌ Не удалось восстановить сессию. Выполните пункт 1")
                return
            logger.info("✅ Сессия восстановлена! Начинаем настройку фильтров регионов...")
            setup_all_region_filters(driver)
        except WebDriverException as e:
            logger.error(f"❌ Ошибка в основном потоке: {str(e)}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException as e:
                    logger.warning(f"⚠️ Ошибка при закрытии драйвера: {e}")
            current_driver = None

    elif choice == "7":
        logger.info("Выход...")
        return

    else:
        logger.warning("❌ Неверный выбор. Попробуйте снова.")

def run_all_regions_cli(headless: bool = False) -> None:
    """
    Неблокирующий CLI-режим для автоматического парсинга всех регионов.
    Используется внешними скриптами/планировщиком:
      python -m src.parsers.ati_parser auto_all_regions
    """
    global current_driver
    try:
        logger.info("=== AUTO MODE: парсинг всех регионов (run_all_regions_cli) ===")
        try:
            driver = init_driver(headless=headless, profile_path=PROFILE_PATH)
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации драйвера (auto_all_regions): {e}")
            return

        try:
            if not load_session(driver) or not is_logged_in(driver):
                logger.error(
                    "❌ Не удалось восстановить сессию в auto_all_regions. "
                    "Сначала выполните ручную авторизацию (пункт 1 интерактивного меню)."
                )
                return

            logger.info("✅ Сессия восстановлена! Запускаем parse_all_regions в автоматическом режиме...")
            parse_all_regions(driver)
        except Exception as e:
            logger.error(f"❌ Ошибка в auto_all_regions: {e}")
        finally:
            try:
                if driver is not None:
                    driver.quit()
            except Exception:
                pass
            current_driver = None
    finally:
        logger.info("=== AUTO MODE: парсинг всех регионов завершён (run_all_regions_cli) ===")

if __name__ == "__main__":
    import sys

    # CLI-режим: python -m src.parsers.ati_parser auto_all_regions
    if len(sys.argv) > 1 and sys.argv[1] == "auto_all_regions":
        # headless=True можно включить позже; пока False, чтобы видеть окно для отладки
        run_all_regions_cli(headless=False)
    else:
        main()
