
import json
import os
import logging
import re
import math
from typing import List, Tuple, Dict, Any, Optional
from config import CITIES_CACHE_PATH, ROAD_CURVATURE_FACTOR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def normalize_city_name(city_name: str) -> str:
    if not city_name:
        return ""
    normalized = city_name.lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def load_cities_cache() -> Dict[str, dict]:
    if os.path.exists(CITIES_CACHE_PATH):
        try:
            with open(CITIES_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ошибка загрузки кеша городов: {str(e)}")
    return {}

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Radius of Earth in km
    R = 6371.0
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def approx_road_km(lat1: float, lon1: float, lat2: float, lon2: float, factor: float = ROAD_CURVATURE_FACTOR) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * factor
