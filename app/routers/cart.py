"""Shopping cart router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.db_models import CartItem, Product, User, Order, OrderItem, Promotion, PromotionUsage
from app.services.auth import get_current_user

router = APIRouter()


class AddToCartRequest(BaseModel):
    product_id: int
    quantity: int = 1


class UpdateCartRequest(BaseModel):
    quantity: int


class CartItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    product_name: str
    product_price: float
    product_image: str
    stock_code: str
    added_at: str


class CartResponse(BaseModel):
    items: list[CartItemOut]
    total: float
    item_count: int


@router.get("/cart", response_model=CartResponse)
async def get_cart(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CartItem).where(CartItem.user_id == user.id).options(selectinload(CartItem.product))
    )
    items = result.scalars().all()
    out = []
    total = 0.0
    for item in items:
        p = item.product
        subtotal = p.price * item.quantity
        total += subtotal
        out.append({
            "id": item.id,
            "product_id": p.id,
            "quantity": item.quantity,
            "product_name": p.name,
            "product_price": p.price,
            "product_image": p.image_url,
            "stock_code": p.stock_code,
            "added_at": item.added_at.isoformat() if item.added_at else "",
        })
    return {"items": out, "total": round(total, 2), "item_count": len(out)}


@router.post("/cart", response_model=CartItemOut)
async def add_to_cart(
    body: AddToCartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, body.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # If already in cart, increment quantity
    result = await db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == body.product_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.quantity += body.quantity
        await db.commit()
        await db.refresh(existing)
        item = existing
    else:
        item = CartItem(user_id=user.id, product_id=body.product_id, quantity=body.quantity)
        db.add(item)
        await db.commit()
        await db.refresh(item)

    return {
        "id": item.id,
        "product_id": product.id,
        "quantity": item.quantity,
        "product_name": product.name,
        "product_price": product.price,
        "product_image": product.image_url,
        "stock_code": product.stock_code,
        "added_at": item.added_at.isoformat() if hasattr(item, "added_at") and item.added_at else "",
    }


@router.patch("/cart/{item_id}")
async def update_cart_item(
    item_id: int,
    body: UpdateCartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(CartItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cart item not found")
    if body.quantity <= 0:
        await db.delete(item)
        await db.commit()
        return {"deleted": True}
    item.quantity = body.quantity
    await db.commit()
    return {"id": item.id, "quantity": item.quantity}


@router.delete("/cart/{item_id}")
async def remove_from_cart(
    item_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(CartItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cart item not found")
    await db.delete(item)
    await db.commit()
    return {"deleted": True}


class CheckoutRequest(BaseModel):
    selected_item_ids: list[int]
    promotion_id: Optional[int] = None

class CheckoutResponse(BaseModel):
    order_id: int
    total_paid: float
    message: str

@router.post("/cart/checkout", response_model=CheckoutResponse)
async def checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.selected_item_ids:
        raise HTTPException(status_code=400, detail="No items selected for checkout")

    # Fetch selected cart items
    result = await db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.id.in_(body.selected_item_ids))
        .options(selectinload(CartItem.product))
    )
    items = result.scalars().all()
    if not items:
        raise HTTPException(status_code=404, detail="Selected items not found in cart")

    # Calculate subtotal
    subtotal = sum([item.product.price * item.quantity for item in items])
    discount = 0.0
    promo = None

    # Handle Promotion
    if body.promotion_id:
        p_res = await db.execute(select(Promotion).where(Promotion.id == body.promotion_id))
        promo = p_res.scalar_one_or_none()
        if not promo or not promo.is_active:
            raise HTTPException(status_code=400, detail="Invalid or inactive promotion")
        
        # We assume validity (date, min_amount) was checked beforehand or we do it quickly here
        if subtotal >= promo.min_order_amount:
            if promo.discount_type == "PERCENTAGE":
                discount = subtotal * (promo.discount_value / 100.0)
            else:
                discount = promo.discount_value
            if discount > subtotal: discount = subtotal

    total_amount = round(subtotal - discount, 2)

    # 1. Create Order
    order = Order(
        user_id=user.id,
        total_amount=total_amount,
        discount_amount=round(discount, 2),
        status="COMPLETED"
    )
    db.add(order)
    await db.flush() # get order.id

    # 2. Create Order Items
    for item in items:
        o_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price_at_time=item.product.price
        )
        db.add(o_item)
        
        # Increase product purchase_count
        item.product.purchase_count += item.quantity

    # 3. Create Promo Usage
    if promo and discount > 0:
        usage = PromotionUsage(
            user_id=user.id,
            promotion_id=promo.id,
            order_id=order.id
        )
        db.add(usage)
        promo.times_used += 1

    # 4. Remove checked out items from Cart
    for item in items:
        await db.delete(item)

    await db.commit()
    
    return CheckoutResponse(
        order_id=order.id,
        total_paid=total_amount,
        message="Order placed successfully!"
    )
