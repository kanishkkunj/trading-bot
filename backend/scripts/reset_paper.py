"""Reset paper trading data for a user (orders, positions, signals)."""

import asyncio

from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.order import Order
from app.models.position import Position
from app.models.signal import Signal


async def reset_user(user_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Order).where(Order.user_id == user_id))
        await session.execute(delete(Position).where(Position.user_id == user_id))
        await session.execute(delete(Signal).where(Signal.user_id == user_id))
        await session.commit()
        print(f"Reset paper data for user {user_id}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python scripts/reset_paper.py <user_id>")
        raise SystemExit(1)

    asyncio.run(reset_user(sys.argv[1]))
