from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from app.models.asset_type import AssetType
from app.models.symbol_target import SymbolTarget
from app.schemas.allocation import SuggestionItem, SuggestionMode
from app.services.securities import ConsolidatedSecurity, bucket_value_from_lots


def round_decimal(value: Decimal, places: int = 8) -> Decimal:
    quantizer = Decimal("1").scaleb(-places)
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def _action_from_delta(delta: Decimal) -> str:
    if delta > 0:
        return "buy"
    if delta < 0:
        return "sell"
    return "hold"


def _apply_mode(delta: Decimal, mode: SuggestionMode) -> Decimal:
    if mode == SuggestionMode.BUY_ONLY:
        return max(delta, Decimal("0"))
    return delta


def _scale_buys(
    items: list[SuggestionItem], new_cash: Decimal
) -> list[SuggestionItem]:
    if new_cash <= 0:
        return [
            item.model_copy(update={"delta": Decimal("0"), "action": "hold"})
            if item.delta > 0
            else item
            for item in items
        ]

    total_buys = sum(item.delta for item in items if item.delta > 0)
    if total_buys <= new_cash or total_buys <= 0:
        return items

    ratio = new_cash / total_buys
    scaled: list[SuggestionItem] = []
    for item in items:
        if item.delta > 0:
            scaled_delta = round_decimal(item.delta * ratio, 2)
            scaled.append(
                item.model_copy(
                    update={
                        "delta": scaled_delta,
                        "action": _action_from_delta(scaled_delta),
                    }
                )
            )
        else:
            scaled.append(item)
    return scaled


def has_type_target(asset_type: AssetType) -> bool:
    return asset_type.target_pct is not None


def weighted_asset_types(asset_types: list[AssetType]) -> list[AssetType]:
    return [asset_type for asset_type in asset_types if has_type_target(asset_type)]


def allocation_target_total(asset_types: list[AssetType]) -> Decimal:
    return sum(
        (
            asset_type.target_pct
            for asset_type in weighted_asset_types(asset_types)
            if asset_type.target_pct is not None
        ),
        start=Decimal("0"),
    )


def allocation_sleeve_value(
    asset_types: list[AssetType],
    values: dict[UUID, Decimal] | None = None,
) -> Decimal:
    portfolio_values = values or {
        asset_type.id: get_effective_type_value(asset_type) for asset_type in asset_types
    }
    return sum(
        (portfolio_values[asset_type.id] for asset_type in weighted_asset_types(asset_types)),
        start=Decimal("0"),
    )


def weight_of_total(value: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return value / total


def weight_of_allocation_sleeve(value: Decimal, sleeve_total: Decimal) -> Decimal | None:
    if sleeve_total <= 0:
        return None
    return value / sleeve_total


def normalize_allocation_target(target: Decimal, target_total: Decimal) -> Decimal | None:
    if target_total <= 0:
        return None
    return target / target_total


def get_effective_type_value(asset_type: AssetType) -> Decimal:
    if asset_type.is_exchange_traded:
        return bucket_value_from_lots(asset_type.securities)
    investments = getattr(asset_type, "investments", None) or []
    return sum((item.current_value for item in investments), start=Decimal("0"))


def calculate_type_suggestions(
    asset_types: list[AssetType],
    mode: SuggestionMode,
    new_cash: Decimal = Decimal("0"),
) -> list[SuggestionItem]:
    portfolio_values = {
        asset_type.id: get_effective_type_value(asset_type) for asset_type in asset_types
    }
    total_portfolio = sum(portfolio_values.values(), start=Decimal("0"))
    total_value = total_portfolio + new_cash

    sleeve_value = allocation_sleeve_value(asset_types, portfolio_values)
    target_total = allocation_target_total(asset_types)

    items: list[SuggestionItem] = []
    for asset_type in weighted_asset_types(asset_types):
        current_value = portfolio_values[asset_type.id]
        target_weight = asset_type.target_pct
        assert target_weight is not None
        ideal_value = round_decimal(total_value * target_weight, 2)
        current_weight = round_decimal(
            weight_of_total(current_value, total_portfolio), 4
        )
        current_weight_allocation = weight_of_allocation_sleeve(
            current_value, sleeve_value
        )
        target_weight_allocation = normalize_allocation_target(
            target_weight, target_total
        )
        raw_delta = ideal_value - current_value
        delta = round_decimal(_apply_mode(raw_delta, mode), 2)
        items.append(
            SuggestionItem(
                id=asset_type.id,
                label=asset_type.name,
                current_value=round_decimal(current_value, 2),
                current_weight=current_weight,
                current_weight_allocation=(
                    round_decimal(current_weight_allocation, 4)
                    if current_weight_allocation is not None
                    else None
                ),
                target_weight=round_decimal(target_weight, 4),
                target_weight_allocation=(
                    round_decimal(target_weight_allocation, 4)
                    if target_weight_allocation is not None
                    else None
                ),
                ideal_value=ideal_value,
                delta=delta,
                action=_action_from_delta(delta),
            )
        )

    if mode == SuggestionMode.BUY_ONLY:
        items = _scale_buys(items, new_cash)
    return items


def calculate_security_suggestions(
    consolidated: list[ConsolidatedSecurity],
    mode: SuggestionMode,
    new_cash: Decimal = Decimal("0"),
) -> list[SuggestionItem]:
    bucket_value = sum(
        (item.current_value_brl for item in consolidated),
        start=Decimal("0"),
    )
    future_bucket = bucket_value + new_cash

    items: list[SuggestionItem] = []
    for item in consolidated:
        current_value = item.current_value_brl
        target_weight = item.target_pct
        ideal_value = round_decimal(future_bucket * target_weight, 2)
        current_weight = (
            round_decimal(current_value / bucket_value, 4)
            if bucket_value > 0
            else Decimal("0")
        )
        raw_delta = ideal_value - current_value
        delta = round_decimal(_apply_mode(raw_delta, mode), 2)
        items.append(
            SuggestionItem(
                id=item.symbol_target_id,
                label=item.symbol,
                current_value=round_decimal(current_value, 2),
                current_weight=current_weight,
                target_weight=round_decimal(target_weight, 4),
                ideal_value=ideal_value,
                delta=delta,
                action=_action_from_delta(delta),
            )
        )

    if mode == SuggestionMode.BUY_ONLY:
        items = _scale_buys(items, new_cash)
    return items


def validate_type_targets(
    asset_types: list[AssetType],
    exclude_id: UUID | None = None,
    new_target: Decimal | None = None,
) -> None:
    total = Decimal("0")
    for asset_type in asset_types:
        if exclude_id and asset_type.id == exclude_id:
            continue
        if asset_type.target_pct is not None:
            total += asset_type.target_pct
    if new_target is not None:
        total += new_target
    if total > Decimal("1"):
        raise ValueError("Asset class target weights cannot exceed 100%.")


def validate_symbol_targets(
    symbol_targets: list[SymbolTarget],
    exclude_id: UUID | None = None,
    new_target: Decimal | None = None,
) -> None:
    total = Decimal("0")
    for target in symbol_targets:
        if exclude_id and target.id == exclude_id:
            continue
        total += target.target_pct
    if new_target is not None:
        total += new_target
    if total > Decimal("1"):
        raise ValueError("Holding target weights cannot exceed 100% within listed securities.")
