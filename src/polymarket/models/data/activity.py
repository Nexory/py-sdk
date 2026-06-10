from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast

from pydantic import Field, field_validator

from polymarket.errors import UnexpectedResponseError
from polymarket.models.base import BaseModel
from polymarket.models.gamma.common import parse_epoch_seconds_optional, parse_optional_decimal
from polymarket.models.types import (
    CtfConditionId,
    TokenId,
    validate_ctf_condition_id,
    validate_optional_ctf_condition_id,
)
from polymarket.types import EvmAddress, TransactionHash


class Trade(BaseModel):
    wallet: EvmAddress | None = Field(default=None, validation_alias="proxyWallet")
    token_id: TokenId | None = Field(default=None, validation_alias="asset")
    condition_id: CtfConditionId | None = Field(default=None, validation_alias="conditionId")
    side: Literal["BUY", "SELL"] | None = None
    size: Decimal | None = None
    price: Decimal | None = None
    timestamp: datetime | None = None
    title: str | None = None
    slug: str | None = None
    icon: str | None = None
    event_slug: str | None = Field(default=None, validation_alias="eventSlug")
    outcome: str | None = None
    outcome_index: int | None = Field(default=None, validation_alias="outcomeIndex")
    name: str | None = None
    pseudonym: str | None = None
    bio: str | None = None
    profile_image: str | None = Field(default=None, validation_alias="profileImage")
    profile_image_optimized: str | None = Field(
        default=None, validation_alias="profileImageOptimized"
    )
    transaction_hash: TransactionHash | None = Field(
        default=None, validation_alias="transactionHash"
    )

    @field_validator("condition_id", mode="before")
    @classmethod
    def _validate_condition_id(cls, value: object) -> CtfConditionId | None:
        return validate_optional_ctf_condition_id(value)

    @field_validator("size", "price", mode="before")
    @classmethod
    def _parse_decimal(cls, value: object) -> Decimal | None:
        return parse_optional_decimal(value)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> datetime | None:
        return parse_epoch_seconds_optional(value)


ActivityType = Literal[
    "TRADE",
    "SPLIT",
    "MERGE",
    "REDEEM",
    "REWARD",
    "CONVERSION",
    "MAKER_REBATE",
    "REFERRAL_REWARD",
    "YIELD",
]


