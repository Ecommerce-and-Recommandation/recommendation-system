"""Products router – public + admin CRUD."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import Product, User
from app.services.auth import get_current_user

router = APIRouter()


# Admin check dependency
def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires admin privileges")
    return current_user


class ProductOut(BaseModel):
    id: int
    stock_code: str
    parent_sku: str
    name: str
    description: str
    price: float
    image_url: str
    category: str
    in_stock: bool
    purchase_count: int


class ProductVariantOut(BaseModel):
    id: int
    stock_code: str
    name: str


class ProductDetailOut(ProductOut):
    variants: list[ProductVariantOut]


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
    # Subquery to get one representative product ID per parent_sku
    subq = select(func.min(Product.id).label("id")).where(Product.in_stock.is_(True))
    if category:
        subq = subq.where(Product.category == category)
    if search:
        pattern = f"%{search}%"
        subq = subq.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))
    subq = subq.group_by(Product.parent_sku)
    
    # Total count of distinct groups
    count_q = select(func.count()).select_from(subq.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Get paginated product rows
    q = select(Product).where(Product.id.in_(subq)).order_by(Product.purchase_count.desc()).offset((page - 1) * page_size).limit(page_size)
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


@router.get("/products/{product_id}", response_model=ProductDetailOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Find variants with the same parent_sku
    variants_query = select(Product).where(
        Product.parent_sku == product.parent_sku, 
        Product.in_stock.is_(True)
    ).order_by(Product.stock_code)
    variants_rows = (await db.execute(variants_query)).scalars().all()
    
    result = _to_dict(product)
    # Only add variants if there's more than 1 (meaning it's actually part of a group)
    result["variants"] = [{"id": v.id, "stock_code": v.stock_code, "name": v.name} for v in variants_rows] if len(variants_rows) > 1 else []
    return result


def _to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "stock_code": p.stock_code,
        "parent_sku": p.parent_sku,
        "name": p.name,
        "description": p.description,
        "price": p.price,
        "image_url": p.image_url,
        "category": p.category,
        "in_stock": p.in_stock,
        "purchase_count": p.purchase_count,
    }


# ── Admin CRUD ─────────────────────────────────────────

class ProductCreate(BaseModel):
    stock_code: str
    name: str
    description: str = ""
    price: float
    image_url: str = ""
    category: str = "Other"
    in_stock: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    in_stock: Optional[bool] = None


@router.get("/admin/products", response_model=ProductListResponse)
async def admin_list_products(
    category: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Admin product list – includes out-of-stock items."""
    q = select(Product)
    count_q = select(func.count(Product.id))

    if category:
        q = q.where(Product.category == category)
        count_q = count_q.where(Product.category == category)
    if search:
        pattern = f"%{search}%"
        q = q.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))
        count_q = count_q.where(Product.name.ilike(pattern) | Product.description.ilike(pattern))

    total = (await db.execute(count_q)).scalar() or 0
    q = q.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return {
        "products": [_to_dict(p) for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/admin/products", response_model=ProductOut)
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Create a new product."""
    existing = await db.execute(select(Product).where(Product.stock_code == body.stock_code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Stock code already exists")

    product = Product(
        stock_code=body.stock_code,
        name=body.name,
        description=body.description,
        price=body.price,
        image_url=body.image_url,
        category=body.category,
        in_stock=body.in_stock,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return _to_dict(product)


@router.put("/admin/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Update an existing product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return _to_dict(product)


@router.delete("/admin/products/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete a product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(product)
    await db.commit()
    return {"status": "deleted"}
