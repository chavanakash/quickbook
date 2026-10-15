import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Schedule

logger = logging.getLogger(__name__)

# Approximate distances drive duration and price, so the data looks realistic.
CITY_DISTANCES_KM = {
    ("Delhi", "Mumbai"): 1400,
    ("Delhi", "Bengaluru"): 2150,
    ("Delhi", "Chennai"): 2180,
    ("Delhi", "Kolkata"): 1530,
    ("Delhi", "Hyderabad"): 1580,
    ("Mumbai", "Bengaluru"): 985,
    ("Mumbai", "Chennai"): 1330,
    ("Mumbai", "Kolkata"): 1970,
    ("Mumbai", "Hyderabad"): 710,
    ("Bengaluru", "Chennai"): 350,
    ("Bengaluru", "Kolkata"): 1870,
    ("Bengaluru", "Hyderabad"): 570,
    ("Chennai", "Kolkata"): 1660,
    ("Chennai", "Hyderabad"): 630,
    ("Kolkata", "Hyderabad"): 1490,
}
AIRLINES = [("SkyJet", "SJ"), ("AirNova", "AN"), ("BlueWings", "BW")]
FLIGHT_DEPARTURES = ["06:15", "13:40", "20:05"]
TRAIN_DEPARTURES = [("07:00", "Express"), ("18:30", "Superfast")]


def build_schedules() -> list[Schedule]:
    schedules = []
    route_no = 100
    for (city_a, city_b), km in CITY_DISTANCES_KM.items():
        for origin, destination in ((city_a, city_b), (city_b, city_a)):
            for i, departure in enumerate(FLIGHT_DEPARTURES):
                airline, prefix = AIRLINES[(route_no + i) % len(AIRLINES)]
                schedules.append(
                    Schedule(
                        mode="flight",
                        code=f"{prefix}-{route_no * 10 + i}",
                        operator=airline,
                        origin=origin,
                        destination=destination,
                        departure_time=departure,
                        duration_minutes=round(45 + km / 12),
                        price=Decimal(round(1800 + km * 3.1 + i * 350)),
                    )
                )
            for i, (departure, train_type) in enumerate(TRAIN_DEPARTURES):
                schedules.append(
                    Schedule(
                        mode="train",
                        code=str(12000 + route_no * 2 + i),
                        operator=f"{origin} - {destination} {train_type}",
                        origin=origin,
                        destination=destination,
                        departure_time=departure,
                        duration_minutes=round(km / 62 * 60) + 20,
                        price=Decimal(round(250 + km * 0.9 + i * 120)),
                    )
                )
            route_no += 1
    return schedules


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(Schedule)):
        return
    db.add_all(build_schedules())
    try:
        db.commit()
        logger.info("seeded schedules")
    except IntegrityError:
        # Another replica seeded at the same time (unique schedule codes protect us).
        db.rollback()
