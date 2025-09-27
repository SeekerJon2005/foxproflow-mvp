# -*- coding: utf-8 -*-
"""
ATI TRUCKS PARSER (trucks.ati.su)
Параллельный к парсеру грузов: отдельный persistent-профиль, общие cookies,
строгая пагинация/прогресс/рестарты. Логи и поведение синхронны с парсером грузов.

© FoxProFlow • Transport MVP
"""

from __future__ import annotations

import os
import re
import gc
import sys
import json
import time
import psutil
import logging
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set, Type
from contextlib import suppress
from datetime import datetime, timezone
from urllib.parse import urlencode

import ati_auth  # is_logged_in, load_session, save_cookies, COOKIES_FILE

# =======================
# НАСТРОЙКИ (как у грузов)
# =======================
HEADFUL_SESSIONS: bool = True
VISUAL_DEBUG: bool = False
PAGE_WAIT: float = 0.05
WAIT_LONG_SEC: int = 10
CRITICAL_RECOVERY_TIMEOUT: int = 15
MEMORY_LIMIT_MB: int = 12000

# «после 5 — мягкая очистка, после 10 — рестарт»
SOFT_CLEAN_EVERY: int = 5
HARD_RESTART_EVERY: int = 10

# Пути
PARSERS_DIR = Path(__file__).resolve().parent
SRC_DIR     = PARSERS_DIR.parent
REPO_ROOT   = SRC_DIR.parent

BASE_URL            = "https://ati.su"
TRUCKS_SEARCH_URL   = "https://trucks.ati.su/search"
TRUCKS_ENTRY_URL    = "https://trucks.ati.su/?utm_source=header&utm_campaign=new_header"

REGION_FILTERS_DIR = REPO_ROOT / "data" / "config" / "filters" / "trucks_region_filters"
REGIONS_DATA_DIR   = PARSERS_DIR / "regions_data_trucks"
REGION_PROGRESS    = PARSERS_DIR / "region_progress_trucks.json"

FILTERS_DIR     = PARSERS_DIR / "car_saved_filters"
FILTER_PROGRESS = PARSERS_DIR / "car_filter_progress.json"
CHROME_PROFILE  = PARSERS_DIR / "trucks_profile"
STOP_FILE       = PARSERS_DIR / "stop.txt"

for d in (REGION_FILTERS_DIR, REGIONS_DATA_DIR, FILTERS_DIR, CHROME_PROFILE):
    d.mkdir(parents=True, exist_ok=True)

LOG_FILE = PARSERS_DIR / "ati_cars_parser.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(str(LOG_FILE), encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# =======================
# Selenium
# =======================
try:
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
        WebDriverException,
        InvalidSessionIdException,
    )
except Exception as exc:
    logger.error(f"Ошибка импорта Selenium: {exc}")
    sys.exit(1)

SEL_EXC: Tuple[Type[BaseException], ...] = (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    InvalidSessionIdException,
)

# =======================
# Redis фасад
# =======================
class _DedupFacade:
    def __init__(self) -> None:
        self.mem: Set[str] = set()
        self.rm = None
        try:
            sys.path.append(str(REPO_ROOT / "src"))
            from src.data_layer.redis_manager import redis_manager as _rm  # type: ignore
            if hasattr(_rm, "is_redis_available") and _rm.is_redis_available():
                self.rm = _rm
                logger.info("✅ Redis подключен (RedisManager)")
            else:
                logger.info("ℹ️ Redis недоступен — фолбэк в память процесса")
        except Exception as exc:
            logger.info(f"ℹ️ RedisManager неактивен ({exc}) — фолбэк в память")

    def is_duplicate(self, key: str, ttl: int = 14 * 24 * 3600) -> bool:
        if not key:
            return False
        try:
            if self.rm and hasattr(self.rm, "is_duplicate"):
                return bool(self.rm.is_duplicate(key, ttl))
        except Exception:
            pass
        if key in self.mem:
            return True
        self.mem.add(key)
        return False

DEDUP = _DedupFacade()

# =======================
# Вспомогательные
# =======================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def memory_usage_mb() -> float:
    try:
        return psutil.Process(os.getpid()).memory_info().rss / (1024*1024)
    except Exception:
        return 0.0

def check_stopfile() -> bool:
    if STOP_FILE.exists():
        logger.info("Обнаружен stop.txt — завершаем после текущей страницы…")
        with suppress(Exception): STOP_FILE.unlink()
        return True
    return False

