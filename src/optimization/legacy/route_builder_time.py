
import json
import os
import logging
import heapq
import itertools
import traceback
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from src.core.config import EXACT_DISTANCE_CACHE_PATH, HOURLY_DRIVING_SPEED, SERVICE_TIME_HOURS
from src.core.models import Freight, Route, RouteSegment
from src.core.geo_utils import approx_road_km
# Для подхвата координат гаража/финиша при их отсутствии в данных:
try:
    from src.core.geo_utils import get_city_coordinates
except Exception:
    get_city_coordinates = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TimeRouteBuilder')
logger.setLevel(logging.DEBUG)

class TimeAwareRouteBuilder:
    """
    Временной планировщик (Revenue-only) с оценкой эффективности по ВЕСЬМУ рейсу.
    Ключевые принципы:
      • Метрики за весь рейс (руб/км, руб/час, руб/день) — "размазанные" от выезда из гаража до возвращения.
      • Строгое правило: следующая загрузка должна состояться ≤ 24 часа после ETA прибытия к точке погрузки.
      • Порожняк учитывается всегда (к первой загрузке, между сегментами и обратно в гараж).
      • Поиск кандидатов разрешает любую длину переброски, которую можно физически преодолеть <= 24ч (радиус ~ speed*24).
    """
    def __init__(self, freight_rows: List[Dict[str, Any]]):
        self.freight_rows = freight_rows
        self.distance_cache = self._load_distance_cache()
        self.city_coords = self._build_city_coordinates()
        self.city_index = self._build_city_index()
        self.nearby_cache: Dict[Tuple[str, float], List[str]] = {}
        self.counter = itertools.count()
        logger.info("TimeAwareRouteBuilder (revenue-only, full-trip) инициализирован")

    # ---------- infra ----------

    def _load_distance_cache(self) -> Dict[str, float]:
        cache = {}
        if not os.path.exists(EXACT_DISTANCE_CACHE_PATH):
            logger.warning("Файл кеша расстояний не найден")
            return cache
        try:
            with open(EXACT_DISTANCE_CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            logger.info(f"Загружено {len(cache)} расстояний из кеша")
        except Exception as e:
            logger.error(f"Ошибка загрузки кеша расстояний: {str(e)}")
            logger.debug(traceback.format_exc())
        return cache

    def _build_city_coordinates(self) -> Dict[str, tuple]:
        city_coords: Dict[str, tuple] = {}
        for row in self.freight_rows:
            for city_key, lat_key, lon_key in (
                ('loading_city', 'loading_lat', 'loading_lon'),
                ('unloading_city', 'unloading_lat', 'unloading_lon')
            ):
                city = row.get(city_key)
                lat = row.get(lat_key); lon = row.get(lon_key)
                if city and lat is not None and lon is not None and city not in city_coords:
                    city_coords[city] = (lat, lon)
        return city_coords

    def _build_city_index(self) -> Dict[str, List[Dict]]:
        logger.info("Построение индекса городов (временная логика)...")
        city_index: Dict[str, List[Dict]] = {}
        processed_count = 0
        for row in self.freight_rows:
            try:
                loading_city = row.get('loading_city', '')
                unloading_city = row.get('unloading_city', '')
                if not loading_city or not unloading_city:
                    continue
                # индексируем по городу погрузки
                city_index.setdefault(loading_city, []).append({
                    'id': row.get('id', ''),
                    'loading_city': loading_city,
                    'unloading_city': unloading_city,
                    'distance': row.get('distance', 0.0),
                    'revenue': row.get('revenue_rub', 0.0),
                    'weight': row.get('weight', 0.0),
                    'volume': row.get('volume', 0.0),
                    'cargo': row.get('cargo', ''),
                    'body_type': row.get('body_type', ''),
                    'loading_date': row.get('loading_date', ''),
                    'loading_dt': row.get('loading_dt', None),
                })
                processed_count += 1
            except Exception as e:
                logger.error(f"Ошибка обработки груза: {str(e)}")
                logger.debug(f"Строка данных: {row}")
                logger.debug(traceback.format_exc())
        logger.info(f"Индекс построен для {len(city_index)} городов; грузов: {processed_count}")
        return city_index

    def _ensure_coord(self, city: str) -> bool:
        """Гарантируем наличие координат для произвольного города (гараж, финиш), если есть геокодер."""
        if city in self.city_coords:
            return True
        if get_city_coordinates is None:
            return False
        try:
            obj = get_city_coordinates(city, None)
            if obj:
                self.city_coords[city] = (obj.lat, obj.lon)
                return True
        except Exception:
            pass
        return False

    def _cached_or_approx_distance(self, city1: str, city2: str) -> Optional[float]:
        if not city1 or not city2:
            return None
        key1 = f"{city1}||{city2}"
        key2 = f"{city2}||{city1}"
        if key1 in self.distance_cache:
            return self.distance_cache[key1]
        if key2 in self.distance_cache:
            return self.distance_cache[key2]
        # try approximate from coords
        c1 = self.city_coords.get(city1); c2 = self.city_coords.get(city2)
        if c1 and c2:
            return approx_road_km(c1[0], c1[1], c2[0], c2[1])
        return None

    def _nearby_cities(self, city: str, radius_km: float) -> List[str]:
        """
        Возвращает список городов-погрузок в радиусе (по координатам) от текущего города.
        Радиус выбирается равным максимальному пробегу за 24 часа (speed*24), чтобы не отсечь валидные кандидаты.
        """
        key = (city, float(radius_km))
        if key in self.nearby_cache:
            return self.nearby_cache[key]

        if city not in self.city_coords:
            # если нет координат, больше смысла попробовать все города (дорого),
            # но это ограничит граф. Лучше обеспечить координаты через _ensure_coord().
            self.nearby_cache[key] = list(self.city_index.keys())
            return self.nearby_cache[key]

        lat0, lon0 = self.city_coords[city]
        res = []
        for other in self.city_index.keys():
            if other == city:
                continue
            c = self.city_coords.get(other)
            if not c:
                continue
            d = approx_road_km(lat0, lon0, c[0], c[1])
            if d <= radius_km:
                res.append(other)
        self.nearby_cache[key] = res
        return res

    # ---------- core ----------

    def build_routes(self, garage_city: str, end_city: str, start_time: datetime,
                     max_depth: int = 7, max_routes: int = 10) -> List[Route]:
        """
        Старт из гаража (garage_city) и оценка кандидатов как ПОЛНЫХ рейсов "гараж -> ... -> гараж".
        Внутри поиска на каждом шаге формируем кандидат-маршрут: текущий путь + порожняк до end_city (гаража),
        чтобы метрики всегда считались "размазано" на весь рейс.
        """
        logger.info(f"Построение временных маршрутов (full-trip): {garage_city} → {end_city}, старт: {start_time.isoformat()}")

        # Гарантируем координаты гаража/финиша
        self._ensure_coord(garage_city)
        self._ensure_coord(end_city)

        # Радиус достижимости за 24 часа
        reachable_24h_km = HOURLY_DRIVING_SPEED * 24.0

        # Пустая очередь: ( -rev_per_hour, -total_revenue, total_time, counter, path, curr_city, visited_ids, total_distance, curr_time )
        queue = []
        heapq.heappush(queue, (0.0, 0.0, 0.0, next(self.counter), [], garage_city, set(), 0.0, start_time))
        best_routes: List[Tuple] = []
        processed_paths = 0

        while queue and len(best_routes) < max_routes:
            neg_rph, neg_rev, total_time, _, path, current_city, visited, total_distance, current_time = heapq.heappop(queue)
            total_revenue = -neg_rev

            processed_paths += 1
            if processed_paths % 2000 == 0:
                logger.info(f"Обработано путей: {processed_paths}, очередь: {len(queue)}")

            # Всегда оцениваем текущий путь как КАНДИДАТ полной поездки до гаража
            if path:
                candidate = self._create_route(path, garage_city, end_city)
                if candidate:
                    # ключ сортировки: руб/час по всему рейсу, далее руб/км
                    heapq.heappush(best_routes, (-candidate.revenue_per_hour, -candidate.revenue_per_km, candidate.estimated_time, candidate))
                    if len(best_routes) > max_routes:
                        heapq.heappop(best_routes)

            # Ограничение глубины
            if len(path) >= max_depth:
                continue

            # Генерируем соседей
            for city in self._nearby_cities(current_city, radius_km=reachable_24h_km):
                for freight in self.city_index.get(city, []):
                    fid = freight['id']
                    if fid in visited:
                        continue
                    # time window check
                    loading_dt_str = freight.get('loading_dt')
                    if not loading_dt_str:
                        continue
                    try:
                        loading_dt = datetime.fromisoformat(loading_dt_str)
                    except Exception:
                        continue

                    empty_run = self._cached_or_approx_distance(current_city, freight['loading_city'])
                    if empty_run is None:
                        continue

                    arrive = current_time + timedelta(hours = empty_run / HOURLY_DRIVING_SPEED)
                    latest = arrive + timedelta(hours=24)
                    if loading_dt < arrive or loading_dt > latest:
                        continue

                    wait_h = max(0.0, (loading_dt - arrive).total_seconds() / 3600.0)
                    drive_h = (freight['distance'] / HOURLY_DRIVING_SPEED) if freight['distance'] is not None else 0.0
                    segment_time = wait_h + (empty_run / HOURLY_DRIVING_SPEED) + drive_h + SERVICE_TIME_HOURS

                    seg_revenue = (freight['revenue'] or 0.0)

                    new_total_time = total_time + segment_time
                    new_total_revenue = total_revenue + seg_revenue
                    new_total_distance = total_distance + empty_run + (freight['distance'] or 0.0)

                    rev_per_hour = new_total_revenue / new_total_time if new_total_time > 0 else 0.0

                    new_path = path + [{
                        'freight': freight,
                        'empty_run_before': empty_run,
                        'arrive_time': arrive.isoformat(),
                        'depart_time': (loading_dt + timedelta(hours=SERVICE_TIME_HOURS)).isoformat()
                    }]
                    new_visited = visited | {fid}
                    new_current_time = loading_dt + timedelta(hours = SERVICE_TIME_HOURS + drive_h)

                    heapq.heappush(queue, (
                        -rev_per_hour,
                        -new_total_revenue,
                        new_total_time,
                        next(self.counter),
                        new_path,
                        freight['unloading_city'],
                        new_visited,
                        new_total_distance,
                        new_current_time
                    ))

                    # Контроль размера очереди
                    if len(queue) > 120000:
                        queue = heapq.nsmallest(60000, queue)
                        heapq.heapify(queue)
                        logger.warning("Очередь > 120000, уменьшена до 60000")

        # Собираем лучшие
        routes = [item[-1] for item in best_routes]
        routes.sort(key=lambda r: (r.revenue_per_hour, r.revenue_per_km), reverse=True)
        return routes[:3]

    def _create_route(self, path: List[Dict[str, Any]], start_city: str, end_city: str) -> Optional[Route]:
        """Формирует маршрут с учётом порожняка от последней точки до end_city (гаража)."""
        if not path:
            return None
        segments: List[RouteSegment] = []
        total_distance = 0.0
        total_revenue = 0.0
        total_time = 0.0
        current_location = start_city

        try:
            for segment in path:
                freight_data = segment['freight']
                empty_run = segment['empty_run_before']
                arrive_time = segment.get('arrive_time')
                depart_time = segment.get('depart_time')

                drive_h = (freight_data['distance'] / HOURLY_DRIVING_SPEED) if freight_data['distance'] else 0.0
                segment_time = (empty_run / HOURLY_DRIVING_SPEED) + drive_h + SERVICE_TIME_HOURS

                seg_revenue = (freight_data['revenue'] or 0.0)

                total_distance += empty_run + (freight_data['distance'] or 0.0)
                total_revenue += seg_revenue
                total_time += segment_time
                current_location = freight_data['unloading_city']

                freight = Freight(
                    id=freight_data.get('id', ''),
                    loading_points=[freight_data.get('loading_city', '')],
                    unloading_points=[freight_data.get('unloading_city', '')],
                    distance=freight_data.get('distance', 0.0),
                    cargo=freight_data.get('cargo', ''),
                    weight=freight_data.get('weight', 0.0),
                    volume=freight_data.get('volume', 0.0),
                    loading_date=freight_data.get('loading_date', ''),
                    loading_dt=freight_data.get('loading_dt', None),
                    body_type=freight_data.get('body_type', ''),
                    revenue_rub=freight_data.get('revenue', 0.0)
                )

                segments.append(RouteSegment(
                    freight=freight,
                    empty_run_before=empty_run,
                    segment_time=segment_time,
                    arrive_time=arrive_time,
                    depart_time=depart_time
                ))

            # Финальный порожний пробег до гаража (end_city)
            empty_run_after = 0.0
            if current_location != end_city and end_city in self.city_coords and current_location in self.city_coords:
                c1 = self.city_coords[current_location]; c2 = self.city_coords[end_city]
                empty_run_after = approx_road_km(c1[0], c1[1], c2[0], c2[1])
                total_distance += empty_run_after
                total_time += empty_run_after / HOURLY_DRIVING_SPEED

            total_time_days = total_time / 24.0
            revenue_per_hour = total_revenue / total_time if total_time > 0 else 0.0

            return Route(
                segments=segments,
                total_distance=total_distance,
                total_revenue=total_revenue,
                revenue_per_hour=revenue_per_hour,
                estimated_time=total_time,
                total_time_days=total_time_days,
                empty_run_after=empty_run_after
            )
        except Exception as e:
            logger.error(f"Ошибка создания маршрута (время): {str(e)}")
            logger.debug(f"Путь: {path}")
            logger.debug(traceback.format_exc())
            return None
