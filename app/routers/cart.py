"""Shopping cart router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.db_models import CartItem, Product, User
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
