from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from .models import RFQStatus


class AuctionConfigIn(BaseModel):
    trigger_window_minutes: int = Field(ge=1, le=120)
    extension_minutes: int = Field(ge=1, le=120)
    trigger_on_bid: bool = True
    trigger_on_any_rank_change: bool = False
    trigger_on_l1_change: bool = True


class AuctionConfigOut(AuctionConfigIn):
    class Config:
        from_attributes = True


class RFQCreate(BaseModel):
    reference_id: str
    name: str
    pickup_date: datetime
    bid_start: datetime
    bid_close: datetime
    forced_close: datetime
    config: AuctionConfigIn

    @model_validator(mode="after")
    def _validate(self):
        if self.bid_close <= self.bid_start:
            raise ValueError("bid_close must be after bid_start")
        if self.forced_close <= self.bid_close:
            raise ValueError("forced_close must be after bid_close")
        return self


class BidCreate(BaseModel):
    supplier_name: str = Field(min_length=1)
    freight_charge: float = Field(ge=0)
    origin_charge: float = Field(ge=0)
    destination_charge: float = Field(ge=0)
    transit_days: int = Field(ge=0)
    quote_valid_until: datetime


class BidOut(BaseModel):
    id: int
    supplier_name: str
    freight_charge: float
    origin_charge: float
    destination_charge: float
    total_price: float
    transit_days: int
    quote_valid_until: datetime
    created_at: datetime
    rank: Optional[int] = None

    class Config:
        from_attributes = True


class ActivityLogOut(BaseModel):
    id: int
    event_type: str
    reason: Optional[str]
    old_close: Optional[datetime]
    new_close: Optional[datetime]
    extra: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class RFQOut(BaseModel):
    id: int
    reference_id: str
    name: str
    pickup_date: datetime
    bid_start: datetime
    original_close: datetime
    current_close: datetime
    forced_close: datetime
    status: RFQStatus
    lowest_bid: Optional[float] = None

    class Config:
        from_attributes = True


class RFQDetail(RFQOut):
    config: AuctionConfigOut
    bids: list[BidOut]
    logs: list[ActivityLogOut]