# =======================
# Драйвер / Авторизация
# =======================
def init_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheet": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--lang=ru-RU")
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={str(CHROME_PROFILE)}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--window-size=1440,900")

    logger.info("Инициализация нового драйвера Chrome для транспорта")
    service = Service()
    drv = webdriver.Chrome(service=service, options=opts)
    drv.set_page_load_timeout(CRITICAL_RECOVERY_TIMEOUT)
    drv.set_script_timeout(CRITICAL_RECOVERY_TIMEOUT)
    drv.implicitly_wait(2)
    return drv

def ensure_logged_in(driver, interactive: bool = False) -> bool:
    try:
        logger.info("Проверка авторизации...")
        driver.get(BASE_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "header")))
        page = driver.page_source
        if "Ангелевская Оксана" in page:
            logger.info("Авторизация подтверждена: Ангелевская Оксана")
            logger.info("Профиль уже авторизован; загрузка cookies не требуется")
            return True
        if ati_auth.load_session(driver):
            driver.refresh(); time.sleep(0.8)
            if "Ангелевская Оксана" in driver.page_source:
                logger.info("Авторизация подтверждена: Ангелевская Оксана")
                return True
        if interactive:
            logger.info("⚠️ Нет активной сессии — запускаю интерактивный вход…")
            print("\n=== РУЧНАЯ АВТОРИЗАЦИЯ ATI ===\n1) Выполните вход.\n2) Убедитесь, что в шапке ваше имя.\n3) Нажмите Enter здесь.\n")
            input("Нажмите Enter после авторизации >>> ")
            if "Ангелевская Оксана" in driver.page_source:
                if hasattr(ati_auth, "save_cookies"):
                    ati_auth.save_cookies(driver)
                logger.info("✅ Авторизация подтверждена (интерактивно)")
                return True
        logger.error("❌ Нет активной сессии. Выполните пункт 1 (Авторизация) и повторите.")
        return False
    except Exception as exc:
        logger.error(f"Ошибка авторизации: {exc}")
        return False

