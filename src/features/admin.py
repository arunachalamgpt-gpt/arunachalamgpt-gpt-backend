# src/features/admin.py
"""
Admin commands — only accessible from ADMIN_PHONE.
Usage: ADMIN config rs50_sold_out true
       ADMIN crowd F:180 T50:45 T200:15
       ADMIN stats
"""
from src.database import get_db
from src.whatsapp import send_text
import logging

logger = logging.getLogger(__name__)


async def handle_admin(phone: str, text: str) -> None:
    """Handle admin commands."""
    parts = text.strip().split()
    if len(parts) < 2:
        await send_text(phone, "Admin commands:\nADMIN config [key] [value]\nADMIN stats")
        return

    command = parts[1].upper()

    if command == "CONFIG" and len(parts) >= 4:
        key = parts[2]
        value = parts[3]
        db = get_db()
        db.table("temple_config").update({"value": value})\
            .eq("key", key).execute()
        await send_text(phone, f"Updated: {key} = {value}")

    elif command == "CROWD" and len(parts) >= 3:
        raw = " ".join(parts[2:])
        from src.features.crowd_alert import handle_volunteer_report
        await handle_volunteer_report(phone, raw)

    elif command == "STATS":
        db = get_db()
        users = db.table("devotee_profile").select("phone", count="exact").execute()
        bookings = db.table("lodge_bookings").select("id", count="exact").execute()
        await send_text(phone,
            f"Stats:\n"
            f"Total users: {users.count or 0}\n"
            f"Lodge bookings: {bookings.count or 0}"
        )
    else:
        await send_text(phone, "Unknown admin command.")