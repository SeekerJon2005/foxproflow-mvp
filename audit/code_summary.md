# Project Code & Content Summary

## Python modules (classes/defs/imports)

- **.\test_infrastructure.py**
- _classes: none_

``
def test_database
def test_redis
def test_config
``


``
import sys
import os
from sqlalchemy import text
from data_layer.database import init_database,
from data_layer.redis_manager import redis_manager
from core.config import DATABASE_CONFIG,
``

- **.\src\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\api\main.py**
- _classes: none_
- _defs: none_

``
from fastapi import FastAPI,
from typing import Optional
from .app.schemas import FreightEnriched,
from .app.repo import list_freights,
``

- **.\src\api\schemas.py**

``
class FreightEnriched
class FreightListResponse
``

- _defs: none_

``
from typing import Optional,
from pydantic import BaseModel,
from datetime import datetime
``

- **.\src\api\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\api\app\db.py**
- _classes: none_
- _defs: none_

``
import os
import asyncpg
from dotenv import load_dotenv
from pathlib import Path
``

- **.\src\api\app\repo.py**
- _classes: none_

``
def build_filters
``


``
from typing import Optional,
from fastapi import HTTPException
from .db import fetch_all,
``

- **.\src\api\app\schemas.py**

``
class FreightEnriched
class FreightListResponse
``

- _defs: none_

``
from typing import Optional,
from datetime import datetime
from pydantic import BaseModel
``

- **.\src\api\app\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\core\config.py**
- _classes: none_

``
def load_existing_cache
def save_cache
def load_route_config
``


``
import os
import json
from pathlib import Path
from typing import Dict,
``

- **.\src\core\geo_utils.py**
- _classes: none_

``
def normalize_city_name
def load_cities_cache
def haversine_km
def approx_road_km
``


``
import json
import os
import logging
import re
import math
from typing import List,
from src.core.config import CITIES_CACHE_PATH,
``

- **.\src\core\models.py**

``
class City
class Freight
class RouteSegment
class Route
``


``
    def revenue_per_km
``


``
from pydantic import BaseModel
from typing import List,
``

- **.\src\core\trip_models.py**

``
class TripMetrics
class Segment
class Trip
``


``
    def revenue_per_hour
    def revenue_per_day
``


``
from __future__ import annotations
from dataclasses import dataclass,
from typing import List,
from datetime import datetime
``

- **.\src\core\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\data_layer\database.py**
- _classes: none_

``
def get_engine
def get_db
def init_database
def insert_freights_batch
def get_database_stats
``


``
import logging
from typing import List,
from sqlalchemy import create_engine,
from sqlalchemy.orm import sessionmaker,
from contextlib import contextmanager
from src.core.config import DATABASE_CONFIG
``

- **.\src\data_layer\gps_feed.py**
- _classes: none_

``
def _db_path
def _conn
def migrate_gps
def set_current_position
def get_current_city
``


``
from __future__ import annotations
from typing import Optional,
from datetime import datetime
import sqlite3
from pathlib import Path
        from src.core.config import DB_PATH
``

- **.\src\data_layer\redis_manager.py**

``
class RedisManager
``


``
    def __init__
    def _check_connection
    def is_duplicate
    def cache_data
    def get_cached_data
    def is_redis_available
``


``
import redis
import json
from typing import Optional,
import logging
import os
        import traceback
``

- **.\src\data_layer\trip_repo.py**
- _classes: none_

``
def _db_path
def _conn
def migrate
def create_trip
def get_trip
def update_trip_actual
def replace_plan
def list_locked_segments
def log_replan
``


``
from __future__ import annotations
from typing import List,
from datetime import datetime
import sqlite3
from pathlib import Path
from src.core.trip_models import Trip,
        from src.core.config import DB_PATH
``

- **.\src\data_layer\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\optimization\data_processor.py**
- _classes: none_

``
def extract_price
def safe_float_convert
def extract_city_and_region
def parse_loading_dt
def process_freight
``


``
import json
import os
import logging
import re
from typing import List,
from datetime import datetime
from models import Freight
``

- **.\src\optimization\market_stats.py**
- _classes: none_

``
def _percentile
def rebuild_market_stats
``


``
from typing import List,
from datetime import datetime,
import sqlite3
from collections import defaultdict
from config import DATABASE_PATH,
    from database import upsert_market_stats
``

- **.\src\optimization\surge_detector.py**
- _classes: none_

``
def check_and_log_surges
``


``
from typing import List
from datetime import datetime
from models import Freight
from database import get_guaranteed_rate,
from config import SURGE_THRESHOLD_MULTIPLIER
                import datetime
``

- **.\src\optimization\trip_manager.py**
- _classes: none_

``
def _normalize_route_obj
def _select_best
    def key
def replan_trip
``


