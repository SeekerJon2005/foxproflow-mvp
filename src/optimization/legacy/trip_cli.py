
from __future__ import annotations
from datetime import datetime
import sys

from src.data_layer.trip_repo import migrate, create_trip, get_trip
from src.data_layer.gps_feed import set_current_position, get_current_city
from src.optimization.trip_manager import replan_trip

def prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return ""

def main():
    migrate()
    print("=== FoxProFlow: Trip CLI (rolling horizon) ===")
    mode = prompt("1) Создать новый рейс  2) Продолжить рейс [1/2]: ") or "2"

    if mode == "1":
        vehicle_id = prompt("ID авто (госномер/код): ")
        garage = prompt("Город гаража: ")
        start_dt = prompt("Старт (ISO, Enter=сейчас): ") or datetime.utcnow().isoformat(timespec="seconds")
        end_target_dt = prompt("Целевая дата завершения рейса (ISO, Enter=пропустить): ") or None
        trip_id = create_trip(vehicle_id=vehicle_id, garage_city=garage, start_dt=start_dt, end_target_dt=end_target_dt)
        print(f"Создан trip_id={trip_id}. Теперь можно его продолжать в режиме 2).")
        return

    trip_id_str = prompt("trip_id (число): ")
    try:
        trip_id = int(trip_id_str)
    except Exception:
        print("Нужно ввести число (trip_id).")
        sys.exit(2)

    trip = get_trip(trip_id)
    if not trip:
        print(f"Trip {trip_id} не найден.")
        sys.exit(2)

    city = prompt(f"Текущий город (Enter=GPS/гараж): ")
    if city:
        # для теста записываем GPS-точку
        set_current_position(trip.vehicle_id, city=city)

    print("Пересчитываем план...")
    res = replan_trip(trip_id)
    if res:
        print(f"Новый план принят: revenue={res.revenue:.0f}, hours={res.hours:.1f}, km={res.km:.0f}, RUR/day={res.revenue_per_day:.0f}")
    else:
        print("Новый план не принят (нет улучшения или нет маршрутов).")

if __name__ == "__main__":
    main()
