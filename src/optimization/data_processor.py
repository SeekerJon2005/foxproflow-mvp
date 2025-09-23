
import json
import os
import logging
import re
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
from models import Freight

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_price(price_str: str) -> float:
    if not price_str or price_str.strip() in ['-', '']:
        return 0.0
    try:
        clean_str = re.sub(r'[^\d.,]', '', price_str)
        clean_str = clean_str.replace(',', '.').replace(' ', '')
        if clean_str.count('.') > 1:
            parts = clean_str.split('.')
            clean_str = parts[0] + '.' + ''.join(parts[1:])
        return float(clean_str) if clean_str else 0.0
    except ValueError:
        return 0.0

def safe_float_convert(value, default=0.0):
    if value is None or str(value).strip() in ['-', 'N/A', '']:
        return default
    try:
        clean_value = str(value).replace(' ', '').replace(',', '.')
        return float(clean_value)
    except (ValueError, TypeError):
        return default

def extract_city_and_region(location: str) -> Tuple[str, str]:
    if not location:
        return "", ""
    location = re.sub(r'\s+', ' ', location).strip()
    region = ""
    if '(' in location:
        parts = re.split(r'[()]', location)
        location = parts[0].strip()
        if len(parts) > 1:
            region = parts[1].strip()
    parts = [p.strip() for p in location.split(',') if p.strip()]
    city = parts[0] if parts else ""
    prefixes = ["г.", "п.", "д.", "с.", "рп.", "ст.", "ж/д", "н.п.", "пгт."]
    for prefix in prefixes:
        if city.startswith(prefix):
            city = city.replace(prefix, "").strip()
            break
    if not city and len(parts) > 1:
        city = parts[1].strip()
    if not region and len(parts) > 1:
        region = parts[1].strip()
    return city, region

def parse_loading_dt(loading_date_str: Optional[str], default_hour: int = 8) -> Optional[str]:
    """Convert 'YYYY-MM-DD' -> 'YYYY-MM-DDTHH:00:00'. Returns None if cannot parse."""
    if not loading_date_str:
        return None
    try:
        # keep basic YYYY-MM-DD; if already has time, try parse and return ISO
        if len(loading_date_str) == 10 and loading_date_str[4] == '-' and loading_date_str[7] == '-':
            dt = datetime(
                year=int(loading_date_str[:4]), month=int(loading_date_str[5:7]), day=int(loading_date_str[8:10]),
                hour=default_hour, minute=0, second=0
            )
            return dt.isoformat()
        # try generic parse
        try:
            dt = datetime.fromisoformat(loading_date_str)
            return dt.isoformat()
        except Exception:
            return None
    except Exception:
        return None

def process_freight(raw_freight: dict) -> Freight:
    data = raw_freight.copy()
    prices = {}
    price_data = data.pop("prices", {})
    if not isinstance(price_data, dict):
        price_data = {}
    for key, value in price_data.items():
        prices[key] = extract_price(value)
    revenue = 0.0
    for key in ["с_НДС", "без_НДС", "наличные", "price", "with_vat", "no_vat", "cash"]:
        if key in prices and prices[key] > revenue:
            revenue = prices[key]
    weight = safe_float_convert(data.pop("weight", None))
    volume = safe_float_convert(data.pop("volume", None))
    distance = safe_float_convert(data.pop("distance", None))
    loading_points = []
    loading_regions = []
    for point in data.pop("loading_points", []):
        city, region = extract_city_and_region(point)
        if city:
            loading_points.append(city)
            loading_regions.append(region)
    unloading_points = []
    unloading_regions = []
    for point in data.pop("unloading_points", []):
        city, region = extract_city_and_region(point)
        if city:
            unloading_points.append(city)
            unloading_regions.append(region)
    loading_date_str = data.get("loading_date")
    return Freight(
        **data,
        loading_points=loading_points,
        unloading_points=unloading_points,
        weight=weight,
        volume=volume,
        distance=distance,
        revenue_rub=revenue,
        prices=prices,
        loading_region=loading_regions[0] if loading_regions else None,
        unloading_region=unloading_regions[0] if unloading_regions else None,
        loading_date=loading_date_str or "",
        loading_dt=parse_loading_dt(loading_date_str)
    )
