from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.db_models import User, Order, OrderItem
from app.services.auth import get_current_user

router = APIRouter()

# ── Schemas ────────────────────────────────────────────

class OrderItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    price_at_time: float
    product_name: str
    product_image: str

    class Config:
        from_attributes = True

class OrderOut(BaseModel):
    id: int
    user_id: int
    total_amount: float
    discount_amount: float
    status: str
    created_at: datetime
    items: List[OrderItemOut]

    class Config:
        from_attributes = True

class OrderUpdateStatusRequest(BaseModel):
    status: str

# Admin check dependency
def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires admin privileges")
    return current_user

# ── User Endpoints ─────────────────────────────────────

@router.get("/orders/me", response_model=List[OrderOut])
async def get_my_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all orders belonging to the authenticated user."""
    result = await db.execute(
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product)
        )
        .order_by(desc(Order.created_at))
    )
    orders = result.scalars().all()
    
    # We must manually map the product details into the items for output
    out = []
    for order in orders:
        items_mapped = []
        for item in order.items:
            items_mapped.append(OrderItemOut(
                id=item.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price_at_time=item.price_at_time,
                product_name=item.product.name if item.product else "Unknown Product",
                product_image=item.product.image_url if item.product else ""
            ))
        
        out.append(OrderOut(
            id=order.id,
            user_id=order.user_id,
            total_amount=order.total_amount,
            discount_amount=order.discount_amount,
            status=order.status,
            created_at=order.created_at,
            items=items_mapped
        ))
    return out

# ── Admin Endpoints ────────────────────────────────────

@router.get("/admin/orders", response_model=List[OrderOut])
async def get_all_orders(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Get all global orders for admin dashboard."""
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product)
        )
        .order_by(desc(Order.created_at))
    )
    orders = result.scalars().all()
    
    out = []
    for order in orders:
        items_mapped = []
        for item in order.items:
            items_mapped.append(OrderItemOut(
                id=item.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price_at_time=item.price_at_time,
                product_name=item.product.name if item.product else "Unknown Product",
                product_image=item.product.image_url if item.product else ""
            ))
        
        out.append(OrderOut(
            id=order.id,
            user_id=order.user_id,
            total_amount=order.total_amount,
            discount_amount=order.discount_amount,
            status=order.status,
            created_at=order.created_at,
            items=items_mapped
        ))
    return out

@router.put("/admin/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    req: OrderUpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Update order status."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    order.status = req.status
    await db.commit()
    await db.refresh(order)
    return {"id": order.id, "status": order.status}
