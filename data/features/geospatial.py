import math
from datetime import datetime


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geo_velocity_kmh(lat1: float, lon1: float, t1: datetime, lat2: float, lon2: float, t2: datetime) -> float:
    distance = haversine(lat1, lon1, lat2, lon2)
    hours = abs((t2 - t1).total_seconds()) / 3600.0
    return distance / hours if hours > 0 else 0.0
