from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from inercia.config import get_settings


@dataclass(frozen=True)
class BidRate:
    amount: float
    bid_type: Literal["hourly", "fixed"]


class RateJobDetail(Protocol):
    job_type: Literal["hourly", "fixed"]
    budget_min: Optional[float]
    budget_max: Optional[float]
    hourly_rate_min: Optional[float]
    hourly_rate_max: Optional[float]


def compute_bid_rate(
    job_detail: RateJobDetail,
    floor_hourly_rate: Optional[float] = None,
    floor_fixed_rate: Optional[float] = None,
) -> BidRate:
    settings = get_settings()
    hourly_floor = floor_hourly_rate if floor_hourly_rate is not None else settings.floor_hourly_rate
    fixed_floor = floor_fixed_rate if floor_fixed_rate is not None else settings.floor_fixed_rate
    if job_detail.job_type == "fixed":
        budget = job_detail.budget_max or job_detail.budget_min or fixed_floor
        return BidRate(amount=round(max(float(budget), fixed_floor), 2), bid_type="fixed")
    hourly = job_detail.hourly_rate_max or job_detail.hourly_rate_min or hourly_floor
    return BidRate(amount=round(max(float(hourly), hourly_floor), 2), bid_type="hourly")


__all__ = ["BidRate", "RateJobDetail", "compute_bid_rate"]
