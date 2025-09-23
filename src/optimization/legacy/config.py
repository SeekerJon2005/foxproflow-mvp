
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Geocoding / caches ---
OSM_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
YANDEX_GEOCODE_URL = "https://geocode-maps.yandex.ru/1.x/"
YANDEX_API_KEY = "117349d4-6768-4587-9885-63e0e30ea2c5"  # <- replace if needed
OSM_USER_AGENT = "FoxProFlow/1.0 (contact@yourdomain.com)"
YANDEX_DAILY_LIMIT = 900

CITIES_CACHE_PATH = os.path.join(BASE_DIR, "cities_cache.json")
EXACT_DISTANCE_CACHE_PATH = os.path.join(BASE_DIR, "exact_distance_cache.json")
YANDEX_COUNTER_PATH = os.path.join(BASE_DIR, "yandex_counter.json")

# --- Economics / costs ---
FUEL_PRICE = 55.0                      # RUB / liter
FUEL_CONSUMPTION = 32.0                # liters per 100 km
DRIVER_SALARY_PER_KM = 8.0             # RUB / km
VEHICLE_DEPRECIATION_PER_KM = 5.0      # RUB / km

# --- Planner dynamics ---
DAILY_DRIVING_DISTANCE = 800           # km / day (legacy)
HOURLY_DRIVING_SPEED = 33.33           # km / hour (≈ 800 km / 24h)

# !!! Fix earlier unit bug: service time in HOURS, not '20 hours' constant
LOAD_TIME_HOURS = 0.5
UNLOAD_TIME_HOURS = 0.5
SERVICE_TIME_HOURS = LOAD_TIME_HOURS + UNLOAD_TIME_HOURS

# Default assumption when only date is known
DEFAULT_LOADING_HOUR = 8               # local time, naive
ROAD_CURVATURE_FACTOR = 1.15           # to scale haversine to road distance

# --- Market analytics ---
MARKET_LOOKBACK_DAYS = 28
MARKET_MIN_SAMPLES = 25
SURGE_THRESHOLD_MULTIPLIER = 1.30      # +30% vs guaranteed baseline

# --- DB ---
DATABASE_PATH = os.path.join(BASE_DIR, "freights.db")
