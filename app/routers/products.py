from fastapi import APIRouter, Depends, HTTPException, status

from app.models.products import Product as ProductModel
from app.models.categories import Category as CategoryModel
from app.models.users import User as UserModel
from app.schemas import Product as ProductSchema, ProductCreate, ProductList
from app.db_depends import get_db
from app.db_depends import get_async_db
from sqlalchemy.orm import Session, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, exists, func
from app.auth import get_current_seller

from app.models.reviews import Review as ReviewModel
from app.schemas import Review as ReviewSchema

# Создаём маршрутизатор для товаров
router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get("/", response_model=ProductList, status_code=status.HTTP_200_OK)
async def get_all_products(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        db: AsyncSession = Depends(get_async_db)
):
    """
    Возвращает список всех активных товаров.
    """

    total_stmt = select(func.count()).select_from(ProductModel).where(
        ProductModel.is_active
    )
    total = await db.scalar(total_stmt) or 0

    products_stmt = (
        select(ProductModel)
        .where(ProductModel.is_active)
        .order_by(ProductModel.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = (await db.scalars(products_stmt)).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/", response_model=ProductSchema, status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Создаёт новый товар, привязанный к текущему продавцу (только для 'seller').
    """

    category_exists = await db.scalar(
        select(
            exists().where(
                CategoryModel.id == product.category_id,
                CategoryModel.is_active == True,
            )
        )
    )

    if not category_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")

    # Создаём товар
    db_product = ProductModel(**product.model_dump(), seller_id=current_user.id)

    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)  # Для получения id и is_active из базы
    return db_product


@router.get("/category/{category_id}", response_model=list[ProductSchema])
async def get_products_by_category(category_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список товаров в указанной категории по её ID.
    """

    category_exists = await db.scalar(
        select(
            exists().where(CategoryModel.id == category_id, CategoryModel.is_active == True)
        )
    )

    if not category_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or inactive")

    product_stmt = select(ProductModel).where(ProductModel.is_active == True, ProductModel.category_id == category_id)
    product_result = await db.scalars(product_stmt)
    return product_result.all()


@router.get("/{product_id}", response_model=ProductSchema)
async def get_product(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает детальную информацию о товаре по его ID.
    """

    product_stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    result = await db.scalars(product_stmt)
    product = result.first()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    # Проверяем, существует ли активная категория
    category_exists = await db.scalar(
        select(
            exists().where(CategoryModel.id == product.category_id, CategoryModel.is_active == True)
        )
    )

    if not category_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")

    return product


@router.put("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def update_product(product_id: int,
                         product: ProductCreate,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Обновляет товар, если он принадлежит текущему продавцу (только для 'seller').
    """
    # Проверяем, существует ли товар

    product_result = await db.scalars(
        select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True))
    db_product = product_result.first()

    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    if db_product.seller_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You only can update your own products"
                            )

    # Проверяем, существует ли активная категория
    category_exists = await db.scalar(
        select(
            exists().where(CategoryModel.id == product.category_id, CategoryModel.is_active == True)
        )
    )

    if not category_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")

    # Обновляем товар

    await db.execute(update(ProductModel).where(ProductModel.id == product_id).values(**product.model_dump()))
    await db.commit()
    await db.refresh(db_product)  # Для консистентности данных

    return db_product


@router.delete("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def delete_product(product_id: int,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)

                         ):
    """
    Выполняет мягкое удаление товара, если он принадлежит текущему продавцу (только для 'seller').
    """
    product_stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active == True)
    result = await db.scalars(product_stmt)
    db_product = result.first()

    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
    if db_product.seller_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You only can delete your own products"
                            )

    # Устанавливаем is_active=False
    db_product.is_active = False
    await db.commit()
    await db.refresh(db_product)  # Для возврата is_active = False

    return db_product


@router.get("/{product_id}/reviews", response_model=list[ReviewSchema])
async def get_product_reviews(product_id: int, db: AsyncSession = Depends(get_async_db)):
    product_exists = await db.scalar(
        select(
            exists().where(ProductModel.id == product_id, ProductModel.is_active == True)
        )
    )

    if not product_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    review_result = await db.scalars(
        select(ReviewModel).where(ReviewModel.product_id == product_id, ReviewModel.is_active))

    reviews = review_result.all()

    return reviews
