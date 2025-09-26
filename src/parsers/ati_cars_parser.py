# -*- coding: utf-8 -*-
"""
ATI TRUCKS PARSER (trucks.ati.su) — видимые сессии + визуальный дебаг (подробные логи и подсветка элементов)

Переключатели в начале файла:
- HEADFUL_SESSIONS: все сессии (2/3/4/6) запускаются с окном браузера
- VISUAL_DEBUG: подсветка элементов + HUD в окне
- TERMINAL_COLOR_LOGS: цвет в консоли (рекомендуется pip install colorama)
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import psutil
import random
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import suppress

# ====== НАСТРОЙКИ ======
HEADFUL_SESSIONS: bool = True     # все сессии (в меню 2/3/4/6) — с окном браузера
VISUAL_DEBUG: bool = True         # встраиваем HUD и подсветку элементов в браузер
TERMINAL_COLOR_LOGS: bool = True  # цветные логи в терминал (если доступен colorama)

# Палитра для подсветки
COLORS = {
    "page_size":   "#42a5f5",
    "nav_input":   "#fdd835",
    "nav_next":    "#fb8c00",
    "card":        "#d81b60",
    "price":       "#66bb6a",
    "company":     "#ab47bc",
}

# ====== selenium ======
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        StaleElementReferenceException,
        WebDriverException,
    )
    ChromeOptionsType = webdriver.ChromeOptions  # type: ignore[attr-defined]
except ImportError:
    # Фолбэк: определим "пустые" типы, чтобы линтер не ругался на кортеж исключений
    class _DummyExc(Exception): ...
    TimeoutException = _DummyExc  # type: ignore
    NoSuchElementException = _DummyExc  # type: ignore
    StaleElementReferenceException = _DummyExc  # type: ignore
    WebDriverException = _DummyExc  # type: ignore
    webdriver = Any  # type: ignore
    By = Keys = WebDriverWait = object  # type: ignore
    ChromeOptionsType = Any  # type: ignore

# Единый набор исключений Selenium (всегда tuple[BaseException,...])
SEL_EXC = (TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException)

# ====== ПУТИ/КАТАЛОГИ ======

PARSERS_DIR = Path(__file__).resolve().parent
SRC_DIR     = PARSERS_DIR.parent
REPO_ROOT   = SRC_DIR.parent

BASE_URL        = "https://ati.su"
LISTING_URL     = "https://trucks.ati.su/?sort=createdAtDesc"

REGION_FILTERS_DIR = REPO_ROOT / "data" / "config" / "filters" / "trucks_region_filters"
REGIONS_DATA_DIR   = PARSERS_DIR / "regions_data_trucks"
REGION_PROGRESS    = PARSERS_DIR / "region_progress_trucks.json"

FILTERS_DIR        = PARSERS_DIR / "car_saved_filters"
FILTER_PROGRESS    = PARSERS_DIR / "car_filter_progress.json"
COOKIES_FILE       = PARSERS_DIR / "ati_cookies.json"
CHROME_PROFILE     = PARSERS_DIR / "trucks_profile"
STOP_FILE          = PARSERS_DIR / "stop.txt"

for d in (REGION_FILTERS_DIR, REGIONS_DATA_DIR, FILTERS_DIR, CHROME_PROFILE):
    d.mkdir(parents=True, exist_ok=True)

WAIT_SHORT = 6
WAIT_LONG  = 18
HARD_RESTART_EVERY = 6
PAUSE_BETWEEN_REGIONS = (4, 6)

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
ALL_REGIONS_164 = RUSSIAN_REGIONS + [f"Московская область - {r}" for r in RUSSIAN_REGIONS]

# ====== ЛОГИРОВАНИЕ ======

class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG:    "\033[36m",  # cyan
        logging.INFO:     "\033[37m",  # white/gray
        logging.WARNING:  "\033[33m",  # yellow
        logging.ERROR:    "\033[31m",  # red
        logging.CRITICAL: "\033[41m",  # red bg
    }
    RESET = "\033[0m"
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{msg}{self.RESET}"

def _setup_logging() -> None:
    level = logging.DEBUG
    fmt = "%(asctime)s - %(levelname)s - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    file_handler = logging.FileHandler(str(PARSERS_DIR / "ati_cars_parser.log"), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt, datefmt))

    console_handler = logging.StreamHandler()
    if TERMINAL_COLOR_LOGS:
        try:
            from colorama import just_fix_windows_console  # type: ignore
            just_fix_windows_console()
            console_handler.setFormatter(_ColorFormatter(fmt, datefmt))
        except Exception:
            console_handler.setFormatter(logging.Formatter(fmt, datefmt))
    else:
        console_handler.setFormatter(logging.Formatter(fmt, datefmt))

    logging.basicConfig(level=level, handlers=[console_handler, file_handler])

_setup_logging()

def banner_once() -> None:
    print("==================================================")
    print("ПАРСЕР ATI.SU - ГИБРИДНАЯ СТАБИЛЬНАЯ ВЕРСИЯ (видимые сессии + подсветка)")
    print("==================================================")

# ====== Redis фасад ======

class _DedupFacade:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self.rm = None
        candidates = [
            ("data_layer.redis_manager", "redis_manager"),
            ("redis_manager", "redis_manager"),
        ]
        for mod, attr in candidates:
            try:
                sys.path.append(str(REPO_ROOT / "src"))
                m = __import__(mod, fromlist=[attr])
                self.rm = getattr(m, attr)
                break
            except (ImportError, AttributeError):
                self.rm = None
        if self.is_redis_available():
            logging.info("✅ Успешное подключение к Redis")
            logging.info("✅ Redis подключен (RedisManager)")
        else:
            logging.warning("❌ Redis недоступен — будет фолбэк")

    def is_redis_available(self) -> bool:
        try:
            return bool(self.rm and getattr(self.rm, "is_redis_available", lambda: False)())
        except Exception:
            return False

    def is_duplicate(self, key: str, ttl: int = 14 * 24 * 3600) -> bool:
        if not key:
            return False
        if self.is_redis_available():
            with suppress(Exception):
                fn = getattr(self.rm, "is_duplicate", None)
                if fn and callable(fn):
                    return bool(fn(key, ttl))
        if key in self._seen:
            return True
        self._seen.add(key)
        return False

DEDUP = _DedupFacade()

# ====== УТИЛИТЫ ======

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\-\s]+", "", s, flags=re.I | re.U)
    s = re.sub(r"\s+", "_", s)
    return s[:120] or "noname"

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
    except OSError as e:
        logging.error("Не удалось сохранить JSON '%s': %s", path, e)

def append_jsonl(path: Path, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    saved, dups = 0, 0
    if not rows:
        return saved, dups
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            key = r.get("_dedup_key") or r.get("id") or r.get("href") or ""
            if key and DEDUP.is_duplicate(str(key)):
                dups += 1
                continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            saved += 1
    return saved, dups

def memory_usage_mib() -> float:
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0

# ====== ВИЗУАЛЬНЫЙ ДЕБАГ (HUD + подсветка) ======

INJECT_DEBUG_JS = r"""
if(!window.__foxDbg){(function(){
  try{
    const styleId='foxdbg-style'; 
    if(!document.getElementById(styleId)){
      const style=document.createElement('style'); style.id=styleId;
      style.textContent = `
        .foxdbg-outline{outline: 3px solid var(--foxdbg-color, #00e676) !important; outline-offset: 2px !important; position: relative !important;}
        .foxdbg-tag{position: absolute; top: -12px; left: -2px; font: 12px/1.2 sans-serif; padding:2px 4px; background: rgba(0,0,0,0.85); color:#fff; border-radius: 4px; z-index: 2147483647;}
        #foxdbg-hud{position: fixed; top: 8px; left: 8px; padding: 8px 10px; background: rgba(0,0,0,0.7); color: #fff; font: 12px sans-serif; border-radius: 6px; z-index: 2147483647; pointer-events:none; white-space: pre-line;}
      `;
      document.head.appendChild(style);
    }
    let hud=document.getElementById('foxdbg-hud');
    if(!hud){ hud=document.createElement('div'); hud.id='foxdbg-hud'; document.body.appendChild(hud); }
    window.__foxDbg = {
      hud: function(msg){ try{ hud.textContent = msg; }catch(e){} },
      mark: function(el, color, label, ttl){
        try{
          if(!el) return;
          el.scrollIntoView({behavior:'instant', block:'center', inline:'center'});
          el.style.setProperty('--foxdbg-color', color || '#00e676');
          el.classList.add('foxdbg-outline');
          if(label){
            const tag=document.createElement('span'); tag.className='foxdbg-tag'; tag.textContent=label;
            el.appendChild(tag);
            setTimeout(()=>{ try{ tag.remove(); }catch(e){} }, ttl||1200);
          }
          setTimeout(()=>{ try{ el.classList.remove('foxdbg-outline'); el.style.removeProperty('--foxdbg-color'); }catch(e){} }, ttl||1200);
        }catch(e){}
      }
    };
  }catch(e){}
})();}
"""

def ensure_debug_ui(driver) -> None:
    if not VISUAL_DEBUG:
        return
    try:
        ok = driver.execute_script("return !!window.__foxDbg")
        if not ok:
            driver.execute_script(INJECT_DEBUG_JS)
    except SEL_EXC:
        pass

def dbg_hud(driver, msg: str) -> None:
    if not VISUAL_DEBUG:
        return
    with suppress(SEL_EXC):
        driver.execute_script("if(window.__foxDbg){__foxDbg.hud(arguments[0]);}", msg)

def dbg_mark(driver, element, color: str, label: str, ttl_ms: int = 1200) -> None:
    if not VISUAL_DEBUG:
        return
    with suppress(SEL_EXC):
        driver.execute_script("if(window.__foxDbg){__foxDbg.mark(arguments[0], arguments[1], arguments[2], arguments[3]);}", element, color, label, ttl_ms)

# ====== DRIVER / COOKIES ======

def _chrome_options(headless: Optional[bool]) -> ChromeOptionsType:  # type: ignore[name-defined]
    if headless is None:
        headless = not HEADFUL_SESSIONS
    opts = webdriver.ChromeOptions()
    opts.add_argument(f"--user-data-dir={str(CHROME_PROFILE)}")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1440,1000")
    opts.add_argument("--remote-allow-origins=*")
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    with suppress(Exception):
        opts.add_experimental_option("prefs", prefs)
    if headless:
        opts.add_argument("--headless=new")
    return opts

def _new_driver(headless: Optional[bool] = None):
    opts = _chrome_options(headless=headless)
    driver = webdriver.Chrome(options=opts)  # type: ignore[call-arg]
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    driver.implicitly_wait(2)
    with suppress(Exception):
        driver.maximize_window()
    return driver

def save_cookies(driver) -> bool:
    try:
        cookies = driver.get_cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        logging.info("Cookies ATI сохранены (%s шт.)", len(cookies))
        return True
    except (WebDriverException, OSError) as e:
        logging.error("Ошибка сохранения cookies ATI: %s", e)
        return False

def load_cookies(driver) -> bool:
    if not COOKIES_FILE.exists():
        return False
    try:
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    try:
        driver.get(BASE_URL)
        time.sleep(0.5)
        for c in cookies:
            c = dict(c)
            dom = c.get("domain") or ".ati.su"
            if "ati.su" not in dom:
                dom = ".ati.su"
            c["domain"] = dom
            c.pop("expiry", None)
            try:
                driver.add_cookie(c)
            except WebDriverException:
                c.pop("sameSite", None)
                c.pop("httpOnly", None)
                c.pop("secure", None)
                with suppress(WebDriverException):
                    driver.add_cookie(c)
        driver.get(LISTING_URL)
        return True
    except WebDriverException as e:
        logging.warning("Не удалось загрузить cookies ATI: %s", e)
        return False

def is_logged_in(driver) -> Tuple[bool, str]:
    try:
        WebDriverWait(driver, WAIT_SHORT).until(lambda _drv: _drv.execute_script("return document.readyState") == "complete")
        cand = driver.find_elements(By.CSS_SELECTOR, '[data-qa*="user"], [class*="user"], [data-qa*="profile"], [class*="profile"]')
        if cand:
            return True, "OK"
        logout = driver.find_elements(By.XPATH, "//a[contains(translate(.,'ВЫЙТИ','выЙти'),'выйти')]")
        if logout:
            return True, "OK"
        return False, ""
    except SEL_EXC:
        return False, ""

# ====== НАВИГАЦИЯ/ПАГИНАЦИЯ ======

def ensure_100_rows(driver) -> None:
    ensure_debug_ui(driver)
    try:
        dbg_hud(driver, "Выставляем отображение: 100")
        driver.execute_script("""
            try {
                const dd = document.querySelector('[data-qa="page-size"] select');
                if (dd && dd.value !== '100') {
                    dd.value='100';
                    dd.dispatchEvent(new Event('change', {bubbles:true}));
                    window._rows_set = true;
                } else if (dd && dd.value === '100') {
                    window._rows_set = true;
                }
            } catch(e) {}
        """)
        time.sleep(0.3)
        val = driver.execute_script("var s=document.querySelector('[data-qa=\"page-size\"] select');return s? s.value: null;")
        if val == "100":
            el = driver.find_element(By.CSS_SELECTOR, '[data-qa="page-size"] select')
            dbg_mark(driver, el, COLORS["page_size"], "page-size:100")
            logging.info("Отображение: 100 (select)")
            return
        btn = driver.find_elements(By.XPATH, "//button[normalize-space(.)='100']")
        if btn:
            btn[0].click()
            dbg_mark(driver, btn[0], COLORS["page_size"], "page-size:100(btn)")
            time.sleep(0.3)
            logging.info("Отображение: 100 (кнопка)")
        else:
            logging.info("Контрол 'по 100' не найден — продолжим по умолчанию")
    except SEL_EXC:
        logging.info("Контрол 'по 100' не найден — продолжим по умолчанию")

def get_total_pages(driver) -> int:
    try:
        total_btns = driver.find_elements(By.CSS_SELECTOR, "button[class*='total'], button.total-index")
        for b in total_btns:
            txt = (b.text or "").strip()
            if txt.isdigit():
                dbg_mark(driver, b, "#29b6f6", f"total={txt}")
                return max(1, int(txt))
        btns = driver.find_elements(By.CSS_SELECTOR, "button")
        digits = [int((b.text or "0").strip()) for b in btns if (b.text or "").strip().isdigit()]
        if digits:
            last = max(digits)
            # подсветим найденную последнюю цифру, если найдём элемент
            for bt in btns:
                if (bt.text or "").strip() == str(last):
                    dbg_mark(driver, bt, "#29b6f6", f"last={last}")
                    break
            return max(1, last)
    except SEL_EXC:
        pass
    return 1

def get_current_page_number(driver) -> int:
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "label input[type='number'], input[type='number']")
        for el in inputs:
            val = el.get_attribute("value") or ""
            if val.isdigit():
                return int(val)
    except SEL_EXC:
        pass
    try:
        active = driver.find_elements(By.CSS_SELECTOR, "button[aria-pressed='true'], button.active")
        for b in active:
            tx = (b.text or "").strip()
            if tx.isdigit():
                return int(tx)
    except SEL_EXC:
        pass
    return 1

def wait_cards_stable(driver, timeout: int = WAIT_LONG) -> bool:
    end = time.time() + timeout
    prev_first = None
    while time.time() < end:
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa^="truck-card-"]')
            if cards:
                first = cards[0].get_attribute("data-qa")
                if first and first == prev_first:
                    return True
                prev_first = first
            time.sleep(0.25)
        except StaleElementReferenceException:
            time.sleep(0.2)
        except SEL_EXC:
            time.sleep(0.2)
    return False

def navigate_to_page(driver, page: int) -> bool:
    ensure_debug_ui(driver)
    try:
        dbg_hud(driver, f"Переход на страницу: {page}")
        inputs = driver.find_elements(By.CSS_SELECTOR, "label input[type='number'], input[type='number']")
        if inputs:
            inp = inputs[0]
            dbg_mark(driver, inp, COLORS["nav_input"], f"PAGE={page}")
            inp.clear()
            inp.send_keys(str(page))
            inp.send_keys(Keys.ENTER)
        else:
            btns = driver.find_elements(By.CSS_SELECTOR, "button")
            for b in btns:
                if (b.text or "").strip() == str(page):
                    dbg_mark(driver, b, COLORS["nav_input"], f"PAGE={page}")
                    b.click()
                    break
        WebDriverWait(driver, WAIT_LONG).until(lambda _drv: get_current_page_number(_drv) == page)
        wait_cards_stable(driver)
        return True
    except TimeoutException:
        return False
    except SEL_EXC:
        return False

def click_next_button(driver) -> Optional[bool]:
    ensure_debug_ui(driver)
    try:
        current = get_current_page_number(driver)
        cand = driver.find_elements(By.XPATH, "//button[contains(@class,'next') or @data-qa='next']")
        if cand:
            nxt = cand[0]
            if nxt.get_attribute("disabled"):
                return None
            dbg_mark(driver, nxt, COLORS["nav_next"], "Next ▶")
            nxt.click()
        else:
            cand = driver.find_elements(By.XPATH, "//button[.//svg or contains(.,'›') or contains(.,'Следующая')]")
            if not cand:
                return None
            dbg_mark(driver, cand[0], COLORS["nav_next"], "Next ▶")
            cand[0].click()
        WebDriverWait(driver, WAIT_LONG).until(lambda _drv: get_current_page_number(_drv) == current + 1)
        wait_cards_stable(driver)
        return True
    except TimeoutException:
        return False
    except SEL_EXC:
        return False

# ====== БЕЛЫЙ ЭКРАН / РЕСТАРТ ======

def check_white_screen(driver) -> bool:
    try:
        src = driver.page_source or ""
        if len(src) < 800:
            return True
        have_list = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa="truck-cards"]')
        have_card = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa^="truck-card-"]')
        have_empty = driver.find_elements(By.CSS_SELECTOR, '[data-qa="empty-result"]')
        return not (have_list or have_card or have_empty)
    except SEL_EXC:
        return True

def restart_driver(driver, restore_url: Optional[str] = None, restore_page: Optional[int] = None, headless: Optional[bool] = None):
    with suppress(Exception):
        driver.quit()
    logging.info("Перезапуск драйвера...")
    drv = _new_driver(headless=headless)  # наследуем текущую политику HEADFUL_SESSIONS
    load_cookies(drv)
    if restore_url:
        drv.get(restore_url)
        WebDriverWait(drv, WAIT_LONG).until(lambda _drv: _drv.execute_script("return document.readyState") == "complete")
        ensure_debug_ui(drv)
        if restore_page and restore_page > 1:
            navigate_to_page(drv, restore_page)
    return drv

# ====== ПАРСИНГ КАРТОЧЕК ======

def _text(el) -> str:
    try:
        return (el.text or "").replace("\xa0", " ").strip()
    except (AttributeError, StaleElementReferenceException):
        return ""

def _parse_price_block(root) -> Dict[str, Any]:
    price_text = ""
    try:
        p = root.find_elements(By.CSS_SELECTOR, '[data-qa="price"], [class*="price"]')
        if p:
            price_text = _text(p[0])
    except SEL_EXC:
        pass

    price_text_norm = price_text.replace("\xa0", " ").lower()

    res: Dict[str, Any] = {
        "pricing_model": None,
        "price_total": None,
        "price_per_km": None,
        "currency": "RUB",
        "vat_flags": [],
        "cash_flags": [],
        "raw": price_text
    }

    if "ндс" in price_text_norm:
        res["vat_flags"].append("WithNds")
    if "без ндс" in price_text_norm or "безндс" in price_text_norm:
        res["vat_flags"].append("WithoutNds")
    if "нал" in price_text_norm:
        res["cash_flags"].append("Cash")
    if "безнал" in price_text_norm:
        res["cash_flags"].append("Cashless")

    # 1 ₽ — placeholder
    if re.search(r"(^|\s)1\s*₽($|\s)", price_text):
        res["skip_reason"] = "placeholder_1_rub"
        return res

    # NN ₽/км
    m = re.search(r"(\d[\d\s]*)\s*(?:₽|руб)\s*/\s*км", price_text_norm)
    if m:
        res["pricing_model"] = "per_km"
        with suppress(Exception):
            res["price_per_km"] = int(re.sub(r"\D+", "", m.group(1)))
        return res

    # NN ₽
    m = re.search(r"(\d[\d\s]*)\s*(?:₽|руб)\b", price_text_norm)
    if m:
        res["pricing_model"] = "fixed"
        with suppress(Exception):
            res["price_total"] = int(re.sub(r"\D+", "", m.group(1)))
        return res

    # договорная
    if "договор" in price_text_norm or "по запросу" in price_text_norm:
        res["pricing_model"] = "negotiable"
        return res

    return res

def parse_cards(driver) -> List[Dict[str, Any]]:
    ensure_debug_ui(driver)
    dbg_hud(driver, "Парсим карточки...")
    out: List[Dict[str, Any]] = []
    cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa^="truck-card-"]')
    for idx in range(len(cards)):
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-qa^="truck-card-"]')
            c = cards[idx]
        except SEL_EXC:
            continue

        try:
            dbg_mark(driver, c, COLORS["card"], f"card[{idx}]")
            qa = c.get_attribute("data-qa") or ""
            href = ""
            a = c.find_elements(By.CSS_SELECTOR, "a[href]")
            if a:
                href = a[0].get_attribute("href") or ""

            origin = destination = ""
            with suppress(SEL_EXC):
                route = c.find_elements(By.CSS_SELECTOR, '[data-qa*="route"], [class*="route"], [data-qa*="direction"]')
                if route:
                    txt = _text(route[0])
                    m = re.split(r"[-–→↔>]+", txt)
                    if len(m) >= 2:
                        origin = m[0].strip()
                        destination = m[-1].strip()

            body_type = None
            weight = volume = None
            with suppress(SEL_EXC):
                specs = c.find_elements(By.CSS_SELECTOR, '[data-qa*="spec"], [class*="spec"]')
                if specs:
                    t = _text(specs[0]).lower()
                    mw = re.search(r"(\d+(?:[.,]\d+)?)\s*т", t)
                    if mw:
                        weight = float(mw.group(1).replace(",", "."))
                    mv = re.search(r"(\d+(?:[.,]\d+)?)\s*м3", t)
                    if mv:
                        volume = float(mv.group(1).replace(",", "."))
                    for bt in ("тент", "рефрижератор", "фургон", "контейнер", "борт", "изотерм", "лесовоз", "самосвал"):
                        if bt in t:
                            body_type = bt
                            break

            price = _parse_price_block(c)
            if price.get("skip_reason") == "placeholder_1_rub":
                continue

            company = ""
            with suppress(SEL_EXC):
                cm = c.find_elements(By.CSS_SELECTOR, '[data-qa*="company"], [class*="company"]')
                if cm:
                    company = _text(cm[0])
                    dbg_mark(driver, cm[0], COLORS["company"], "Компания")

            posted_at = None
            with suppress(SEL_EXC):
                tm = c.find_elements(By.CSS_SELECTOR, "time, [datetime]")
                if tm:
                    posted_at = tm[0].get_attribute("datetime") or tm[0].get_attribute("title") or _text(tm[0])

            rec = {
                "_dedup_key": qa or href,
                "id": qa,
                "href": href,
                "origin": origin,
                "destination": destination,
                "body_type": body_type,
                "weight_t": weight,
                "volume_m3": volume,
                "company": company,
                "price": price,
                "posted_at": posted_at,
                "ts": int(time.time()),
            }
            out.append(rec)
        except SEL_EXC:
            continue
    return out

# ====== ПРОГРЕСС ======

def get_next_page_for_filter(name: str) -> int:
    mp = read_json(FILTER_PROGRESS, {})
    return int(mp.get(name, 1))

def set_next_page_for_filter(name: str, next_page: int) -> None:
    mp = read_json(FILTER_PROGRESS, {})
    mp[name] = int(max(1, next_page))
    write_json(FILTER_PROGRESS, mp)

def load_region_progress() -> Dict[str, Any]:
    return read_json(REGION_PROGRESS, {"region": "", "page": 0, "total_pages": 0, "region_idx": 0})

def save_region_progress(region: str, page: int, total_pages: int, region_idx: int) -> None:
    write_json(REGION_PROGRESS, {
        "region": region,
        "page": int(page),
        "total_pages": int(total_pages),
        "region_idx": int(region_idx),
    })

# ====== РЕЖИМЫ РАБОТЫ ======

def run_parse_filter(driver, name: str, url: str) -> None:
    logging.info("Старт фильтра '%s'. Память: %.2f MB", name, memory_usage_mib())
    driver.get(url)
    WebDriverWait(driver, WAIT_LONG).until(lambda _drv: _drv.execute_script("return document.readyState") == "complete")
    ensure_debug_ui(driver)
    dbg_hud(driver, f"Фильтр: {name}")
    ensure_100_rows(driver)
    total_pages = get_total_pages(driver)
    start_page = get_next_page_for_filter(name)
    start_page = max(1, min(start_page, total_pages))
    logging.info("ОБЩЕЕ КОЛИЧЕСТВО СТРАНИЦ: %s", total_pages)

    out_path = PARSERS_DIR / f"{slugify(name)}.jsonl"
    pages_ok = 0
    since_restart = 0

    for page in range(start_page, total_pages + 1):
        if STOP_FILE.exists():
            logging.info("Найден stop.txt — мягкая остановка после страницы %s", page)
            break

        if not navigate_to_page(driver, page):
            logging.warning("Не удалось перейти на страницу %s — прерываю фильтр", page)
            break

        if check_white_screen(driver):
            logging.warning("Обнаружен 'белый экран' на странице %s — перезапуск драйвера", page)
            driver = restart_driver(driver, restore_url=url, restore_page=page, headless=None)
            if check_white_screen(driver):
                logging.error("После перезапуска экран по-прежнему пуст — выхожу из фильтра")
                break

        logging.info("Перед парсингом страницы %s. Память: %.2f MB", page, memory_usage_mib())
        dbg_hud(driver, f"Парсинг страницы {page}/{total_pages}")
        rows = parse_cards(driver)
        saved, dups = append_jsonl(out_path, rows)
        logging.info("Страница %s/%s: найдено %s, сохранено %s, дубликатов %s",
                     page, total_pages, len(rows), saved, dups)

        set_next_page_for_filter(name, page + 1)
        pages_ok += 1
        since_restart += 1

        if page == total_pages:
            logging.info("Кнопка 'Далее' неактивна — последняя страница")
            break

        moved = click_next_button(driver)
        if moved is None:
            logging.info("Кнопка 'Далее' неактивна — последняя страница")
            break
        if moved is False:
            navigate_to_page(driver, page + 1)

        if since_restart >= HARD_RESTART_EVERY:
            logging.info("Профилактический перезапуск драйвера...")
            driver = restart_driver(driver, restore_url=url, restore_page=page + 1, headless=None)
            since_restart = 0

    logging.info("Успешно обработан фильтр '%s'. Страниц OK: %s/%s", name, pages_ok, total_pages)

def run_parse_region(driver, region_name: str, region_idx: int, url: str) -> None:
    logging.info("Начало региона %s (%s/%s). Память: %.2f MB", region_name, region_idx, len(ALL_REGIONS_164), memory_usage_mib())
    driver.get(url)
    WebDriverWait(driver, WAIT_LONG).until(lambda _drv: _drv.execute_script("return document.readyState") == "complete")
    ensure_debug_ui(driver)
    dbg_hud(driver, f"Регион: {region_name}")
    ensure_100_rows(driver)
    total_pages = get_total_pages(driver)
    prog = load_region_progress()
    if prog.get("region") == region_name:
        start_page = max(1, int(prog.get("page", 1)))
    else:
        start_page = 1
    save_region_progress(region_name, start_page, total_pages, region_idx)
    logging.info("ОБЩЕЕ КОЛИЧЕСТВО СТРАНИЦ: %s", total_pages)

    out_path = REGIONS_DATA_DIR / f"{region_idx:03d}_{slugify(region_name)}.jsonl"
    pages_ok = 0
    since_restart = 0

    for page in range(start_page, total_pages + 1):
        if STOP_FILE.exists():
            logging.info("Найден stop.txt — мягкая остановка после страницы %s", page)
            break

        if not navigate_to_page(driver, page):
            logging.warning("Не удалось перейти на страницу %s — прерываю регион '%s'", page, region_name)
            break

        if check_white_screen(driver):
            logging.warning("Обнаружен 'белый экран' на странице %s — перезапуск драйвера", page)
            driver = restart_driver(driver, restore_url=url, restore_page=page, headless=None)
            if check_white_screen(driver):
                logging.error("После перезапуска экран по-прежнему пуст — выхожу из региона '%s'", region_name)
                break

        logging.info("Перед парсингом страницы %s. Память: %.2f MB", page, memory_usage_mib())
        dbg_hud(driver, f"Парсинг страницы {page}/{total_pages}")
        rows = parse_cards(driver)
        saved, dups = append_jsonl(out_path, rows)
        logging.info("Страница %s/%s: найдено %s, сохранено %s, дубликатов %s",
                     page, total_pages, len(rows), saved, dups)

        save_region_progress(region_name, page + 1, total_pages, region_idx)
        pages_ok += 1
        since_restart += 1

        if page == total_pages:
            logging.info("Кнопка 'Далее' неактивна — последняя страница")
            break

        moved = click_next_button(driver)
        if moved is None:
            logging.info("Кнопка 'Далее' неактивна — последняя страница")
            break
        if moved is False:
            navigate_to_page(driver, page + 1)

        if since_restart >= HARD_RESTART_EVERY:
            logging.info("Профилактический перезапуск драйвера...")
            driver = restart_driver(driver, restore_url=url, restore_page=page + 1, headless=None)
            since_restart = 0

    logging.info("Регион '%s' завершён. Страниц OK: %s/%s", region_name, pages_ok, total_pages)

# ====== КОМАНДЫ МЕНЮ ======

def cmd_authorize() -> None:
    drv = _new_driver(headless=False)
    try:
        drv.get(LISTING_URL)
        ensure_debug_ui(drv)
        dbg_hud(drv, "Авторизация: выполните вход в аккаунт ATI, затем вернитесь в терминал")
        print("\n=== РУЧНАЯ АВТОРИЗАЦИЯ ATI ===")
        print("1) В открывшемся окне Chrome выполните вход в аккаунт ATI")
        print("2) Вернитесь в терминал и нажмите Enter — я сохраню cookies")
        input("Нажмите Enter после входа в аккаунт >>> ")
        save_cookies(drv)
        ok, uname = is_logged_in(drv)
        if ok:
            logging.info("Авторизация подтверждена: %s", uname)
        else:
            logging.warning("Не удалось подтвердить авторизацию. Продолжу, но парсинг может не работать.")
    finally:
        with suppress(Exception):
            drv.quit()

def cmd_record_filter() -> None:
    name = input("Введите имя фильтра (например: 'МО → Урал, 20т тент'): ").strip()
    if not name:
        print("Имя фильтра не задано.")
        return
    drv = _new_driver(headless=False)
    try:
        load_cookies(drv)
        is_logged_in(drv)
        drv.get(LISTING_URL)
        ensure_debug_ui(drv)
        dbg_hud(drv, "Настройте фильтр в этом окне, затем вернитесь и нажмите Enter")
        print("\nОткрыл страницу поиска транспорта.")
        print("Настройте фильтр в открытом браузере (регион/направление/тип и т.д.).")
        print("После настройки вернитесь в терминал и нажмите Enter — я сохраню URL фильтра.")
        input("Нажмите Enter, когда фильтр настроен >>> ")
        url = drv.current_url
        rec = {"name": name, "url": url, "ts": int(time.time())}
        path = FILTERS_DIR / f"{slugify(name)}.json"
        write_json(path, rec)
        set_next_page_for_filter(name, 1)
        logging.info("Фильтр '%s' сохранён: %s", name, path)
    finally:
        with suppress(Exception):
            drv.quit()

def cmd_parse_saved_filter() -> None:
    files = sorted(FILTERS_DIR.glob("*.json"))
    if not files:
        print("Нет сохранённых фильтров. Сначала выполните пункт 2.")
        return
    print("\nСохранённые фильтры:")
    for i, p in enumerate(files, 1):
        rec = read_json(p, {})
        nm = rec.get("name") or p.stem
        print(f"{i}. {nm}")
    try:
        idx = int(input("Выберите номер фильтра >>> ").strip())
    except ValueError:
        print("Неверный ввод.")
        return
    if idx < 1 or idx > len(files):
        print("Неверный номер.")
        return
    rec = read_json(files[idx - 1], {})
    url = rec.get("url")
    name = rec.get("name") or files[idx - 1].stem
    if not url:
        print("В выбранном файле нет URL.")
        return

    drv = _new_driver(headless=False if HEADFUL_SESSIONS else True)
    try:
        load_cookies(drv)
        is_logged_in(drv)
        run_parse_filter(drv, name, url)
    finally:
        with suppress(Exception):
            drv.quit()

def cmd_setup_filters_for_all_regions() -> None:
    print("\nМАСТЕР СОХРАНЕНИЯ ФИЛЬТРОВ ДЛЯ ВСЕХ РЕГИОНОВ")
    print("Для каждого региона я открою страницу. Настройте фильтр (например, откуда/куда),")
    print("затем нажмите Enter — я сохраню URL в JSON.")
    drv = _new_driver(headless=False)
    try:
        load_cookies(drv)
        is_logged_in(drv)
        for idx, region in enumerate(ALL_REGIONS_164, 1):
            drv.get(LISTING_URL)
            WebDriverWait(drv, WAIT_LONG).until(lambda _drv: _drv.execute_script("return document.readyState") == "complete")
            ensure_debug_ui(drv)
            dbg_hud(drv, f"[{idx}/{len(ALL_REGIONS_164)}] Регион: {region}\nНастройте фильтр и нажмите Enter в терминале")
            print(f"\n[{idx}/{len(ALL_REGIONS_164)}] Регион: {region}")
            print("Настройте фильтр для этого региона в открытом окне браузера.")
            input("Нажмите Enter, чтобы сохранить URL текущего фильтра >>> ")
            url = drv.current_url
            out = REGION_FILTERS_DIR / f"{idx:03d}_{slugify(region)}.json"
            write_json(out, {"region": region, "url": url, "ts": int(time.time())})
            print(f"✔ Сохранено: {out}")
    finally:
        with suppress(Exception):
            drv.quit()

def cmd_parse_all_regions() -> None:
    files = sorted(REGION_FILTERS_DIR.glob("*.json"))
    if not files:
        print("Нет сохранённых региональных фильтров. Сначала выполните пункт 6.")
        return
    drv = _new_driver(headless=False if HEADFUL_SESSIONS else True)
    try:
        load_cookies(drv)
        is_logged_in(drv)
        prog = load_region_progress()
        start_idx = int(prog.get("region_idx", 1))
        start_idx = max(1, start_idx)

        for idx, p in enumerate(files, 1):
            if idx < start_idx:
                continue
            region_rec = read_json(p, {})
            region_name = region_rec.get("region") or p.stem.split("_", 1)[-1]
            url = region_rec.get("url")
            if not url:
                logging.warning("В файле '%s' отсутствует URL — пропускаю", p.name)
                continue
            try:
                run_parse_region(drv, region_name, idx, url)
                time.sleep(random.uniform(*PAUSE_BETWEEN_REGIONS))
                save_region_progress(region_name, 0, 0, idx + 1)
            except (WebDriverException, TimeoutException, json.JSONDecodeError, OSError) as e:
                logging.error("Ошибка при обработке региона '%s': %s", region_name, e)
                continue
    finally:
        with suppress(Exception):
            drv.quit()

def cmd_stop_file() -> None:
    try:
        STOP_FILE.write_text("stop", encoding="utf-8")
        print("Создан stop.txt — парсер мягко завершится при ближайшей проверке.")
    except OSError as e:
        print("Не удалось создать stop.txt:", e)

# ====== MAIN ======

def main(argv: List[str]) -> None:
    banner_once()
    while True:
        print("\nВыберите действие:")
        print("1 - Авторизация (общая, cookies)")
        print("2 - Запись параметров фильтра (произвольный)")
        print("3 - Парсинг транспорта по сохранённому фильтру")
        print("4 - Автоматический парсинг всех регионов")
        print("5 - Создать файл остановки (stop.txt)")
        print("6 - Настройка фильтров для всех регионов")
        print("7 - Выход")
        c = input("> ").strip()
        if c == "1":
            cmd_authorize()
        elif c == "2":
            cmd_record_filter()
        elif c == "3":
            cmd_parse_saved_filter()
        elif c == "4":
            cmd_parse_all_regions()
        elif c == "5":
            cmd_stop_file()
        elif c == "6":
            cmd_setup_filters_for_all_regions()
        elif c == "7" or c.lower() in ("q", "quit", "exit"):
            break
        else:
            print("Неизвестная команда")

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\nЗавершение работы.")
