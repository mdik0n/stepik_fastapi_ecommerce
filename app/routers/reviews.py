from fastapi import APIRouter, Depends, status, HTTPException
from app.db_depends import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, exists
from app.models.reviews import Review as ReviewModel
from app.models.users import User as UserModel
from app.models.products import Product as ProductModel

from app.schemas import Review as ReviewSchema, ReviewCreate

from app.auth import get_current_user

router = APIRouter(prefix="/reviews", tags=["reviews"])


async def update_product_rating(db: AsyncSession, product_id: int):
    '''
         Расчет рейтинга товара
    '''
    result = await db.execute(
        select(func.avg(ReviewModel.grade)).where(
            ReviewModel.product_id == product_id,
            ReviewModel.is_active == True
        )
    )
    avg_rating = result.scalar() or 0.0
    product = await db.get(ProductModel, product_id)
    product.rating = avg_rating
    await db.commit()


@router.get("/", response_model=list[ReviewSchema])
async def get_reviews(db: AsyncSession = Depends(get_async_db)):
    '''
         Получение всех отзывов
    '''

    result = await db.scalars(select(ReviewModel).where(ReviewModel.is_active))

    return result.all()


@router.post("/", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(review_data: ReviewCreate,
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_user)
                        ):
    '''
         создание отзыва
    '''

    # Проверка что пользователь может оставлять один отзыв на  конкретный товар
    review_exist = await db.scalar(
        select(
            exists().where(ReviewModel.user_id == current_user.id, ReviewModel.product_id == review_data.product_id)
        )
    )
    if review_exist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You can only add one review")

    # Проверка что отзыв может создавать юзер с ролью buyer

    if current_user.role != "buyer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only buyer can create review")

    # Проверка на существование продукта
    product_exists = await db.scalar(
        select(
            exists().where(ProductModel.id == review_data.product_id, ProductModel.is_active == True)
        )
    )

    if not product_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    db_order = ReviewModel(comment=review_data.comment,
                           grade=review_data.grade,
                           user_id=current_user.id,
                           product_id=review_data.product_id
                           )

    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)

    await update_product_rating(db, review_data.product_id)

    return db_order


@router.delete("/{review_id}", response_model=dict[str, str])
async def delete_review(review_id: int,
                        current_user: UserModel = Depends(get_current_user),
                        db: AsyncSession = Depends(get_async_db)
                        ):
    """
        удаление отзыва
    """

    review_result = await db.scalars(select(ReviewModel).where(ReviewModel.id == review_id, ReviewModel.is_active))
    review = review_result.first()

    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")

    # Проверка что отзыв может удалять юзер с ролью buyer или admin
    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own reviews")

    review.is_active = False

    await db.commit()
    await db.refresh(review)

    await update_product_rating(db, review.product.id)

    return {"message": "Review deleted"}
