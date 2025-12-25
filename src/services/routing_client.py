from typing import List, Tuple, Optional
import os, json, math, hashlib
import httpx

class RoutingError(Exception):
    pass

class RoutingClient:
    """
    Универсальный клиент для OSRM/Valhalla с безопасным fallback на Haversine.
    Координаты в методах — [(lat, lon), ...].
    """
    def __init__(self) -> None:
        self.enabled = os.getenv("ROUTING_ENABLED", "1") == "1"
        self.backend = os.getenv("ROUTING_BACKEND", "osrm").lower()  # osrm|valhalla
        self.base_url = os.getenv("ROUTING_BASE_URL", "http://localhost:5000")
        self.profile = os.getenv("ROUTING_OSRM_PROFILE", "truck")
        self.timeout = float(os.getenv("ROUTING_TIMEOUT_SEC", "8"))
        self.haversine_fallback = True

    async def route(self, coords: List[Tuple[float, float]]) -> dict:
        """
        Возвращает dict: {distance_m, duration_s, polyline?, backend}
        """
        if not self.enabled:
            raise RoutingError("Routing disabled (ROUTING_ENABLED=0)")
        if len(coords) < 2:
            raise RoutingError("Need at least 2 coordinates")

        try:
            if self.backend == "osrm":
                path = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in coords])  # OSRM: lon,lat
                url = f"{self.base_url}/route/v1/{self.profile}/{path}"
                params = {
                    "overview": "full",
                    "geometries": "polyline6",
                    "annotations": "duration,distance",
                    "steps": "false",
                    "alternatives": "false",
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.get(url, params=params)
                    r.raise_for_status()
                    data = r.json()
                routes = data.get("routes") or []
                if not routes:
                    raise RoutingError("OSRM: no routes")
                route = routes[0]
                return {
                    "distance_m": float(route["distance"]),
                    "duration_s": float(route["duration"]),
                    "polyline": route.get("geometry"),
                    "backend": "osrm",
                }

            elif self.backend == "valhalla":
                url = f"{self.base_url}/route"
                locations = [{"lat": lat, "lon": lon} for lat, lon in coords]
                body = {
                    "locations": locations,
                    "costing": "truck",
                    "directions_options": {"units": "kilometers"},
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.post(url, json=body)
                    r.raise_for_status()
                    data = r.json()
                trip = data.get("trip") or {}
                summary = trip.get("summary") or {}
                legs = trip.get("legs") or []
                shape = (legs[0].get("shape") if legs else None)
                return {
                    "distance_m": float(summary.get("length", 0.0)) * 1000.0,
                    "duration_s": float(summary.get("time", 0.0)),
                    "polyline": shape,
                    "backend": "valhalla",
                }

            else:
                raise RoutingError(f"Unknown backend: {self.backend}")

        except Exception:
            if not self.haversine_fallback:
                raise
            d_km = self._haversine_path_km(coords)
            duration_s = (d_km / 60.0) * 3600.0  # грубо 60 км/ч
            return {
                "distance_m": d_km * 1000.0,
                "duration_s": duration_s,
                "polyline": None,
                "backend": "haversine",
            }

    async def table(
        self,
        sources: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
    ) -> dict:
        """
        Возвращает матрицы dist/dur или делает грубую Haversine-оценку.
        """
        if self.backend == "osrm":
            coords = sources + destinations
            path = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in coords])
            src_idx = list(range(0, len(sources)))
            dst_idx = list(range(len(sources), len(coords)))
            url = f"{self.base_url}/table/v1/{self.profile}/{path}"
            params = {
                "annotations": "distance,duration",
                "sources": ";".join(map(str, src_idx)),
                "destinations": ";".join(map(str, dst_idx)),
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
            return {
                "distances": data.get("distances"),
                "durations": data.get("durations"),
                "backend": "osrm",
            }

        if self.backend == "valhalla":
            url = f"{self.base_url}/matrix"
            locations = [{"lat": lat, "lon": lon} for lat, lon in (sources + destinations)]
            body = {
                "locations": locations,
                "sources": list(range(0, len(sources))),
                "targets": list(range(len(sources), len(sources) + len(destinations))),
                "costing": "truck",
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=body)
                r.raise_for_status()
                data = r.json()
            return {
                "distances": data.get("distance_matrix"),
                "durations": data.get("time_matrix"),
                "backend": "valhalla",
            }

        # fallback: Haversine-аппроксимация
        distances = [[self._haversine_km(a, b) * 1000.0 for b in destinations] for a in sources]
        durations = [[(d_km / 60.0) * 3600.0 for d_km in [dist / 1000.0 for dist in row]] for row in distances]
        return {"distances": distances, "durations": durations, "backend": "haversine"}

    # --- helpers ---
    def _haversine_km(self, a: Tuple[float, float], b: Tuple[float, float]) -> float:
        lat1, lon1 = a
        lat2, lon2 = b
        R = 6371.0088
        from math import radians, sin, cos, asin, sqrt
        phi1, phi2 = radians(lat1), radians(lat2)
        dphi, dl = radians(lat2 - lat1), radians(lon2 - lon1)
        h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dl / 2) ** 2
        return 2 * R * asin(sqrt(h))

    def _haversine_path_km(self, coords: List[Tuple[float, float]]) -> float:
        s = 0.0
        for i in range(1, len(coords)):
            s += self._haversine_km(coords[i - 1], coords[i])
        return s
