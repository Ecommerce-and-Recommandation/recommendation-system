"""Behavior analysis engine – converts raw events into ML features."""

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import BehaviorEvent, CartItem, Product


async def compute_rfm_from_behavior(user_id: int, db: AsyncSession) -> dict:
    """Aggregate behavior_events + cart → approximate RFM features."""
    now = datetime.now(timezone.utc)

    # All events for user
    result = await db.execute(
        select(BehaviorEvent)
        .where(BehaviorEvent.user_id == user_id)
        .order_by(BehaviorEvent.created_at)
    )
    events = result.scalars().all()

    if not events:
        return _default_features()

    first_event = events[0].created_at.replace(tzinfo=timezone.utc) if events[0].created_at.tzinfo is None else events[0].created_at
    last_event = events[-1].created_at.replace(tzinfo=timezone.utc) if events[-1].created_at.tzinfo is None else events[-1].created_at

    recency = (now - last_event).days
    days_since_first = max((now - first_event).days, 1)

    # Count "sessions" – groups of events <30 min apart
    sessions = 1
    prev_time = first_event
    for e in events[1:]:
        t = e.created_at.replace(tzinfo=timezone.utc) if e.created_at.tzinfo is None else e.created_at
        if (t - prev_time).total_seconds() > 1800:
            sessions += 1
        prev_time = t

    # Cart value as monetary proxy
    cart_result = await db.execute(
        select(CartItem).where(CartItem.user_id == user_id)
    )
    cart_items = cart_result.scalars().all()
    monetary = 0.0
    total_items = 0
    for ci in cart_items:
        product = await db.get(Product, ci.product_id)
        if product:
            monetary += product.price * ci.quantity
            total_items += ci.quantity

    # Unique products viewed
    viewed_products = set()
    add_to_cart_count = 0
    search_count = 0
    weekend_events = 0
    hour_counts: dict[int, int] = defaultdict(int)

    for e in events:
        if e.product_id:
            viewed_products.add(e.product_id)
        if e.event_type == "add_to_cart":
            add_to_cart_count += 1
        if e.event_type == "search":
            search_count += 1
        t = e.created_at
        if t.weekday() >= 5:
            weekend_events += 1
        hour_counts[t.hour] += 1

    total_unique_products = len(viewed_products)
    avg_order_value = monetary / max(sessions, 1)
    avg_items_per_order = total_items / max(sessions, 1)
    is_weekend_shopper = weekend_events / max(len(events), 1)
    favorite_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 12
    avg_days_between = days_since_first / max(sessions - 1, 1) if sessions > 1 else 0

    return {
        "recency": recency,
        "frequency": sessions,
        "monetary": round(monetary, 2),
        "avg_order_value": round(avg_order_value, 2),
        "avg_items_per_order": round(avg_items_per_order, 2),
        "total_unique_products": total_unique_products,
        "avg_days_between_orders": round(avg_days_between, 1),
        "cancellation_rate": 0.0,
        "days_since_first_purchase": days_since_first,
        "is_weekend_shopper": round(is_weekend_shopper, 3),
        "favorite_hour": favorite_hour,
        "country": "United Kingdom",
    }


async def get_most_interacted_product(user_id: int, db: AsyncSession) -> str | None:
    """Find the product the user spent most time viewing or added to cart most."""
    add_to_cart_bonus = case(
        (BehaviorEvent.event_type == "add_to_cart", 30),
        else_=0,
    )
    score_expr = func.sum(
        func.coalesce(BehaviorEvent.duration_seconds, 0) + add_to_cart_bonus
    )

    result = await db.execute(
        select(BehaviorEvent.product_id, score_expr.label("score"))
        .where(BehaviorEvent.user_id == user_id, BehaviorEvent.product_id.isnot(None))
        .group_by(BehaviorEvent.product_id)
        .order_by(score_expr.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None

    product = await db.get(Product, row[0])
    return product.stock_code if product else None


def _default_features() -> dict:
    return {
        "recency": 0,
        "frequency": 1,
        "monetary": 0,
        "avg_order_value": 0,
        "avg_items_per_order": 0,
        "total_unique_products": 0,
        "avg_days_between_orders": 0,
        "cancellation_rate": 0,
        "days_since_first_purchase": 1,
        "is_weekend_shopper": 0,
        "favorite_hour": 12,
        "country": "United Kingdom",
    }
