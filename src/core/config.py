import os
import json
from pathlib import Path
from typing import Dict, Any, List

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
MODELS_DIR = DATA_DIR / "models"
PARSED_DATA_DIR = DATA_DIR / "parsed_data"

# Настройки базы данных
DATABASE_CONFIG = {
    "drivername": "postgresql",
    "username": "admin",
    "password": "password",
    "host": "localhost",
    "port": 5432,
    "database": "foxproflow"
}

# Настройки Redis
REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
    "password": "redis_password",
    "db": 0,
    "decode_responses": True
}

# Настройки парсеров
PARSER_CONFIG = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "request_timeout": 30,
    "max_retries": 3,
    "retry_delay": 2,
    "headless": True,
    "session_timeout": 3600,  # 1 час
    "max_concurrent_requests": 5
}

# Настройки дедупликации
DEDUPLICATION_CONFIG = {
    "hash_fields": ["loading_city", "unloading_city", "cargo", "weight", "volume", "loading_date", "revenue_rub"],
    "hash_ttl_days": 7,  # Хранить хэши 7 дней
    "similarity_threshold": 0.95  # Порог схожести для определения дубликатов
}

# Настройки геокодирования
GEOCODING_CONFIG = {
    "yandex_api_key": "117349d4-6768-4587-9885-63e0e30ea2c5",
    "yandex_daily_limit": 900,
    "osm_user_agent": "FoxProFlow/1.0 (contact@yourdomain.com)",
    "cache_ttl_days": 30
}

# Загрузка существующих кэшей
def load_existing_cache(cache_name: str) -> Dict[Any, Any]:
    cache_path = CACHE_DIR / f"{cache_name}.json"
    if cache_path.exists():
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# Сохранение кэша
def save_cache(cache_name: str, data: Dict[Any, Any]):
    cache_path = CACHE_DIR / f"{cache_name}.json"
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загрузка конфигурации маршрутизатора
def load_route_config() -> Dict[str, Any]:
    route_config_path = BASE_DIR / "src" / "optimization" / "legacy" / "route_config.json"
    if route_config_path.exists():
        with open(route_config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # Конфигурация по умолчанию
    return {
        "fuel_price": 55.0,
        "fuel_consumption": 32.0,
        "driver_salary_per_km": 8.0,
        "vehicle_depreciation_per_km": 5.0,
        "max_route_time_hours": 1080,
        "load_unload_time": 20,
        "daily_driving_distance": 800,
        "hourly_driving_speed": 33.33
    }

# Инициализация кэшей
CITIES_CACHE = load_existing_cache("cities_cache")
DISTANCE_CACHE = load_existing_cache("distance_cache")
EXACT_DISTANCE_CACHE = load_existing_cache("exact_distance_cache")
ROUTE_CONFIG = load_route_config()

# Регионы России для парсинга
RUSSIAN_REGIONS = [
    "Республика Адыгея", "Республика Алтай", "Республика Башкортостан",
    "Республика Бурятия", "Республика Дагестан", "Республика Ингушетия",
    "Кабардино-Балкарская Республика", "Республика Калмыкия",
    "Карачаево-Черкесская Республика", "Республика Карелия",
    "Республика Коми", "Республика Крым", "Республика Марий Эл",
    "Республика Мордовия", "Республика Саха (Якутия)", "Республика Северная Осетия-Алания",
    "Республика Татарстан", "Республика Тыва", "Удмуртская Республика",
    "Республика Хакасия", "Чеченская Республика", "Чувашская Республика",
    "Алтайский край", "Забайкальский край", "Камчатский край",
    "Краснодарский край", "Красноярский край", "Пермский край",
    "Приморский край", "Ставропольский край", "Хабаровский край",
    "Амурская область", "Архангельская область", "Астраханская область",
    "Белгородская область", "Брянская область", "Владимирская область",
    "Волгоградская область", "Вологодская область", "Воронежская область",
    "Ивановская область", "Иркутская область", "Калининградская область",
    "Калужская область", "Кемеровская область", "Кировская область",
    "Костромская область", "Курганская область", "Курская область",
    "Ленинградская область", "Липецкая область", "Магаданская область",
    "Московская область", "Мурманская область", "Нижегородская область",
    "Новгородская область", "Новосибирская область", "Омская область",
    "Оренбургская область", "Орловская область", "Пензенская область",
    "Псковская область", "Ростовская область", "Рязанская область",
    "Самарская область", "Саратовская область", "Сахалинская область",
    "Свердловская область", "Смоленская область", "Тамбовская область",
    "Тверская область", "Томская область", "Тульская область",
    "Тюменская область", "Ульяновская область", "Челябинская область",
    "Ярославская область", "Санкт-Петербург", "Еврейская автономная область",
    "Ненецкий автономный округ", "Ханты-Мансийский автономный округ — Югра",
    "Чукотский автономный округ", "Ямало-Ненецкий автономный округ"
]