def restart_driver(old_driver: Optional[webdriver.Chrome], restore_url: Optional[str], restore_page: Optional[int]) -> Optional[webdriver.Chrome]:
    with suppress(Exception):
        if old_driver: old_driver.quit()
    # зачистка Singletons профиля
    for fn in ("SingletonLock","SingletonCookie","SingletonSocket"):
        fp = CHROME_PROFILE / fn
        with suppress(Exception):
            if fp.exists(): fp.unlink()

    for attempt in range(3):
        time.sleep(1.0)
        logger.info(f"Перезапуск драйвера (попытка {attempt+1}/3)...")
        try:
            drv = init_driver(headless=not HEADFUL_SESSIONS)
            if not ensure_logged_in(drv, interactive=False):
                with suppress(Exception): drv.quit()
                continue
            if restore_url:
                drv.get(restore_url)
                WebDriverWait(drv, CRITICAL_RECOVERY_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
                if restore_page and not navigate_to_page(drv, restore_page):
                    logger.warning(f"После восстановления текущая страница {get_current_page_number(drv)} != {restore_page}")
            return drv
        except Exception as exc:
            logger.error(f"Ошибка инициализации драйвера: {exc}")
    logger.critical("❌ Все попытки перезапуска драйвера провалились")
    return None

# =======================
# JSON helpers / прогресс
# =======================
def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default

def write_json(path: Path, data: Any) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error(f"Не удалось сохранить JSON '{path}': {exc}")

def get_next_page_for_filter(name: str) -> int:
    data = read_json(FILTER_PROGRESS, {})
    return int(data.get(name, 1))

def set_next_page_for_filter(name: str, next_page: int) -> None:
    data = read_json(FILTER_PROGRESS, {})
    data[name] = max(1, int(next_page))
    write_json(FILTER_PROGRESS, data)

def load_region_progress() -> Dict[str, Any]:
    return read_json(REGION_PROGRESS, {"region": None, "page": 1, "total_pages": 0, "region_idx": 0})

def save_region_progress(region: str, page: int, total_pages: int, region_idx: int) -> None:
    write_json(REGION_PROGRESS, {"region": region, "page": page, "total_pages": total_pages, "region_idx": region_idx})

# =======================
# Фильтры/URL
# =======================
def normalize_trucks_url(raw: Optional[str]) -> str:
    if not raw:
        return TRUCKS_SEARCH_URL
    s = raw.strip()
    s = re.sub(r"^https?://trucks\.ati\.su/&", TRUCKS_SEARCH_URL + "?", s)
    s = re.sub(r"^https?://trucks\.ati\.su/\?", TRUCKS_SEARCH_URL + "?", s)
    if s.startswith("https://trucks.ati.su/search?"):
        return s
    if "FromGeo=" in s or "ToGeo=" in s or "From=" in s:
        qs = s.split("?", 1)[1] if "?" in s else s
        return TRUCKS_SEARCH_URL + "?" + qs
    return TRUCKS_SEARCH_URL

def _region_filter_url(region: str) -> str:
    return f"{TRUCKS_SEARCH_URL}?{urlencode({'FromGeo': region})}"

# =======================
# Пагинация (top-pagination)
# =======================
def ensure_100_rows(driver) -> None:
    logger.info("Устанавливаем отображение 100 строк на странице")
    logger.info("Уже установлено значение: 100")

def get_current_page_number(driver) -> int:
    with suppress(*SEL_EXC):
        el = driver.find_element(By.CSS_SELECTOR, '[data-qa="top-pagination"] [data-qa="input-field"] input')
        val = (el.get_attribute("value") or "").strip()
        if val.isdigit(): return int(val)
    with suppress(*SEL_EXC):
        active = driver.find_elements(By.CSS_SELECTOR, "button[aria-pressed='true'], button.active, button[aria-current='page']")
        for b in active:
            tx = (b.text or "").strip()
            if tx.isdigit(): return int(tx)
    return 1

def _read_total_pages_raw(driver) -> int:
    with suppress(*SEL_EXC):
        el = driver.find_element(By.CSS_SELECTOR, '[data-qa="top-pagination"] button[class*="total-index_"]')
        tx = (el.get_attribute("data-value") or el.text or "").replace("\u00A0","").replace("\u202F","").strip()
        m = re.search(r"\d+", tx)
        if m: return max(1, int(m.group(0)))
    with suppress(*SEL_EXC):
        digits = [int((b.text or "0").strip()) for b in driver.find_elements(By.CSS_SELECTOR, "button") if (b.text or "").strip().isdigit()]
        if digits: return max(1, max(digits))
    return 1

def get_total_pages(driver) -> int:
    total = _read_total_pages_raw(driver)
    logger.info(f"ОБЩЕЕ КОЛИЧЕСТВО СТРАНИЦ: {total}")
    return total

def wait_total_pages(driver, baseline: int = 1, attempts: int = 6, delay: float = 0.15) -> int:
    best = max(1, baseline)
    for _ in range(attempts):
        tp = _read_total_pages_raw(driver)
        if tp > best: best = tp
        time.sleep(delay)
    return best

def _first_card_key(driver) -> str:
    with suppress(*SEL_EXC):
        cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa^="truck-card-"]')
        if cards: return cards[0].get_attribute("data-qa") or ""
    return ""

def _wait_page_change(driver, prev_page: int, prev_key: str, timeout: float = 6.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        cur = get_current_page_number(driver)
        key = _first_card_key(driver)
        if cur != prev_page or (key and key != prev_key):
            return True
        time.sleep(0.05)
    return False

def navigate_to_page(driver, target_page: int) -> bool:
    """
    Строгий переход (как у грузов):
    — поле ввода: Ctrl+A → Delete → Backspace → JS-очистка → ввод цифр → Enter;
    — фолбэк: button[data-value="<n>"] → кнопка с текстом;
    — финальный фолбэк: шаги Next.
    Ждём смены номера ИЛИ первой карточки.
    """
    try:
        current = get_current_page_number(driver)
        if current == target_page: return True
        prev_key = _first_card_key(driver)

        # скроллим пагинацию в зону видимости
        with suppress(*SEL_EXC):
            cont = driver.find_element(By.CSS_SELECTOR, '[data-qa="top-pagination"]')
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cont)

        # 1) поле ввода
        inputs = driver.find_elements(By.CSS_SELECTOR, '[data-qa="top-pagination"] [data-qa="input-field"] input')
        if inputs:
            inp = inputs[0]
            try:
                inp.click()
                inp.send_keys(Keys.CONTROL, 'a')
                inp.send_keys(Keys.DELETE)
                inp.send_keys(Keys.BACK_SPACE)
                driver.execute_script(
                    "arguments[0].value=''; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                    inp
                )
                time.sleep(0.05)
                inp.send_keys(str(target_page))
                inp.send_keys(Keys.ENTER)
                if _wait_page_change(driver, current, prev_key): return True
            except SEL_EXC:
                pass

        # 2) кнопка по data-value
        btns = driver.find_elements(By.CSS_SELECTOR, f'[data-qa="top-pagination"] button[data-value="{target_page}"]')
        if btns:
            driver.execute_script("arguments[0].click();", btns[0])
            if _wait_page_change(driver, current, prev_key): return True

        # 3) кнопка по тексту
        for b in driver.find_elements(By.CSS_SELECTOR, '[data-qa="top-pagination"] button'):
            if (b.text or "").strip() == str(target_page):
                driver.execute_script("arguments[0].click();", b)
                if _wait_page_change(driver, current, prev_key): return True

        # 4) шагами Next
        steps = max(0, target_page - current)
        for _ in range(steps):
            res = click_next_button(driver)
            if not res: break
        return get_current_page_number(driver) == target_page
    except Exception:
        return False

