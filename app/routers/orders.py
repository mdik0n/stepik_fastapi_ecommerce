from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import selectinload

from app.db_depends import get_async_db
from app.auth import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orders import Order as OrderModel, OrderItem as OrderItemModel
from app.models.users import User as UserModel
from app.models.cart_items import CartItem as CartItemModel
from app.schemas import Order as OrderSchema, OrderList as OrderListSchema
from sqlalchemy import select, delete, func
from decimal import Decimal

router = APIRouter(prefix="/order", tags=["order"])


async def _load_order_with_order_items(order_id: int, db: AsyncSession) -> OrderModel | None:
    result = await db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.order_items).selectinload(OrderItemModel.product))
        .where(OrderModel.id == order_id)
    )

    return result.first()


@router.post("/checkout", response_model=OrderSchema, status_code=status.HTTP_201_CREATED)
async def checkout(
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    Создаёт заказ на основе текущей корзины пользователя.
    Сохраняет позиции заказа, вычитает остатки и очищает корзину.
    """
    cart_items_result = await db.scalars(
        select(CartItemModel)
        .options(selectinload(CartItemModel.product))
        .where(CartItemModel.user_id == current_user.id)
    )

    cart_items = cart_items_result.all()

    if not cart_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found")

    order = OrderModel(user_id=current_user.id)

    total_amount = Decimal("0")

    for cart_item in cart_items:
        product = cart_item.product

        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {cart_item.product_id} is unavailable",
            )

        if product.stock < cart_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not enough stock for product {product.name}",
            )

        unit_price = product.price
        if unit_price is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {product.name} has no price set",
            )
        total_price = cart_item.quantity * unit_price
        total_amount += total_price

        order_item = OrderItemModel(
            product_id=product.id,
            quantity=cart_item.quantity,
            unit_price=unit_price,
            total_price=total_price
        )

        order.order_items.append(order_item)
        product.stock -= cart_item.quantity

    order.total_amount = total_amount

    db.add(order)

    await db.execute(delete(CartItemModel).where(CartItemModel.user_id == current_user.id))
    await db.commit()

    created_order = await _load_order_with_order_items(order.id, db)

    if not created_order:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load created order",
        )

    return created_order


@router.get("/", response_model=OrderListSchema)
async def get_user_orders(
        page: int = Query(default=1),
        page_size: int = Query(default=20),
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    Возвращает заказы текущего пользователя с простой пагинацией.
    """
    total = await db.scalar(
        select(func.count(OrderModel.id))
        .where(OrderModel.user_id == current_user.id)
    )

    order_result = await db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.order_items).selectinload(OrderItemModel.product))
        .where(OrderModel.user_id == current_user.id)
        .order_by(OrderModel.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    order_items = order_result.all()

    return OrderListSchema(
        items=order_items,
        total=total or 0,
        page=page,
        page_size=page_size
    )


@router.get("/{order_id}", response_model=OrderSchema)
async def get_order(
        order_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_user)
):
    """
    Возвращает детальную информацию по заказу, если он принадлежит пользователю.
    """
    order = await _load_order_with_order_items(order_id, db)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return order
