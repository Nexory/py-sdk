from decimal import Decimal

import pytest

from polymarket import (
    ConversionActivity,
    MakerRebateActivity,
    MergeActivity,
    RedeemActivity,
    ReferralRewardActivity,
    RewardActivity,
    SplitActivity,
    TradeActivity,
    UnknownActivity,
    YieldActivity,
)
from polymarket.errors import UnexpectedResponseError
from polymarket.models.data.activity import parse_activities, parse_activity

_CONDITION_ID = "0x5c19f205507ce03ff5f3be08a8090a5969ea6870cc07b902a4ca2e61dfe48fdd"


def _trade_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "TRADE",
        "proxyWallet": "0xWALLET",
        "timestamp": 1_700_000_000,
        "transactionHash": "0xHASH",
        "conditionId": _CONDITION_ID,
        "asset": "TOKEN",
        "side": "BUY",
        "size": "10",
        "price": "0.42",
        "outcome": "Yes",
        "outcomeIndex": 0,
        "title": "Some market",
        "slug": "some-market",
        "icon": "https://example.test/icon.png",
        "eventSlug": "some-event",
    }
    base.update(overrides)
    return base


def _market_event_payload(activity_type: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": activity_type,
        "proxyWallet": "0xWALLET",
        "timestamp": 1_700_000_000,
        "transactionHash": "0xHASH",
        "conditionId": _CONDITION_ID,
        "size": "5",
        "title": "T",
        "slug": "t",
        "icon": "i",
        "eventSlug": "e",
    }
    base.update(overrides)
    return base


def _credit_payload(activity_type: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": activity_type,
        "proxyWallet": "0xWALLET",
        "timestamp": 1_700_000_000,
        "transactionHash": "0xHASH",
        "size": "0.25",
    }
    base.update(overrides)
    return base


def test_parse_trade_activity() -> None:
    activity = parse_activity(_trade_payload())
    assert isinstance(activity, TradeActivity)
    assert activity.wallet == "0xWALLET"
    assert activity.condition_id == _CONDITION_ID
    assert activity.token_id == "TOKEN"
    assert activity.side == "BUY"
    assert activity.shares == Decimal("10")
    assert activity.price == Decimal("0.42")
    assert activity.amount == Decimal("10")
    assert activity.outcome_index == 0


def test_parse_trade_activity_uses_usdc_size_when_present() -> None:
    activity = parse_activity(
        _trade_payload(side="SELL", outcomeIndex=1, usdcSize="4.20", outcome="No")
    )
    assert isinstance(activity, TradeActivity)
    assert activity.amount == Decimal("4.20")


def test_trade_missing_required_field_raises_unexpected_response() -> None:
    payload = _trade_payload()
    del payload["price"]
    with pytest.raises(UnexpectedResponseError):
        parse_activity(payload)


def test_trade_missing_wallet_raises_unexpected_response() -> None:
    payload = _trade_payload()
    del payload["proxyWallet"]
    with pytest.raises(UnexpectedResponseError):
        parse_activity(payload)


def test_trade_missing_transaction_hash_raises_unexpected_response() -> None:
    payload = _trade_payload()
    del payload["transactionHash"]
    with pytest.raises(UnexpectedResponseError):
        parse_activity(payload)


def test_outcome_index_999_sentinel_is_dropped() -> None:
    activity = parse_activity(_credit_payload("REWARD", outcomeIndex=999))
    assert isinstance(activity, RewardActivity)
    assert activity.amount == Decimal("0.25")


def test_empty_string_sentinels_drop_to_none_on_trade_raises() -> None:
    payload = _trade_payload(conditionId="", asset="", side="", outcome="")
    with pytest.raises(UnexpectedResponseError):
        parse_activity(payload)


def test_market_event_variants_parse() -> None:
    for activity_type, expected_class in [
        ("SPLIT", SplitActivity),
        ("MERGE", MergeActivity),
        ("REDEEM", RedeemActivity),
        ("CONVERSION", ConversionActivity),
    ]:
        activity = parse_activity(_market_event_payload(activity_type))
        assert isinstance(activity, expected_class)
        assert activity.amount == Decimal("5")


def test_market_event_missing_condition_raises() -> None:
    payload = _market_event_payload("SPLIT")
    del payload["conditionId"]
    with pytest.raises(UnexpectedResponseError):
        parse_activity(payload)


def test_account_credit_variants_parse() -> None:
    for activity_type, expected_class in [
        ("REWARD", RewardActivity),
        ("MAKER_REBATE", MakerRebateActivity),
        ("REFERRAL_REWARD", ReferralRewardActivity),
        ("YIELD", YieldActivity),
    ]:
        activity = parse_activity(_credit_payload(activity_type))
        assert isinstance(activity, expected_class)
        assert activity.amount == Decimal("0.25")


def test_credit_missing_amount_raises() -> None:
    payload = _credit_payload("REWARD")
    del payload["size"]
    with pytest.raises(UnexpectedResponseError):
        parse_activity(payload)


def test_unknown_type_falls_back() -> None:
    payload = {
        "type": "BRAND_NEW_TYPE",
        "proxyWallet": "0xWALLET",
        "timestamp": 1_700_000_000,
        "transactionHash": "0xHASH",
    }
    activity = parse_activity(payload)
    assert isinstance(activity, UnknownActivity)
    assert activity.type == "BRAND_NEW_TYPE"
    assert activity.raw["type"] == "BRAND_NEW_TYPE"


def test_unknown_activity_is_permissive() -> None:
    activity = parse_activity({"type": "BRAND_NEW_TYPE"})
    assert isinstance(activity, UnknownActivity)
    assert activity.wallet is None
    assert activity.timestamp is None
    assert activity.transaction_hash is None


def test_missing_type_falls_back_to_unknown() -> None:
    activity = parse_activity({"proxyWallet": "0xWALLET"})
    assert isinstance(activity, UnknownActivity)
    assert activity.type == ""


def test_non_dict_payload_raises_unexpected_response() -> None:
    with pytest.raises(UnexpectedResponseError):
        parse_activity("not a dict")  # type: ignore[arg-type]


def test_parse_activities_non_list_raises_unexpected_response() -> None:
    with pytest.raises(UnexpectedResponseError):
        parse_activities({"not": "a list"})


def test_parse_activities_handles_list() -> None:
    payload = [
        _trade_payload(),
        _credit_payload("REWARD"),
    ]
    activities = parse_activities(payload)
    assert len(activities) == 2
    assert isinstance(activities[0], TradeActivity)
    assert isinstance(activities[1], RewardActivity)


# --- Finding D: icon: null tolerance ---


def test_trade_activity_icon_null_parses_and_is_none() -> None:
    """Data API returns icon: null for sparse historical rows (finding D).
    TradeActivity must accept None instead of crashing with a ValidationError.
    """
    activity = parse_activity(_trade_payload(icon=None))
    assert isinstance(activity, TradeActivity)
    assert activity.icon is None


def test_split_activity_icon_null_parses_and_is_none() -> None:
    """_MarketEventActivity (and its subclasses, e.g. SplitActivity) must
    also accept icon: null for sparse historical rows (finding D).
    """
    activity = parse_activity(_market_event_payload("SPLIT", icon=None))
    assert isinstance(activity, SplitActivity)
    assert activity.icon is None
