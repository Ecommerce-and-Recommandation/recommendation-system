"""Behavior analysis engine – converts raw events into ML features."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import BehaviorEvent, CartItem, Product, Order, OrderItem


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


async def get_recommendation_sources(
    user_id: int,
    db: AsyncSession,
    current_product_id: int | None = None,
) -> list[dict]:
    """Collect multiple recommendation sources with priority weights.

    Returns a ranked list of {"stock_code": str, "weight": float, "source": str}
    gathered from:
      1. Currently viewed product (highest priority)
      2. Recently viewed products (last 30 min, recency-weighted)
      3. All-time top viewed products (duration-weighted)
      4. Top 5 most-recent cart items
      5. Search history → matched products
    """
    sources: list[dict] = []
    seen_codes: set[str] = set()

    # ── 1. Currently viewed product ──────────────────────
    if current_product_id:
        product = await db.get(Product, current_product_id)
        if product and product.stock_code not in seen_codes:
            sources.append({
                "stock_code": product.stock_code,
                "weight": 1.0,
                "source": "current_view",
            })
            seen_codes.add(product.stock_code)

    # ── 2. Recently viewed products (last 30 min) ────────
    # Recency matters: newest views first, regardless of total duration
    recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    recent_result = await db.execute(
        select(
            BehaviorEvent.product_id,
            func.max(BehaviorEvent.created_at).label("last_seen"),
            func.sum(BehaviorEvent.duration_seconds).label("total_duration"),
        )
        .where(
            BehaviorEvent.user_id == user_id,
            BehaviorEvent.event_type == "view",
            BehaviorEvent.product_id.isnot(None),
            BehaviorEvent.duration_seconds > 5,
            BehaviorEvent.created_at >= recent_cutoff,
        )
        .group_by(BehaviorEvent.product_id)
        .order_by(func.max(BehaviorEvent.created_at).desc())
        .limit(8)
    )
    for row in recent_result.all():
        product = await db.get(Product, row[0])
        if product and product.stock_code not in seen_codes:
            sources.append({
                "stock_code": product.stock_code,
                "weight": 1.0,  # Max priority for recent activity
                "source": "recent_view",
            })
            seen_codes.add(product.stock_code)

    # ── 3. All-time top viewed products (by duration) ────
    view_result = await db.execute(
        select(
            BehaviorEvent.product_id,
            func.sum(BehaviorEvent.duration_seconds).label("total_duration"),
        )
        .where(
            BehaviorEvent.user_id == user_id,
            BehaviorEvent.event_type == "view",
            BehaviorEvent.product_id.isnot(None),
            BehaviorEvent.duration_seconds > 5,
        )
        .group_by(BehaviorEvent.product_id)
        .order_by(func.sum(BehaviorEvent.duration_seconds).desc())
        .limit(8)
    )
    for row in view_result.all():
        product = await db.get(Product, row[0])
        if product and product.stock_code not in seen_codes:
            duration = float(row[1])
            # Lowered weight for old accumulated duration to prevent stagnation
            weight = min(0.4, 0.1 + (duration / 500))
            sources.append({
                "stock_code": product.stock_code,
                "weight": weight,
                "source": "viewed",
            })
            seen_codes.add(product.stock_code)

    # ── 3. Top 5 most-recent cart items ──────────────────
    cart_result = await db.execute(
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.added_at.desc())
        .limit(5)
    )
    for ci in cart_result.scalars().all():
        product = await db.get(Product, ci.product_id)
        if product and product.stock_code not in seen_codes:
            sources.append({
                "stock_code": product.stock_code,
                "weight": 0.7,
                "source": "cart",
            })
            seen_codes.add(product.stock_code)

    # ── 4. Purchased products (order history) ────────────
    order_result = await db.execute(
        select(OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == user_id,
            Order.status == "COMPLETED",
        )
        .distinct()
        .limit(10)
    )
    for row in order_result.all():
        product = await db.get(Product, row[0])
        if product and product.stock_code not in seen_codes:
            sources.append({
                "stock_code": product.stock_code,
                "weight": 0.9,
                "source": "purchased",
            })
            seen_codes.add(product.stock_code)

    # ── 5. Search history → match products ───────────────
    search_result = await db.execute(
        select(BehaviorEvent.metadata_json)
        .where(
            BehaviorEvent.user_id == user_id,
            BehaviorEvent.event_type == "search",
        )
        .order_by(BehaviorEvent.created_at.desc())
        .limit(10)
    )
    search_queries: list[str] = []
    for row in search_result.all():
        meta = row[0]
        if meta and isinstance(meta, dict) and "query" in meta:
            search_queries.append(str(meta["query"]))

    if search_queries:
        # Match unique search terms to products
        for query in search_queries[:5]:
            pattern = f"%{query}%"
            match_result = await db.execute(
                select(Product)
                .where(
                    Product.in_stock.is_(True),
                    Product.name.ilike(pattern) | Product.description.ilike(pattern),
                )
                .order_by(Product.purchase_count.desc())
                .limit(2)
            )
            for p in match_result.scalars().all():
                if p.stock_code not in seen_codes:
                    sources.append({
                        "stock_code": p.stock_code,
                        "weight": 0.4,
                        "source": "search",
                    })
                    seen_codes.add(p.stock_code)

    return sources


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