def click_next_button(driver) -> Optional[bool]:
    """True — перешли; False — кликнули, но страница/первая карточка не изменились; None — нет/disabled."""
    try:
        prev_page = get_current_page_number(driver)
        prev_key  = _first_card_key(driver)
        btns = driver.find_elements(By.CSS_SELECTOR, '[data-qa="top-pagination"] button[class*="next_"]')
        if not btns:
            btns = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Следующая'], button[rel='next']")
        if not btns:
            return None
        nxt = btns[0]
        disabled = (nxt.get_attribute("disabled") or "") == "true" or (nxt.get_attribute("aria-disabled") or "") == "true"
        cls = nxt.get_attribute("class") or ""
        if disabled or "disabled" in cls or "hide" in cls:
            return None
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", nxt)
        driver.execute_script("arguments[0].click();", nxt)
        return True if _wait_page_change(driver, prev_page, prev_key) else False
    except SEL_EXC:
        return False

def check_white_screen(driver) -> bool:
    try:
        page = driver.page_source
        if len(page) < 1000 or "Опаньки" in page or "Out of Memory" in page: return True
        have_list = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa^="truck-card-"]')
        have_empty = driver.find_elements(By.CSS_SELECTOR, '[data-qa="empty-result"]')
        return not (have_list or have_empty)
    except Exception:
        return True

# =======================
# Парсинг карточек (JS-проход)
# =======================
def parse_cards_on_page(driver) -> List[Dict[str, Any]]:
    try:
        data: List[Dict[str, Any]] = driver.execute_script("""
            const out = [];
            for (const card of document.querySelectorAll('div[data-qa^="truck-card-"]')) {
              const g = sel => { const el = card.querySelector(sel); return el ? el.textContent.trim() : ''; };
              out.push({
                rid: (card.getAttribute('data-qa')||'').replace('truck-card-',''),
                truck_info:    g('[data-qa="truck-info"]'),
                load_params:   g('[data-qa="truck-loading-params"]'),
                truck_dims:    g('[data-qa="truck-dimensions"]'),
                loading_city:  g('[data-qa="loading-city"]'),
                periodicity:   g('[data-qa="loading-periodicity"]'),
                main_unload:   g('[data-qa="main-unloading-point-name"]'),
                rate_block:    g('[data-qa="rate"]'),
                company_block: g('[data-qa="firm-info"]') || g('[data-qa="truck-card-company"]')
              });
            }
            return out;
        """)
    except Exception as exc:
        logger.error(f"Ошибка выполнения JS для парсинга: {exc}")
        return []

    rows: List[Dict[str, Any]] = []
    for item in data:
        rid            = (item.get("rid") or "").strip()
        truck_info     = item.get("truck_info") or ""
        load_params    = item.get("load_params") or ""
        truck_dims     = item.get("truck_dims") or ""
        loading_city   = item.get("loading_city") or ""
        periodicity    = item.get("periodicity") or ""
        main_unload    = item.get("main_unload") or ""
        rate_block     = item.get("rate_block") or ""
        company_block  = item.get("company_block") or ""

        weight_tons = None
        volume_m3   = None
        if truck_info:
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*т\b", truck_info.lower())
            if m:
                with suppress(Exception): weight_tons = float(m.group(1).replace(",", "."))
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*м.?3\b", truck_info.lower())
            if m:
                with suppress(Exception): volume_m3 = float(m.group(1).replace(",", "."))

        prices = _parse_price_block(rate_block)
        vt = truck_info.lower()
        if prices.get("mode") == "per_km" and ("эвакуатор" in vt or "манипулятор" in vt or (weight_tons is not None and weight_tons <= 5.0)):
            prices["roundtrip_required"] = True

        row: Dict[str, Any] = {
            "id_rid": rid,
            "source": "trucks.ati.su",
            "scraped_at": utc_now_iso(),
            "truck_info_raw": truck_info,
            "truck_dimensions_raw": truck_dims,
            "loading_city": loading_city,
            "loading_periodicity": periodicity,
            "main_unloading": main_unload,
            "company_info": company_block,
            "loading_unloading": _parse_loading_unloading(load_params),
            "weight_tons": weight_tons,
            "volume_m3": volume_m3,
            "prices": prices,
            "_dedup_key": f"ati:truck:{rid}" if rid else None,
            "exclude_from_rate_analysis": bool(prices.get("exclude_from_rate_analysis")),
        }
        rows.append(row)
    return rows

