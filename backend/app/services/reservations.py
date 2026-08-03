from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool

CENTS = Decimal("0.01")


def to_cents(amount: Any) -> Decimal:
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


async def get_property_timezone(session, property_id: str, tenant_id: str) -> Optional[str]:
    query = text("""
        SELECT timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """)
    row = (await session.execute(query, {
        "property_id": property_id,
        "tenant_id": tenant_id
    })).fetchone()

    return row.timezone if row else None


def month_bounds_utc(month: int, year: int, timezone: str):
    tz = ZoneInfo(timezone)
    start_local = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)

    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month, using the property's local calendar.
    """
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        timezone = await get_property_timezone(session, property_id, tenant_id)
        if not timezone:
            return Decimal("0.00")

        start_date, end_date = month_bounds_utc(month, year, timezone)

        query = text("""
            SELECT SUM(total_amount) as total
            FROM reservations
            WHERE property_id = :property_id
            AND tenant_id = :tenant_id
            AND check_in_date >= :start_date
            AND check_in_date < :end_date
        """)

        row = (await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date
        })).fetchone()

        return to_cents(row.total if row else None)


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        query = text("""
            SELECT
                currency,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY currency
        """)

        rows = (await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })).fetchall()

        if len(rows) > 1:
            currencies = sorted(row.currency for row in rows)
            raise ValueError(
                f"Property {property_id} has reservations in multiple currencies {currencies}; "
                "totals cannot be summed"
            )

        row = rows[0] if rows else None

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(to_cents(row.total_revenue if row else None)),
            "currency": row.currency if row else "USD",
            "count": row.reservation_count if row else 0
        }
