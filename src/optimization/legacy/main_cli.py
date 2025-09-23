
import datetime
from src.optimization.legacy.route_builder_time import TimeAwareRouteBuilder
from src.data_layer.database import load_suitable_freights, init_database
def main():
    init_database()
    start_city = input("Город гаража (домашняя база): ").strip()
    end_city = input("Конечная цель (пусто = вернуться в гараж): ").strip() or start_city
    max_weight = float(input("Макс. грузоподъемность (тонн): ").strip())
    max_volume = float(input("Макс. объем (м³): ").strip())
    trailer_type = input("Тип прицепа: ").strip().lower()
    start_time = datetime.datetime.now()
    freight_rows = load_suitable_freights(max_weight, max_volume, trailer_type)
    builder = TimeAwareRouteBuilder(freight_rows)
    routes = builder.build_routes(start_city, end_city, start_time, max_depth=7, max_routes=10)
    for r in routes:
        rev_per_km = (r.total_revenue / r.total_distance) if r.total_distance > 0 else 0.0
        rev_per_day = r.total_revenue / r.total_time_days if r.total_time_days > 0 else 0.0
        print(f"Маршрут: {rev_per_km:.0f} руб/км, {r.revenue_per_hour:.0f} руб/час, {rev_per_day:.0f} руб/день")
if __name__ == "__main__":
    main()
