"""Products router – public (no auth required for browsing)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import Product

router = APIRouter()


class ProductOut(BaseModel):
    id: int
    stock_code: str
    name: str
    description: str
    price: float
    image_url: str
    category: str
    in_stock: bool
    purchase_count: int


class ProductListResponse(BaseModel):
    products: list[ProductOut]
    total: int
    page: int
    page_size: int


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    category: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    q = select(Product).where(Product.in_stock.is_(True))
    count_q = select(func.count(Product.id)).where(Product.in_stock.is_(True))

    if category:
        q = q.where(Product.category == category)
        count_q = count_q.where(Product.category == category)
    if search:
        pattern = f"%{search}%"
        q = q.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))
        count_q = count_q.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))

    total = (await db.execute(count_q)).scalar() or 0
    q = q.order_by(Product.purchase_count.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return {
        "products": [_to_dict(p) for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/products/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product.category, func.count(Product.id))
        .where(Product.in_stock.is_(True))
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
    )
    return [{"name": row[0], "count": row[1]} for row in result.all()]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _to_dict(product)


def _to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "stock_code": p.stock_code,
        "name": p.name,
        "description": p.description,
        "price": p.price,
        "image_url": p.image_url,
        "category": p.category,
        "in_stock": p.in_stock,
        "purchase_count": p.purchase_count,
    }