``
from __future__ import annotations
from typing import List,
from datetime import datetime,
from src.core.trip_models import Trip,
from src.data_layer.trip_repo import (migrate,
from src.data_layer.gps_feed import get_current_city
    from src.core.config import FREEZE_MINUTES,
        from src.optimization.legacy.route_builder_time import build_routes
``

- **.\src\optimization\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\optimization\legacy\config.py**
- _classes: none_
- _defs: none_

``
import os
``

- **.\src\optimization\legacy\database.py**
- _classes: none_

``
def _column_exists
def init_database
def insert_freights_batch
def upsert_market_stats
def get_guaranteed_rate
def insert_rate_surge_event
def fetch_recent_surge_events
def load_suitable_freights
def get_database_stats
``


``
import sqlite3
import logging
import traceback
from typing import List,
from datetime import datetime,
from config import DATABASE_PATH
``

- **.\src\optimization\legacy\main_cli.py**
- _classes: none_

``
def main
``


``
import datetime
from src.optimization.legacy.route_builder_time import TimeAwareRouteBuilder
from src.data_layer.database import load_suitable_freights,
``

- **.\src\optimization\legacy\route_builder_time.py**

``
class TimeAwareRouteBuilder
``


``
    def __init__
    def _load_distance_cache
    def _build_city_coordinates
    def _build_city_index
    def _ensure_coord
    def _cached_or_approx_distance
    def _nearby_cities
    def build_routes
    def _create_route
``


``
import json
import os
import logging
import heapq
import itertools
import traceback
from typing import List,
from datetime import datetime,
from src.core.config import EXACT_DISTANCE_CACHE_PATH,
from src.core.models import Freight,
from src.core.geo_utils import approx_road_km
    from src.core.geo_utils import get_city_coordinates
``

- **.\src\optimization\legacy\trip_cli.py**
- _classes: none_

``
def prompt
def main
``


``
from __future__ import annotations
from datetime import datetime
import sys
from src.data_layer.trip_repo import migrate,
from src.data_layer.gps_feed import set_current_position,
from src.optimization.trip_manager import replan_trip
``

- **.\src\optimization\legacy\__init__.py**
- _classes: none_
- _defs: none_
- _imports: none_
- **.\src\parsers\ati_auth.py**
- _classes: none_

``
def init_driver
def save_cookies
def load_session
def is_logged_in
def manual_login
``


``
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
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException,
``

- **.\src\parsers\ati_cars_parser.py**

``
class _DedupFacade
class TruckItem
``


``
    def __init__
    def is_duplicate
def utc_now_iso
def memory_usage_mb
def check_stopfile
def init_driver
def ensure_authorized
def _find_pagination_root
def get_total_pages
def get_current_page_number
def ensure_100_rows
def navigate_to_page
def _wait_cards_stable
def apply_saved_filter
def _parse_price
def parse_current_page
def parse_current_page_with_recheck
def _read_json
def _write_json
def save_items
def read_filter_progress
def write_filter_progress
def action_manual_auth
def action_save_common_filter
def action_parse_by_saved_filter
def action_autoparse_regions
def action_create_stopfile
def main_menu
``


``
from __future__ import annotations
import os
import re
import gc
import sys
import json
import time
import psutil
import random
import logging
from dataclasses import dataclass
from contextlib import suppress
from pathlib import Path
from typing import Any,
from datetime import datetime,
    from src.parsers.ati_parser import RUSSIAN_REGIONS
    from src.data_layer.redis_manager import redis_manager
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions
    from selenium.common.exceptions import (
``

- **.\src\parsers\ati_parser.py**

``
    class RedisManagerStub
``


``
        def is_duplicate
        def cache_data
        def get_cached_data
        def is_redis_available
def signal_handler
def log_memory_usage
def check_stop_file
def random_delay
def check_memory_usage
def is_browser_responsive
def safe_current_url
def _kill_chrome_by_profile
def kill_own_chrome_process
def _normalize_string
def _normalize_city_name
def _normalize_weight_value
def _normalize_volume_value
def _normalize_price_and_currency
def _normalize_freight_minimal
def _generate_freight_hash
    def _normpoint_list
def _parse_loading_unloading
    def find_methods
def is_duplicate_with_fallback
def init_driver
def soft_memory_cleanup
def restart_driver
def is_logged_in
def save_cookies
def load_session
def manual_login
def record_filter_actions
def apply_recorded_filter
def apply_region_filter
def set_display_rows
def check_white_screen
def restore_session
def get_current_page_number
def get_total_pages
def click_next_button
def navigate_to_page
def handle_pagination
def parse_current_page
def get_region_jsonl_filename
def append_freights_to_jsonl
def save_region_progress
def load_region_progress
def clear_region_progress
def parse_all_regions
def setup_all_region_filters
def main
``


``
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
from typing import Optional,
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.common.exceptions import (
    from src.data_layer.redis_manager import redis_manager
``

- **.\src\parsers\record_region_filters.py**
- _classes: none_

``
def init_driver
def is_logged_in
def load_session
def record_region_filter
def main
``


``
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
from selenium.webdriver.support import expected_conditions
from webdriver_manager.chrome import ChromeDriverManager
``

- **.\src\worker\celery_app.py**
- _classes: none_

``
def refresh_mv
``


``
from celery import Celery
from celery.schedules import crontab
import asyncpg
import os
from dotenv import load_dotenv
from pathlib import Path
    import asyncio
``

- **.\tools\generate_move_suggestions.py**
- _classes: none_

``
def detect_main_target
def main
    def is_ignored_by_gitignore
    def should_skip
``


``
import sys,
from pathlib import Path
``

- **.\tools\inventory.py**
- _classes: none_

``
def human
def md5_small
def summarize_py
def summarize_text_head
def summarize_json
def summarize_csv_header
def guess_category
def looks_like_screenshot
def main
    def write_csv
``


``
import os
import sys
import csv
import re
import json
import ast
import math
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
``

## SQL DDL (CREATE ...)

- **.\src\data_layer\create_freights_enriched.sql**

``
CREATE TABLE IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
``

- **.\src\data_layer\init_db.sql**

``
CREATE TABLE IF
CREATE TABLE IF
CREATE TABLE IF
CREATE TABLE IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
``

- **.\src\data_layer\init_transport.sql**

``
CREATE TABLE IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
``

- **.\src\data_layer\sql_bootstrap_business.sql**

``
CREATE TABLE IF
CREATE TABLE IF
CREATE TABLE IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
CREATE INDEX IF
``

## Markdown docs (headings)

- **.\PROJECT_INVENTORY.md**

``
# Project Inventory
## Summary by category
## Summary by extension
## Large files
## Candidates to delete (logs/screenshots)
## File list (sample)
``

- **.\audit\code_summary.md**

``
# Project Code & Content Summary
## Python modules (classes/defs/imports)
## SQL DDL (CREATE ...)
## Markdown docs (headings)
## JSONL stats (records)
``

- **.\docs\PROJECT_STATUS_and_PLAN.md**

``
# FoxProFlow — Состояние проекта и план выравнивания (на 2025-09-25)
## 1) Текущее состояние (снимок)
## 2) Целевая картина данных (MVP транспортного ядра)
## 3) Проблемы/несоответствия
## 4) Что уже реализовано (согласно репозиторию и SQL‑аддендуму)
## 5) Блоки, которые можно сделать быстро и правильно
## 6) Пошаговый план выравнивания (1–2 дня)
## 7) Команды (Docker + psql)
# применить SQL (копируем файл внутрь контейнера → выполняем)
# проверить
## 8) Что поменять в коде (минимум)
## 9) Наблюдаемость
``

## JSONL stats (records)

- **.\data\loads_data\Республика Адыгея\Республика Адыгея_2025-09-24_11-12-26.jsonl**  106 records
- **.\data\loads_data\Республика Алтай\Республика Алтай_2025-09-24_11-13-26.jsonl**  24 records
- **.\data\loads_data\Республика Башкортостан\Республика Башкортостан_2025-09-24_11-13-53.jsonl**  422 records
- **.\src\parsers\test.jsonl**  1 records
- **.\src\parsers\transport.jsonl**  155 records
- **.\src\parsers\cars_data\cars.jsonl**  1861 records
- **.\src\parsers\data\freights_by_region\Республика Адыгея\Республика Адыгея_2025-09-24_14-23-29.jsonl**  106 records
- **.\src\parsers\data\freights_by_region\Республика Алтай\Республика Алтай_2025-09-24_14-23-50.jsonl**  20 records
- **.\src\parsers\data\freights_by_region\Республика Башкортостан\Республика Башкортостан_2025-09-24_14-24-24.jsonl**  106 records
- **.\src\parsers\data\freights_by_region\Республика Бурятия\Республика Бурятия_2025-09-24_14-24-47.jsonl**  344 records
- **.\src\parsers\data_transport\Test_2025-09-27_23-53-20.jsonl**  2759 records
- **.\src\parsers\regions_data\filter\filter_2025-09-02_10-25-39.jsonl**  38 records
- **.\src\parsers\regions_data\filter\filter_2025-09-02_10-33-07.jsonl**  111 records
- **.\src\parsers\regions_data\filter\filter_2025-09-03_14-21-50.jsonl**  11 records
- **.\src\parsers\regions_data\filter\filter_2025-09-03_16-22-17.jsonl**  85 records
- **.\src\parsers\regions_data\filter\filter_2025-09-03_17-00-37.jsonl**  86 records
- **.\src\parsers\regions_data\filter\filter_2025-09-03_17-40-35.jsonl**  605 records
- **.\src\parsers\regions_data\filter\filter_2025-09-03_21-38-47.jsonl**  54 records
- **.\src\parsers\regions_data\filter\filter_2025-09-03_22-25-46.jsonl**  3 records
- **.\src\parsers\regions_data\filter\filter_2025-09-08_13-52-21.jsonl**  682 records
- **.\src\parsers\regions_data\filter\filter_2025-09-08_14-40-09.jsonl**  155 records
- **.\src\parsers\regions_data\filter\filter_2025-09-08_14-42-49.jsonl**  121 records
- **.\src\parsers\regions_data\filter\filter_2025-09-08_15-23-48.jsonl**  56 records
- **.\src\parsers\regions_data\filter\filter_2025-09-09_19-37-58.jsonl**  84 records
- **.\src\parsers\regions_data\filter\filter_2025-09-09_19-48-42.jsonl**  38 records
- **.\src\parsers\regions_data\filter\filter_2025-09-09_21-46-03.jsonl**  7 records
- **.\src\parsers\regions_data\filter\filter_2025-09-10_23-30-01.jsonl**  187 records
- **.\src\parsers\regions_data\filter\filter_2025-09-11_00-20-42.jsonl**  108 records
- **.\src\parsers\regions_data\filter\filter_2025-09-11_01-23-05.jsonl**  104 records
- **.\src\parsers\regions_data\filter\filter_2025-09-12_11-38-27.jsonl**  100 records
- **.\src\parsers\regions_data\filter\filter_2025-09-12_11-52-31.jsonl**  241 records
- **.\src\parsers\regions_data\filter\filter_2025-09-12_12-41-38.jsonl**  18 records
- **.\src\parsers\regions_data\filter\filter_2025-09-14_20-22-18.jsonl**  26 records
- **.\src\parsers\regions_data\filter\filter_2025-09-14_21-10-32.jsonl**  50 records
- **.\src\parsers\regions_data\filter\filter_2025-09-14_23-04-12.jsonl**  290 records
- **.\src\parsers\regions_data\filter\filter_2025-09-14_23-51-37.jsonl**  1 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_00-17-52.jsonl**  181 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_01-04-53.jsonl**  18 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_03-14-49.jsonl**  56 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_03-25-28.jsonl**  5 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_11-39-29.jsonl**  80 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_20-11-13.jsonl**  251 records
- **.\src\parsers\regions_data\filter\filter_2025-09-15_20-13-41.jsonl**  27 records
- **.\src\parsers\regions_data\filter\filter_2025-09-17_10-05-00.jsonl**  301 records
- **.\src\parsers\regions_data\filter\filter_2025-09-17_15-24-37.jsonl**  528 records
- **.\src\parsers\regions_data\filter\filter_2025-09-17_16-56-56.jsonl**  77 records
- **.\src\parsers\regions_data\filter\filter_2025-09-17_19-41-14.jsonl**  64 records
- **.\src\parsers\regions_data\filter\filter_2025-09-17_20-55-01.jsonl**  5 records
- **.\src\parsers\regions_data\filter\filter_2025-09-17_21-30-11.jsonl**  3 records
- **.\src\parsers\regions_data\filter\filter_2025-09-19_22-12-12.jsonl**  513 records
- **.\src\parsers\regions_data\filter\filter_2025-09-20_00-44-01.jsonl**  2664 records
- **.\src\parsers\regions_data\filter\filter_2025-09-20_20-55-48.jsonl**  138 records
- **.\src\parsers\regions_data\filter\filter_2025-09-20_21-25-27.jsonl**  4 records
- **.\src\parsers\regions_data\filter\filter_2025-09-21_17-17-20.jsonl**  2023 records
- **.\src\parsers\regions_data\filter\filter_2025-09-21_20-34-04.jsonl**  2881 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-09_14-47-03.jsonl**  1590 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-20_02-32-45.jsonl**  873 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-20_03-54-32.jsonl**  813 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-20_12-34-49.jsonl**  174 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-20_22-16-57.jsonl**  55 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-21_18-52-41.jsonl**  239 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-21_21-46-13.jsonl**  1017 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-22_00-30-58.jsonl**  1595 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-22_05-36-16.jsonl**  333 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-22_18-27-35.jsonl**  1045 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-22_21-27-48.jsonl**  19 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-23_02-30-59.jsonl**  30 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-23_13-44-37.jsonl**  1374 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-24_12-00-32.jsonl**  1349 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-24_17-30-07.jsonl**  673 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-25_12-40-56.jsonl**  1609 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-25_14-33-27.jsonl**  666 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-26_15-57-25.jsonl**  85 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-27_14-09-45.jsonl**  1166 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-29_15-56-52.jsonl**  1518 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-09-30_13-50-12.jsonl**  91 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-01_17-34-10.jsonl**  1388 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-02_14-33-39.jsonl**  1100 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-03_10-37-38.jsonl**  967 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-08_01-00-13.jsonl**  1282 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-08_10-32-55.jsonl**  933 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-09_13-29-40.jsonl**  1167 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-10_18-08-17.jsonl**  758 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-13_13-45-45.jsonl**  852 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-14_12-10-08.jsonl**  969 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-15_20-06-35.jsonl**  1123 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-16_15-17-57.jsonl**  939 records
- **.\src\parsers\regions_data\Алтайский край\Алтайский край_2025-10-19_16-48-53.jsonl**  671 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-09_15-47-06.jsonl**  742 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-20_04-43-31.jsonl**  703 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-20_13-25-25.jsonl**  84 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-20_22-51-31.jsonl**  37 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-21_22-19-48.jsonl**  535 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-22_06-05-11.jsonl**  661 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-22_22-19-30.jsonl**  425 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-23_03-33-54.jsonl**  37 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-24_12-35-46.jsonl**  655 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-24_18-05-13.jsonl**  190 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-25_13-17-57.jsonl**  481 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-25_15-11-03.jsonl**  51 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-26_16-48-24.jsonl**  432 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-27_15-20-38.jsonl**  157 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-29_16-51-59.jsonl**  559 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-09-30_14-24-04.jsonl**  502 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-01_18-25-56.jsonl**  570 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-02_15-38-36.jsonl**  517 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-03_11-32-56.jsonl**  493 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-08_01-51-09.jsonl**  846 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-08_11-08-19.jsonl**  615 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-09_14-25-05.jsonl**  855 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-10_18-43-24.jsonl**  707 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-13_14-18-35.jsonl**  728 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-14_13-05-33.jsonl**  770 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-15_20-43-36.jsonl**  922 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-16_15-57-20.jsonl**  778 records
- **.\src\parsers\regions_data\Амурская область\Амурская область_2025-10-19_17-19-38.jsonl**  795 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-09_15-49-14.jsonl**  349 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-20_04-44-45.jsonl**  304 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-20_13-26-35.jsonl**  161 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-20_13-47-28.jsonl**  331 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-20_22-53-04.jsonl**  37 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-21_22-20-52.jsonl**  314 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-22_06-06-42.jsonl**  580 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-22_22-21-04.jsonl**  477 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-23_03-35-14.jsonl**  58 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-24_12-37-15.jsonl**  748 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-24_18-06-37.jsonl**  261 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-25_13-19-27.jsonl**  624 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-25_15-12-32.jsonl**  85 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-26_16-49-49.jsonl**  653 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-27_15-22-04.jsonl**  270 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-29_16-53-24.jsonl**  662 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-09-30_14-25-54.jsonl**  607 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-01_18-27-23.jsonl**  626 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-02_15-40-23.jsonl**  601 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-03_11-34-25.jsonl**  560 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-08_01-52-36.jsonl**  827 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-08_11-10-25.jsonl**  633 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-09_14-27-18.jsonl**  955 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-10_18-45-39.jsonl**  908 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-13_14-20-36.jsonl**  820 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-14_13-07-47.jsonl**  866 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-15_20-45-54.jsonl**  956 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-16_15-59-38.jsonl**  775 records
- **.\src\parsers\regions_data\Архангельская область\Архангельская область_2025-10-19_17-21-45.jsonl**  745 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-20_05-05-49.jsonl**  391 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-20_13-48-45.jsonl**  170 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-20_22-54-12.jsonl**  35 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-22_06-07-39.jsonl**  426 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-22_22-22-14.jsonl**  594 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-23_03-36-19.jsonl**  18 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-24_12-38-31.jsonl**  598 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-24_18-08-19.jsonl**  215 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-25_13-21-22.jsonl**  465 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-25_15-14-22.jsonl**  111 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-26_16-51-44.jsonl**  429 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-27_15-23-23.jsonl**  185 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-29_16-54-39.jsonl**  406 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-09-30_14-27-12.jsonl**  383 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-01_18-28-33.jsonl**  431 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-02_15-41-44.jsonl**  313 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-03_11-35-43.jsonl**  303 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-08_01-53-54.jsonl**  421 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-08_11-12-23.jsonl**  251 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-09_14-29-24.jsonl**  295 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-10_18-47-51.jsonl**  239 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-13_14-22-34.jsonl**  207 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-14_13-09-51.jsonl**  154 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-15_20-48-01.jsonl**  226 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-16_16-01-43.jsonl**  224 records
- **.\src\parsers\regions_data\Астраханская область\Астраханская область_2025-10-19_17-23-25.jsonl**  167 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-09_15-55-56.jsonl**  1191 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-20_05-06-27.jsonl**  1235 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-20_13-50-02.jsonl**  206 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-20_22-55-48.jsonl**  68 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-22_06-08-46.jsonl**  206 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-22_22-23-39.jsonl**  1238 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-23_03-37-34.jsonl**  17 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-24_12-39-55.jsonl**  1296 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-24_18-09-35.jsonl**  760 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-25_13-22-54.jsonl**  999 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-25_15-15-44.jsonl**  301 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-26_16-53-03.jsonl**  906 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-27_15-24-34.jsonl**  274 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-29_16-55-51.jsonl**  983 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-09-30_14-28-23.jsonl**  941 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-01_18-29-40.jsonl**  960 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-02_15-43-21.jsonl**  974 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-03_11-36-51.jsonl**  902 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-08_11-13-18.jsonl**  1338 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-09_14-30-17.jsonl**  968 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-10_18-48-42.jsonl**  924 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-13_14-23-21.jsonl**  957 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-14_13-10-34.jsonl**  890 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-15_20-48-55.jsonl**  997 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-16_16-02-28.jsonl**  904 records
- **.\src\parsers\regions_data\Белгородская область\Белгородская область_2025-10-19_17-24-06.jsonl**  831 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-09_16-00-14.jsonl**  997 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-20_05-08-47.jsonl**  1058 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-20_14-13-25.jsonl**  181 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-20_22-58-10.jsonl**  51 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-21_19-50-54.jsonl**  171 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-22_06-10-43.jsonl**  845 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-22_22-26-02.jsonl**  1023 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-23_03-39-42.jsonl**  36 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-24_12-42-27.jsonl**  1194 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-24_18-12-09.jsonl**  598 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-25_13-25-23.jsonl**  967 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-25_15-18-15.jsonl**  252 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-26_16-55-27.jsonl**  1039 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-27_15-26-46.jsonl**  310 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-29_16-58-07.jsonl**  1095 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-09-30_14-30-46.jsonl**  935 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-01_18-31-46.jsonl**  947 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-02_15-46-01.jsonl**  967 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-03_11-39-19.jsonl**  843 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-08_01-55-31.jsonl**  1178 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-08_11-15-45.jsonl**  841 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-09_14-32-24.jsonl**  1141 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-10_18-50-54.jsonl**  1027 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-13_14-25-29.jsonl**  1186 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-14_13-12-42.jsonl**  981 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-15_20-51-07.jsonl**  1 records
- **.\src\parsers\regions_data\Брянская область\Брянская область_2025-10-16_16-04-41.jsonl**  11 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-09_16-04-40.jsonl**  1720 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-20_05-10-43.jsonl**  3193 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-20_14-15-30.jsonl**  483 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-20_23-00-46.jsonl**  139 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-21_19-53-48.jsonl**  540 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-22_06-12-13.jsonl**  2788 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-22_22-28-34.jsonl**  2526 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-23_03-41-58.jsonl**  109 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-24_12-45-04.jsonl**  3820 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-24_18-14-48.jsonl**  1999 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-25_13-28-02.jsonl**  3033 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-25_15-20-53.jsonl**  874 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-26_16-58-07.jsonl**  3113 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-27_15-29-09.jsonl**  985 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-29_17-00-46.jsonl**  3365 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-09-30_14-33-21.jsonl**  3166 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-01_18-34-00.jsonl**  3398 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-02_15-49-10.jsonl**  3287 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-03_11-41-47.jsonl**  2875 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-08_01-57-44.jsonl**  3093 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-08_11-18-21.jsonl**  2139 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-09_14-34-59.jsonl**  3413 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-10_18-53-26.jsonl**  2850 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-13_14-28-12.jsonl**  2370 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-14_13-15-14.jsonl**  2547 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-15_20-53-31.jsonl**  3084 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-16_16-07-02.jsonl**  2515 records
- **.\src\parsers\regions_data\Владимирская область\Владимирская область_2025-10-19_17-28-30.jsonl**  1897 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-20_05-16-11.jsonl**  28 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-20_14-21-14.jsonl**  567 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-20_23-06-38.jsonl**  25 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-21_20-00-22.jsonl**  542 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-22_06-16-35.jsonl**  723 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-22_22-34-54.jsonl**  709 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-23_03-47-25.jsonl**  2186 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-24_12-52-35.jsonl**  779 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-24_18-22-26.jsonl**  3155 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-25_13-35-48.jsonl**  606 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-25_15-28-26.jsonl**  580 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-26_17-05-39.jsonl**  3003 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-27_15-35-17.jsonl**  495 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-29_17-08-11.jsonl**  2518 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-09-30_14-41-08.jsonl**  2596 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-01_18-40-47.jsonl**  2426 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-02_15-58-33.jsonl**  709 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-03_11-49-40.jsonl**  604 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-08_02-02-57.jsonl**  2157 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-08_11-25-11.jsonl**  1580 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-09_14-42-07.jsonl**  2032 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-10_19-00-42.jsonl**  1344 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-13_14-34-03.jsonl**  1377 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-14_13-21-07.jsonl**  701 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-15_20-59-40.jsonl**  578 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-16_16-13-35.jsonl**  1973 records
- **.\src\parsers\regions_data\Волгоградская область\Волгоградская область_2025-10-19_17-32-37.jsonl**  762 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-20_05-21-05.jsonl**  1871 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-20_14-26-42.jsonl**  332 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-20_23-12-46.jsonl**  71 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-23_03-52-57.jsonl**  1905 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-24_18-29-46.jsonl**  2451 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-25_15-30-34.jsonl**  2043 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-26_17-12-11.jsonl**  2119 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-27_15-57-01.jsonl**  566 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-29_17-14-23.jsonl**  1976 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-09-30_14-47-13.jsonl**  2204 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-01_18-47-32.jsonl**  2216 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-02_16-20-55.jsonl**  2049 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-03_12-11-23.jsonl**  1848 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-08_02-08-10.jsonl**  1931 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-08_11-29-55.jsonl**  1495 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-09_14-46-49.jsonl**  2042 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-10_19-04-57.jsonl**  1323 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-13_14-38-02.jsonl**  1961 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-14_13-42-53.jsonl**  2054 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-15_21-21-02.jsonl**  2445 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-16_16-17-39.jsonl**  2124 records
- **.\src\parsers\regions_data\Вологодская область\Вологодская область_2025-10-19_17-38-30.jsonl**  1517 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-20_05-24-29.jsonl**  2832 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-20_14-30-18.jsonl**  467 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-20_23-16-26.jsonl**  199 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-23_03-56-20.jsonl**  2866 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-24_18-34-18.jsonl**  778 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-25_15-35-44.jsonl**  3333 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-26_17-16-57.jsonl**  621 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-27_16-01-14.jsonl**  2082 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-29_17-18-48.jsonl**  831 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-09-30_14-51-50.jsonl**  645 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-01_18-51-52.jsonl**  762 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-02_16-26-28.jsonl**  678 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-03_12-15-55.jsonl**  636 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-08_02-11-35.jsonl**  2725 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-08_11-33-58.jsonl**  1756 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-09_14-51-01.jsonl**  838 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-10_19-07-54.jsonl**  2584 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-13_14-42-03.jsonl**  2249 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-14_13-47-21.jsonl**  651 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-15_21-26-15.jsonl**  3134 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-16_16-22-45.jsonl**  2331 records
- **.\src\parsers\regions_data\Воронежская область\Воронежская область_2025-10-19_17-41-59.jsonl**  2038 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-20_19-06-09.jsonl**  21 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-21_01-45-09.jsonl**  2 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-23_06-35-04.jsonl**  21 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-24_22-26-43.jsonl**  16 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-25_19-17-45.jsonl**  15 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-26_21-21-59.jsonl**  16 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-27_19-06-40.jsonl**  3 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-30_00-20-36.jsonl**  16 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-09-30_18-59-06.jsonl**  17 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-02_20-32-35.jsonl**  40 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-03_16-40-00.jsonl**  30 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-08_04-58-16.jsonl**  30 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-08_14-55-46.jsonl**  13 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-09_18-22-48.jsonl**  12 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-10_23-53-27.jsonl**  24 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-13_17-42-54.jsonl**  22 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-14_16-52-19.jsonl**  10 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-16_01-07-09.jsonl**  22 records
- **.\src\parsers\regions_data\Еврейская автономная область\Еврейская автономная область_2025-10-16_20-12-34.jsonl**  17 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-09_14-52-51.jsonl**  955 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-20_02-36-03.jsonl**  1209 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-20_03-57-15.jsonl**  7 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-20_12-37-35.jsonl**  155 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-20_22-19-57.jsonl**  77 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-21_18-55-20.jsonl**  286 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-21_21-49-25.jsonl**  530 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-21_21-52-05.jsonl**  183 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-22_00-33-30.jsonl**  1219 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-22_05-38-50.jsonl**  182 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-22_18-30-22.jsonl**  603 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-22_21-31-03.jsonl**  71 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-23_02-33-38.jsonl**  68 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-23_13-48-10.jsonl**  752 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-24_12-04-13.jsonl**  791 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-24_17-33-47.jsonl**  344 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-25_12-44-40.jsonl**  768 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-25_14-37-29.jsonl**  116 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-26_15-58-05.jsonl**  748 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-27_14-12-47.jsonl**  291 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-29_15-59-48.jsonl**  664 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-09-30_13-50-51.jsonl**  793 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-01_17-36-52.jsonl**  753 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-02_14-36-57.jsonl**  767 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-03_10-40-28.jsonl**  631 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-08_01-02-45.jsonl**  1206 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-08_10-35-36.jsonl**  645 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-09_13-32-17.jsonl**  771 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-10_18-10-39.jsonl**  926 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-13_13-48-00.jsonl**  894 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-14_12-12-46.jsonl**  939 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-15_20-09-07.jsonl**  1314 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-16_15-20-28.jsonl**  1242 records
- **.\src\parsers\regions_data\Забайкальский край\Забайкальский край_2025-10-19_16-50-48.jsonl**  1264 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-20_05-29-40.jsonl**  859 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-20_14-36-01.jsonl**  188 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-20_23-22-38.jsonl**  42 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-23_04-00-58.jsonl**  962 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-24_18-56-02.jsonl**  1306 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-25_15-42-05.jsonl**  1192 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-26_17-38-37.jsonl**  949 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-27_16-06-55.jsonl**  296 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-29_17-40-51.jsonl**  937 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-09-30_15-13-36.jsonl**  977 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-01_18-53-45.jsonl**  1007 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-02_16-48-31.jsonl**  1104 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-03_12-37-30.jsonl**  828 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-08_02-15-54.jsonl**  1083 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-08_11-39-34.jsonl**  944 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-09_15-12-58.jsonl**  1284 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-10_19-14-07.jsonl**  997 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-13_14-47-26.jsonl**  930 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-14_14-08-59.jsonl**  1015 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-15_21-32-03.jsonl**  1103 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-16_16-28-35.jsonl**  998 records
- **.\src\parsers\regions_data\Ивановская область\Ивановская область_2025-10-19_17-46-16.jsonl**  724 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-20_05-30-55.jsonl**  760 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-20_14-37-55.jsonl**  2183 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-20_23-24-40.jsonl**  52 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-23_04-02-49.jsonl**  3053 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-24_18-58-22.jsonl**  2942 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-25_15-44-38.jsonl**  2557 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-26_17-40-53.jsonl**  2285 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-27_16-09-00.jsonl**  654 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-29_17-43-04.jsonl**  2166 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-09-30_15-15-47.jsonl**  2396 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-01_18-55-57.jsonl**  2405 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-02_16-51-25.jsonl**  2520 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-03_12-39-55.jsonl**  1937 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-08_02-17-57.jsonl**  2609 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-08_11-42-06.jsonl**  1794 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-09_15-15-29.jsonl**  2161 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-10_19-16-22.jsonl**  2063 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-13_14-49-35.jsonl**  2014 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-14_14-11-16.jsonl**  1966 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-15_21-34-21.jsonl**  2639 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-16_16-30-54.jsonl**  2422 records
- **.\src\parsers\regions_data\Иркутская область\Иркутская область_2025-10-19_17-48-03.jsonl**  2271 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-08_17-11-31.jsonl**  186 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-09_13-39-07.jsonl**  136 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-09_16-49-38.jsonl**  47 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-19_22-28-06.jsonl**  170 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-20_11-39-27.jsonl**  16 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-20_21-39-14.jsonl**  38 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-21_21-08-33.jsonl**  109 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-21_23-48-07.jsonl**  160 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-21_23-58-03.jsonl**  3 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-22_05-05-41.jsonl**  19 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-22_17-49-07.jsonl**  192 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-22_20-50-00.jsonl**  25 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-23_01-57-17.jsonl**  8 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-23_13-05-41.jsonl**  119 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-24_11-21-29.jsonl**  180 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-24_16-49-03.jsonl**  139 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-25_12-00-31.jsonl**  126 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-25_13-53-22.jsonl**  52 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-26_15-15-15.jsonl**  125 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-27_13-12-28.jsonl**  54 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-29_15-18-59.jsonl**  129 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-30_13-11-52.jsonl**  157 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-01_16-54-41.jsonl**  146 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-02_13-53-05.jsonl**  141 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-03_10-02-15.jsonl**  66 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-08_00-27-02.jsonl**  290 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-08_09-59-46.jsonl**  160 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-09_12-55-04.jsonl**  205 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-10_17-34-56.jsonl**  135 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-13_13-15-00.jsonl**  384 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-14_11-38-33.jsonl**  280 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-15_19-32-28.jsonl**  279 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-16_14-42-19.jsonl**  189 records
- **.\src\parsers\regions_data\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-10-19_16-21-56.jsonl**  306 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-20_05-52-34.jsonl**  1 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-20_14-43-30.jsonl**  22 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-23_04-08-15.jsonl**  37 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-24_19-04-15.jsonl**  22 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-25_15-51-34.jsonl**  15 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-26_17-47-43.jsonl**  6 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-29_17-48-59.jsonl**  22 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-09-30_15-21-41.jsonl**  22 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-01_19-01-38.jsonl**  5 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-02_16-59-11.jsonl**  18 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-03_12-46-06.jsonl**  20 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-08_02-23-00.jsonl**  22 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-08_11-47-59.jsonl**  23 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-09_15-21-04.jsonl**  33 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-10_19-22-23.jsonl**  4 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-13_14-54-56.jsonl**  19 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-14_14-16-43.jsonl**  13 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-15_21-40-17.jsonl**  21 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-16_16-37-09.jsonl**  19 records
- **.\src\parsers\regions_data\Калининградская область\Калининградская область_2025-10-19_17-53-24.jsonl**  4 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-20_05-53-17.jsonl**  2303 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-20_14-44-00.jsonl**  372 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-20_23-31-27.jsonl**  126 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-23_04-08-54.jsonl**  2741 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-24_19-04-55.jsonl**  3452 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-25_15-52-14.jsonl**  2987 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-26_17-48-21.jsonl**  2599 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-27_16-15-35.jsonl**  792 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-29_17-49-39.jsonl**  2803 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-09-30_15-22-20.jsonl**  2955 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-01_19-02-16.jsonl**  2517 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-02_16-59-50.jsonl**  2717 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-03_12-46-45.jsonl**  2392 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-08_02-23-39.jsonl**  2199 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-08_11-48-41.jsonl**  1887 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-09_15-21-41.jsonl**  2792 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-10_19-23-01.jsonl**  2307 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-13_14-55-33.jsonl**  2112 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-14_14-17-21.jsonl**  2053 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-15_21-40-57.jsonl**  2028 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-16_16-37-48.jsonl**  2218 records
- **.\src\parsers\regions_data\Калужская область\Калужская область_2025-10-19_17-54-01.jsonl**  1644 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-09_14-57-08.jsonl**  3 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-20_02-38-41.jsonl**  4 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-21_21-53-32.jsonl**  2 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-22_00-36-04.jsonl**  4 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-22_21-52-53.jsonl**  2 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-23_02-36-02.jsonl**  1 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-23_13-50-45.jsonl**  1 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-24_12-06-37.jsonl**  1 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-25_12-47-06.jsonl**  3 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-25_14-39-53.jsonl**  2 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-26_16-00-35.jsonl**  1 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-27_14-34-35.jsonl**  1 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-29_16-21-40.jsonl**  7 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-09-30_13-53-18.jsonl**  4 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-01_17-58-43.jsonl**  2 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-02_14-59-20.jsonl**  7 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-03_11-02-13.jsonl**  4 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-08_01-05-09.jsonl**  5 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-08_10-38-02.jsonl**  3 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-09_13-54-04.jsonl**  4 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-10_18-13-11.jsonl**  3 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-13_13-50-22.jsonl**  2 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-14_12-15-26.jsonl**  1 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-15_20-12-03.jsonl**  4 records
- **.\src\parsers\regions_data\Камчатский край\Камчатский край_2025-10-16_15-23-36.jsonl**  2 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-08_17-13-34.jsonl**  126 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-09_13-41-15.jsonl**  111 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-09_16-51-47.jsonl**  49 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-19_22-29-05.jsonl**  255 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-20_11-40-25.jsonl**  33 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-20_21-40-33.jsonl**  19 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-21_18-19-06.jsonl**  28 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-21_21-10-01.jsonl**  125 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-21_23-49-33.jsonl**  174 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-22_05-07-11.jsonl**  8 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-22_17-50-43.jsonl**  100 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-22_20-51-18.jsonl**  3 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-23_01-58-37.jsonl**  2 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-23_13-07-01.jsonl**  106 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-24_11-23-02.jsonl**  103 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-24_16-50-42.jsonl**  52 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-25_12-01-53.jsonl**  111 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-25_13-54-41.jsonl**  70 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-26_15-16-40.jsonl**  165 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-27_13-13-49.jsonl**  56 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-29_15-20-15.jsonl**  125 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-30_13-13-11.jsonl**  88 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-01_16-57-19.jsonl**  99 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-02_13-54-23.jsonl**  83 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-03_10-03-28.jsonl**  117 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-08_00-28-34.jsonl**  128 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-08_10-01-10.jsonl**  70 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-09_12-56-26.jsonl**  181 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-10_17-36-14.jsonl**  146 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-13_13-16-29.jsonl**  262 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-14_11-40-03.jsonl**  165 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-15_19-33-53.jsonl**  238 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-16_14-43-42.jsonl**  223 records
- **.\src\parsers\regions_data\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-10-19_16-23-19.jsonl**  137 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-20_05-57-21.jsonl**  1123 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-20_14-48-31.jsonl**  125 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-20_23-35-55.jsonl**  20 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-21_20-08-50.jsonl**  141 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-23_04-13-27.jsonl**  987 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-24_19-10-57.jsonl**  1112 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-25_15-59-07.jsonl**  900 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-26_17-54-38.jsonl**  943 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-27_16-20-33.jsonl**  204 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-29_17-55-24.jsonl**  745 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-09-30_15-28-40.jsonl**  824 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-01_19-07-32.jsonl**  660 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-02_17-07-27.jsonl**  660 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-03_12-52-53.jsonl**  592 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-08_02-27-31.jsonl**  74 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-08_11-54-05.jsonl**  885 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-09_15-27-06.jsonl**  679 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-10_19-28-33.jsonl**  721 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-13_15-00-08.jsonl**  664 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-14_14-21-50.jsonl**  621 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-15_21-45-11.jsonl**  572 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-16_16-43-04.jsonl**  596 records
- **.\src\parsers\regions_data\Кемеровская область\Кемеровская область_2025-10-19_17-57-30.jsonl**  538 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-20_14-50-57.jsonl**  1710 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-20_23-38-05.jsonl**  65 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-21_20-14-38.jsonl**  278 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-23_04-15-19.jsonl**  1695 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-24_19-13-13.jsonl**  1824 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-25_16-01-28.jsonl**  1669 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-26_17-57-15.jsonl**  1488 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-27_16-23-03.jsonl**  414 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-29_17-57-31.jsonl**  1496 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-09-30_15-30-49.jsonl**  1766 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-01_19-09-27.jsonl**  1757 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-02_17-09-59.jsonl**  1773 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-03_12-54-58.jsonl**  1566 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-08_02-29-18.jsonl**  1891 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-08_11-56-06.jsonl**  1376 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-09_15-29-05.jsonl**  1812 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-10_19-30-33.jsonl**  1547 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-13_15-02-06.jsonl**  1514 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-14_14-23-40.jsonl**  1629 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-15_21-47-03.jsonl**  1755 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-16_16-44-55.jsonl**  1548 records
- **.\src\parsers\regions_data\Кировская область\Кировская область_2025-10-19_17-58-39.jsonl**  1237 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-20_14-53-55.jsonl**  777 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-20_15-15-34.jsonl**  108 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-20_23-41-16.jsonl**  32 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-21_20-17-40.jsonl**  133 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-23_04-18-07.jsonl**  809 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-24_19-16-55.jsonl**  988 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-25_16-05-29.jsonl**  883 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-26_18-01-59.jsonl**  808 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-27_16-26-30.jsonl**  279 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-29_18-01-13.jsonl**  768 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-09-30_15-34-52.jsonl**  827 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-01_19-13-11.jsonl**  6 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-02_17-15-24.jsonl**  940 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-03_12-59-11.jsonl**  662 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-08_02-32-45.jsonl**  726 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-08_12-00-01.jsonl**  539 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-09_15-33-05.jsonl**  854 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-10_19-34-25.jsonl**  563 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-13_15-05-49.jsonl**  701 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-14_14-27-29.jsonl**  734 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-15_21-50-55.jsonl**  783 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-16_16-48-43.jsonl**  698 records
- **.\src\parsers\regions_data\Костромская область\Костромская область_2025-10-19_18-01-26.jsonl**  565 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-09_14-58-28.jsonl**  1949 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-20_02-39-49.jsonl**  690 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-20_04-19-41.jsonl**  2655 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-20_13-01-11.jsonl**  495 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-20_22-24-32.jsonl**  311 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-21_18-58-52.jsonl**  521 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-21_21-54-35.jsonl**  1614 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-22_00-36-57.jsonl**  3223 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-22_05-42-10.jsonl**  52 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-22_21-53-31.jsonl**  2571 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-23_02-36-41.jsonl**  67 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-23_13-51-24.jsonl**  3329 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-24_12-07-16.jsonl**  2754 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-24_17-36-45.jsonl**  1932 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-25_12-47-44.jsonl**  2773 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-25_14-40-32.jsonl**  978 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-26_16-01-15.jsonl**  2928 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-27_14-35-16.jsonl**  1092 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-29_16-22-19.jsonl**  3424 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-09-30_13-53-57.jsonl**  2718 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-01_17-59-21.jsonl**  2816 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-02_14-59-59.jsonl**  2706 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-03_11-02-52.jsonl**  2482 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-08_01-05-48.jsonl**  3472 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-08_10-38-42.jsonl**  2055 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-09_13-54-42.jsonl**  3476 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-10_18-13-51.jsonl**  2956 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-13_13-51-00.jsonl**  2973 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-14_12-16-05.jsonl**  2952 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-15_20-12-42.jsonl**  3573 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-16_15-24-16.jsonl**  3450 records
- **.\src\parsers\regions_data\Краснодарский край\Краснодарский край_2025-10-19_16-54-24.jsonl**  2525 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-09_15-08-35.jsonl**  1745 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-20_04-25-22.jsonl**  1816 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-20_13-07-00.jsonl**  281 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-20_22-31-04.jsonl**  47 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-21_19-05-31.jsonl**  295 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-21_22-00-37.jsonl**  1276 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-22_00-42-34.jsonl**  1796 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-22_05-47-26.jsonl**  306 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-22_21-59-50.jsonl**  1152 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-23_02-42-14.jsonl**  27 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-24_12-14-22.jsonl**  1915 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-24_17-43-57.jsonl**  780 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-25_12-55-07.jsonl**  1425 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-25_14-48-00.jsonl**  290 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-26_16-08-34.jsonl**  1391 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-27_14-41-36.jsonl**  424 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-29_16-29-53.jsonl**  1616 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-09-30_14-01-15.jsonl**  1475 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-01_18-05-22.jsonl**  1506 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-02_15-09-34.jsonl**  1592 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-03_11-10-00.jsonl**  1277 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-08_01-11-57.jsonl**  1934 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-08_10-45-44.jsonl**  1270 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-09_14-02-07.jsonl**  1563 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-10_18-20-54.jsonl**  1246 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-13_13-57-52.jsonl**  1329 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-14_12-23-45.jsonl**  1368 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-15_20-20-04.jsonl**  1437 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-16_15-33-04.jsonl**  1347 records
- **.\src\parsers\regions_data\Красноярский край\Красноярский край_2025-10-19_17-00-12.jsonl**  1055 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-20_15-16-08.jsonl**  575 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-20_23-42-32.jsonl**  4 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-23_04-19-25.jsonl**  605 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-24_19-18-59.jsonl**  605 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-25_16-07-42.jsonl**  562 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-26_18-04-13.jsonl**  550 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-27_16-28-33.jsonl**  260 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-29_18-03-06.jsonl**  448 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-09-30_15-36-53.jsonl**  510 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-01_19-14-59.jsonl**  440 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-02_17-17-55.jsonl**  382 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-03_13-01-19.jsonl**  404 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-08_02-33-55.jsonl**  493 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-08_12-01-23.jsonl**  300 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-09_15-35-00.jsonl**  414 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-10_19-36-16.jsonl**  394 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-13_15-07-09.jsonl**  377 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-14_14-29-18.jsonl**  376 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-15_21-53-00.jsonl**  433 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-16_16-50-35.jsonl**  385 records
- **.\src\parsers\regions_data\Курганская область\Курганская область_2025-10-19_18-02-53.jsonl**  247 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-20_15-17-09.jsonl**  650 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-20_23-43-53.jsonl**  16 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-23_04-20-40.jsonl**  670 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-24_19-20-19.jsonl**  729 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-25_16-09-14.jsonl**  602 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-26_18-05-51.jsonl**  606 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-27_16-30-04.jsonl**  141 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-29_18-04-38.jsonl**  538 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-09-30_15-38-11.jsonl**  609 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-01_19-16-10.jsonl**  577 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-02_17-19-35.jsonl**  553 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-03_13-02-35.jsonl**  530 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-08_02-34-59.jsonl**  887 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-08_12-02-37.jsonl**  565 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-09_15-36-05.jsonl**  739 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-10_19-37-22.jsonl**  602 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-13_15-08-17.jsonl**  591 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-14_14-30-25.jsonl**  712 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-15_21-54-08.jsonl**  857 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-16_16-51-40.jsonl**  601 records
- **.\src\parsers\regions_data\Курская область\Курская область_2025-10-19_18-03-38.jsonl**  521 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-20_15-18-17.jsonl**  91 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-20_15-38-50.jsonl**  1517 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-20_23-44-55.jsonl**  64 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-23_04-21-43.jsonl**  1707 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-24_19-21-36.jsonl**  857 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-25_16-10-33.jsonl**  831 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-26_18-07-10.jsonl**  719 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-27_16-31-17.jsonl**  1259 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-29_18-05-51.jsonl**  832 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-09-30_15-39-22.jsonl**  2051 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-01_19-17-22.jsonl**  753 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-02_17-20-51.jsonl**  816 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-03_13-03-56.jsonl**  719 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-08_02-36-46.jsonl**  1713 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-08_12-04-47.jsonl**  1341 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-09_15-38-06.jsonl**  1591 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-10_19-38-40.jsonl**  732 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-13_15-09-48.jsonl**  837 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-14_14-32-19.jsonl**  1547 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-15_21-56-09.jsonl**  4417 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-16_16-53-28.jsonl**  3521 records
- **.\src\parsers\regions_data\Ленинградская область\Ленинградская область_2025-10-19_18-04-47.jsonl**  867 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-20_15-41-53.jsonl**  1711 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-20_23-48-07.jsonl**  59 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-23_04-24-44.jsonl**  1901 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-24_19-43-25.jsonl**  1828 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-25_16-32-25.jsonl**  1505 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-26_18-28-59.jsonl**  1274 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-27_16-34-51.jsonl**  319 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-29_18-27-49.jsonl**  1467 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-09-30_15-43-41.jsonl**  1505 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-01_19-38-58.jsonl**  1219 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-02_17-43-24.jsonl**  1331 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-03_13-25-43.jsonl**  1173 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-08_02-39-37.jsonl**  1566 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-08_12-08-54.jsonl**  1075 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-09_15-41-42.jsonl**  1385 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-10_21-35-18.jsonl**  1408 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-13_15-31-32.jsonl**  1511 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-14_14-35-20.jsonl**  1491 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-15_22-05-23.jsonl**  1662 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-16_17-02-43.jsonl**  1472 records
- **.\src\parsers\regions_data\Липецкая область\Липецкая область_2025-10-19_18-26-38.jsonl**  1386 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-20_15-44-52.jsonl**  35 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-23_04-28-02.jsonl**  29 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-24_19-47-02.jsonl**  29 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-25_16-36-14.jsonl**  27 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-26_18-32-38.jsonl**  23 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-27_16-37-32.jsonl**  5 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-29_18-31-20.jsonl**  25 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-09-30_15-47-19.jsonl**  23 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-01_19-41-54.jsonl**  20 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-02_17-47-04.jsonl**  22 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-03_13-28-41.jsonl**  12 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-08_02-42-16.jsonl**  25 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-08_12-12-14.jsonl**  18 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-09_15-44-36.jsonl**  18 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-10_21-39-08.jsonl**  11 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-13_15-35-11.jsonl**  14 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-14_14-39-04.jsonl**  14 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-15_22-09-11.jsonl**  12 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-16_17-06-28.jsonl**  10 records
- **.\src\parsers\regions_data\Магаданская область\Магаданская область_2025-10-19_18-29-26.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-20_19-27-11.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-21_02-07-37.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-23_06-59-32.jsonl**  93 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-24_22-53-08.jsonl**  124 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-25_19-46-31.jsonl**  84 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-26_21-47-40.jsonl**  63 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-27_19-34-10.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-30_00-43-26.jsonl**  51 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-30_19-22-59.jsonl**  97 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-02_21-12-52.jsonl**  161 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-03_17-05-22.jsonl**  102 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-08_05-20-40.jsonl**  160 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-08_15-21-03.jsonl**  154 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-09_18-46-35.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-11_00-16-04.jsonl**  117 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-13_18-05-38.jsonl**  102 records
- **.\src\parsers\regions_data\Московская область - Алтайский край\Московская область - Алтайский край_2025-10-14_17-15-40.jsonl**  105 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-20_19-45-41.jsonl**  108 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-21_02-15-08.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-23_07-08-18.jsonl**  93 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-24_23-05-15.jsonl**  96 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-25_20-00-42.jsonl**  50 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-26_21-59-18.jsonl**  57 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-27_19-44-08.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-30_00-54-21.jsonl**  74 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-09-30_19-33-26.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-02_21-27-44.jsonl**  70 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-08_05-29-01.jsonl**  22 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-08_15-31-01.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-09_18-54-58.jsonl**  87 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-11_00-26-28.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-13_18-15-29.jsonl**  39 records
- **.\src\parsers\regions_data\Московская область - Амурская область\Московская область - Амурская область_2025-10-14_17-25-51.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-20_19-46-06.jsonl**  153 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-21_02-15-47.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-23_07-09-10.jsonl**  150 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-24_23-05-46.jsonl**  109 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-25_20-01-12.jsonl**  99 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-26_22-00-00.jsonl**  114 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-27_19-44-49.jsonl**  41 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-30_00-55-03.jsonl**  82 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-09-30_19-34-08.jsonl**  81 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-02_21-29-10.jsonl**  152 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-03_17-18-51.jsonl**  120 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-08_05-29-42.jsonl**  107 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-08_15-31-43.jsonl**  74 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-09_18-55-40.jsonl**  88 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-11_00-27-09.jsonl**  81 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-13_18-16-13.jsonl**  70 records
- **.\src\parsers\regions_data\Московская область - Архангельская область\Московская область - Архангельская область_2025-10-14_17-26-32.jsonl**  83 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-20_19-46-34.jsonl**  108 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-21_02-16-12.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-23_07-09-40.jsonl**  111 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-24_23-06-30.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-25_20-02-05.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-26_22-00-51.jsonl**  114 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-27_19-45-36.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-30_00-55-48.jsonl**  106 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-09-30_19-34-50.jsonl**  136 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-02_21-29-41.jsonl**  107 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-03_17-19-37.jsonl**  119 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-08_05-30-19.jsonl**  145 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-08_15-32-23.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-09_18-56-19.jsonl**  160 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-11_00-27-48.jsonl**  151 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-13_18-17-04.jsonl**  100 records
- **.\src\parsers\regions_data\Московская область - Астраханская область\Московская область - Астраханская область_2025-10-14_17-27-12.jsonl**  99 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-20_19-47-00.jsonl**  219 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-21_02-17-07.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-23_07-10-19.jsonl**  279 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-24_23-07-00.jsonl**  213 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-25_20-02-36.jsonl**  205 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-26_22-01-24.jsonl**  250 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-27_19-46-18.jsonl**  48 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-30_00-56-18.jsonl**  240 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-09-30_19-35-20.jsonl**  301 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-02_21-31-07.jsonl**  266 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-03_17-20-08.jsonl**  291 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-08_05-30-49.jsonl**  287 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-08_15-32-55.jsonl**  216 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-09_18-57-05.jsonl**  200 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-11_00-28-19.jsonl**  172 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-13_18-17-35.jsonl**  172 records
- **.\src\parsers\regions_data\Московская область - Белгородская область\Московская область - Белгородская область_2025-10-14_17-27-43.jsonl**  180 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-20_19-47-46.jsonl**  266 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-21_02-17-36.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-23_07-10-54.jsonl**  332 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-24_23-08-02.jsonl**  270 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-25_20-03-32.jsonl**  256 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-26_22-02-21.jsonl**  266 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-27_19-47-18.jsonl**  100 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-30_00-57-07.jsonl**  348 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-09-30_19-36-11.jsonl**  355 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-02_21-31-45.jsonl**  334 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-03_17-21-03.jsonl**  236 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-08_05-31-33.jsonl**  297 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-08_15-33-40.jsonl**  219 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-09_18-57-49.jsonl**  228 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-11_00-28-58.jsonl**  142 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-13_18-18-20.jsonl**  306 records
- **.\src\parsers\regions_data\Московская область - Брянская область\Московская область - Брянская область_2025-10-14_17-28-27.jsonl**  321 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-20_19-48-18.jsonl**  277 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-21_02-18-20.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-23_07-11-45.jsonl**  336 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-24_23-08-48.jsonl**  234 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-25_20-04-13.jsonl**  268 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-26_22-03-04.jsonl**  266 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-27_19-48-11.jsonl**  63 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-30_00-57-48.jsonl**  344 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-09-30_19-36-55.jsonl**  360 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-02_21-33-16.jsonl**  275 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-03_17-21-44.jsonl**  277 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-08_05-32-13.jsonl**  260 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-08_15-34-21.jsonl**  211 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-09_18-58-24.jsonl**  214 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-11_00-29-33.jsonl**  251 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-13_18-19-01.jsonl**  243 records
- **.\src\parsers\regions_data\Московская область - Владимирская область\Московская область - Владимирская область_2025-10-14_17-29-13.jsonl**  169 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-20_19-48-50.jsonl**  345 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-21_02-18-51.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-23_07-12-25.jsonl**  343 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-24_23-09-42.jsonl**  296 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-25_20-05-11.jsonl**  396 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-26_22-04-01.jsonl**  414 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-27_19-49-12.jsonl**  171 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-30_00-58-43.jsonl**  458 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-09-30_19-37-48.jsonl**  511 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-02_21-34-02.jsonl**  523 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-03_17-22-33.jsonl**  513 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-08_05-32-58.jsonl**  393 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-08_15-35-17.jsonl**  445 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-09_18-59-06.jsonl**  441 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-11_00-30-18.jsonl**  571 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-13_18-19-58.jsonl**  359 records
- **.\src\parsers\regions_data\Московская область - Волгоградская область\Московская область - Волгоградская область_2025-10-14_17-29-55.jsonl**  441 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-20_19-49-28.jsonl**  246 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-21_02-19-55.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-23_07-13-14.jsonl**  249 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-24_23-10-30.jsonl**  161 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-25_20-06-09.jsonl**  209 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-26_22-04-58.jsonl**  192 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-27_19-50-06.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-30_00-59-40.jsonl**  228 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-09-30_19-38-51.jsonl**  211 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-02_21-35-48.jsonl**  278 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-03_17-23-37.jsonl**  196 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-08_05-34-12.jsonl**  176 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-08_15-36-24.jsonl**  190 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-09_19-00-11.jsonl**  209 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-11_00-31-20.jsonl**  184 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-13_18-20-46.jsonl**  179 records
- **.\src\parsers\regions_data\Московская область - Вологодская область\Московская область - Вологодская область_2025-10-14_17-30-54.jsonl**  159 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-20_19-49-58.jsonl**  779 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-21_02-20-24.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-23_07-13-47.jsonl**  874 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-24_23-11-28.jsonl**  891 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-25_20-07-01.jsonl**  893 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-26_22-05-53.jsonl**  884 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-27_19-50-57.jsonl**  331 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-30_01-00-25.jsonl**  1229 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-09-30_19-39-37.jsonl**  1191 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-02_21-36-25.jsonl**  1214 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-03_17-24-27.jsonl**  990 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-08_05-34-48.jsonl**  890 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-08_15-37-09.jsonl**  1054 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-09_19-00-55.jsonl**  905 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-11_00-32-02.jsonl**  776 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-13_18-21-28.jsonl**  838 records
- **.\src\parsers\regions_data\Московская область - Воронежская область\Московская область - Воронежская область_2025-10-14_17-31-37.jsonl**  762 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-09-26_22-49-54.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-09-27_20-33-16.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-02_22-36-48.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-03_18-07-25.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-08_06-09-54.jsonl**  56 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-08_16-18-23.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-09_19-38-56.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-13_18-54-31.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Еврейская автономная область\Московская область - Еврейская автономная область_2025-10-14_18-08-04.jsonl**  18 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-20_19-27-39.jsonl**  49 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-21_02-08-04.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-23_07-00-03.jsonl**  43 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-24_22-53-43.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-25_19-47-05.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-26_21-48-33.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-27_19-34-57.jsonl**  16 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-30_00-44-10.jsonl**  39 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-09-30_19-23-37.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-02_21-13-27.jsonl**  64 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-03_17-06-14.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-08_05-21-33.jsonl**  58 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-08_15-21-51.jsonl**  41 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-09_18-47-24.jsonl**  69 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-11_00-16-45.jsonl**  54 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-13_18-06-21.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Забайкальский край\Московская область - Забайкальский край_2025-10-14_17-16-23.jsonl**  40 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-20_19-53-52.jsonl**  133 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-21_02-21-49.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-23_07-15-17.jsonl**  154 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-24_23-13-50.jsonl**  124 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-25_20-09-22.jsonl**  127 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-26_22-08-14.jsonl**  169 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-27_19-53-16.jsonl**  42 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-30_01-02-54.jsonl**  227 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-09-30_19-41-56.jsonl**  253 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-02_21-40-15.jsonl**  189 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-03_17-26-45.jsonl**  223 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-08_05-36-36.jsonl**  140 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-08_15-39-29.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-09_19-03-04.jsonl**  88 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-11_00-34-00.jsonl**  83 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-13_18-23-23.jsonl**  73 records
- **.\src\parsers\regions_data\Московская область - Ивановская область\Московская область - Ивановская область_2025-10-14_17-33-39.jsonl**  55 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-20_19-54-18.jsonl**  321 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-21_02-22-14.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-23_07-15-47.jsonl**  349 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-24_23-14-31.jsonl**  122 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-25_20-10-15.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-26_22-09-42.jsonl**  139 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-27_19-54-13.jsonl**  70 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-30_01-03-44.jsonl**  176 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-09-30_19-42-46.jsonl**  289 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-02_21-41-04.jsonl**  251 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-03_17-27-36.jsonl**  199 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-08_05-37-12.jsonl**  367 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-08_15-40-13.jsonl**  219 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-09_19-03-45.jsonl**  205 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-11_00-34-40.jsonl**  237 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-13_18-24-15.jsonl**  202 records
- **.\src\parsers\regions_data\Московская область - Иркутская область\Московская область - Иркутская область_2025-10-14_17-34-30.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-20_19-15-37.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-21_01-54-40.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-23_06-46-45.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-24_22-39-21.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-25_19-30-55.jsonl**  53 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-26_21-33-16.jsonl**  47 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-27_19-17-24.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-30_00-30-05.jsonl**  33 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-09-30_19-09-15.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-02_20-51-41.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-03_16-50-58.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-08_05-08-19.jsonl**  22 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-09_18-33-26.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-11_00-03-24.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-13_17-52-58.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Кабардино-Балкарская Республика\Московская область - Кабардино-Балкарская Республика_2025-10-14_17-02-43.jsonl**  23 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-20_19-54-56.jsonl**  65 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-21_02-23-05.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-24_23-15-14.jsonl**  47 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-25_20-11-03.jsonl**  52 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-26_22-10-27.jsonl**  52 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-27_19-54-59.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-30_01-04-30.jsonl**  36 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-09-30_19-43-31.jsonl**  23 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-02_21-42-41.jsonl**  29 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-03_17-28-24.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-08_05-37-57.jsonl**  25 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-08_15-41-01.jsonl**  29 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-09_19-04-32.jsonl**  45 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-11_00-35-27.jsonl**  18 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-13_18-25-04.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Калининградская область\Московская область - Калининградская область_2025-10-14_17-35-18.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-20_19-55-37.jsonl**  186 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-21_02-23-45.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-23_07-17-30.jsonl**  223 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-24_23-16-07.jsonl**  235 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-25_20-12-04.jsonl**  243 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-26_22-11-26.jsonl**  198 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-27_19-56-00.jsonl**  50 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-30_01-05-23.jsonl**  325 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-09-30_19-44-25.jsonl**  101 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-02_21-43-22.jsonl**  328 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-03_17-29-22.jsonl**  270 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-08_05-38-47.jsonl**  225 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-08_15-41-53.jsonl**  250 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-09_19-05-24.jsonl**  203 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-11_00-36-17.jsonl**  233 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-13_18-25-55.jsonl**  230 records
- **.\src\parsers\regions_data\Московская область - Калужская область\Московская область - Калужская область_2025-10-14_17-36-09.jsonl**  192 records
- **.\src\parsers\regions_data\Московская область - Камчатский край\Московская область - Камчатский край_2025-09-20_19-28-21.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Камчатский край\Московская область - Камчатский край_2025-09-23_07-01-30.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Камчатский край\Московская область - Камчатский край_2025-09-26_21-49-16.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Камчатский край\Московская область - Камчатский край_2025-09-30_19-24-19.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Камчатский край\Московская область - Камчатский край_2025-10-08_05-22-16.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Камчатский край\Московская область - Камчатский край_2025-10-08_15-22-35.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-20_19-17-01.jsonl**  12 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-21_01-56-17.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-23_06-48-21.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-24_22-40-58.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-25_19-32-43.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-26_21-35-03.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-27_19-19-07.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-30_00-31-41.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-09-30_19-10-52.jsonl**  35 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-02_20-53-59.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-03_16-52-39.jsonl**  17 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-08_05-09-52.jsonl**  43 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-08_15-08-46.jsonl**  55 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-09_18-35-01.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-11_00-04-58.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-13_17-54-31.jsonl**  16 records
- **.\src\parsers\regions_data\Московская область - Карачаево-Черкесская Республика\Московская область - Карачаево-Черкесская Республика_2025-10-14_17-04-19.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-20_19-56-04.jsonl**  172 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-21_02-24-25.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-23_07-18-25.jsonl**  188 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-24_23-16-47.jsonl**  117 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-25_20-12-46.jsonl**  125 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-26_22-12-02.jsonl**  114 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-27_19-56-38.jsonl**  45 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-30_01-06-05.jsonl**  130 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-09-30_19-45-06.jsonl**  185 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-02_21-44-52.jsonl**  230 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-03_17-30-04.jsonl**  154 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-08_05-39-23.jsonl**  244 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-08_15-42-33.jsonl**  151 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-09_19-05-59.jsonl**  173 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-11_00-36-52.jsonl**  189 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-13_18-26-31.jsonl**  118 records
- **.\src\parsers\regions_data\Московская область - Кемеровская область\Московская область - Кемеровская область_2025-10-14_17-36-44.jsonl**  113 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-20_19-56-56.jsonl**  178 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-21_02-24-51.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-23_07-18-56.jsonl**  193 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-24_23-17-33.jsonl**  99 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-25_20-13-39.jsonl**  127 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-26_22-12-57.jsonl**  159 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-27_19-57-42.jsonl**  41 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-30_01-06-52.jsonl**  224 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-09-30_19-45-53.jsonl**  184 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-02_21-45-30.jsonl**  188 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-03_17-30-57.jsonl**  173 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-08_05-40-08.jsonl**  194 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-08_15-43-27.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-09_19-06-45.jsonl**  114 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-11_00-37-36.jsonl**  130 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-13_18-27-16.jsonl**  167 records
- **.\src\parsers\regions_data\Московская область - Кировская область\Московская область - Кировская область_2025-10-14_17-37-26.jsonl**  83 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-20_19-57-25.jsonl**  84 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-21_02-25-34.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-23_07-19-38.jsonl**  113 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-24_23-18-03.jsonl**  84 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-25_20-14-11.jsonl**  85 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-26_22-13-32.jsonl**  103 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-27_19-58-18.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-30_01-07-29.jsonl**  104 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-09-30_19-46-28.jsonl**  101 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-02_21-46-54.jsonl**  66 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-03_17-31-34.jsonl**  78 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-08_05-40-52.jsonl**  115 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-08_15-44-00.jsonl**  99 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-09_19-07-17.jsonl**  59 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-11_00-38-10.jsonl**  103 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-13_18-27-51.jsonl**  92 records
- **.\src\parsers\regions_data\Московская область - Костромская область\Московская область - Костромская область_2025-10-14_17-37-57.jsonl**  82 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-20_19-29-12.jsonl**  1483 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-21_02-09-36.jsonl**  53 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-23_07-02-09.jsonl**  1443 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-24_22-57-12.jsonl**  1305 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-25_19-51-37.jsonl**  1691 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-26_21-50-12.jsonl**  1605 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-27_19-36-33.jsonl**  599 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-30_00-47-01.jsonl**  1482 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-09-30_19-25-07.jsonl**  1647 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-02_21-15-39.jsonl**  2038 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-03_17-09-11.jsonl**  1540 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-08_05-23-01.jsonl**  1483 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-08_15-23-25.jsonl**  1131 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-09_18-50-14.jsonl**  99 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-11_00-19-33.jsonl**  1518 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-13_18-09-08.jsonl**  1039 records
- **.\src\parsers\regions_data\Московская область - Краснодарский край\Московская область - Краснодарский край_2025-10-14_17-19-08.jsonl**  1105 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-20_19-31-58.jsonl**  310 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-21_02-12-06.jsonl**  12 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-23_07-04-46.jsonl**  313 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-24_23-01-03.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-25_19-56-02.jsonl**  207 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-26_21-54-29.jsonl**  154 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-27_19-39-37.jsonl**  71 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-30_00-50-01.jsonl**  204 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-09-30_19-28-47.jsonl**  329 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-02_21-21-48.jsonl**  287 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-03_17-13-17.jsonl**  205 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-08_05-25-28.jsonl**  349 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-08_15-26-35.jsonl**  269 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-09_18-50-57.jsonl**  282 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-11_00-22-23.jsonl**  222 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-13_18-11-32.jsonl**  174 records
- **.\src\parsers\regions_data\Московская область - Красноярский край\Московская область - Красноярский край_2025-10-14_17-21-55.jsonl**  173 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-20_19-58-07.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-23_07-20-09.jsonl**  16 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-24_23-18-46.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-25_20-15-00.jsonl**  17 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-26_22-14-24.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-27_19-59-11.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-09-30_19-47-14.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-02_21-47-37.jsonl**  28 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-03_17-32-20.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-08_05-41-31.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-08_15-44-43.jsonl**  39 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-09_19-08-09.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-11_00-38-50.jsonl**  25 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-13_18-28-32.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Курганская область\Московская область - Курганская область_2025-10-14_17-38-47.jsonl**  21 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-20_19-58-48.jsonl**  177 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-21_02-27-08.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-23_07-21-02.jsonl**  244 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-24_23-19-28.jsonl**  190 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-25_20-15-42.jsonl**  197 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-26_22-15-06.jsonl**  218 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-27_19-59-53.jsonl**  79 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-30_01-08-53.jsonl**  239 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-09-30_19-47-56.jsonl**  203 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-02_21-49-10.jsonl**  267 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-03_17-33-02.jsonl**  171 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-08_05-42-12.jsonl**  205 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-08_15-45-25.jsonl**  192 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-09_19-08-50.jsonl**  162 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-11_00-39-30.jsonl**  165 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-13_18-29-14.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Курская область\Московская область - Курская область_2025-10-14_17-39-28.jsonl**  139 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-20_19-59-16.jsonl**  382 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-21_02-27-35.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-23_07-21-36.jsonl**  496 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-24_23-20-11.jsonl**  345 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-25_20-16-36.jsonl**  428 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-26_22-15-59.jsonl**  483 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-27_20-00-45.jsonl**  151 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-30_01-09-37.jsonl**  460 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-09-30_19-48-43.jsonl**  485 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-02_21-49-47.jsonl**  554 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-03_17-33-57.jsonl**  429 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-08_05-42-54.jsonl**  372 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-08_15-46-10.jsonl**  335 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-09_19-09-34.jsonl**  305 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-11_00-40-22.jsonl**  309 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-13_18-29-50.jsonl**  191 records
- **.\src\parsers\regions_data\Московская область - Ленинградская область\Московская область - Ленинградская область_2025-10-14_17-40-11.jsonl**  276 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-20_20-00-18.jsonl**  151 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-21_02-28-23.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-23_07-22-31.jsonl**  183 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-24_23-21-26.jsonl**  216 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-25_20-17-34.jsonl**  198 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-26_22-16-57.jsonl**  259 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-27_20-01-45.jsonl**  89 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-30_01-10-34.jsonl**  291 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-09-30_19-49-39.jsonl**  288 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-02_21-52-04.jsonl**  239 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-03_17-34-57.jsonl**  233 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-08_05-43-34.jsonl**  257 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-08_15-47-00.jsonl**  235 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-09_19-10-19.jsonl**  214 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-11_00-41-07.jsonl**  185 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-13_18-30-27.jsonl**  207 records
- **.\src\parsers\regions_data\Московская область - Липецкая область\Московская область - Липецкая область_2025-10-14_17-40-51.jsonl**  199 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-20_20-00-47.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-23_07-23-04.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-24_23-22-19.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-25_20-18-36.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-26_22-18-05.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-27_20-02-41.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-30_01-11-26.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-09-30_19-50-38.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-10-02_21-52-43.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-10-03_17-35-48.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-10-08_05-44-20.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-10-08_15-47-53.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-10-11_00-41-52.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Магаданская область\Московская область - Магаданская область_2025-10-14_17-41-39.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-20_20-01-29.jsonl**  90 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-21_02-29-46.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-23_07-23-57.jsonl**  94 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-24_23-23-00.jsonl**  98 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-25_20-19-18.jsonl**  209 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-26_22-18-47.jsonl**  136 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-27_20-03-24.jsonl**  53 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-30_01-12-08.jsonl**  135 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-09-30_19-51-20.jsonl**  133 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-02_21-54-17.jsonl**  172 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-03_17-36-32.jsonl**  142 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-08_05-45-01.jsonl**  112 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-08_15-48-34.jsonl**  105 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-09_19-11-43.jsonl**  144 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-11_00-42-32.jsonl**  166 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-13_18-31-54.jsonl**  97 records
- **.\src\parsers\regions_data\Московская область - Мурманская область\Московская область - Мурманская область_2025-10-14_17-42-23.jsonl**  62 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-20_20-49-41.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-23_07-50-37.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-24_23-53-40.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-25_20-54-04.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-26_22-50-37.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-27_20-33-59.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-30_01-41-24.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-09-30_20-23-51.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-10-02_22-38-16.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-10-08_16-19-07.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-10-09_19-39-39.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ненецкий автономный округ\Московская область - Ненецкий автономный округ_2025-10-11_01-11-29.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-20_20-02-08.jsonl**  590 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-21_02-30-23.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-23_07-24-36.jsonl**  634 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-24_23-23-40.jsonl**  515 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-25_20-20-21.jsonl**  476 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-26_22-19-32.jsonl**  538 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-27_20-04-08.jsonl**  138 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-30_01-12-46.jsonl**  593 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-09-30_19-51-58.jsonl**  656 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-02_21-54-48.jsonl**  618 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-03_17-37-12.jsonl**  581 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-08_05-45-37.jsonl**  674 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-08_15-49-14.jsonl**  488 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-09_19-12-19.jsonl**  375 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-11_00-43-11.jsonl**  452 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-13_18-32-30.jsonl**  473 records
- **.\src\parsers\regions_data\Московская область - Нижегородская область\Московская область - Нижегородская область_2025-10-14_17-43-12.jsonl**  429 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-20_20-03-10.jsonl**  160 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-21_02-31-41.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-23_07-25-48.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-24_23-24-57.jsonl**  105 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-25_20-21-31.jsonl**  125 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-26_22-20-46.jsonl**  133 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-27_20-05-12.jsonl**  33 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-30_01-13-57.jsonl**  145 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-09-30_19-53-31.jsonl**  192 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-02_21-56-59.jsonl**  171 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-03_17-38-24.jsonl**  161 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-08_05-46-39.jsonl**  161 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-08_15-50-18.jsonl**  124 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-09_19-13-15.jsonl**  104 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-11_00-44-07.jsonl**  126 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-13_18-33-32.jsonl**  107 records
- **.\src\parsers\regions_data\Московская область - Новгородская область\Московская область - Новгородская область_2025-10-14_17-44-19.jsonl**  101 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-20_20-03-54.jsonl**  626 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-21_02-32-04.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-23_07-26-16.jsonl**  633 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-24_23-25-37.jsonl**  397 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-25_20-22-19.jsonl**  488 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-26_22-21-35.jsonl**  590 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-27_20-05-59.jsonl**  231 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-30_01-14-38.jsonl**  635 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-09-30_19-54-15.jsonl**  682 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-02_21-57-29.jsonl**  983 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-03_17-39-08.jsonl**  710 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-08_05-47-16.jsonl**  808 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-08_15-51-01.jsonl**  705 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-09_19-13-58.jsonl**  591 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-11_00-44-45.jsonl**  757 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-13_18-34-09.jsonl**  601 records
- **.\src\parsers\regions_data\Московская область - Новосибирская область\Московская область - Новосибирская область_2025-10-14_17-45-02.jsonl**  633 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-20_20-05-30.jsonl**  167 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-21_02-33-14.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-23_07-27-32.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-24_23-26-57.jsonl**  116 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-25_20-23-37.jsonl**  140 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-26_22-23-36.jsonl**  143 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-27_20-07-12.jsonl**  87 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-30_01-15-57.jsonl**  178 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-09-30_19-56-10.jsonl**  190 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-02_22-01-28.jsonl**  226 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-03_17-41-22.jsonl**  147 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-08_05-49-04.jsonl**  188 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-08_15-53-13.jsonl**  149 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-09_19-15-59.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-11_00-46-47.jsonl**  198 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-13_18-36-02.jsonl**  152 records
- **.\src\parsers\regions_data\Московская область - Омская область\Московская область - Омская область_2025-10-14_17-47-06.jsonl**  147 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-20_20-05-58.jsonl**  222 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-21_02-33-40.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-23_07-28-02.jsonl**  193 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-24_23-27-49.jsonl**  172 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-25_20-24-38.jsonl**  243 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-26_22-24-30.jsonl**  304 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-27_20-08-09.jsonl**  97 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-30_01-16-47.jsonl**  273 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-09-30_19-56-54.jsonl**  309 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-02_22-02-05.jsonl**  444 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-03_17-42-13.jsonl**  278 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-08_05-49-57.jsonl**  233 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-08_15-54-04.jsonl**  242 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-09_19-16-46.jsonl**  259 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-11_00-47-33.jsonl**  203 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-13_18-36-49.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Оренбургская область\Московская область - Оренбургская область_2025-10-14_17-47-54.jsonl**  189 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-20_20-06-29.jsonl**  202 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-21_02-34-19.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-23_07-28-44.jsonl**  169 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-24_23-28-25.jsonl**  176 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-25_20-25-18.jsonl**  218 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-26_22-25-14.jsonl**  161 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-27_20-08-50.jsonl**  69 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-30_01-17-26.jsonl**  177 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-09-30_19-57-39.jsonl**  202 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-02_22-03-52.jsonl**  154 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-03_17-42-55.jsonl**  156 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-08_05-50-31.jsonl**  132 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-08_15-54-45.jsonl**  100 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-09_19-17-26.jsonl**  89 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-11_00-48-23.jsonl**  120 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-13_18-37-20.jsonl**  112 records
- **.\src\parsers\regions_data\Московская область - Орловская область\Московская область - Орловская область_2025-10-14_17-48-30.jsonl**  96 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-20_20-06-59.jsonl**  182 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-21_02-35-08.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-23_07-29-14.jsonl**  221 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-24_23-29-11.jsonl**  246 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-25_20-26-14.jsonl**  234 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-26_22-26-17.jsonl**  211 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-27_20-09-42.jsonl**  64 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-30_01-18-09.jsonl**  259 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-09-30_19-58-30.jsonl**  276 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-02_22-04-24.jsonl**  261 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-03_17-43-52.jsonl**  253 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-08_05-51-09.jsonl**  288 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-08_15-55-26.jsonl**  264 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-09_19-18-09.jsonl**  214 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-11_00-49-03.jsonl**  206 records
- **.\src\parsers\regions_data\Московская область - Пензенская область\Московская область - Пензенская область_2025-10-13_18-38-00.jsonl**  202 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-20_19-32-38.jsonl**  287 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-21_02-12-41.jsonl**  25 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-23_07-05-24.jsonl**  271 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-24_23-02-00.jsonl**  236 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-25_19-57-05.jsonl**  223 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-26_21-55-37.jsonl**  278 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-27_19-40-40.jsonl**  98 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-30_00-51-10.jsonl**  264 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-09-30_19-29-46.jsonl**  288 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-02_21-22-39.jsonl**  340 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-03_17-14-15.jsonl**  268 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-08_05-26-19.jsonl**  281 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-08_15-27-37.jsonl**  254 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-09_18-51-52.jsonl**  181 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-11_00-23-28.jsonl**  193 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-13_18-12-26.jsonl**  240 records
- **.\src\parsers\regions_data\Московская область - Пермский край\Московская область - Пермский край_2025-10-14_17-22-49.jsonl**  174 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-20_19-33-11.jsonl**  173 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-21_02-13-24.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-23_07-06-09.jsonl**  177 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-24_23-02-41.jsonl**  80 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-25_19-57-49.jsonl**  63 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-26_21-56-19.jsonl**  76 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-27_19-41-23.jsonl**  47 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-30_00-51-51.jsonl**  113 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-09-30_19-30-27.jsonl**  120 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-02_21-24-12.jsonl**  100 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-03_17-14-59.jsonl**  93 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-08_05-26-55.jsonl**  159 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-08_15-28-17.jsonl**  89 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-09_18-52-31.jsonl**  93 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-11_00-24-04.jsonl**  86 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-13_18-13-03.jsonl**  74 records
- **.\src\parsers\regions_data\Московская область - Приморский край\Московская область - Приморский край_2025-10-14_17-23-26.jsonl**  79 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-20_20-07-45.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-21_02-35-49.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-23_07-30-00.jsonl**  80 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-24_23-29-52.jsonl**  81 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-25_20-26-56.jsonl**  61 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-26_22-26-53.jsonl**  79 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-27_20-10-20.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-30_01-18-48.jsonl**  69 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-09-30_19-59-11.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-02_22-05-53.jsonl**  81 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-03_17-44-32.jsonl**  92 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-08_05-51-47.jsonl**  62 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-08_15-56-09.jsonl**  49 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-09_19-18-46.jsonl**  45 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-11_00-49-39.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-13_18-38-37.jsonl**  50 records
- **.\src\parsers\regions_data\Московская область - Псковская область\Московская область - Псковская область_2025-10-14_17-49-42.jsonl**  58 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-20_19-11-22.jsonl**  174 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-21_01-50-06.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-23_06-42-10.jsonl**  146 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-24_22-34-32.jsonl**  121 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-25_19-25-57.jsonl**  146 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-26_21-28-09.jsonl**  156 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-27_19-12-16.jsonl**  90 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-30_00-25-35.jsonl**  142 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-09-30_19-04-41.jsonl**  139 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-02_20-43-14.jsonl**  253 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-03_16-45-32.jsonl**  205 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-08_05-03-28.jsonl**  174 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-08_15-01-56.jsonl**  148 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-09_18-28-38.jsonl**  125 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-10_23-58-55.jsonl**  96 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-13_17-48-24.jsonl**  74 records
- **.\src\parsers\regions_data\Московская область - Республика Адыгея\Московская область - Республика Адыгея_2025-10-14_16-58-00.jsonl**  55 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-20_19-11-50.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-21_01-50-48.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-24_22-35-18.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-25_19-26-48.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-26_21-28-47.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-27_19-12-50.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-30_00-26-04.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-09-30_19-05-13.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-02_20-44-46.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-03_16-46-10.jsonl**  16 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-08_05-04-02.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-08_15-02-34.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-09_18-29-11.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-10_23-59-27.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Республика Алтай\Московская область - Республика Алтай_2025-10-14_16-58-32.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-20_19-12-30.jsonl**  421 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-21_01-51-28.jsonl**  18 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-23_06-43-32.jsonl**  406 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-24_22-36-00.jsonl**  277 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-25_19-27-29.jsonl**  338 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-26_21-29-44.jsonl**  411 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-27_19-13-46.jsonl**  137 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-30_00-26-50.jsonl**  418 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-09-30_19-06-06.jsonl**  395 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-02_20-45-26.jsonl**  544 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-03_16-47-14.jsonl**  441 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-08_05-04-48.jsonl**  478 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-08_15-03-26.jsonl**  451 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-09_18-29-59.jsonl**  524 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-11_00-00-14.jsonl**  398 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-13_17-49-48.jsonl**  230 records
- **.\src\parsers\regions_data\Московская область - Республика Башкортостан\Московская область - Республика Башкортостан_2025-10-14_16-59-18.jsonl**  409 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-20_19-13-14.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-23_06-44-27.jsonl**  22 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-24_22-37-05.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-25_19-28-29.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-26_21-30-41.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-27_19-14-36.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-30_00-27-47.jsonl**  28 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-09-30_19-06-55.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-02_20-48-55.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-03_16-48-21.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-08_05-06-02.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-08_15-04-32.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-09_18-31-10.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-11_00-01-10.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-13_17-50-34.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Республика Бурятия\Московская область - Республика Бурятия_2025-10-14_17-00-15.jsonl**  29 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-20_19-14-13.jsonl**  90 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-21_01-53-01.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-23_06-45-10.jsonl**  89 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-24_22-37-46.jsonl**  66 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-25_19-29-13.jsonl**  64 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-26_21-31-41.jsonl**  88 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-27_19-15-38.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-30_00-28-39.jsonl**  102 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-09-30_19-07-48.jsonl**  123 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-02_20-49-37.jsonl**  163 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-03_16-49-21.jsonl**  90 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-08_05-06-47.jsonl**  49 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-08_15-05-28.jsonl**  80 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-09_18-32-01.jsonl**  115 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-11_00-02-00.jsonl**  77 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-13_17-51-22.jsonl**  28 records
- **.\src\parsers\regions_data\Московская область - Республика Дагестан\Московская область - Республика Дагестан_2025-10-14_17-01-07.jsonl**  94 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-20_19-14-55.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-23_06-46-02.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-24_22-38-38.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-25_19-30-12.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-26_21-32-13.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-27_19-16-22.jsonl**  23 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-30_00-29-10.jsonl**  35 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-09-30_19-08-21.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-02_20-50-56.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-03_16-50-01.jsonl**  29 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-08_05-07-29.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-08_15-06-12.jsonl**  28 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-09_18-32-33.jsonl**  25 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-11_00-02-31.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-13_17-52-05.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Республика Ингушетия\Московская область - Республика Ингушетия_2025-10-14_17-01-51.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-20_19-16-19.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-23_06-47-38.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-24_22-40-16.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-25_19-32-01.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-26_21-33-59.jsonl**  21 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-27_19-18-07.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-30_00-30-48.jsonl**  21 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-09-30_19-09-58.jsonl**  23 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-02_20-53-17.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-03_16-51-42.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-08_05-09-01.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-08_15-07-50.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-09_18-34-09.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-11_00-04-07.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-13_17-53-40.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Республика Калмыкия\Московская область - Республика Калмыкия_2025-10-14_17-03-26.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-20_19-17-57.jsonl**  73 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-21_01-57-12.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-23_06-49-15.jsonl**  58 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-24_22-41-54.jsonl**  50 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-25_19-33-45.jsonl**  51 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-26_21-35-46.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-27_19-19-50.jsonl**  17 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-30_00-32-24.jsonl**  64 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-09-30_19-11-36.jsonl**  75 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-02_20-55-25.jsonl**  63 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-03_16-53-23.jsonl**  68 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-08_05-10-35.jsonl**  62 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-08_15-09-29.jsonl**  47 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-09_18-35-44.jsonl**  65 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-11_00-05-41.jsonl**  50 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-13_17-55-14.jsonl**  67 records
- **.\src\parsers\regions_data\Московская область - Республика Карелия\Московская область - Республика Карелия_2025-10-14_17-05-03.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-20_19-18-39.jsonl**  39 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-21_01-57-54.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-23_06-49-58.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-24_22-42-39.jsonl**  35 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-25_19-34-28.jsonl**  71 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-26_21-36-49.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-27_19-20-55.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-30_00-33-18.jsonl**  58 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-09-30_19-12-29.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-02_20-56-08.jsonl**  52 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-03_16-54-21.jsonl**  43 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-08_05-11-26.jsonl**  87 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-08_15-10-21.jsonl**  64 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-09_18-36-38.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-11_00-06-33.jsonl**  36 records
- **.\src\parsers\regions_data\Московская область - Республика Коми\Московская область - Республика Коми_2025-10-13_17-56-07.jsonl**  57 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-20_19-19-19.jsonl**  320 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-21_01-58-48.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-23_06-50-51.jsonl**  309 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-24_22-43-32.jsonl**  192 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-25_19-35-44.jsonl**  314 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-26_21-37-30.jsonl**  270 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-27_19-21-37.jsonl**  94 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-30_00-34-00.jsonl**  286 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-09-30_19-13-11.jsonl**  361 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-02_20-57-30.jsonl**  441 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-03_16-55-02.jsonl**  337 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-08_05-12-07.jsonl**  448 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-08_15-10-51.jsonl**  255 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-09_18-37-20.jsonl**  268 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-11_00-07-13.jsonl**  231 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-13_17-56-49.jsonl**  163 records
- **.\src\parsers\regions_data\Московская область - Республика Крым\Московская область - Республика Крым_2025-10-14_17-06-37.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-20_19-19-57.jsonl**  33 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-21_01-59-24.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-23_06-51-42.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-24_22-44-16.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-25_19-36-33.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-26_21-38-35.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-27_19-23-04.jsonl**  11 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-30_00-34-54.jsonl**  62 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-09-30_19-14-09.jsonl**  48 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-02_20-58-30.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-03_16-56-20.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-08_05-13-01.jsonl**  41 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-08_15-11-51.jsonl**  25 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-09_18-38-14.jsonl**  40 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-11_00-08-03.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Республика Марий Эл\Московская область - Республика Марий Эл_2025-10-13_17-57-35.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-20_19-20-39.jsonl**  71 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-21_02-00-19.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-23_06-52-35.jsonl**  65 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-24_22-45-13.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-25_19-37-32.jsonl**  53 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-26_21-39-18.jsonl**  52 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-27_19-23-48.jsonl**  16 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-30_00-35-37.jsonl**  56 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-09-30_19-14-52.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-02_21-00-02.jsonl**  71 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-03_16-57-02.jsonl**  82 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-08_05-13-44.jsonl**  69 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-08_15-12-35.jsonl**  70 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-09_18-38-55.jsonl**  85 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-11_00-08-44.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-13_17-58-18.jsonl**  48 records
- **.\src\parsers\regions_data\Московская область - Республика Мордовия\Московская область - Республика Мордовия_2025-10-14_17-08-07.jsonl**  33 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-20_19-21-36.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-23_06-53-18.jsonl**  41 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-24_22-45-56.jsonl**  52 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-25_19-38-15.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-26_21-40-22.jsonl**  35 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-27_19-24-49.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-30_00-36-31.jsonl**  35 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-09-30_19-15-50.jsonl**  44 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-02_21-00-45.jsonl**  48 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-03_16-57-48.jsonl**  48 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-08_05-14-30.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-08_15-13-33.jsonl**  36 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-11_00-09-24.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-13_17-59-10.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Республика Саха _Якутия_\Московская область - Республика Саха _Якутия__2025-10-14_17-09-00.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-20_19-22-31.jsonl**  814 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-21_02-02-18.jsonl**  33 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-23_06-54-28.jsonl**  851 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-24_22-47-16.jsonl**  632 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-25_19-39-57.jsonl**  740 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-26_21-41-17.jsonl**  782 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-27_19-25-45.jsonl**  233 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-30_00-37-26.jsonl**  1044 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-09-30_19-16-45.jsonl**  1030 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-02_21-03-54.jsonl**  1086 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-03_16-58-42.jsonl**  997 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-08_05-15-22.jsonl**  870 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-08_15-14-28.jsonl**  775 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-09_18-40-28.jsonl**  874 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-11_00-10-18.jsonl**  821 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-13_18-00-04.jsonl**  791 records
- **.\src\parsers\regions_data\Московская область - Республика Татарстан\Московская область - Республика Татарстан_2025-10-14_17-09-55.jsonl**  728 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-20_19-23-51.jsonl**  6 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-21_02-03-47.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-23_06-55-43.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-24_22-49-21.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-25_19-42-06.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-26_21-43-53.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-30_00-39-55.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-09-30_19-19-26.jsonl**  12 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-02_21-07-02.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-03_17-01-37.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-08_15-16-56.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-09_18-42-51.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-11_00-12-35.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-13_18-02-19.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Республика Тыва\Московская область - Республика Тыва_2025-10-14_17-12-07.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-20_19-24-52.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-23_06-57-09.jsonl**  21 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-24_22-50-47.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-25_19-43-41.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-26_21-45-26.jsonl**  17 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-27_19-31-59.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-30_00-41-19.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-09-30_19-20-53.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-02_21-09-12.jsonl**  21 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-03_17-03-15.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-08_05-18-39.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-08_15-18-23.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-09_18-44-17.jsonl**  23 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-11_00-14-01.jsonl**  23 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-13_18-03-36.jsonl**  39 records
- **.\src\parsers\regions_data\Московская область - Республика Хакасия\Московская область - Республика Хакасия_2025-10-14_17-13-36.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-20_20-08-23.jsonl**  1076 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-21_02-36-27.jsonl**  45 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-23_07-30-40.jsonl**  1203 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-24_23-30-29.jsonl**  1009 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-25_20-27-49.jsonl**  1340 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-26_22-27-45.jsonl**  1274 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-27_20-11-17.jsonl**  441 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-30_01-19-36.jsonl**  1049 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-09-30_20-00-01.jsonl**  1267 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-02_22-06-34.jsonl**  1485 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-03_17-45-13.jsonl**  1281 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-08_05-52-37.jsonl**  1291 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-08_15-56-59.jsonl**  1066 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-09_19-19-33.jsonl**  1086 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-11_00-50-25.jsonl**  969 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-13_18-39-27.jsonl**  741 records
- **.\src\parsers\regions_data\Московская область - Ростовская область\Московская область - Ростовская область_2025-10-14_17-50-31.jsonl**  770 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-20_20-10-34.jsonl**  236 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-21_02-38-34.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-23_07-33-14.jsonl**  245 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-24_23-33-14.jsonl**  236 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-25_20-30-45.jsonl**  230 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-26_22-30-34.jsonl**  274 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-27_20-13-52.jsonl**  76 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-30_01-21-57.jsonl**  355 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-09-30_20-02-33.jsonl**  315 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-02_22-10-55.jsonl**  272 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-03_17-48-02.jsonl**  169 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-08_05-54-55.jsonl**  222 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-08_16-00-03.jsonl**  278 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-09_19-22-06.jsonl**  239 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-11_00-52-46.jsonl**  227 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-13_18-41-36.jsonl**  256 records
- **.\src\parsers\regions_data\Московская область - Рязанская область\Московская область - Рязанская область_2025-10-14_17-52-43.jsonl**  270 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-20_20-11-05.jsonl**  752 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-21_02-39-02.jsonl**  14 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-23_07-33-47.jsonl**  884 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-24_23-34-04.jsonl**  632 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-25_20-31-40.jsonl**  826 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-26_22-31-34.jsonl**  883 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-27_20-14-52.jsonl**  320 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-30_01-22-51.jsonl**  828 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-09-30_20-03-30.jsonl**  889 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-02_22-11-35.jsonl**  958 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-03_17-49-00.jsonl**  857 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-08_05-55-36.jsonl**  750 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-08_16-00-58.jsonl**  692 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-09_19-22-55.jsonl**  756 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-11_00-53-32.jsonl**  792 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-13_18-42-23.jsonl**  699 records
- **.\src\parsers\regions_data\Московская область - Самарская область\Московская область - Самарская область_2025-10-14_17-53-34.jsonl**  688 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-20_20-44-20.jsonl**  1497 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-21_02-49-18.jsonl**  62 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-23_07-45-34.jsonl**  1847 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-24_23-48-53.jsonl**  1262 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-25_20-46-54.jsonl**  1549 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-26_22-46-31.jsonl**  1254 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-27_20-29-30.jsonl**  540 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-30_01-35-33.jsonl**  1455 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-09-30_20-17-04.jsonl**  1793 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-02_22-31-45.jsonl**  1667 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-03_18-02-52.jsonl**  1519 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-08_06-07-08.jsonl**  1591 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-08_16-14-29.jsonl**  1263 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-09_19-35-54.jsonl**  1253 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-11_01-06-06.jsonl**  1091 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-13_18-53-39.jsonl**  194 records
- **.\src\parsers\regions_data\Московская область - Санкт-Петербург\Московская область - Санкт-Петербург_2025-10-14_18-05-39.jsonl**  946 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-20_20-12-22.jsonl**  275 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-20_20-33-23.jsonl**  47 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-21_02-40-20.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-23_07-35-15.jsonl**  290 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-24_23-37-18.jsonl**  296 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-25_20-34-03.jsonl**  327 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-26_22-33-55.jsonl**  370 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-27_20-16-57.jsonl**  129 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-30_01-24-44.jsonl**  347 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-09-30_20-05-33.jsonl**  405 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-02_22-15-06.jsonl**  485 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-03_17-51-09.jsonl**  358 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-08_05-56-46.jsonl**  491 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-08_16-02-53.jsonl**  420 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-09_19-24-46.jsonl**  438 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-11_00-55-28.jsonl**  428 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-13_18-43-42.jsonl**  237 records
- **.\src\parsers\regions_data\Московская область - Саратовская область\Московская область - Саратовская область_2025-10-14_17-55-31.jsonl**  298 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-20_20-34-11.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-23_07-35-58.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-24_23-38-19.jsonl**  10 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-25_20-35-12.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-26_22-35-05.jsonl**  15 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-27_20-18-06.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-30_01-25-42.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-09-30_20-06-37.jsonl**  8 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-10-02_22-16-05.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-10-08_05-58-02.jsonl**  18 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-10-08_16-04-09.jsonl**  4 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-10-09_19-26-00.jsonl**  1 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-10-13_18-44-28.jsonl**  36 records
- **.\src\parsers\regions_data\Московская область - Сахалинская область\Московская область - Сахалинская область_2025-10-14_17-56-24.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-20_20-34-50.jsonl**  803 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-20_20-37-14.jsonl**  126 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-21_02-41-42.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-23_07-36-45.jsonl**  941 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-24_23-38-58.jsonl**  647 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-25_20-35-52.jsonl**  894 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-26_22-35-45.jsonl**  798 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-27_20-18-47.jsonl**  273 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-30_01-26-21.jsonl**  770 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-09-30_20-07-16.jsonl**  980 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-02_22-17-32.jsonl**  1242 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-03_17-52-48.jsonl**  1006 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-08_05-58-41.jsonl**  1045 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-08_16-04-49.jsonl**  773 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-09_19-26-40.jsonl**  796 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-11_00-57-15.jsonl**  780 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-13_18-45-06.jsonl**  653 records
- **.\src\parsers\regions_data\Московская область - Свердловская область\Московская область - Свердловская область_2025-10-14_17-57-03.jsonl**  654 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-20_20-38-32.jsonl**  222 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-21_02-42-58.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-23_07-38-34.jsonl**  278 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-24_23-41-27.jsonl**  229 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-25_20-38-55.jsonl**  293 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-26_22-38-23.jsonl**  196 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-27_20-21-33.jsonl**  132 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-30_01-28-38.jsonl**  243 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-09-30_20-09-48.jsonl**  293 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-02_22-20-45.jsonl**  284 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-03_17-55-37.jsonl**  210 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-08_06-00-57.jsonl**  210 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-08_16-07-24.jsonl**  133 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-09_19-29-13.jsonl**  103 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-11_00-59-29.jsonl**  103 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-13_18-47-10.jsonl**  135 records
- **.\src\parsers\regions_data\Московская область - Смоленская область\Московская область - Смоленская область_2025-10-14_17-59-21.jsonl**  229 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-20_19-44-12.jsonl**  472 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-21_02-13-50.jsonl**  13 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-23_07-06-38.jsonl**  555 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-24_23-03-22.jsonl**  339 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-25_19-58-36.jsonl**  524 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-26_21-57-06.jsonl**  546 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-27_19-42-04.jsonl**  216 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-30_00-52-31.jsonl**  558 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-09-30_19-31-05.jsonl**  656 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-02_21-24-43.jsonl**  807 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-03_17-15-41.jsonl**  623 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-08_05-27-29.jsonl**  481 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-08_15-29-06.jsonl**  476 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-09_18-53-07.jsonl**  509 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-11_00-24-39.jsonl**  453 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-13_18-13-42.jsonl**  389 records
- **.\src\parsers\regions_data\Московская область - Ставропольский край\Московская область - Ставропольский край_2025-10-14_17-24-02.jsonl**  395 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-20_20-39-05.jsonl**  229 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-21_02-43-44.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-24_23-42-08.jsonl**  188 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-25_20-39-35.jsonl**  191 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-26_22-39-07.jsonl**  252 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-27_20-22-11.jsonl**  76 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-30_01-29-14.jsonl**  243 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-09-30_20-10-28.jsonl**  287 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-02_22-22-20.jsonl**  259 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-03_17-56-14.jsonl**  158 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-08_06-01-31.jsonl**  256 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-08_16-08-01.jsonl**  209 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-09_19-29-48.jsonl**  227 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-11_01-00-03.jsonl**  198 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-13_18-47-48.jsonl**  194 records
- **.\src\parsers\regions_data\Московская область - Тамбовская область\Московская область - Тамбовская область_2025-10-14_17-59-58.jsonl**  170 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-20_20-39-35.jsonl**  274 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-21_02-44-14.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-23_07-39-56.jsonl**  302 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-24_23-42-56.jsonl**  220 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-25_20-40-44.jsonl**  258 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-26_22-40-16.jsonl**  231 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-27_20-23-33.jsonl**  67 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-30_01-30-01.jsonl**  371 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-09-30_20-11-20.jsonl**  296 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-02_22-22-57.jsonl**  318 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-03_17-57-06.jsonl**  206 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-08_06-02-14.jsonl**  272 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-08_16-08-49.jsonl**  278 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-09_19-30-34.jsonl**  265 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-11_01-00-47.jsonl**  257 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-13_18-48-36.jsonl**  257 records
- **.\src\parsers\regions_data\Московская область - Тверская область\Московская область - Тверская область_2025-10-14_18-00-43.jsonl**  244 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-20_20-40-27.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-23_07-40-55.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-24_23-43-39.jsonl**  19 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-25_20-41-27.jsonl**  30 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-26_22-41-00.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-27_20-24-11.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-30_01-30-48.jsonl**  28 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-09-30_20-12-03.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-02_22-24-28.jsonl**  42 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-03_17-57-45.jsonl**  46 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-08_06-02-54.jsonl**  45 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-08_16-09-34.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-09_19-31-16.jsonl**  36 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-11_01-01-28.jsonl**  34 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-13_18-49-18.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Томская область\Московская область - Томская область_2025-10-14_18-01-26.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-20_20-41-07.jsonl**  352 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-21_02-45-39.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-23_07-41-36.jsonl**  390 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-24_23-44-27.jsonl**  354 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-25_20-42-27.jsonl**  310 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-26_22-42-01.jsonl**  398 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-27_20-25-13.jsonl**  112 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-30_01-31-42.jsonl**  366 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-09-30_20-12-57.jsonl**  399 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-02_22-25-08.jsonl**  375 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-03_17-58-38.jsonl**  291 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-08_06-03-44.jsonl**  299 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-08_16-10-26.jsonl**  360 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-09_19-32-08.jsonl**  264 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-11_01-02-18.jsonl**  281 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-13_18-50-12.jsonl**  294 records
- **.\src\parsers\regions_data\Московская область - Тульская область\Московская область - Тульская область_2025-10-14_18-02-17.jsonl**  235 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-20_20-41-44.jsonl**  253 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-21_02-46-29.jsonl**  3 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-23_07-42-27.jsonl**  241 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-24_23-45-23.jsonl**  164 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-25_20-43-13.jsonl**  179 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-26_22-42-49.jsonl**  174 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-27_20-26-00.jsonl**  56 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-30_01-32-28.jsonl**  181 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-09-30_20-13-42.jsonl**  237 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-02_22-26-44.jsonl**  353 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-03_17-59-19.jsonl**  191 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-08_06-04-25.jsonl**  173 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-08_16-11-13.jsonl**  187 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-09_19-32-48.jsonl**  201 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-11_01-02-58.jsonl**  204 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-13_18-50-53.jsonl**  141 records
- **.\src\parsers\regions_data\Московская область - Тюменская область\Московская область - Тюменская область_2025-10-14_18-02-57.jsonl**  114 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-20_19-24-24.jsonl**  168 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-21_02-04-37.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-23_06-56-37.jsonl**  148 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-24_22-50-15.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-25_19-43-04.jsonl**  172 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-26_21-44-34.jsonl**  133 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-27_19-31-10.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-30_00-40-37.jsonl**  121 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-09-30_19-20-08.jsonl**  142 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-02_21-08-36.jsonl**  211 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-03_17-02-22.jsonl**  223 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-08_05-17-59.jsonl**  144 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-08_15-17-39.jsonl**  133 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-09_18-43-32.jsonl**  164 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-11_00-13-16.jsonl**  144 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-13_18-03-00.jsonl**  122 records
- **.\src\parsers\regions_data\Московская область - Удмуртская Республика\Московская область - Удмуртская Республика_2025-10-14_17-12-50.jsonl**  145 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-20_20-42-15.jsonl**  105 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-21_02-46-59.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-23_07-43-02.jsonl**  105 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-24_23-46-17.jsonl**  119 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-25_20-44-13.jsonl**  109 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-26_22-43-47.jsonl**  166 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-27_20-26-57.jsonl**  42 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-30_01-33-17.jsonl**  108 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-09-30_20-14-30.jsonl**  190 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-02_22-27-30.jsonl**  169 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-03_18-00-12.jsonl**  112 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-08_06-05-17.jsonl**  136 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-08_16-12-03.jsonl**  102 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-09_19-33-37.jsonl**  100 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-11_01-03-42.jsonl**  123 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-13_18-51-40.jsonl**  93 records
- **.\src\parsers\regions_data\Московская область - Ульяновская область\Московская область - Ульяновская область_2025-10-14_18-03-36.jsonl**  45 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-20_19-45-14.jsonl**  138 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-21_02-14-43.jsonl**  9 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-23_07-07-47.jsonl**  127 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-24_23-04-27.jsonl**  74 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-25_19-59-49.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-26_21-58-19.jsonl**  72 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-27_19-43-13.jsonl**  53 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-30_00-53-35.jsonl**  139 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-09-30_19-32-42.jsonl**  90 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-02_21-27-07.jsonl**  164 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-03_17-17-03.jsonl**  107 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-08_05-28-25.jsonl**  161 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-08_15-30-12.jsonl**  114 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-09_18-54-10.jsonl**  156 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-11_00-25-41.jsonl**  147 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-13_18-14-39.jsonl**  145 records
- **.\src\parsers\regions_data\Московская область - Хабаровский край\Московская область - Хабаровский край_2025-10-14_17-25-01.jsonl**  149 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-20_20-50-22.jsonl**  120 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-21_02-54-44.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-23_07-51-18.jsonl**  134 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-24_23-54-32.jsonl**  78 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-25_20-54-47.jsonl**  91 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-26_22-51-35.jsonl**  87 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-27_20-35-03.jsonl**  57 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-30_01-42-04.jsonl**  82 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-09-30_20-24-32.jsonl**  119 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-02_22-38-57.jsonl**  123 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-03_18-09-01.jsonl**  113 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-08_06-13-07.jsonl**  171 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-08_16-19-56.jsonl**  93 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-09_19-40-30.jsonl**  122 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-11_01-12-10.jsonl**  84 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-13_18-56-06.jsonl**  78 records
- **.\src\parsers\regions_data\Московская область - Ханты-Мансийский автономный округ _ Югра\Московская область - Ханты-Мансийский автономный округ _ Югра_2025-10-14_18-09-39.jsonl**  66 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-20_20-42-41.jsonl**  274 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-21_02-47-55.jsonl**  5 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-23_07-43-42.jsonl**  304 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-24_23-46-49.jsonl**  245 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-25_20-44-44.jsonl**  309 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-26_22-44-36.jsonl**  230 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-27_20-27-30.jsonl**  96 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-30_01-33-47.jsonl**  289 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-09-30_20-15-06.jsonl**  374 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-02_22-28-48.jsonl**  456 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-03_18-00-40.jsonl**  367 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-08_06-05-46.jsonl**  250 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-08_16-12-35.jsonl**  238 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-09_19-34-07.jsonl**  292 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-11_01-04-12.jsonl**  229 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-13_18-52-09.jsonl**  224 records
- **.\src\parsers\regions_data\Московская область - Челябинская область\Московская область - Челябинская область_2025-10-14_18-04-08.jsonl**  203 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-20_19-25-49.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-23_06-58-02.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-24_22-51-42.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-25_19-44-56.jsonl**  47 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-26_21-46-10.jsonl**  59 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-27_19-32-42.jsonl**  20 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-30_00-42-02.jsonl**  42 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-09-30_19-21-36.jsonl**  66 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-02_21-10-39.jsonl**  54 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-03_17-03-59.jsonl**  48 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-08_05-19-22.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-08_15-19-07.jsonl**  25 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-09_18-45-00.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-11_00-14-44.jsonl**  28 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-13_18-04-19.jsonl**  12 records
- **.\src\parsers\regions_data\Московская область - Чеченская Республика\Московская область - Чеченская Республика_2025-10-14_17-14-20.jsonl**  22 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-20_19-26-31.jsonl**  94 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-21_02-06-43.jsonl**  2 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-23_06-58-45.jsonl**  95 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-24_22-52-24.jsonl**  109 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-25_19-45-38.jsonl**  111 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-26_21-47-09.jsonl**  100 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-27_19-33-40.jsonl**  26 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-30_00-42-55.jsonl**  112 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-09-30_19-22-28.jsonl**  165 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-02_21-11-20.jsonl**  90 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-03_17-04-52.jsonl**  78 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-08_05-20-11.jsonl**  113 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-08_15-20-34.jsonl**  73 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-11_00-15-34.jsonl**  126 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-13_18-05-09.jsonl**  101 records
- **.\src\parsers\regions_data\Московская область - Чувашская Республика\Московская область - Чувашская Республика_2025-10-14_17-15-10.jsonl**  82 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-20_20-51-05.jsonl**  37 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-23_07-52-27.jsonl**  70 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-24_23-55-20.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-25_20-56-11.jsonl**  43 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-26_22-52-22.jsonl**  35 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-27_20-35-50.jsonl**  7 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-30_01-43-12.jsonl**  27 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-09-30_20-25-37.jsonl**  31 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-02_22-41-12.jsonl**  53 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-03_18-09-50.jsonl**  42 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-08_06-14-08.jsonl**  43 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-08_16-20-45.jsonl**  38 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-09_19-41-18.jsonl**  24 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-11_01-13-12.jsonl**  36 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-13_18-56-53.jsonl**  32 records
- **.\src\parsers\regions_data\Московская область - Ямало-Ненецкий автономный округ\Московская область - Ямало-Ненецкий автономный округ_2025-10-14_18-10-26.jsonl**  39 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-20_20-43-24.jsonl**  474 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-21_02-48-26.jsonl**  17 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-23_07-44-28.jsonl**  512 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-24_23-47-50.jsonl**  400 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-25_20-45-50.jsonl**  455 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-26_22-45-32.jsonl**  441 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-27_20-28-31.jsonl**  198 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-30_01-34-35.jsonl**  420 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-09-30_20-16-02.jsonl**  505 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-02_22-29-47.jsonl**  576 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-03_18-01-48.jsonl**  455 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-08_06-06-26.jsonl**  392 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-08_16-13-22.jsonl**  423 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-09_19-34-55.jsonl**  389 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-11_01-04-57.jsonl**  315 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-13_18-52-56.jsonl**  369 records
- **.\src\parsers\regions_data\Московская область - Ярославская область\Московская область - Ярославская область_2025-10-14_18-04-52.jsonl**  311 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-20_15-45-26.jsonl**  172 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-20_23-51-53.jsonl**  9 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-23_04-28-53.jsonl**  155 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-24_19-47-55.jsonl**  156 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-26_18-33-35.jsonl**  158 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-27_16-38-28.jsonl**  35 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-29_18-32-12.jsonl**  144 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-09-30_15-48-13.jsonl**  155 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-01_19-42-45.jsonl**  163 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-02_17-48-35.jsonl**  121 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-03_13-29-38.jsonl**  116 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-08_02-43-06.jsonl**  199 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-08_12-13-04.jsonl**  140 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-09_15-45-26.jsonl**  228 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-10_21-40-04.jsonl**  140 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-13_15-36-03.jsonl**  205 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-14_14-39-54.jsonl**  215 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-15_22-51-46.jsonl**  218 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-16_17-49-49.jsonl**  194 records
- **.\src\parsers\regions_data\Мурманская область\Мурманская область_2025-10-19_18-58-41.jsonl**  149 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-09-20_19-06-44.jsonl**  3 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-09-23_06-35-56.jsonl**  2 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-09-24_22-27-37.jsonl**  5 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-09-25_19-18-52.jsonl**  2 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-09-26_21-22-57.jsonl**  1 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-09-30_19-00-00.jsonl**  4 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-02_20-34-46.jsonl**  4 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-03_16-41-04.jsonl**  2 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-08_04-59-07.jsonl**  2 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-08_14-56-37.jsonl**  1 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-09_18-23-40.jsonl**  1 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-13_17-43-47.jsonl**  2 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-14_16-53-11.jsonl**  2 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-16_01-07-52.jsonl**  1 records
- **.\src\parsers\regions_data\Ненецкий автономный округ\Ненецкий автономный округ_2025-10-16_20-13-17.jsonl**  3 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-20_15-45-51.jsonl**  495 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-20_16-06-57.jsonl**  4466 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-20_23-52-18.jsonl**  395 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-23_04-29-21.jsonl**  5404 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-24_19-48-24.jsonl**  6577 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-25_16-37-50.jsonl**  5834 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-26_18-34-19.jsonl**  5758 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-27_16-38-58.jsonl**  1623 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-29_18-32-48.jsonl**  6065 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-09-30_15-48-47.jsonl**  6378 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-01_19-43-17.jsonl**  4924 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-02_17-49-10.jsonl**  5613 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-03_13-30-13.jsonl**  4856 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-08_02-43-38.jsonl**  6106 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-08_12-13-38.jsonl**  4691 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-09_15-46-12.jsonl**  5791 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-10_21-40-40.jsonl**  5134 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-13_15-36-36.jsonl**  5025 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-14_14-40-32.jsonl**  4914 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-15_22-52-33.jsonl**  5799 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-16_17-50-32.jsonl**  5198 records
- **.\src\parsers\regions_data\Нижегородская область\Нижегородская область_2025-10-19_18-59-25.jsonl**  3906 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-20_16-16-02.jsonl**  488 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-21_00-01-43.jsonl**  9 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-23_04-38-38.jsonl**  438 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-24_20-00-19.jsonl**  561 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-25_16-51-21.jsonl**  482 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-26_18-48-15.jsonl**  462 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-27_16-50-17.jsonl**  147 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-29_18-46-12.jsonl**  468 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-09-30_16-02-39.jsonl**  479 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-02_13-11-58.jsonl**  52 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-02_18-06-19.jsonl**  660 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-03_13-43-08.jsonl**  579 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-08_02-53-45.jsonl**  443 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-08_12-26-16.jsonl**  394 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-09_15-58-03.jsonl**  410 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-10_21-54-05.jsonl**  381 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-13_15-47-14.jsonl**  333 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-14_14-51-17.jsonl**  324 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-15_23-03-55.jsonl**  444 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-16_18-02-09.jsonl**  506 records
- **.\src\parsers\regions_data\Новгородская область\Новгородская область_2025-10-19_19-07-29.jsonl**  304 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-20_16-17-23.jsonl**  3895 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-21_00-02-45.jsonl**  104 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-23_04-39-33.jsonl**  3973 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-24_20-01-21.jsonl**  3878 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-25_16-52-25.jsonl**  3579 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-26_18-49-20.jsonl**  3065 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-27_16-51-13.jsonl**  959 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-29_18-47-09.jsonl**  3008 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-09-30_16-03-41.jsonl**  3796 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-02_18-07-34.jsonl**  3680 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-03_13-44-25.jsonl**  813 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-08_02-54-54.jsonl**  3476 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-08_12-27-20.jsonl**  2531 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-09_15-59-05.jsonl**  3211 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-10_21-55-34.jsonl**  2436 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-13_15-47-57.jsonl**  2797 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-14_14-52-13.jsonl**  2383 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-15_23-05-01.jsonl**  2823 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-16_18-03-24.jsonl**  2164 records
- **.\src\parsers\regions_data\Новосибирская область\Новосибирская область_2025-10-19_19-08-20.jsonl**  2073 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-20_16-24-37.jsonl**  1947 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-21_00-10-08.jsonl**  78 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-23_04-46-22.jsonl**  1976 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-24_20-09-42.jsonl**  2087 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-25_17-01-37.jsonl**  1624 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-26_18-59-31.jsonl**  1577 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-27_16-59-03.jsonl**  615 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-29_18-55-14.jsonl**  1661 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-09-30_16-12-32.jsonl**  2068 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-02_18-19-04.jsonl**  1845 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-03_14-06-44.jsonl**  1588 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-08_03-00-47.jsonl**  1735 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-08_12-35-05.jsonl**  1406 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-09_16-07-11.jsonl**  1468 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-10_22-03-09.jsonl**  1437 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-13_15-54-58.jsonl**  1703 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-14_14-59-08.jsonl**  1420 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-15_23-11-04.jsonl**  514 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-16_18-09-30.jsonl**  573 records
- **.\src\parsers\regions_data\Омская область\Омская область_2025-10-19_19-13-33.jsonl**  1713 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-20_16-28-32.jsonl**  1192 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-21_00-14-23.jsonl**  35 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-23_04-49-48.jsonl**  1118 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-24_20-13-44.jsonl**  1299 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-25_17-05-35.jsonl**  1117 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-26_19-03-58.jsonl**  1089 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-27_17-02-51.jsonl**  442 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-29_18-59-06.jsonl**  965 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-09-30_16-16-50.jsonl**  805 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-02_18-24-20.jsonl**  1084 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-03_14-11-00.jsonl**  815 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-08_03-03-35.jsonl**  682 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-08_12-38-53.jsonl**  732 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-09_16-10-43.jsonl**  814 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-10_22-07-14.jsonl**  605 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-13_15-58-41.jsonl**  600 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-14_15-02-50.jsonl**  551 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-15_23-32-27.jsonl**  796 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-16_18-31-03.jsonl**  697 records
- **.\src\parsers\regions_data\Оренбургская область\Оренбургская область_2025-10-19_19-16-49.jsonl**  515 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-20_16-30-47.jsonl**  949 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-21_00-16-44.jsonl**  17 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-23_04-52-04.jsonl**  1013 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-24_20-16-29.jsonl**  1066 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-25_17-08-22.jsonl**  1128 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-26_19-07-13.jsonl**  863 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-27_17-05-37.jsonl**  199 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-29_19-01-36.jsonl**  718 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-09-30_16-38-39.jsonl**  860 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-02_18-27-57.jsonl**  1199 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-03_14-13-41.jsonl**  814 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-08_03-25-03.jsonl**  983 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-08_12-41-05.jsonl**  811 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-09_16-12-56.jsonl**  1117 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-10_22-09-21.jsonl**  912 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-13_16-00-09.jsonl**  822 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-14_15-04-17.jsonl**  845 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-15_23-34-22.jsonl**  1022 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-16_18-32-59.jsonl**  908 records
- **.\src\parsers\regions_data\Орловская область\Орловская область_2025-10-19_19-18-02.jsonl**  606 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-20_16-32-55.jsonl**  2332 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-21_00-18-45.jsonl**  83 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-23_04-54-03.jsonl**  2525 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-24_20-18-35.jsonl**  2916 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-25_17-10-47.jsonl**  2359 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-26_19-09-29.jsonl**  1958 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-27_17-07-50.jsonl**  547 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-29_19-03-40.jsonl**  2120 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-09-30_16-40-49.jsonl**  2171 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-02_18-30-56.jsonl**  2227 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-03_14-16-03.jsonl**  2098 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-08_03-26-57.jsonl**  2320 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-08_12-43-24.jsonl**  1798 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-09_16-15-15.jsonl**  2209 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-10_22-11-42.jsonl**  1955 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-13_16-02-14.jsonl**  1764 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-14_15-06-22.jsonl**  1738 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-15_23-36-39.jsonl**  1751 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-16_18-35-30.jsonl**  1565 records
- **.\src\parsers\regions_data\Пензенская область\Пензенская область_2025-10-19_19-19-39.jsonl**  1417 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-09_15-17-43.jsonl**  1813 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-20_04-28-51.jsonl**  3249 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-20_13-10-32.jsonl**  658 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-20_22-34-46.jsonl**  117 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-21_19-10-56.jsonl**  489 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-21_19-33-05.jsonl**  133 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-21_22-04-16.jsonl**  1922 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-22_00-45-24.jsonl**  830 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-22_05-50-06.jsonl**  1895 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-22_22-03-29.jsonl**  2719 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-23_02-45-14.jsonl**  55 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-24_12-18-21.jsonl**  3850 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-24_17-47-51.jsonl**  1885 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-25_12-59-03.jsonl**  3383 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-25_14-51-50.jsonl**  871 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-26_16-12-20.jsonl**  3581 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-27_14-45-20.jsonl**  1117 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-29_16-33-42.jsonl**  3975 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-09-30_14-05-05.jsonl**  3590 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-01_18-08-58.jsonl**  3719 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-02_15-14-40.jsonl**  3589 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-03_11-13-47.jsonl**  3225 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-08_01-15-38.jsonl**  3313 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-08_10-49-37.jsonl**  2454 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-09_14-05-59.jsonl**  3149 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-10_18-24-27.jsonl**  2605 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-13_14-01-16.jsonl**  2366 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-14_12-27-39.jsonl**  2334 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-15_20-23-33.jsonl**  2663 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-16_15-36-42.jsonl**  2417 records
- **.\src\parsers\regions_data\Пермский край\Пермский край_2025-10-19_17-02-48.jsonl**  1761 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-09_15-27-55.jsonl**  1982 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-20_04-34-23.jsonl**  2815 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-20_13-16-14.jsonl**  546 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-20_22-41-20.jsonl**  126 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-21_19-38-41.jsonl**  539 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-21_22-10-05.jsonl**  2162 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-22_00-53-59.jsonl**  2892 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-22_05-56-10.jsonl**  260 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-22_22-09-46.jsonl**  1646 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-23_03-06-45.jsonl**  143 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-24_12-25-51.jsonl**  2110 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-24_17-55-01.jsonl**  546 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-25_13-07-02.jsonl**  1462 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-25_15-00-25.jsonl**  167 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-26_16-20-25.jsonl**  1474 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-27_14-52-55.jsonl**  622 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-29_16-41-48.jsonl**  2210 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-09-30_14-13-48.jsonl**  1810 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-01_18-16-31.jsonl**  2221 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-02_15-25-59.jsonl**  2315 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-03_11-22-28.jsonl**  2108 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-08_01-21-26.jsonl**  3420 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-08_10-56-33.jsonl**  2337 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-09_14-12-52.jsonl**  3221 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-10_18-31-01.jsonl**  3052 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-13_14-06-48.jsonl**  3106 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-14_12-33-38.jsonl**  2974 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-15_20-29-12.jsonl**  4170 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-16_15-42-21.jsonl**  3234 records
- **.\src\parsers\regions_data\Приморский край\Приморский край_2025-10-19_17-08-15.jsonl**  3088 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-20_16-37-33.jsonl**  347 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-21_00-23-14.jsonl**  21 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-23_04-58-23.jsonl**  358 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-24_20-24-17.jsonl**  446 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-25_17-16-32.jsonl**  316 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-26_19-15-04.jsonl**  348 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-27_17-12-26.jsonl**  89 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-29_19-10-14.jsonl**  362 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-09-30_16-45-37.jsonl**  393 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-02_18-37-38.jsonl**  381 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-03_14-21-36.jsonl**  329 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-08_03-31-00.jsonl**  360 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-08_12-48-44.jsonl**  267 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-09_16-20-24.jsonl**  369 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-10_22-16-59.jsonl**  293 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-13_16-06-12.jsonl**  288 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-14_15-10-37.jsonl**  335 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-15_23-40-31.jsonl**  348 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-16_18-39-22.jsonl**  296 records
- **.\src\parsers\regions_data\Псковская область\Псковская область_2025-10-19_19-22-30.jsonl**  243 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-08_16-45-42.jsonl**  370 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-08_18-26-37.jsonl**  43 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-09_11-52-35.jsonl**  205 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-09_13-23-31.jsonl**  81 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-09_16-23-20.jsonl**  72 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-16_10-20-20.jsonl**  322 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-17_13-33-05.jsonl**  300 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-17_15-48-44.jsonl**  99 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-17_16-16-26.jsonl**  28 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-19_22-14-34.jsonl**  500 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-20_00-50-16.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-20_10-52-23.jsonl**  76 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-20_10-57-55.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-20_11-27-49.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-20_21-26-05.jsonl**  48 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-21_18-05-09.jsonl**  106 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-21_20-53-55.jsonl**  170 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-21_23-35-51.jsonl**  402 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-22_04-54-26.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-22_17-35-34.jsonl**  341 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-23_01-45-35.jsonl**  66 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-23_12-52-00.jsonl**  301 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-24_11-15-38.jsonl**  315 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-24_16-33-42.jsonl**  336 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-25_11-44-45.jsonl**  332 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-25_13-38-02.jsonl**  138 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-26_14-59-07.jsonl**  469 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-27_12-57-51.jsonl**  202 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-29_15-03-51.jsonl**  367 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-09-30_12-58-26.jsonl**  396 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-01_16-41-24.jsonl**  438 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-02_13-40-46.jsonl**  392 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-03_09-49-59.jsonl**  308 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-08_00-16-49.jsonl**  346 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-08_09-49-04.jsonl**  157 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-09_12-43-20.jsonl**  448 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-10_17-24-28.jsonl**  416 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-13_13-05-15.jsonl**  291 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-14_11-27-12.jsonl**  334 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-15_19-21-40.jsonl**  357 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-16_14-30-18.jsonl**  332 records
- **.\src\parsers\regions_data\Республика Адыгея\Республика Адыгея_2025-10-19_16-13-09.jsonl**  261 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-08_16-47-28.jsonl**  34 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-08_18-28-03.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-09_11-54-24.jsonl**  20 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-09_16-24-51.jsonl**  8 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-19_22-15-17.jsonl**  27 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-20_00-51-00.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-20_10-52-54.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-21_18-05-40.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-21_20-19-59.jsonl**  33 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-21_20-54-50.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-21_23-36-45.jsonl**  25 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-22_04-54-58.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-22_17-36-11.jsonl**  21 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-23_12-52-39.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-24_11-16-14.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-24_16-34-26.jsonl**  12 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-25_11-45-34.jsonl**  16 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-25_13-38-46.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-26_14-59-52.jsonl**  20 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-27_12-58-30.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-29_15-04-30.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-09-30_12-59-11.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-01_16-42-10.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-02_13-41-32.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-03_09-51-01.jsonl**  23 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-08_00-17-25.jsonl**  26 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-08_09-49-37.jsonl**  12 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-09_12-44-07.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-10_17-25-14.jsonl**  22 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-13_13-05-49.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-14_11-27-53.jsonl**  22 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-15_19-22-15.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-16_14-30-56.jsonl**  12 records
- **.\src\parsers\regions_data\Республика Алтай\Республика Алтай_2025-10-19_16-13-39.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-08_16-48-06.jsonl**  1566 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-08_18-28-41.jsonl**  404 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-09_11-55-00.jsonl**  1486 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-09_13-25-55.jsonl**  885 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-09_16-25-27.jsonl**  611 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-16_10-21-51.jsonl**  311 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-17_13-36-10.jsonl**  378 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-17_15-13-21.jsonl**  337 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-17_16-19-28.jsonl**  283 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-19_22-15-39.jsonl**  5570 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-20_00-51-22.jsonl**  95 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-20_01-48-50.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-20_02-51-12.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-20_10-53-22.jsonl**  862 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-20_11-28-48.jsonl**  108 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-20_21-27-22.jsonl**  475 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-21_18-06-29.jsonl**  1173 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-21_20-20-29.jsonl**  754 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-21_20-55-47.jsonl**  1968 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-21_23-37-37.jsonl**  4735 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-22_04-55-51.jsonl**  175 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-22_17-37-05.jsonl**  4362 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-22_20-38-40.jsonl**  160 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-23_01-46-48.jsonl**  162 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-23_12-53-17.jsonl**  4311 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-24_11-16-51.jsonl**  854 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-24_16-35-06.jsonl**  5529 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-25_11-46-13.jsonl**  4836 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-25_13-39-26.jsonl**  1243 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-26_15-00-35.jsonl**  5718 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-27_12-59-10.jsonl**  2253 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-29_15-05-19.jsonl**  5336 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-09-30_12-59-50.jsonl**  4444 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-01_16-42-49.jsonl**  4424 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-02_13-42-09.jsonl**  3756 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-03_09-51-39.jsonl**  3200 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-08_00-18-01.jsonl**  4334 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-08_09-50-15.jsonl**  2363 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-09_12-44-49.jsonl**  3758 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-10_17-25-51.jsonl**  2927 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-13_13-06-28.jsonl**  2755 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-14_11-28-31.jsonl**  2915 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-15_19-22-58.jsonl**  3825 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-16_14-31-33.jsonl**  3330 records
- **.\src\parsers\regions_data\Республика Башкортостан\Республика Башкортостан_2025-10-19_16-14-19.jsonl**  2747 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-08_17-07-59.jsonl**  330 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-09_13-35-30.jsonl**  215 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-09_16-46-00.jsonl**  25 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-19_22-26-12.jsonl**  338 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-20_01-01-05.jsonl**  8 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-20_01-59-42.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-20_02-59-25.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-20_11-37-34.jsonl**  72 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-20_21-36-54.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-21_18-14-47.jsonl**  58 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-21_21-04-14.jsonl**  243 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-21_23-45-24.jsonl**  296 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-22_05-03-06.jsonl**  69 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-22_17-46-33.jsonl**  154 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-22_20-47-56.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-23_01-55-17.jsonl**  6 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-23_13-03-44.jsonl**  211 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-24_11-19-36.jsonl**  204 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-24_16-46-59.jsonl**  72 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-25_11-58-24.jsonl**  200 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-25_13-51-17.jsonl**  36 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-26_15-13-10.jsonl**  215 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-27_13-10-11.jsonl**  80 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-29_15-16-58.jsonl**  292 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-09-30_13-09-53.jsonl**  266 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-01_16-52-14.jsonl**  274 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-02_13-51-12.jsonl**  248 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-03_10-00-16.jsonl**  219 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-08_00-25-12.jsonl**  318 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-08_09-57-56.jsonl**  204 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-09_12-52-58.jsonl**  312 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-10_17-32-44.jsonl**  282 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-13_13-12-55.jsonl**  248 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-14_11-36-19.jsonl**  290 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-15_19-30-15.jsonl**  401 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-16_14-39-55.jsonl**  369 records
- **.\src\parsers\regions_data\Республика Бурятия\Республика Бурятия_2025-10-19_16-19-57.jsonl**  337 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-08_17-09-30.jsonl**  120 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-09_13-37-04.jsonl**  65 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-09_16-47-35.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-19_22-26-42.jsonl**  83 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-20_01-01-35.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-20_11-38-04.jsonl**  16 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-20_21-37-44.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-21_18-15-46.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-21_21-06-44.jsonl**  37 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-21_23-46-06.jsonl**  80 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-22_05-03-51.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-22_17-47-41.jsonl**  81 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-22_20-48-41.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-23_13-04-29.jsonl**  79 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-24_11-20-19.jsonl**  71 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-24_16-47-43.jsonl**  33 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-25_11-59-10.jsonl**  63 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-25_13-52-02.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-26_15-14-00.jsonl**  75 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-27_13-11-02.jsonl**  46 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-29_15-17-48.jsonl**  103 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-09-30_13-10-42.jsonl**  65 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-01_16-53-21.jsonl**  69 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-02_13-51-57.jsonl**  70 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-03_10-01-07.jsonl**  47 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-08_00-25-55.jsonl**  110 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-08_09-58-38.jsonl**  39 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-09_12-53-44.jsonl**  57 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-10_17-33-35.jsonl**  68 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-13_13-13-40.jsonl**  52 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-14_11-37-11.jsonl**  64 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-15_19-31-06.jsonl**  70 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-16_14-40-59.jsonl**  55 records
- **.\src\parsers\regions_data\Республика Дагестан\Республика Дагестан_2025-10-19_16-20-46.jsonl**  90 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-08_17-10-46.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-09_13-38-23.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-09_16-48-52.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-19_22-27-32.jsonl**  8 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-20_11-38-53.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-20_21-38-20.jsonl**  6 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-21_18-16-21.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-21_21-07-51.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-21_23-46-51.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-22_17-48-06.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-22_20-49-15.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-23_13-04-54.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-24_11-20-43.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-24_16-48-18.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-25_11-59-45.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-25_13-52-37.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-26_15-14-25.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-27_13-11-39.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-29_15-18-12.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-09-30_13-11-06.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-01_16-53-46.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-02_13-52-22.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-03_10-01-32.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-08_00-26-20.jsonl**  8 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-08_09-59-03.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-09_12-54-19.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-10_17-34-11.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-13_13-14-16.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-14_11-37-48.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-15_19-31-42.jsonl**  6 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-16_14-41-35.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Ингушетия\Республика Ингушетия_2025-10-19_16-21-10.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-08_17-12-45.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-09_13-40-26.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-09_16-50-58.jsonl**  6 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-19_22-28-29.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-20_11-39-49.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-21_18-18-02.jsonl**  6 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-21_21-09-18.jsonl**  8 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-21_23-48-30.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-22_17-49-39.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-22_20-50-31.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-23_13-06-14.jsonl**  19 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-24_11-22-14.jsonl**  17 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-24_16-49-50.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-25_12-01-04.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-25_13-53-54.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-26_15-15-47.jsonl**  24 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-27_13-12-56.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-29_15-19-27.jsonl**  21 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-09-30_13-12-23.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-01_16-55-15.jsonl**  7 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-02_13-53-38.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-03_10-02-43.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-08_00-27-48.jsonl**  16 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-08_10-00-24.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-09_12-55-40.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-10_17-35-28.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-13_13-15-43.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-14_11-39-19.jsonl**  24 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-15_19-33-06.jsonl**  19 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-16_14-42-56.jsonl**  12 records
- **.\src\parsers\regions_data\Республика Калмыкия\Республика Калмыкия_2025-10-19_16-22-32.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-08_17-14-35.jsonl**  276 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-09_13-42-36.jsonl**  203 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-09_16-53-11.jsonl**  76 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-19_22-29-33.jsonl**  426 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-20_01-04-21.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-20_11-40-51.jsonl**  52 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-20_21-41-00.jsonl**  42 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-21_18-19-29.jsonl**  78 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-21_21-10-45.jsonl**  258 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-21_23-49-57.jsonl**  368 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-22_05-07-37.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-22_17-51-11.jsonl**  305 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-22_20-51-54.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-23_01-59-05.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-23_13-07-29.jsonl**  287 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-24_11-23-30.jsonl**  298 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-24_16-51-09.jsonl**  162 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-25_12-02-22.jsonl**  264 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-25_13-55-09.jsonl**  65 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-26_15-17-13.jsonl**  275 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-27_13-14-16.jsonl**  112 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-29_15-20-42.jsonl**  294 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-09-30_13-13-38.jsonl**  96 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-01_16-57-51.jsonl**  369 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-02_13-54-51.jsonl**  321 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-03_10-03-57.jsonl**  274 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-08_00-29-02.jsonl**  342 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-08_10-01-38.jsonl**  176 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-09_12-56-58.jsonl**  380 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-10_17-36-46.jsonl**  304 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-13_13-17-05.jsonl**  288 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-14_11-40-39.jsonl**  293 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-15_19-34-26.jsonl**  455 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-16_14-44-17.jsonl**  426 records
- **.\src\parsers\regions_data\Республика Карелия\Республика Карелия_2025-10-19_16-23-46.jsonl**  357 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-08_17-16-24.jsonl**  455 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-09_13-44-49.jsonl**  303 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-09_16-55-29.jsonl**  81 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-19_22-30-23.jsonl**  802 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-20_01-05-08.jsonl**  12 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-20_02-05-00.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-20_11-42-04.jsonl**  79 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-20_21-41-57.jsonl**  42 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-21_18-20-21.jsonl**  99 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-21_21-11-15.jsonl**  481 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-21_23-50-42.jsonl**  612 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-22_00-00-37.jsonl**  27 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-22_05-08-24.jsonl**  37 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-22_17-52-01.jsonl**  463 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-22_20-52-42.jsonl**  19 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-23_01-59-49.jsonl**  20 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-23_13-08-18.jsonl**  498 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-24_11-24-23.jsonl**  606 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-24_16-52-00.jsonl**  299 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-25_12-03-13.jsonl**  518 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-25_13-55-59.jsonl**  65 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-26_15-18-15.jsonl**  575 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-27_13-15-07.jsonl**  171 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-29_15-21-31.jsonl**  527 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-09-30_13-14-21.jsonl**  520 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-01_16-58-54.jsonl**  467 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-02_13-55-38.jsonl**  444 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-03_10-04-48.jsonl**  287 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-08_00-29-45.jsonl**  791 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-08_10-02-23.jsonl**  437 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-09_12-57-45.jsonl**  728 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-10_17-37-34.jsonl**  766 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-13_13-17-52.jsonl**  659 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-14_11-41-29.jsonl**  631 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-15_19-35-32.jsonl**  799 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-16_14-45-31.jsonl**  827 records
- **.\src\parsers\regions_data\Республика Коми\Республика Коми_2025-10-19_16-24-34.jsonl**  642 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-08_17-17-50.jsonl**  274 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-09_13-46-21.jsonl**  187 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-09_16-57-05.jsonl**  81 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-19_22-31-38.jsonl**  358 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-20_01-06-23.jsonl**  7 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-20_11-43-12.jsonl**  47 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-20_21-43-06.jsonl**  31 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-21_18-21-22.jsonl**  45 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-21_21-12-42.jsonl**  128 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-22_00-01-33.jsonl**  324 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-22_05-09-20.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-22_17-53-09.jsonl**  249 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-22_20-53-48.jsonl**  16 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-23_02-00-52.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-23_13-09-29.jsonl**  277 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-24_11-25-39.jsonl**  318 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-24_16-53-18.jsonl**  218 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-25_12-04-33.jsonl**  280 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-25_13-57-18.jsonl**  89 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-26_15-19-33.jsonl**  290 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-27_13-16-12.jsonl**  109 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-29_15-22-33.jsonl**  233 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-09-30_13-15-49.jsonl**  199 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-01_17-00-21.jsonl**  254 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-02_13-56-39.jsonl**  233 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-03_10-05-49.jsonl**  180 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-08_00-31-03.jsonl**  286 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-08_10-03-36.jsonl**  173 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-09_12-59-03.jsonl**  356 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-10_17-39-22.jsonl**  258 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-13_13-19-14.jsonl**  318 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-14_11-42-55.jsonl**  315 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-15_19-37-24.jsonl**  351 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-16_14-47-28.jsonl**  370 records
- **.\src\parsers\regions_data\Республика Крым\Республика Крым_2025-10-19_16-25-48.jsonl**  256 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-08_17-21-21.jsonl**  367 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-09_13-48-11.jsonl**  310 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-09_16-59-00.jsonl**  182 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-19_22-32-15.jsonl**  488 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-20_01-06-59.jsonl**  115 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-20_02-06-51.jsonl**  129 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-20_03-05-06.jsonl**  2 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-20_11-43-49.jsonl**  156 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-20_12-05-26.jsonl**  68 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-20_21-44-02.jsonl**  74 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-21_18-22-23.jsonl**  171 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-21_21-13-13.jsonl**  479 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-22_00-02-19.jsonl**  739 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-22_05-10-11.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-22_17-54-16.jsonl**  890 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-22_20-54-38.jsonl**  32 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-23_02-01-41.jsonl**  20 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-23_13-10-24.jsonl**  664 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-24_11-26-34.jsonl**  740 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-24_16-54-13.jsonl**  517 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-25_12-05-28.jsonl**  670 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-25_13-58-24.jsonl**  169 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-26_15-20-34.jsonl**  683 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-27_13-17-04.jsonl**  336 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-29_15-23-32.jsonl**  823 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-09-30_13-16-46.jsonl**  832 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-01_17-02-20.jsonl**  742 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-02_13-57-23.jsonl**  680 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-03_10-06-29.jsonl**  544 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-08_00-31-50.jsonl**  609 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-08_10-04-22.jsonl**  454 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-09_12-59-55.jsonl**  627 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-10_17-40-09.jsonl**  599 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-13_13-20-03.jsonl**  525 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-14_11-43-46.jsonl**  545 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-15_19-38-34.jsonl**  535 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-16_14-48-33.jsonl**  497 records
- **.\src\parsers\regions_data\Республика Марий Эл\Республика Марий Эл_2025-10-19_16-26-28.jsonl**  430 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-20_02-09-20.jsonl**  1278 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-20_12-06-04.jsonl**  141 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-20_21-45-19.jsonl**  57 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-21_18-23-34.jsonl**  182 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-21_21-14-47.jsonl**  772 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-22_00-03-25.jsonl**  1345 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-22_05-11-16.jsonl**  25 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-22_17-56-19.jsonl**  1086 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-22_20-56-39.jsonl**  35 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-23_02-04-28.jsonl**  24 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-23_13-12-32.jsonl**  1172 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-24_11-28-38.jsonl**  766 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-24_16-56-05.jsonl**  1099 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-25_12-07-25.jsonl**  1152 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-25_14-00-22.jsonl**  342 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-26_15-22-31.jsonl**  1214 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-27_13-18-25.jsonl**  280 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-29_15-25-27.jsonl**  1119 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-09-30_13-18-51.jsonl**  1066 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-01_17-04-14.jsonl**  1134 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-02_13-59-11.jsonl**  953 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-03_10-07-47.jsonl**  741 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-08_00-33-02.jsonl**  1327 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-08_10-05-34.jsonl**  737 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-09_13-01-06.jsonl**  1166 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-10_17-41-20.jsonl**  1158 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-13_13-21-26.jsonl**  935 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-14_11-45-02.jsonl**  782 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-15_19-39-38.jsonl**  1146 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-16_14-49-39.jsonl**  905 records
- **.\src\parsers\regions_data\Республика Мордовия\Республика Мордовия_2025-10-19_16-27-23.jsonl**  748 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-09_14-19-55.jsonl**  200 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-20_02-12-13.jsonl**  203 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-20_12-08-35.jsonl**  19 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-20_21-48-36.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-21_18-26-38.jsonl**  42 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-21_21-17-19.jsonl**  105 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-22_00-06-03.jsonl**  204 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-22_05-13-47.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-22_17-59-09.jsonl**  110 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-22_20-59-33.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-23_02-07-17.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-23_13-15-41.jsonl**  106 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-24_11-31-17.jsonl**  116 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-24_16-59-17.jsonl**  49 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-25_12-10-26.jsonl**  87 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-25_14-03-27.jsonl**  42 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-26_15-25-43.jsonl**  127 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-27_13-40-17.jsonl**  50 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-29_15-28-09.jsonl**  155 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-09-30_13-21-31.jsonl**  128 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-01_17-06-46.jsonl**  31 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-02_14-01-44.jsonl**  151 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-03_10-10-15.jsonl**  113 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-08_00-35-34.jsonl**  82 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-08_10-08-24.jsonl**  124 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-09_13-04-00.jsonl**  136 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-10_17-44-08.jsonl**  107 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-13_13-23-54.jsonl**  39 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-14_11-47-27.jsonl**  25 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-15_19-42-10.jsonl**  176 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-16_14-52-08.jsonl**  124 records
- **.\src\parsers\regions_data\Республика Саха _Якутия_\Республика Саха _Якутия__2025-10-19_16-29-34.jsonl**  111 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-09_14-21-48.jsonl**  95 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-20_02-13-44.jsonl**  77 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-20_12-09-39.jsonl**  29 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-20_21-49-09.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-21_18-27-29.jsonl**  21 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-21_21-18-41.jsonl**  60 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-22_00-07-02.jsonl**  88 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-22_05-14-20.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-22_17-59-40.jsonl**  87 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-22_21-00-05.jsonl**  7 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-23_02-07-47.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-23_13-16-15.jsonl**  86 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-24_11-31-51.jsonl**  112 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-24_17-00-03.jsonl**  54 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-25_12-11-08.jsonl**  66 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-25_14-04-03.jsonl**  22 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-26_15-26-30.jsonl**  59 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-27_13-40-50.jsonl**  27 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-29_15-28-42.jsonl**  63 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-09-30_13-22-04.jsonl**  66 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-01_17-07-20.jsonl**  70 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-02_14-02-21.jsonl**  49 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-03_10-10-52.jsonl**  35 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-08_00-36-08.jsonl**  124 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-08_10-08-55.jsonl**  40 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-09_13-04-45.jsonl**  92 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-10_17-44-39.jsonl**  99 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-13_13-24-26.jsonl**  86 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-14_11-47-59.jsonl**  109 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-15_19-42-55.jsonl**  74 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-16_14-52-40.jsonl**  62 records
- **.\src\parsers\regions_data\Республика Северная Осетия-Алания\Республика Северная Осетия-Алания_2025-10-19_16-30-06.jsonl**  50 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-09_14-22-56.jsonl**  1600 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-20_02-14-23.jsonl**  3527 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-20_03-30-37.jsonl**  5672 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-20_12-10-03.jsonl**  1478 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-20_21-50-04.jsonl**  766 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-21_18-28-32.jsonl**  1861 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-21_21-19-30.jsonl**  4960 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-22_00-08-09.jsonl**  8910 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-22_05-15-23.jsonl**  461 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-22_18-00-19.jsonl**  7719 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-22_21-00-46.jsonl**  486 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-23_02-08-24.jsonl**  303 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-23_13-16-56.jsonl**  6939 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-24_11-32-28.jsonl**  7749 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-24_17-00-43.jsonl**  6116 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-25_12-11-45.jsonl**  7094 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-25_14-04-52.jsonl**  2582 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-26_15-27-23.jsonl**  8460 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-27_13-41-41.jsonl**  4400 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-29_15-29-31.jsonl**  8756 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-09-30_13-22-54.jsonl**  8026 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-01_17-08-07.jsonl**  8458 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-02_14-03-09.jsonl**  7889 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-03_10-11-39.jsonl**  6257 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-08_10-09-30.jsonl**  4400 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-09_13-05-22.jsonl**  7282 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-10_17-45-16.jsonl**  6950 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-13_13-25-03.jsonl**  5758 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-14_11-48-39.jsonl**  6465 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-15_19-43-30.jsonl**  8132 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-16_14-53-30.jsonl**  6092 records
- **.\src\parsers\regions_data\Республика Татарстан\Республика Татарстан_2025-10-19_16-30-56.jsonl**  4797 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-09_14-33-00.jsonl**  9 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-20_02-24-08.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-20_12-27-48.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-20_22-08-50.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-21_18-44-33.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-21_21-37-50.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-22_00-23-10.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-22_18-18-31.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-22_21-19-01.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-23_13-35-46.jsonl**  13 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-24_11-51-26.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-24_17-21-07.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-25_12-31-41.jsonl**  20 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-25_14-24-29.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-26_15-48-28.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-27_14-01-03.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-29_15-48-10.jsonl**  15 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-09-30_13-41-43.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-01_17-25-56.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-02_14-22-35.jsonl**  8 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-03_10-29-28.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-08_00-52-30.jsonl**  10 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-08_10-25-14.jsonl**  5 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-09_13-21-52.jsonl**  18 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-10_18-01-02.jsonl**  35 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-13_13-38-46.jsonl**  31 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-14_12-05-07.jsonl**  27 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-15_19-59-23.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-16_15-09-49.jsonl**  4 records
- **.\src\parsers\regions_data\Республика Тыва\Республика Тыва_2025-10-19_16-42-19.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-09_14-39-50.jsonl**  187 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-20_02-28-00.jsonl**  113 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-20_03-51-02.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-20_12-31-10.jsonl**  12 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-20_22-12-38.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-21_18-48-25.jsonl**  11 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-21_21-41-56.jsonl**  77 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-22_00-26-56.jsonl**  107 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-22_05-31-51.jsonl**  7 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-22_18-23-08.jsonl**  85 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-22_21-23-34.jsonl**  3 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-23_02-27-09.jsonl**  1 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-23_13-40-24.jsonl**  82 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-24_11-56-03.jsonl**  80 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-24_17-25-59.jsonl**  38 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-25_12-36-35.jsonl**  100 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-25_14-29-25.jsonl**  20 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-26_15-53-24.jsonl**  70 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-27_14-05-50.jsonl**  19 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-29_15-52-54.jsonl**  98 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-09-30_13-46-07.jsonl**  95 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-01_17-30-29.jsonl**  93 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-02_14-28-39.jsonl**  72 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-03_10-33-51.jsonl**  98 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-08_00-56-33.jsonl**  140 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-08_10-28-54.jsonl**  75 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-09_13-25-34.jsonl**  146 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-10_18-04-27.jsonl**  118 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-13_13-42-10.jsonl**  118 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-14_12-06-35.jsonl**  95 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-15_20-02-58.jsonl**  125 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-16_15-14-12.jsonl**  162 records
- **.\src\parsers\regions_data\Республика Хакасия\Республика Хакасия_2025-10-19_16-46-00.jsonl**  86 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-20_16-38-07.jsonl**  3484 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-21_00-23-47.jsonl**  135 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-23_04-59-01.jsonl**  3533 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-24_20-25-13.jsonl**  4316 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-25_17-17-27.jsonl**  3645 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-26_19-16-28.jsonl**  3421 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-27_17-13-12.jsonl**  991 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-29_19-11-02.jsonl**  3561 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-09-30_16-46-47.jsonl**  3399 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-02_18-38-25.jsonl**  4012 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-03_14-22-47.jsonl**  2691 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-08_03-31-39.jsonl**  3203 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-08_12-49-27.jsonl**  2526 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-09_16-21-06.jsonl**  3231 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-10_22-17-41.jsonl**  2962 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-13_16-06-54.jsonl**  2929 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-14_15-11-22.jsonl**  3034 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-15_23-41-22.jsonl**  3188 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-16_18-40-14.jsonl**  3069 records
- **.\src\parsers\regions_data\Ростовская область\Ростовская область_2025-10-19_19-23-18.jsonl**  2318 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-20_16-44-20.jsonl**  831 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-20_17-06-03.jsonl**  826 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-21_00-30-00.jsonl**  52 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-23_05-04-53.jsonl**  1449 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-24_20-33-10.jsonl**  1904 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-25_17-26-05.jsonl**  1702 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-26_19-25-08.jsonl**  1762 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-27_17-20-55.jsonl**  525 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-29_19-18-55.jsonl**  1843 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-09-30_16-54-20.jsonl**  1846 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-02_18-49-32.jsonl**  2141 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-03_14-30-40.jsonl**  1943 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-08_03-37-07.jsonl**  1708 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-08_12-56-38.jsonl**  1453 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-09_16-28-01.jsonl**  1740 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-10_22-24-46.jsonl**  1488 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-13_16-13-22.jsonl**  1395 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-14_15-18-55.jsonl**  1454 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-15_23-48-02.jsonl**  1493 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-16_18-46-50.jsonl**  712 records
- **.\src\parsers\regions_data\Рязанская область\Рязанская область_2025-10-19_19-28-22.jsonl**  1094 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-20_17-08-08.jsonl**  676 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-20_17-29-35.jsonl**  4079 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-21_00-32-45.jsonl**  268 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-23_05-07-25.jsonl**  5020 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-24_20-36-51.jsonl**  5969 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-25_17-29-59.jsonl**  4973 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-26_19-29-14.jsonl**  4327 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-27_17-24-44.jsonl**  1286 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-29_19-22-57.jsonl**  4480 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-09-30_16-58-16.jsonl**  5229 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-02_18-55-06.jsonl**  1848 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-03_14-35-06.jsonl**  821 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-08_03-39-54.jsonl**  700 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-08_13-00-22.jsonl**  5342 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-09_16-31-37.jsonl**  4380 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-10_22-28-34.jsonl**  3395 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-13_16-16-45.jsonl**  4133 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-14_15-22-35.jsonl**  3565 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-15_23-51-02.jsonl**  3944 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-16_19-08-27.jsonl**  3658 records
- **.\src\parsers\regions_data\Самарская область\Самарская область_2025-10-19_19-30-44.jsonl**  2734 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-20_18-57-27.jsonl**  4723 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-21_01-37-43.jsonl**  133 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-23_06-27-42.jsonl**  4741 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-24_22-16-26.jsonl**  5266 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-25_19-12-23.jsonl**  1760 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-26_21-10-31.jsonl**  4898 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-27_18-57-17.jsonl**  1527 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-30_00-10-18.jsonl**  4710 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-09-30_18-48-16.jsonl**  5345 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-02_20-14-50.jsonl**  5474 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-03_16-37-08.jsonl**  1205 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-08_04-49-37.jsonl**  5419 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-08_14-44-37.jsonl**  4212 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-09_18-12-03.jsonl**  4957 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-10_23-43-42.jsonl**  4059 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-13_17-34-27.jsonl**  3692 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-14_16-43-12.jsonl**  3508 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-16_01-04-09.jsonl**  1441 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-16_20-09-27.jsonl**  1263 records
- **.\src\parsers\regions_data\Санкт-Петербург\Санкт-Петербург_2025-10-19_20-41-41.jsonl**  792 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-20_17-37-58.jsonl**  2946 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-21_00-42-56.jsonl**  85 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-23_05-15-57.jsonl**  3011 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-24_20-50-11.jsonl**  3443 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-25_17-42-25.jsonl**  2695 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-26_19-40-41.jsonl**  2758 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-27_17-34-31.jsonl**  912 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-29_19-32-54.jsonl**  2393 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-09-30_17-09-39.jsonl**  2717 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-02_19-00-58.jsonl**  830 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-03_14-56-56.jsonl**  2666 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-08_04-01-21.jsonl**  2182 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-08_13-10-05.jsonl**  1522 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-09_16-40-42.jsonl**  1702 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-10_22-37-16.jsonl**  1696 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-13_16-25-44.jsonl**  1412 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-14_15-32-28.jsonl**  1716 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-15_23-59-08.jsonl**  1731 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-16_19-16-41.jsonl**  1632 records
- **.\src\parsers\regions_data\Саратовская область\Саратовская область_2025-10-19_19-36-36.jsonl**  609 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-20_17-44-10.jsonl**  36 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-21_00-48-22.jsonl**  3 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-23_05-21-05.jsonl**  29 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-24_20-57-02.jsonl**  26 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-25_17-49-17.jsonl**  14 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-26_19-48-13.jsonl**  20 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-27_17-40-49.jsonl**  7 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-29_19-38-57.jsonl**  14 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-09-30_17-15-41.jsonl**  17 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-02_19-04-44.jsonl**  43 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-03_15-02-32.jsonl**  21 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-08_04-05-17.jsonl**  27 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-08_13-14-30.jsonl**  17 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-09_16-44-53.jsonl**  27 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-10_22-41-29.jsonl**  37 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-13_16-29-34.jsonl**  28 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-14_15-36-41.jsonl**  23 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-16_19-20-55.jsonl**  27 records
- **.\src\parsers\regions_data\Сахалинская область\Сахалинская область_2025-10-19_19-58-13.jsonl**  27 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-20_17-44-48.jsonl**  7557 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-21_00-49-06.jsonl**  216 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-23_05-21-53.jsonl**  7774 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-25_17-50-08.jsonl**  8098 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-26_19-49-06.jsonl**  7105 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-27_17-41-42.jsonl**  2092 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-29_19-39-50.jsonl**  6600 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-09-30_17-16-33.jsonl**  7003 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-02_19-06-03.jsonl**  8018 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-03_15-03-24.jsonl**  5780 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-08_04-06-03.jsonl**  6718 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-08_13-15-17.jsonl**  5422 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-09_16-45-41.jsonl**  6415 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-10_22-42-16.jsonl**  3473 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-13_16-30-24.jsonl**  6079 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-14_15-37-26.jsonl**  5274 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-16_00-03-48.jsonl**  6101 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-16_19-21-34.jsonl**  5629 records
- **.\src\parsers\regions_data\Свердловская область\Свердловская область_2025-10-19_19-58-52.jsonl**  3990 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-20_17-59-17.jsonl**  1208 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-21_01-03-02.jsonl**  47 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-23_05-34-24.jsonl**  822 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-24_21-14-46.jsonl**  1615 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-25_18-09-16.jsonl**  1218 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-26_20-07-31.jsonl**  1123 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-27_17-56-43.jsonl**  328 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-29_19-55-28.jsonl**  631 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-09-30_17-31-32.jsonl**  1262 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-02_19-28-42.jsonl**  1412 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-03_15-19-21.jsonl**  946 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-08_13-29-59.jsonl**  1647 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-09_17-00-37.jsonl**  1214 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-10_22-49-42.jsonl**  1049 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-13_16-42-50.jsonl**  794 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-14_15-50-32.jsonl**  662 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-16_00-16-20.jsonl**  1216 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-16_19-34-55.jsonl**  877 records
- **.\src\parsers\regions_data\Смоленская область\Смоленская область_2025-10-19_20-08-36.jsonl**  630 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-09_15-38-02.jsonl**  1161 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-20_04-39-32.jsonl**  1472 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-20_13-21-30.jsonl**  226 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-20_22-47-00.jsonl**  159 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-21_19-43-45.jsonl**  238 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-21_22-15-32.jsonl**  489 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-22_00-58-31.jsonl**  710 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-22_06-00-51.jsonl**  632 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-22_22-15-12.jsonl**  1133 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-23_03-11-13.jsonl**  28 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-24_12-30-57.jsonl**  1409 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-24_18-00-19.jsonl**  825 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-25_13-12-26.jsonl**  1248 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-25_15-05-28.jsonl**  458 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-26_16-24-54.jsonl**  590 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-27_14-57-18.jsonl**  547 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-29_16-47-01.jsonl**  1397 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-09-30_14-19-24.jsonl**  955 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-01_18-21-40.jsonl**  1106 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-02_15-32-53.jsonl**  998 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-03_11-28-12.jsonl**  854 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-08_01-27-17.jsonl**  911 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-08_11-03-20.jsonl**  1189 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-09_14-20-08.jsonl**  1253 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-10_18-38-29.jsonl**  1039 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-13_14-13-48.jsonl**  1101 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-14_12-41-34.jsonl**  777 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-15_20-37-40.jsonl**  1660 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-16_15-51-09.jsonl**  1368 records
- **.\src\parsers\regions_data\Ставропольский край\Ставропольский край_2025-10-19_17-15-07.jsonl**  1034 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-20_18-01-33.jsonl**  1294 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-21_01-05-30.jsonl**  121 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-23_05-56-06.jsonl**  1296 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-24_21-17-35.jsonl**  1271 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-25_18-12-12.jsonl**  1004 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-26_20-10-34.jsonl**  946 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-27_18-18-31.jsonl**  453 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-29_20-17-09.jsonl**  1116 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-09-30_17-34-12.jsonl**  1228 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-02_19-33-05.jsonl**  856 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-03_15-21-53.jsonl**  1425 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-08_04-20-57.jsonl**  1260 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-08_13-32-59.jsonl**  1145 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-09_17-03-19.jsonl**  1227 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-10_22-52-21.jsonl**  1268 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-13_17-04-41.jsonl**  935 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-14_15-52-29.jsonl**  1153 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-16_00-18-45.jsonl**  1239 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-16_19-37-08.jsonl**  1309 records
- **.\src\parsers\regions_data\Тамбовская область\Тамбовская область_2025-10-19_20-09-52.jsonl**  811 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-20_18-04-08.jsonl**  1619 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-21_01-08-00.jsonl**  53 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-23_05-58-13.jsonl**  1689 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-24_21-20-12.jsonl**  873 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-25_18-14-51.jsonl**  1889 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-26_20-13-13.jsonl**  1562 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-27_18-21-12.jsonl**  378 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-29_20-19-54.jsonl**  1547 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-09-30_17-36-49.jsonl**  831 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-02_19-36-48.jsonl**  902 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-03_15-24-54.jsonl**  658 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-08_04-23-09.jsonl**  1658 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-08_13-36-13.jsonl**  599 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-09_17-06-08.jsonl**  750 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-10_22-55-14.jsonl**  612 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-13_17-06-56.jsonl**  1437 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-14_15-55-13.jsonl**  710 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-16_00-21-32.jsonl**  1545 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-16_19-40-42.jsonl**  1206 records
- **.\src\parsers\regions_data\Тверская область\Тверская область_2025-10-19_20-19-39.jsonl**  991 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-20_18-07-19.jsonl**  419 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-21_01-11-09.jsonl**  12 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-23_06-00-59.jsonl**  322 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-24_21-42-02.jsonl**  421 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-25_18-19-36.jsonl**  286 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-26_20-17-36.jsonl**  282 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-27_18-24-36.jsonl**  88 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-29_20-24-06.jsonl**  277 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-09-30_17-58-37.jsonl**  277 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-02_19-40-42.jsonl**  321 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-03_15-46-38.jsonl**  264 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-08_04-25-56.jsonl**  320 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-08_13-57-52.jsonl**  205 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-09_17-27-51.jsonl**  197 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-10_23-16-48.jsonl**  237 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-13_17-09-49.jsonl**  214 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-14_16-16-56.jsonl**  159 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-16_00-24-28.jsonl**  252 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-16_19-43-22.jsonl**  255 records
- **.\src\parsers\regions_data\Томская область\Томская область_2025-10-19_20-21-52.jsonl**  205 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-20_18-07-56.jsonl**  2952 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-21_01-11-47.jsonl**  90 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-23_06-01-37.jsonl**  3100 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-24_21-42-44.jsonl**  3687 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-25_18-20-26.jsonl**  2904 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-26_20-18-20.jsonl**  2672 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-27_18-25-17.jsonl**  714 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-29_20-24-47.jsonl**  2767 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-09-30_17-59-15.jsonl**  3178 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-02_19-41-26.jsonl**  1846 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-03_15-47-23.jsonl**  3509 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-08_04-26-32.jsonl**  3278 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-08_13-58-31.jsonl**  2350 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-09_17-28-31.jsonl**  2670 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-10_23-17-26.jsonl**  2365 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-13_17-10-23.jsonl**  2319 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-14_16-17-34.jsonl**  2361 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-16_00-25-11.jsonl**  2354 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-16_19-44-10.jsonl**  2161 records
- **.\src\parsers\regions_data\Тульская область\Тульская область_2025-10-19_20-22-35.jsonl**  1633 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-20_18-13-24.jsonl**  2383 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-21_01-17-25.jsonl**  165 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-23_06-06-59.jsonl**  2457 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-24_21-50-02.jsonl**  2471 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-25_18-28-32.jsonl**  1791 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-26_20-26-03.jsonl**  1877 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-27_18-31-47.jsonl**  658 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-29_20-31-38.jsonl**  1940 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-09-30_18-06-12.jsonl**  1804 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-02_19-48-13.jsonl**  1809 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-03_15-55-21.jsonl**  1521 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-08_04-32-06.jsonl**  1766 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-08_14-05-21.jsonl**  1394 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-09_17-34-43.jsonl**  2037 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-10_23-23-03.jsonl**  1510 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-13_17-15-55.jsonl**  1742 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-14_16-23-22.jsonl**  1605 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-16_00-30-21.jsonl**  1697 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-16_19-49-16.jsonl**  1676 records
- **.\src\parsers\regions_data\Тюменская область\Тюменская область_2025-10-19_20-26-21.jsonl**  1395 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-09_14-33-58.jsonl**  1585 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-20_02-24-46.jsonl**  845 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-20_03-48-15.jsonl**  743 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-20_12-28-18.jsonl**  186 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-20_22-09-40.jsonl**  96 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-21_18-45-30.jsonl**  236 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-21_21-38-38.jsonl**  1098 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-22_00-24-16.jsonl**  1606 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-22_05-29-22.jsonl**  33 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-22_18-19-35.jsonl**  1443 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-22_21-19-52.jsonl**  38 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-23_02-24-22.jsonl**  45 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-23_13-36-36.jsonl**  1484 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-24_11-52-13.jsonl**  1694 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-24_17-21-54.jsonl**  1074 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-25_12-32-29.jsonl**  1666 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-25_14-25-15.jsonl**  444 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-26_15-49-20.jsonl**  1718 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-27_14-02-05.jsonl**  484 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-29_15-49-00.jsonl**  1759 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-09-30_13-42-32.jsonl**  1510 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-01_17-26-46.jsonl**  1764 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-02_14-23-20.jsonl**  1742 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-03_10-30-14.jsonl**  1433 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-08_00-53-16.jsonl**  1818 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-08_10-25-59.jsonl**  1064 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-09_13-22-40.jsonl**  1473 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-10_18-01-50.jsonl**  1205 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-13_13-39-32.jsonl**  1165 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-14_12-05-53.jsonl**  78 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-15_20-00-10.jsonl**  1565 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-16_15-10-37.jsonl**  1400 records
- **.\src\parsers\regions_data\Удмуртская Республика\Удмуртская Республика_2025-10-19_16-43-36.jsonl**  973 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-20_18-17-42.jsonl**  863 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-20_18-39-24.jsonl**  1720 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-21_01-21-30.jsonl**  79 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-23_06-10-52.jsonl**  2903 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-24_21-55-02.jsonl**  2727 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-25_18-33-10.jsonl**  566 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-26_20-30-56.jsonl**  470 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-27_18-36-34.jsonl**  2002 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-29_20-35-57.jsonl**  2481 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-09-30_18-10-13.jsonl**  2521 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-02_19-54-41.jsonl**  2689 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-03_15-59-25.jsonl**  2207 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-08_04-35-32.jsonl**  2136 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-08_14-09-06.jsonl**  1706 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-09_17-38-58.jsonl**  740 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-10_23-27-03.jsonl**  1793 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-13_17-19-45.jsonl**  1767 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-14_16-27-17.jsonl**  1821 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-16_00-34-36.jsonl**  1998 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-16_19-53-29.jsonl**  1539 records
- **.\src\parsers\regions_data\Ульяновская область\Ульяновская область_2025-10-19_20-30-09.jsonl**  1483 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-09_15-43-12.jsonl**  812 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-20_04-42-21.jsonl**  705 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-20_13-24-17.jsonl**  132 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-20_22-50-21.jsonl**  26 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-21_22-18-10.jsonl**  553 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-22_06-04-01.jsonl**  744 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-22_22-18-10.jsonl**  401 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-23_03-32-43.jsonl**  58 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-24_12-33-55.jsonl**  709 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-24_18-03-19.jsonl**  181 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-25_13-16-04.jsonl**  602 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-25_15-09-12.jsonl**  55 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-26_16-46-28.jsonl**  548 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-27_15-19-18.jsonl**  211 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-29_16-50-04.jsonl**  717 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-09-30_14-22-10.jsonl**  589 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-01_18-24-09.jsonl**  580 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-02_15-36-20.jsonl**  642 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-03_11-30-58.jsonl**  630 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-08_01-49-03.jsonl**  928 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-08_11-06-13.jsonl**  531 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-09_14-22-57.jsonl**  797 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-10_18-41-11.jsonl**  803 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-13_14-16-30.jsonl**  764 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-14_13-03-25.jsonl**  856 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-15_20-41-19.jsonl**  1053 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-16_15-54-57.jsonl**  887 records
- **.\src\parsers\regions_data\Хабаровский край\Хабаровский край_2025-10-19_17-17-32.jsonl**  827 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-20_19-07-23.jsonl**  965 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-21_01-46-33.jsonl**  21 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-23_06-36-35.jsonl**  1059 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-24_22-28-16.jsonl**  952 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-25_19-19-31.jsonl**  807 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-26_21-23-36.jsonl**  719 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-27_19-08-14.jsonl**  324 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-30_00-21-55.jsonl**  699 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-09-30_19-00-39.jsonl**  678 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-02_20-35-27.jsonl**  705 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-03_16-41-45.jsonl**  554 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-08_04-59-45.jsonl**  878 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-08_14-57-16.jsonl**  666 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-09_18-24-19.jsonl**  817 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-10_23-54-56.jsonl**  643 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-13_17-44-25.jsonl**  657 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-14_16-53-50.jsonl**  664 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-16_01-08-39.jsonl**  794 records
- **.\src\parsers\regions_data\Ханты-Мансийский автономный округ _ Югра\Ханты-Мансийский автономный округ _ Югра_2025-10-16_20-14-05.jsonl**  844 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-20_18-43-44.jsonl**  4986 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-21_01-26-06.jsonl**  100 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-23_06-15-58.jsonl**  5001 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-24_22-00-33.jsonl**  6561 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-25_18-54-47.jsonl**  5173 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-26_20-52-26.jsonl**  5061 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-27_18-41-45.jsonl**  1261 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-29_23-55-34.jsonl**  4996 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-09-30_18-15-52.jsonl**  5178 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-02_20-04-29.jsonl**  875 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-03_16-05-22.jsonl**  4929 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-08_04-39-24.jsonl**  4029 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-08_14-13-42.jsonl**  4045 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-09_18-00-48.jsonl**  4019 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-10_23-30-57.jsonl**  3716 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-13_17-23-38.jsonl**  3228 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-14_16-31-43.jsonl**  3224 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-16_00-38-48.jsonl**  838 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-16_19-57-24.jsonl**  4208 records
- **.\src\parsers\regions_data\Челябинская область\Челябинская область_2025-10-19_20-33-39.jsonl**  2471 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-09_14-41-25.jsonl**  38 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-20_02-29-09.jsonl**  25 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-20_12-31-55.jsonl**  9 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-21_18-49-19.jsonl**  8 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-21_21-42-22.jsonl**  20 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-22_00-27-43.jsonl**  29 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-22_05-33-01.jsonl**  2 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-22_18-23-55.jsonl**  29 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-22_21-24-20.jsonl**  4 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-23_02-27-52.jsonl**  2 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-23_13-41-10.jsonl**  22 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-24_11-56-45.jsonl**  19 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-24_17-26-42.jsonl**  12 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-25_12-37-18.jsonl**  23 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-25_14-30-09.jsonl**  7 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-26_15-54-08.jsonl**  30 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-27_14-06-36.jsonl**  17 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-29_15-53-42.jsonl**  37 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-09-30_13-46-52.jsonl**  36 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-01_17-31-09.jsonl**  30 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-02_14-29-34.jsonl**  23 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-03_10-34-32.jsonl**  23 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-08_00-57-12.jsonl**  38 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-08_10-29-38.jsonl**  19 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-09_13-26-16.jsonl**  1 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-10_18-05-10.jsonl**  40 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-13_13-42-53.jsonl**  23 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-14_12-07-16.jsonl**  23 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-15_20-03-41.jsonl**  22 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-16_15-14-58.jsonl**  24 records
- **.\src\parsers\regions_data\Чеченская Республика\Чеченская Республика_2025-10-19_16-46-47.jsonl**  26 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-09_14-42-24.jsonl**  1157 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-20_02-29-47.jsonl**  882 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-20_03-52-20.jsonl**  359 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-20_12-32-33.jsonl**  241 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-20_22-14-08.jsonl**  127 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-21_18-49-54.jsonl**  266 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-21_21-43-43.jsonl**  774 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-22_00-28-35.jsonl**  1267 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-22_05-33-54.jsonl**  23 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-22_18-24-48.jsonl**  1170 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-22_21-24-59.jsonl**  36 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-23_02-28-31.jsonl**  25 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-23_13-41-49.jsonl**  1121 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-24_11-57-24.jsonl**  1215 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-24_17-27-22.jsonl**  748 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-25_12-37-57.jsonl**  1073 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-25_14-30-48.jsonl**  266 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-26_15-54-47.jsonl**  1134 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-27_14-07-15.jsonl**  397 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-29_15-54-21.jsonl**  1145 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-09-30_13-47-31.jsonl**  1116 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-01_17-31-48.jsonl**  1104 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-02_14-30-14.jsonl**  994 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-03_10-35-10.jsonl**  947 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-08_00-57-51.jsonl**  1243 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-08_10-30-16.jsonl**  836 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-09_13-26-53.jsonl**  1300 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-10_18-05-48.jsonl**  997 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-13_13-43-32.jsonl**  857 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-14_12-07-55.jsonl**  785 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-15_20-04-19.jsonl**  908 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-16_15-15-37.jsonl**  930 records
- **.\src\parsers\regions_data\Чувашская Республика\Чувашская Республика_2025-10-19_16-47-25.jsonl**  629 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-09-26_21-26-08.jsonl**  1 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-03_16-43-31.jsonl**  1 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-08_05-01-46.jsonl**  2 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-08_14-59-45.jsonl**  2 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-09_18-26-41.jsonl**  2 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-13_17-46-28.jsonl**  1 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-14_16-56-05.jsonl**  3 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-16_01-10-43.jsonl**  1 records
- **.\src\parsers\regions_data\Чукотский автономный округ\Чукотский автономный округ_2025-10-16_20-16-09.jsonl**  3 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-20_19-10-39.jsonl**  472 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-21_01-49-27.jsonl**  10 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-23_06-41-26.jsonl**  477 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-24_22-33-19.jsonl**  407 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-25_19-24-59.jsonl**  346 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-26_21-26-48.jsonl**  330 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-27_19-11-13.jsonl**  122 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-30_00-24-27.jsonl**  394 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-09-30_19-03-27.jsonl**  397 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-02_20-42-12.jsonl**  415 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-03_16-44-10.jsonl**  341 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-08_05-02-24.jsonl**  535 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-08_15-00-25.jsonl**  380 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-09_18-27-19.jsonl**  447 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-10_23-57-41.jsonl**  425 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-13_17-47-06.jsonl**  468 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-14_16-56-44.jsonl**  389 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-16_01-11-30.jsonl**  423 records
- **.\src\parsers\regions_data\Ямало-Ненецкий автономный округ\Ямало-Ненецкий автономный округ_2025-10-16_20-16-56.jsonl**  441 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-20_18-53-52.jsonl**  1875 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-21_01-34-45.jsonl**  61 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-23_06-24-02.jsonl**  2059 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-24_22-12-11.jsonl**  2176 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-25_19-07-42.jsonl**  1540 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-26_21-05-37.jsonl**  1693 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-27_18-53-06.jsonl**  485 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-30_00-06-12.jsonl**  1821 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-09-30_18-26-24.jsonl**  824 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-02_20-08-29.jsonl**  2340 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-03_16-15-11.jsonl**  723 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-08_04-46-09.jsonl**  1809 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-08_14-22-55.jsonl**  681 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-09_18-09-55.jsonl**  850 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-10_23-39-46.jsonl**  1970 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-13_17-30-44.jsonl**  1576 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-14_16-39-11.jsonl**  1438 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-16_01-00-32.jsonl**  1455 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-16_20-05-40.jsonl**  1484 records
- **.\src\parsers\regions_data\Ярославская область\Ярославская область_2025-10-19_20-39-06.jsonl**  1212 records
- **.\src\parsers\regions_data_trucks\transport.jsonl**  17 records
- **.\src\parsers\regions_data_trucks\filter\filter_2025-09-27_20-26-08.jsonl**  0 records
- **.\src\parsers\regions_data_trucks\filter_custom\filter_custom_2025-09-27_02-09-14.jsonl**  0 records
- **.\src\parsers\regions_data_trucks\filter_custom\filter_custom_2025-09-27_02-23-58.jsonl**  771 records
- **.\src\parsers\regions_data_trucks\filter_custom\filter_custom_2025-09-27_03-03-36.jsonl**  205 records
- **.\src\parsers\regions_data_trucks\filter_Test\Test_2025-09-27_18-41-22.jsonl**  0 records
- **.\src\parsers\regions_data_trucks\filter_Test\Test_2025-09-27_18-52-00.jsonl**  38 records
- **.\src\parsers\regions_data_trucks\filter_Test\Test_2025-09-27_22-38-36.jsonl**  429 records
- **.\src\parsers\regions_data_trucks\filter_Test\Test_2025-09-27_23-17-30.jsonl**  0 records
- **.\src\parsers\regions_data_trucks\filter_Test\Test_2025-09-27_23-41-05.jsonl**  373 records
- **.\src\parsers\regions_data_trucks\filter_Test\Test_2025-10-03_10-50-02.jsonl**  73 records
- **.\src\parsers\regions_data_trucks\filter_Тест\Тест_2025-09-26_22-17-26.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\filter_Тест\Тест_2025-09-27_01-02-36.jsonl**  30 records
- **.\src\parsers\regions_data_trucks\filter_Тест\Тест_2025-09-27_13-12-36.jsonl**  1016 records
- **.\src\parsers\regions_data_trucks\Алтайский край\Алтайский край_2025-09-27_04-31-34.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Алтайский край\Алтайский край_2025-09-27_16-18-22.jsonl**  866 records
- **.\src\parsers\regions_data_trucks\Амурская область\Амурская область_2025-09-27_04-31-38.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Амурская область\Амурская область_2025-09-27_16-19-10.jsonl**  507 records
- **.\src\parsers\regions_data_trucks\Архангельская область\Архангельская область_2025-09-27_04-32-00.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Архангельская область\Архангельская область_2025-09-27_16-20-56.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Астраханская область\Астраханская область_2025-09-27_04-32-55.jsonl**  102 records
- **.\src\parsers\regions_data_trucks\Белгородская область\Белгородская область_2025-09-27_04-44-49.jsonl**  768 records
- **.\src\parsers\regions_data_trucks\Брянская область\Брянская область_2025-09-27_04-46-18.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Владимирская область\Владимирская область_2025-09-27_04-47-37.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Волгоградская область\Волгоградская область_2025-09-27_04-48-13.jsonl**  892 records
- **.\src\parsers\regions_data_trucks\Вологодская область\Вологодская область_2025-09-27_04-50-02.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Воронежская область\Воронежская область_2025-09-27_04-50-38.jsonl**  1038 records
- **.\src\parsers\regions_data_trucks\Еврейская автономная область\Еврейская автономная область_2025-09-27_04-52-48.jsonl**  8 records
- **.\src\parsers\regions_data_trucks\Забайкальский край\Забайкальский край_2025-09-27_04-53-21.jsonl**  769 records
- **.\src\parsers\regions_data_trucks\Ивановская область\Ивановская область_2025-09-27_04-55-06.jsonl**  104 records
- **.\src\parsers\regions_data_trucks\Иркутская область\Иркутская область_2025-09-27_04-55-43.jsonl**  910 records
- **.\src\parsers\regions_data_trucks\Кабардино-Балкарская Республика\Кабардино-Балкарская Республика_2025-09-27_04-57-14.jsonl**  89 records
- **.\src\parsers\regions_data_trucks\Калининградская область\Калининградская область_2025-09-27_04-58-11.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Калужская область\Калужская область_2025-09-27_04-59-31.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Камчатский край\Камчатский край_2025-09-27_05-00-23.jsonl**  25 records
- **.\src\parsers\regions_data_trucks\Карачаево-Черкесская Республика\Карачаево-Черкесская Республика_2025-09-27_05-01-38.jsonl**  40 records
- **.\src\parsers\regions_data_trucks\Кемеровская область\Кемеровская область_2025-09-27_05-02-11.jsonl**  705 records
- **.\src\parsers\regions_data_trucks\Кировская область\Кировская область_2025-09-27_05-03-49.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Костромская область\Костромская область_2025-09-27_05-04-49.jsonl**  101 records
- **.\src\parsers\regions_data_trucks\Краснодарский край\Краснодарский край_2025-09-27_05-05-47.jsonl**  921 records
- **.\src\parsers\regions_data_trucks\Красноярский край\Красноярский край_2025-09-27_05-06-47.jsonl**  904 records
- **.\src\parsers\regions_data_trucks\Курганская область\Курганская область_2025-09-27_05-08-19.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Курская область\Курская область_2025-09-27_05-09-20.jsonl**  105 records
- **.\src\parsers\regions_data_trucks\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-27_05-53-40.jsonl**  2858 records
- **.\src\parsers\regions_data_trucks\Московская область - Алтайский край\Московская область - Алтайский край_2025-09-27_06-16-29.jsonl**  4823 records
- **.\src\parsers\regions_data_trucks\Московская область - Амурская область\Московская область - Амурская область_2025-09-27_13-43-28.jsonl**  2078 records
- **.\src\parsers\transport_stats\saved_filter.jsonl**  2 records
- **.\src\parsers\trucks_data\filters\проба_2025-09-22_23-42-04.jsonl**  1138 records