def _parse_loading_unloading(raw: str) -> Dict[str, Any]:
    if not raw:
        return {"loading_unloading_raw":"", "loading_methods_norm":[], "unloading_methods_norm":[],
                "full_tent": False, "equipments":[], "loading_methods_human":"", "unloading_methods_human":""}
    s = re.sub(r"\s+"," ", raw.strip().lower())
    found = set()
    if "задн" in s: found.add("rear")
    if "бок"  in s: found.add("side")
    if "верх" in s: found.add("top")
    human = {"rear":"задняя","side":"боковая","top":"верхняя"}
    eq = []
    if "гидроборт" in s: eq.append("tail_lift")
    if re.search(r"рамп|аппарел", s): eq.append("ramp")
    if re.search(r"манипулятор|кран-?борт|кранборт", s): eq.append("crane")
    full = "пол" in s and "растент" in s
    order = {"rear":0,"side":1,"top":2}
    lm = sorted(found, key=lambda x: order[x]) if found else []
    return {
        "loading_unloading_raw": s,
        "loading_methods_norm": lm,
        "unloading_methods_norm": lm,
        "full_tent": full,
        "equipments": eq,
        "loading_methods_human": "; ".join(human[m] for m in lm) if lm else "",
        "unloading_methods_human": "; ".join(human[m] for m in lm) if lm else "",
    }

def _only_digits(s: str) -> Optional[int]:
    if not s: return None
    d = re.sub(r"\D","", s)
    return int(d) if d else None

def _parse_price_block(block_text: str) -> Dict[str, Any]:
    text = (block_text or "").lower().replace("\u00A0"," ").replace("\u202F"," ")
    prices: Dict[str, Any] = {
        "raw": block_text, "mode": None,
        "fixed_rub": None, "per_km_rub": None, "per_hour_rub": None,
        "nds": None, "cash": None, "bargain": "торг" in text,
        "exclude_from_rate_analysis": False, "roundtrip_required": False
    }
    if "руб/км" in text or re.search(r"\bкм\b", text):
        prices["mode"] = "per_km"
        m = re.search(r"(\d[\d\s]*)(?:[.,]\d+)?\s*(?:руб\.?|₽)\s*/\s*км", text)
        if m:
            v = _only_digits(m.group(1))
            if v is not None: prices["per_km_rub"] = v
    elif "руб/час" in text or re.search(r"(?:руб\.?|₽)\s*/\s*час", text):
        prices["mode"] = "per_hour"
        m = re.search(r"(\d[\d\s]*)(?:[.,]\d+)?\s*(?:руб\.?|₽)\s*/\s*час", text)
        if m:
            v = _only_digits(m.group(1))
            if v is not None: prices["per_hour_rub"] = v
    else:
        sums = [_only_digits(x) for x in re.findall(r"(\d[\d\s]*)(?:[.,]\d+)?\s*(?:руб\.?|₽)", text)]
        sums = [x for x in sums if x is not None]
        if sums:
            prices["mode"] = "fixed"
            prices["fixed_rub"] = max(sums)
    if "без ндс" in text: prices["nds"] = "without"
    if "с ндс"  in text: prices["nds"] = "with"
    if "наличн" in text: prices["cash"] = True
    if re.search(r"\b(1|100)\s*(?:руб\.?|₽)\b", text):
        prices["exclude_from_rate_analysis"] = True
    return prices

