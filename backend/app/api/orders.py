"""Orders API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.order import OrderStatus
from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderListResponse,
    OrderUpdate,
)
from app.services.order_service import OrderService

router = APIRouter()


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Create a new order."""
    order_service = OrderService(db)
    user_id = 1  # Single-user mode
    try:
        order = await order_service.create_order(user_id, order_data)
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/", response_model=OrderListResponse)
async def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    symbol: Optional[str] = None,
    status: Optional[OrderStatus] = None,
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """List orders for the single user."""
    order_service = OrderService(db)
    user_id = 1  # Single-user mode
    orders = await order_service.get_user_orders(
        user_id,
        skip=skip,
        limit=limit,
        symbol=symbol,
        status=status,
    )
    total = await order_service.get_order_count(user_id)
    return OrderListResponse(
        orders=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Get a specific order for the single user."""
    order_service = OrderService(db)
    user_id = 1  # Single-user mode
    order = await order_service.get_order(order_id, user_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return OrderResponse.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Cancel an order for the single user."""
    order_service = OrderService(db)
    user_id = 1  # Single-user mode
    try:
        order = await order_service.cancel_order(order_id, user_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    update_data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Update an order for the single user."""
    order_service = OrderService(db)
    user_id = 1  # Single-user mode
    try:
        order = await order_service.update_order(
            order_id, user_id, update_data
        )
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
