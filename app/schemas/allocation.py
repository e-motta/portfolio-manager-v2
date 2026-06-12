from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class SuggestionMode(str, Enum):
    BUY_ONLY = "buy_only"
    BUY_AND_SELL = "buy_and_sell"


class SuggestionItem(BaseModel):
    id: UUID
    label: str
    current_value: Decimal
    current_weight: Decimal
    current_weight_allocation: Decimal | None = None
    target_weight: Decimal
    target_weight_allocation: Decimal | None = None
    ideal_value: Decimal
    delta: Decimal
    action: str


class TypeSuggestionRequest(BaseModel):
    mode: SuggestionMode = SuggestionMode.BUY_ONLY
    new_cash: Decimal = Field(default=Decimal("0"), ge=0)


class SecuritySuggestionRequest(BaseModel):
    mode: SuggestionMode = SuggestionMode.BUY_ONLY
    new_cash: Decimal = Field(default=Decimal("0"), ge=0)