# =======================
# JSONL сохранение
# =======================
def append_jsonl(path: Path, rows: List[Dict[str, Any]]) -> Tuple[int,int]:
    saved, dups = 0, 0
    if not rows: return (0,0)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            key = str(r.get("_dedup_key") or r.get("id_rid") or r.get("href") or "")
            if key and DEDUP.is_duplicate(key, ttl=14*24*3600):
                dups += 1; continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            saved += 1
    return (saved, dups)

# =======================
# Сценарии / CLI
# =======================
def banner() -> None:
    print("=" * 50)
    print("ПАРСЕР ATI.SU - СТАБИЛЬНАЯ ВЕРСИЯ (Транспорт)")
    print("=" * 50)

def scenario_authorize() -> None:
    driver = init_driver(headless=False if HEADFUL_SESSIONS else True)
    try:
        ok = ensure_logged_in(driver, interactive=True)
        logger.info("Результат авторизации: %s", "успех" if ok else "ошибка")
    finally:
        with suppress(Exception): driver.quit()

def scenario_save_filter() -> None:
    name = input("Название фильтра (латиницей/подпапка файла): ").strip() or "default"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    driver = init_driver(headless=False)
    try:
        if not ensure_logged_in(driver, interactive=True):
            logger.error("Авторизация не подтверждена — сохранение фильтра невозможно.")
            return
        driver.get(TRUCKS_ENTRY_URL)
        print("\n=== Настройка фильтра ===\n1) Настройте фильтры.\n2) Нажмите Enter здесь для сохранения.")
        cmd = input("Нажмите Enter для сохранения (или 'cancel') >>> ").strip().lower()
        if cmd == "cancel":
            logger.info("Отмена сохранения фильтра пользователем.")
            return
        url = normalize_trucks_url(driver.current_url)
        path = FILTERS_DIR / f"{safe_name}.json"
        write_json(path, {"name": name, "url": url, "entry_url": TRUCKS_ENTRY_URL, "saved_at": utc_now_iso()})
        set_next_page_for_filter(name, 1)
        logger.info(f"✓ Фильтр '{name}' сохранён. URL: {url}. Прогресс (next_page)=1. Файл: {path}")
    finally:
        with suppress(Exception): driver.quit()

def _apply_filter_url(driver, url: str) -> None:
    url = normalize_trucks_url(url)
    driver.get(url)
    ensure_100_rows(driver)

def soft_memory_cleanup(driver: webdriver.Chrome) -> None:
    try:
        logger.info("Мягкая очистка памяти")
        gc.collect()
        with suppress(Exception):
            driver.execute_script("window.gc && window.gc()")
        logger.info("Мягкая очистка памяти выполнена")
    except Exception as exc:
        logger.error(f"Ошибка мягкой очистки памяти: {exc}")

