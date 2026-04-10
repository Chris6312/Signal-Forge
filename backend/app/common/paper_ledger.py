import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models.ledger import LedgerAccount, LedgerEntry, EntryType
from app.common.models.order import Order, OrderStatus

logger = logging.getLogger(__name__)

# Kraken Pro base-tier fees (< $10k 30-day volume)
KRAKEN_MAKER_FEE_RATE = 0.0025  # 0.25%
KRAKEN_TAKER_FEE_RATE = 0.0040  # 0.40%  (market / stop orders)


async def size_paper_position(
    db: AsyncSession,
    asset_class: str,
    entry_price: float,
    stop_price: float,
    risk_per_trade_pct: float,
) -> float:
    """Return quantity sized to risk a fixed % of available cash. Capped at 10% of balance."""
    stmt = select(LedgerAccount).where(LedgerAccount.asset_class == asset_class)
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account or account.cash_balance <= 0:
        logger.warning("No cash available in %s ledger for paper sizing", asset_class)
        return 0.0

    risk_per_unit = entry_price - stop_price
    if risk_per_unit <= 0:
        logger.warning(
            "Invalid stop placement for paper sizing: entry=%.4f stop=%.4f",
            entry_price, stop_price,
        )
        return 0.0

    risk_amount = account.cash_balance * risk_per_trade_pct
    quantity = risk_amount / risk_per_unit
    cost = quantity * entry_price

    if cost > account.cash_balance * 0.10:
        quantity = (account.cash_balance * 0.10) / entry_price

    return round(quantity, 8)


async def record_paper_fill(
    db: AsyncSession,
    asset_class: str,
    symbol: str,
    position_id,
    order_id,
    quantity: float,
    price: float,
) -> None:
    """Deduct position cost from the paper ledger and record a FILL entry."""
    if quantity <= 0:
        return

    stmt = select(LedgerAccount).where(LedgerAccount.asset_class == asset_class)
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        logger.warning("No ledger account for %s — skipping paper fill", asset_class)
        return

    cost = round(quantity * price, 8)
    account.cash_balance -= cost
    account.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    entry = LedgerEntry(
        id=uuid.uuid4(),
        asset_class=asset_class,
        entry_type=EntryType.FILL,
        symbol=symbol,
        amount=-cost,
        balance_after=account.cash_balance,
        position_id=position_id,
        order_id=order_id,
        notes=f"Paper entry: {symbol} × {quantity:.6f} @ {price:.4f}",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(entry)

    # If an order row exists for this paper fill, mark it as filled so order lifecycle is complete.
    try:
        if order_id:
            stmt = select(Order).where(Order.id == order_id)
            result = await db.execute(stmt)
            ord = result.scalar_one_or_none()
            if ord:
                ord.status = OrderStatus.FILLED
                ord.fill_price = price
                ord.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
                if not ord.broker_order_id:
                    ord.broker_order_id = "PAPER_EXEC"
                db.add(ord)
                await db.flush()
    except Exception as exc:
        logger.warning("Failed to mark paper order filled for %s: %s", symbol, exc)

    if asset_class == "crypto":
        fee = round(cost * KRAKEN_TAKER_FEE_RATE, 8)
        account.cash_balance -= fee
        account.fees_total = (account.fees_total or 0.0) + fee
        fee_entry = LedgerEntry(
            id=uuid.uuid4(),
            asset_class=asset_class,
            entry_type=EntryType.FEE,
            symbol=symbol,
            amount=-fee,
            balance_after=account.cash_balance,
            position_id=position_id,
            order_id=order_id,
            notes=f"Kraken taker fee {KRAKEN_TAKER_FEE_RATE * 100:.2f}% on entry: {symbol}",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(fee_entry)

    logger.info(
        "Paper fill: %s × %.6f @ %.4f | cost=%.2f | balance=%.2f",
        symbol, quantity, price, cost, account.cash_balance,
    )
