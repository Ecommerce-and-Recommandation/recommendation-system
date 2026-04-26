from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import User, Promotion, PromotionUsage, Product, BehaviorEvent, Order
from app.services.auth import get_current_user

router = APIRouter()

# ── Schemas ────────────────────────────────────────────

class PromotionCreate(BaseModel):
    code: str
    discount_type: str = "PERCENTAGE"
    discount_value: float
    min_order_amount: float = 0.0
    usage_limit: Optional[int] = None
    valid_until: Optional[datetime] = None
    target_audience: str = "ALL"

class PromotionOut(PromotionCreate):
    id: int
    is_active: bool
    times_used: int
    created_at: datetime

    class Config:
        from_attributes = True

class PromoApplyRequest(BaseModel):
    code: str
    cart_total: float

class PromoApplyResponse(BaseModel):
    valid: bool
    message: str
    discount_amount: float
    promotion_id: Optional[int] = None

# Admin check dependency
def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires admin privileges")
    return current_user

# ── Admin CRUD ─────────────────────────────────────────

@router.get("/promotions", response_model=List[PromotionOut])
async def get_promotions(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Get all promotions (Admin)"""
    result = await db.execute(select(Promotion).order_by(desc(Promotion.created_at)))
    return result.scalars().all()

@router.post("/promotions", response_model=PromotionOut)
async def create_promotion(
    promo: PromotionCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Create a new promotion (Admin)"""
    # Check if exists
    result = await db.execute(select(Promotion).where(Promotion.code == promo.code))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Promotion code already exists")
    
    new_promo = Promotion(
        code=promo.code,
        discount_type=promo.discount_type,
        discount_value=promo.discount_value,
        min_order_amount=promo.min_order_amount,
        usage_limit=promo.usage_limit,
        valid_until=promo.valid_until,
        target_audience=promo.target_audience
    )
    db.add(new_promo)
    await db.commit()
    await db.refresh(new_promo)
    return new_promo

@router.delete("/promotions/{promo_id}")
async def delete_promotion(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Delete a promotion"""
    promo = await db.get(Promotion, promo_id)
    if not promo:
        raise HTTPException(status_code=404)
    await db.delete(promo)
    await db.commit()
    return {"status": "deleted"}

# ── User Facing ────────────────────────────────────────

@router.get("/promotions/available", response_model=List[PromotionOut])
async def get_available_promotions(
    cart_total: float,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a list of active promotions the user can use right now."""
    result = await db.execute(select(Promotion).where(Promotion.is_active == True))
    promos = result.scalars().all()

    available = []
    
    # Calculate days since user registration
    user_age_days = (datetime.now(timezone.utc) - current_user.created_at).days if getattr(current_user, 'created_at', None) else 31
    
    # Get user order count
    order_count_res = await db.execute(select(func.count(Order.id)).where(Order.user_id == current_user.id, Order.status == "COMPLETED"))
    user_order_count = order_count_res.scalar_one()

    for promo in promos:
        # Check amount
        if cart_total < promo.min_order_amount:
            continue
        # Check target audience
        if promo.target_audience == "NEW_USER" and user_age_days > 30:
            continue
        if promo.target_audience == "LOYAL_USER" and user_order_count < 3:
            continue
            
        # Check limits
        if promo.usage_limit and (promo.times_used or 0) >= promo.usage_limit:
            continue
        # Check expire
        if promo.valid_until and getattr(promo, 'valid_until', None):
            # SQLAlchemy might return naive datetime from PG if not configured well, so just do a safe check
            try:
                if promo.valid_until.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    continue
            except:
                pass

        available.append(promo)
    return available

@router.post("/promotions/apply", response_model=PromoApplyResponse)
async def apply_promotion(
    req: PromoApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Calculate and validate how much discount a promo applies to the cart total."""
    result = await db.execute(select(Promotion).where(Promotion.code == req.code, Promotion.is_active == True))
    promo = result.scalar_one_or_none()

    if not promo:
        return PromoApplyResponse(valid=False, message="Mã giảm giá không tồn tại hoặc đã hết hạn.", discount_amount=0)

    # Check expiration
    if promo.valid_until and getattr(promo, 'valid_until', None):
        try:
            if promo.valid_until.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                return PromoApplyResponse(valid=False, message="Mã giảm giá đã hết hạn.", discount_amount=0)
        except:
             pass

    # Check minimum order amount
    if req.cart_total < promo.min_order_amount:
        return PromoApplyResponse(valid=False, message=f"Đơn hàng tối thiểu £{promo.min_order_amount} để áp mã.", discount_amount=0)

    # Check limits
    if promo.usage_limit and (promo.times_used or 0) >= promo.usage_limit:
        return PromoApplyResponse(valid=False, message="Mã giảm giá đã hết lượt sử dụng.", discount_amount=0)
        
    # Check target audience
    user_age_days = (datetime.now(timezone.utc) - current_user.created_at).days if getattr(current_user, 'created_at', None) else 31
    if promo.target_audience == "NEW_USER" and user_age_days > 30:
        return PromoApplyResponse(valid=False, message="Mã này chỉ dành cho tài khoản tạo dưới 30 ngày.", discount_amount=0)
        
    if promo.target_audience == "LOYAL_USER":
        order_count_res = await db.execute(select(func.count(Order.id)).where(Order.user_id == current_user.id, Order.status == "COMPLETED"))
        user_order_count = order_count_res.scalar_one()
        if user_order_count < 3:
            return PromoApplyResponse(valid=False, message="Mã này chỉ dành cho khách hàng đã mua từ 3 đơn trở lên.", discount_amount=0)

    # Check if user already used this promo
    usage = await db.execute(select(PromotionUsage).where(
        PromotionUsage.user_id == current_user.id,
        PromotionUsage.promotion_id == promo.id
    ))
    if usage.scalar_one_or_none():
        return PromoApplyResponse(valid=False, message="Bạn đã sử dụng mã này rồi.", discount_amount=0)

    # Calculate discount
    discount = 0.0
    if promo.discount_type == "PERCENTAGE":
        discount = req.cart_total * (promo.discount_value / 100.0)
    else:
        discount = promo.discount_value
        if discount > req.cart_total:
            discount = req.cart_total  # can't discount more than total

    return PromoApplyResponse(
        valid=True,
        message="Áp dụng mã giảm giá thành công!",
        discount_amount=round(discount, 2),
        promotion_id=promo.id
    )

# ── AI Insights ─────────────────────────────────────────

@router.get("/promotions/insights/suggestions")
async def get_ai_suggestions(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """
    AI Insight: Trả về danh sách sản phẩm có Lượt xem cao nhưng Lượt mua thấp.
    Đề xuất Admin hệ thống tạo Voucher giảm giá cho các sản phẩm này.
    """
    # AI Insight: Trả về danh sách sản phẩm có Lượt xem cao nhưng Lượt mua thấp.
    # Relaxed thresholds: any product with views, prioritizing low conversion rates
    result = await db.execute(
        select(Product)
        .where(Product.num_customers > 0)
        .order_by(Product.purchase_count.asc(), desc(Product.num_customers))
        .limit(3)
    )
    products = result.scalars().all()
    
    suggestions = []
    for p in products:
        suggestions.append({
            "product_id": p.id,
            "product_name": p.name,
            "image_url": p.image_url,
            "reason": f"Sản phẩm có {p.num_customers} khách hàng quan tâm nhưng lượng mua rất thấp ({p.purchase_count}).",
            "suggested_action": "TẠO VOUCHER",
            "suggested_promo": {
                "code": f"SALE_{p.stock_code}",
                "discount_type": "PERCENTAGE",
                "discount_value": 15,
                "message": f"Giảm 15% để kích thích bán hàng."
            }
        })

    return suggestions


# ── Dynamic AI Voucher by Probability ──────────────────

@router.get("/promotions/dynamic-voucher")
async def get_dynamic_voucher(
    cart_total: float,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a personalized voucher suggestion based on ML purchase probability.

    Strategy:
      - prob < 0.3  → No voucher (very unlikely to purchase regardless)
      - prob 0.3-0.5 → 20% discount (strong nudge needed)
      - prob 0.5-0.7 → 10% discount (moderate nudge)
      - prob 0.7-0.9 → 5% discount or freeship (likely buyer, small incentive)
      - prob > 0.9  → No discount (will buy anyway, maximize profit)
    """
    from app.services.behavior_engine import compute_rfm_from_behavior
    from app.services.predictor import predict_purchase
    from app.schemas.models import CustomerFeatures

    rfm = await compute_rfm_from_behavior(current_user.id, db)
    features = CustomerFeatures(**rfm)

    try:
        prediction = predict_purchase(features)
    except Exception:
        return {"voucher": None, "reason": "Could not compute prediction"}

    prob = prediction["probability"]
    segment_name = prediction.get("segment_name", "Unknown")

    voucher = None
    if 0.3 <= prob < 0.5:
        voucher = {
            "discount_type": "PERCENTAGE",
            "discount_value": 20,
            "message": f"🎁 Giảm 20% đặc biệt cho bạn! Đừng bỏ lỡ nhé.",
            "min_order_amount": max(cart_total * 0.5, 5.0),
        }
    elif 0.5 <= prob < 0.7:
        voucher = {
            "discount_type": "PERCENTAGE",
            "discount_value": 10,
            "message": f"✨ Giảm 10% cho đơn hàng tiếp theo!",
            "min_order_amount": max(cart_total * 0.7, 5.0),
        }
    elif 0.7 <= prob < 0.9:
        voucher = {
            "discount_type": "FIXED",
            "discount_value": round(cart_total * 0.05, 2),
            "message": f"🚚 Ưu đãi freeship trị giá £{round(cart_total * 0.05, 2)} cho bạn!",
            "min_order_amount": 0,
        }

    return {
        "probability": prob,
        "segment": segment_name,
        "voucher": voucher,
        "reason": "high_intent_no_discount" if prob >= 0.9 else ("low_intent" if prob < 0.3 else "nudge"),
    }
