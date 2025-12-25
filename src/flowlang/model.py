from dataclasses import dataclass
from typing import Optional

@dataclass
class AutoplanPlanConfig:
    name: str                      # произвольное имя плана
    region: Optional[str] = None   # "RU-MOW" и т.п.
    limit: int = 50
    window_minutes: int = 240
    confirm_horizon_hours: int = 96
    freeze_hours_before: int = 2

    rpm_floor_min: Optional[int] = None
    p_arrive_min: Optional[float] = None

    dry: bool = False
    chain_every_min: Optional[int] = None  # для будущей интеграции с beat
