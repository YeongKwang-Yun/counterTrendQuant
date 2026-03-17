from __future__ import annotations

from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, TypeAdapter, field_validator


class BaseTradeEvent(BaseModel):
    sort: Literal["trade"]
    exchange: Literal["bybit"]
    time_frame: Literal["4h"]
    message_type: str
    update_gubun: str
    ticker: str
    side: Literal["Buy", "Sell"]
    trade_id: str
    order_time: str | None = None
    tbc_gubun: Literal["tbc", "n"] | None = "n"

    @field_validator("ticker", mode="before")
    @classmethod
    def clean_ticker(cls, v):
        if v is None:
            return ""
        result = str(v).strip()
        if " " in result:
            result = result.split()[0]
        if result.endswith(".P"):
            result = result[:-2]
        return result

    @property
    def stream_key(self) -> str:
        return f"{self.exchange}:{self.time_frame}:{self.ticker}"


class OpenOrderEvent(BaseTradeEvent):
    message_type: Literal["open_order"]
    entry_price: float
    target_price_1: float
    stop_loss: float
    qty: float


class UpdateSlEvent(BaseTradeEvent):
    message_type: Literal["update_sl"]
    update_gubun: Literal["tp1_hit", "sl_hit"]
    entry_price: float | None = None
    target_price_1: float | None = None
    stop_loss: float | None = None
    qty: float | None = None


TradeEvent = Annotated[
    Union[OpenOrderEvent, UpdateSlEvent],
    Field(discriminator="message_type")
]

trade_event_adapter = TypeAdapter(TradeEvent)


def parse_trade_event(payload: dict) -> OpenOrderEvent | UpdateSlEvent:
    return trade_event_adapter.validate_python(payload)