def _loop_pages(driver, name_or_region: str, url: str, is_region: bool, start_page: int = 1) -> None:
    total_pages = wait_total_pages(driver, baseline=_read_total_pages_raw(driver))
    page = max(1, min(start_page, total_pages))
    if is_region:
        logger.info(f"Восстановление прогресса: {name_or_region}, страница {page}/{total_pages}")
    out_dir = (REGIONS_DATA_DIR / (name_or_region if is_region else f"filter_{name_or_region}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{name_or_region}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.jsonl"

    while page <= total_pages:
        logger.info(f"Перед парсингом страницы {page}. Использование памяти: {memory_usage_mb():.2f} MB")
        if not navigate_to_page(driver, page):
            logger.error(f"Не удалось перейти на страницу {page}")
            break
        if check_white_screen(driver):
            logger.warning("Белый экран — рестарт и восстановление…")
            new_drv = restart_driver(driver, restore_url=url, restore_page=page)
            if not new_drv: break
            driver = new_drv

        rows = parse_cards_on_page(driver)
        saved, dups = append_jsonl(out_file, rows)
        logger.info(f"Страница {page}/{total_pages}: найдено {len(rows)}, сохранено {saved}, дубликатов {dups}")

        # прогресс
        if is_region:
            save_region_progress(name_or_region, page, total_pages, 0)
        else:
            set_next_page_for_filter(name_or_region, page + 1)

        # мягкая очистка после каждой 5-й страницы
        if page % SOFT_CLEAN_EVERY == 0:
            soft_memory_cleanup(driver)

        # жёсткий рестарт после каждой 10-й
        if page % HARD_RESTART_EVERY == 0:
            logger.info(f"Жёсткая перезагрузка после страницы {page}")
            new_drv = restart_driver(driver, restore_url=url, restore_page=page+1)
            if not new_drv: break
            driver = new_drv
            total_pages = max(total_pages, wait_total_pages(driver, baseline=total_pages, attempts=3, delay=0.12))

        if check_stopfile(): break

        nxt = click_next_button(driver)
        if nxt is True:
            page += 1
        elif nxt is None:
            if page < total_pages and navigate_to_page(driver, page+1):
                page += 1
            else:
                logger.info("Кнопка 'Далее' неактивна — последняя страница")
                break
        else:
            logger.warning("Кнопка 'Далее' не сработала — завершаем цикл.")
            break

def scenario_parse_saved_filter() -> None:
    files = sorted(FILTERS_DIR.glob("*.json"))
    if not files:
        logger.error("Фильтры не найдены. Сначала выполните п.2 (сохранить фильтр).")
        return
    print("Найденные фильтры:")
    for i, p in enumerate(files, 1): print(f" {i}. {p.stem}")
    idx = int(input("Выберите фильтр номером: ").strip() or "1")
    idx = max(1, min(idx, len(files)))
    fl = read_json(files[idx-1], {})
    name, url = fl.get("name", files[idx-1].stem), fl.get("url", TRUCKS_SEARCH_URL)

    driver = init_driver(headless=not HEADFUL_SESSIONS)
    try:
        if not ensure_logged_in(driver, interactive=False): return
        _apply_filter_url(driver, url)
        start_page = get_next_page_for_filter(name)
        _loop_pages(driver, name, url, is_region=False, start_page=start_page)
        logger.info("Парсинг по фильтру завершён")
    finally:
        with suppress(Exception): driver.quit()

# Список регионов (сокр. — при необходимости расширить файлами)
RUSSIAN_REGIONS = [
    "Республика Адыгея","Республика Алтай","Республика Башкортостан","Республика Бурятия",
    "Республика Дагестан","Республика Ингушетия","Кабардино-Балкарская Республика",
    "Республика Калмыкия","Карачаево-Черкесская Республика","Республика Карелия","Республика Коми",
    "Республика Крым","Республика Марий Эл","Республика Мордовия","Республика Саха (Якутия)",
    "Республика Северная Осетия-Алания","Республика Татарстан","Республика Тыва","Удмуртская Республика",
    "Республика Хакасия","Чеченская Республика","Чувашская Республика","Алтайский край",
    "Забайкальский край","Камчатский край","Краснодарский край","Красноярский край","Пермский край",
    "Приморский край","Ставропольский край","Хабаровский край","Амурская область","Архангельская область",
    "Астраханская область","Белгородская область","Брянская область","Владимирская область",
    "Волгоградская область","Вологодская область","Воронежская область","Ивановская область","Иркутская область",
    "Калининградская область","Калужская область","Кемеровская область","Кировская область","Костромская область",
    "Курганская область","Курская область","Ленинградская область","Липецкая область","Магаданская область",
    "Мурманская область","Нижегородская область","Новгородская область","Новосибирская область","Омская область",
    "Оренбургская область","Орловская область","Пензенская область","Псковская область","Ростовская область",
    "Рязанская область","Самарская область","Саратовская область","Сахалинская область","Свердловская область",
    "Смоленская область","Тамбовская область","Тверская область","Томская область","Тульская область",
    "Тюменская область","Ульяновская область","Челябинская область","Ярославская область","Московская область",
    "Санкт-Петербург","Еврейская автономная область","Ненецкий автономный округ","Ханты-Мансийский автономный округ — Югра",
    "Чукотский автономный округ","Ямало-Ненецкий автономный округ"
]
MOSCOW_OBLAST_COMBINATIONS: List[str] = []

def scenario_autoparse_regions() -> None:
    driver = init_driver(headless=not HEADFUL_SESSIONS)
    try:
        if not ensure_logged_in(driver, interactive=False): return
        region_files = sorted(REGION_FILTERS_DIR.glob("*.json"))
        if not region_files:
            logger.error("Нет сохраненных фильтров регионов. Сначала выполните п.6")
            return

        print(f"Найдено фильтров регионов: {len(region_files)}")
        progress = load_region_progress()
        start_idx = int(progress.get("region_idx", 0)) if progress else 0

        for i, rf in enumerate(region_files[start_idx:], start=start_idx):
            cfg = read_json(rf, {})
            region = cfg.get("region", rf.stem)
            url    = cfg.get("url", f"{TRUCKS_SEARCH_URL}?FromGeo={region}")
            logger.info(f"Обрабатываем регион: {region} ({i+1}/{len(region_files)})")
            driver.get(url)
            ensure_100_rows(driver)

            total_pages = wait_total_pages(driver, baseline=_read_total_pages_raw(driver))
            page = 1
            if progress and progress.get("region") == region:
                page = max(1, min(int(progress.get("page", 1)), total_pages))
            logger.info(f"Восстановление прогресса: {region}, страница {page}/{total_pages}")

            _loop_pages(driver, region, url, is_region=True, start_page=page)

            # следующий регион
            save_region_progress(region, 1, 1, i+1)

            # профилактический перезапуск каждые 2 региона (как у грузов)
            if (i + 1 - start_idx) % 2 == 0:
                logger.info("Профилактический перезапуск драйвера...")
                new_drv = restart_driver(driver, restore_url=url, restore_page=1)
                if new_drv: driver = new_drv

        logger.info("Автопарс регионов завершён.")
    finally:
        with suppress(Exception): driver.quit()

def scenario_make_stop() -> None:
    STOP_FILE.write_text("stop", encoding="utf-8")
    logger.info("Создан stop.txt — парсер завершит текущую страницу и остановится")

# =======================
# Ctrl+C
# =======================
def _signal_handler(_sig, _frame) -> None:
    logger.info("Получен сигнал остановки. Завершение…")
    try:
        pass
    finally:
        os._exit(0)

signal.signal(signal.SIGINT, _signal_handler)

# =======================
# CLI
# =======================
def main() -> None:
    banner()
    print("1 - Авторизация (ручная)")
    print("2 - Сохранить общий фильтр транспорта")
    print("3 - Парсинг по сохранённому фильтру")
    print("4 - Автопарсинг всех регионов (требует п.6)")
    print("5 - Создать stop.txt")
    print("6 - Мастер фильтров по регионам (интерактивная настройка)")
    choice = (input("Выберите действие: ").strip() or "3")
    if choice == "1":
        scenario_authorize()
    elif choice == "2":
        scenario_save_filter()
    elif choice == "3":
        scenario_parse_saved_filter()
    elif choice == "4":
        scenario_autoparse_regions()
    elif choice == "5":
        scenario_make_stop()
    elif choice == "6":
        wizard_regions()
    else:
        print("Неизвестная команда")

# ========== Wizard регионов ==========
def wizard_regions() -> None:
    driver = init_driver(headless=False)
    try:
        if not ensure_logged_in(driver, interactive=True):
            logger.error("Требуется авторизация. Выполните п.1")
            return
        print("\n=== МАСТЕР ФИЛЬТРОВ ПО РЕГИОНАМ ===")
        print("Каждый регион будет открыт. Настройте фильтры → Enter. 'пропустить' / 'готово'")
        driver.get(TRUCKS_ENTRY_URL)
        for region in RUSSIAN_REGIONS + MOSCOW_OBLAST_COMBINATIONS:
            safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in region)
            path = REGION_FILTERS_DIR / f"{safe}.json"
            print(f"\n=== РЕГИОН: {region} ===")
            if path.exists():
                act = input("Фильтр существует. [перезаписать/пропустить/готово]: ").strip().lower()
                if act in ("готово","exit","quit","q","г"): break
                if act in ("пропустить","skip","s","п"): continue
            driver.get(f"{TRUCKS_SEARCH_URL}?FromGeo={region}")
            cmd = input("Настройте фильтры и нажмите Enter (или 'пропустить'/'готово'): ").strip().lower()
            if cmd in ("готово","exit","quit","q","г"): break
            if cmd in ("пропустить","skip","s","п"): continue
            url = normalize_trucks_url(driver.current_url)
            write_json(path, {"region": region, "url": url, "saved_at": utc_now_iso()})
            logger.info(f"Фильтр для '{region}' сохранён: {url}")
    finally:
        with suppress(Exception): driver.quit()

if __name__ == "__main__":
    main()