class _KnownActivityBase(BaseModel):
    wallet: EvmAddress = Field(validation_alias="proxyWallet")
    timestamp: datetime
    transaction_hash: TransactionHash = Field(validation_alias="transactionHash")
    name: str | None = None
    pseudonym: str | None = None
    bio: str | None = None
    profile_image: str | None = Field(default=None, validation_alias="profileImage")
    profile_image_optimized: str | None = Field(
        default=None, validation_alias="profileImageOptimized"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> datetime | None:
        return parse_epoch_seconds_optional(value)

    def _repr_html_(self) -> str:
        from polymarket._jupyter import card, safe_html_repr, truncate_mid

        @safe_html_repr
        def render(self: _KnownActivityBase) -> str:
            title = type(self).__name__
            rows: list[tuple[str, str]] = [
                ("timestamp", self.timestamp.isoformat()),
                ("tx", truncate_mid(self.transaction_hash)),
                ("wallet", truncate_mid(self.wallet)),
            ]
            for attr in ("amount", "shares", "price", "side", "outcome", "title"):
                value = getattr(self, attr, None)
                if value is not None:
                    rows.append((attr, str(value)))
            return card(title, rows=rows)

        return render(self)


class TradeActivity(_KnownActivityBase):
    type: Literal["TRADE"]
    condition_id: CtfConditionId = Field(validation_alias="conditionId")
    token_id: TokenId = Field(validation_alias="asset")
    side: Literal["BUY", "SELL"]
    shares: Decimal = Field(validation_alias="size")
    amount: Decimal
    price: Decimal
    outcome: str
    outcome_index: int = Field(validation_alias="outcomeIndex")
    title: str
    slug: str
    icon: str | None = None
    event_slug: str = Field(validation_alias="eventSlug")

    @field_validator("condition_id", mode="before")
    @classmethod
    def _validate_condition_id(cls, value: object) -> CtfConditionId:
        return validate_ctf_condition_id(value)

    @field_validator("shares", "amount", "price", mode="before")
    @classmethod
    def _parse_decimal(cls, value: object) -> Decimal | None:
        return parse_optional_decimal(value)


class _MarketEventActivity(_KnownActivityBase):
    condition_id: CtfConditionId = Field(validation_alias="conditionId")
    amount: Decimal
    title: str
    slug: str
    icon: str | None = None
    event_slug: str = Field(validation_alias="eventSlug")

    @field_validator("condition_id", mode="before")
    @classmethod
    def _validate_condition_id(cls, value: object) -> CtfConditionId:
        return validate_ctf_condition_id(value)

    @field_validator("amount", mode="before")
    @classmethod
    def _parse_decimal(cls, value: object) -> Decimal | None:
        return parse_optional_decimal(value)


class SplitActivity(_MarketEventActivity):
    type: Literal["SPLIT"]


class MergeActivity(_MarketEventActivity):
    type: Literal["MERGE"]


class RedeemActivity(_MarketEventActivity):
    type: Literal["REDEEM"]


class ConversionActivity(_MarketEventActivity):
    type: Literal["CONVERSION"]


class _AccountCreditActivity(_KnownActivityBase):
    amount: Decimal

    @field_validator("amount", mode="before")
    @classmethod
    def _parse_decimal(cls, value: object) -> Decimal | None:
        return parse_optional_decimal(value)


class RewardActivity(_AccountCreditActivity):
    type: Literal["REWARD"]


class MakerRebateActivity(_AccountCreditActivity):
    type: Literal["MAKER_REBATE"]


class ReferralRewardActivity(_AccountCreditActivity):
    type: Literal["REFERRAL_REWARD"]


class YieldActivity(_AccountCreditActivity):
    type: Literal["YIELD"]


class UnknownActivity(BaseModel):
    type: str
    wallet: EvmAddress | None = Field(default=None, validation_alias="proxyWallet")
    timestamp: datetime | None = None
    transaction_hash: TransactionHash | None = Field(
        default=None, validation_alias="transactionHash"
    )
    name: str | None = None
    pseudonym: str | None = None
    bio: str | None = None
    profile_image: str | None = Field(default=None, validation_alias="profileImage")
    profile_image_optimized: str | None = Field(
        default=None, validation_alias="profileImageOptimized"
    )
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> datetime | None:
        return parse_epoch_seconds_optional(value)

    def _repr_html_(self) -> str:
        from polymarket._jupyter import card, safe_html_repr, truncate_mid

        @safe_html_repr
        def render(self: UnknownActivity) -> str:
            title = f"UnknownActivity  ·  {self.type or '(no type)'}"
            rows: list[tuple[str, str]] = []
            if self.timestamp is not None:
                rows.append(("timestamp", self.timestamp.isoformat()))
            if self.transaction_hash is not None:
                rows.append(("tx", truncate_mid(self.transaction_hash)))
            rows.append(("raw fields", str(len(self.raw))))
            return card(title, rows=rows)

        return render(self)


Activity = (
    TradeActivity
    | SplitActivity
    | MergeActivity
    | RedeemActivity
    | ConversionActivity
    | RewardActivity
    | MakerRebateActivity
    | ReferralRewardActivity
    | YieldActivity
    | UnknownActivity
)


_KNOWN_ACTIVITY_TYPES: dict[str, type[_KnownActivityBase]] = {
    "TRADE": TradeActivity,
    "SPLIT": SplitActivity,
    "MERGE": MergeActivity,
    "REDEEM": RedeemActivity,
    "CONVERSION": ConversionActivity,
    "REWARD": RewardActivity,
    "MAKER_REBATE": MakerRebateActivity,
    "REFERRAL_REWARD": ReferralRewardActivity,
    "YIELD": YieldActivity,
}


def parse_activity(payload: object) -> Activity:
    if not isinstance(payload, dict):
        raise UnexpectedResponseError("Activity payload must be an object.")
    data = _normalize_activity_payload(cast(dict[str, Any], payload))
    activity_type = data.get("type")
    if isinstance(activity_type, str) and activity_type in _KNOWN_ACTIVITY_TYPES:
        cls = _KNOWN_ACTIVITY_TYPES[activity_type]
        return cast(Activity, cls.parse_response(data))
    raw_type = activity_type if isinstance(activity_type, str) else ""
    return UnknownActivity.parse_response({**data, "type": raw_type, "raw": dict(data)})


def parse_activities(payload: object) -> tuple[Activity, ...]:
    if not isinstance(payload, list):
        raise UnexpectedResponseError("Activity list payload must be a list.")
    return tuple(parse_activity(item) for item in cast(list[object], payload))


def _normalize_activity_payload(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)

    if normalized.get("outcomeIndex") == 999:
        normalized.pop("outcomeIndex", None)

    for sentinel_key in ("conditionId", "asset", "side", "outcome"):
        if normalized.get(sentinel_key) == "":
            normalized.pop(sentinel_key, None)

    if "amount" not in normalized:
        amount = normalized.get("usdcSize")
        if amount is None:
            amount = normalized.get("size")
        if amount is not None:
            normalized["amount"] = amount

    return normalized


__all__ = [
    "Activity",
    "ActivityType",
    "ConversionActivity",
    "MakerRebateActivity",
    "MergeActivity",
    "RedeemActivity",
    "ReferralRewardActivity",
    "RewardActivity",
    "SplitActivity",
    "Trade",
    "TradeActivity",
    "UnknownActivity",
    "YieldActivity",
    "parse_activities",
    "parse_activity",
]
