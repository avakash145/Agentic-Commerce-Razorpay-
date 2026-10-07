import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from app.db.database import engine


DEFAULT_LOGISTICS_FIRMS = [
    {
        "id": "ats",
        "name": "Amazon Transportation Services (ATS)",
        "code": "ATS-EXPRESS",
        "type": "Amazon Fleet Logistics",
        "hotline": "9909665466",
        "coverage": "Same-Day & Next-Day Prime Hubs",
    },
    {
        "id": "bluedart",
        "name": "Blue Dart Express Logistics",
        "code": "BD-AIR",
        "type": "Aviation & Ground Partner",
        "hotline": "9909665466",
        "coverage": "Domestic High-Priority Air Express",
    },
    {
        "id": "delhivery",
        "name": "Delhivery Surface & Express",
        "code": "DLV-FAST",
        "type": "National Tech Logistics Network",
        "hotline": "9909665466",
        "coverage": "Pan-India Surface Logistics",
    },
]

DEFAULT_DELIVERY_AGENTS = [
    {
        "id": "agent-101",
        "name": "Rajesh Kumar",
        "badge_id": "ATS-8821",
        "phone": "+91 98765 12044",
        "firm": "Amazon Transportation Services (ATS)",
        "vehicle": "Amazon Electric Van (KA-01-EV-4412)",
        "hub": "Bengaluru South Fulfillment DC",
        "rating": 4.9,
    },
    {
        "id": "agent-102",
        "name": "Vikram Singh",
        "badge_id": "BD-4091",
        "phone": "+91 98234 56789",
        "firm": "Blue Dart Express Logistics",
        "vehicle": "Motorcycle (KA-04-EK-9021)",
        "hub": "Whitefield Hub-04",
        "rating": 4.8,
    },
    {
        "id": "agent-103",
        "name": "Amit Sharma",
        "badge_id": "DLV-5512",
        "phone": "+91 98111 22334",
        "firm": "Delhivery Surface & Express",
        "vehicle": "Delivery Van (KA-01-MJ-3321)",
        "hub": "Koramangala DC",
        "rating": 4.85,
    },
    {
        "id": "agent-104",
        "name": "Pooja Verma",
        "badge_id": "ATS-9909",
        "phone": "+91 99096 65466",
        "firm": "Amazon Transportation Services (ATS)",
        "vehicle": "Amazon Smart Scooter (KA-05-AB-1102)",
        "hub": "Indiranagar Prime DC",
        "rating": 4.95,
    },
]


class DeliveryLogisticsService:
    """
    Manages Courier Logistics Firms, Delivery Associates, Outbound Deliveries,
    and Doorstep Return Pickups with strict 10-day return policy and instant wallet refund.
    """

    def __init__(self):
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure delivery & return columns exist on commerce_orders."""
        with engine.connect() as conn:
            conn.execute(
                text("""
                    ALTER TABLE commerce_orders 
                    ADD COLUMN IF NOT EXISTS return_status VARCHAR(50) DEFAULT 'none',
                    ADD COLUMN IF NOT EXISTS return_reason TEXT,
                    ADD COLUMN IF NOT EXISTS return_requested_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS return_otp VARCHAR(10),
                    ADD COLUMN IF NOT EXISTS delivery_otp VARCHAR(10),
                    ADD COLUMN IF NOT EXISTS logistics_firm VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS delivery_agent_name VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS delivery_agent_phone VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS delivery_agent_badge VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS return_notes TEXT;
                """)
            )
            conn.commit()

    def get_logistics_firms(self) -> List[Dict[str, Any]]:
        return list(DEFAULT_LOGISTICS_FIRMS)

    def get_delivery_agents(self) -> List[Dict[str, Any]]:
        return list(DEFAULT_DELIVERY_AGENTS)

    def assign_default_logistics(self, order_id: int) -> Dict[str, Any]:
        """Assign random or default delivery associate and OTP to an order."""
        agent = random.choice(DEFAULT_DELIVERY_AGENTS)
        delivery_otp = f"{random.randint(1000, 9999)}"
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE commerce_orders
                    SET logistics_firm = :firm,
                        delivery_agent_name = :agent,
                        delivery_agent_phone = :phone,
                        delivery_agent_badge = :badge,
                        delivery_otp = :otp
                    WHERE id = :oid
                """),
                {
                    "firm": agent["firm"],
                    "agent": agent["name"],
                    "phone": agent["phone"],
                    "badge": agent["badge_id"],
                    "otp": delivery_otp,
                    "oid": order_id,
                },
            )
            conn.commit()
        return {
            "firm": agent["firm"],
            "agent_name": agent["name"],
            "agent_phone": agent["phone"],
            "agent_badge": agent["badge_id"],
            "delivery_otp": delivery_otp,
        }

    # -------------------------------------------------------------
    # CUSTOMER RETURN WORKFLOW (Under 10 Days Constraint)
    # -------------------------------------------------------------

    def request_return(
        self,
        user_id: int,
        order_number: str,
        reason: str = "Defective / Not as described",
    ) -> Dict[str, Any]:
        """
        Customer requests an order return.
        STRICT CONSTRAINT: Must be within 10 days of order placement!
        """
        reason = reason.strip() or "Product condition issue"

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_orders WHERE order_number = :onum"),
                {"onum": order_number},
            ).mappings().first()

            if not row:
                raise ValueError(f"Order #{order_number} not found.")

            order = dict(row)

            # Check ownership (unless user_id == 0 or matches)
            if user_id and order["user_id"] != user_id:
                raise ValueError("Unauthorized: You can only return your own orders.")

            # Check status
            if order.get("status") == "cancelled":
                raise ValueError("Cancelled orders cannot be returned.")

            if order.get("return_status") in ["pickup_assigned", "approved", "returned"]:
                raise ValueError(f"Return is already {order.get('return_status')} for this order.")

            # CONSTRAINT: Return under 10 days
            created_at = order.get("created_at")
            if created_at:
                age_days = (datetime.now() - created_at).total_seconds() / (24 * 3600)
                if age_days > 10.0:
                    raise ValueError(
                        f"Return window expired ({age_days:.1f} days ago). "
                        "Amazon return policy strictly allows returns under 10 days from order placement."
                    )

            # Assign doorstep pickup associate
            agent = random.choice(DEFAULT_DELIVERY_AGENTS)
            return_otp = f"{random.randint(1000, 9999)}"

            conn.execute(
                text("""
                    UPDATE commerce_orders
                    SET return_status = 'pickup_assigned',
                        return_reason = :reason,
                        return_requested_at = CURRENT_TIMESTAMP,
                        return_otp = :otp,
                        logistics_firm = :firm,
                        delivery_agent_name = :agent,
                        delivery_agent_phone = :phone,
                        delivery_agent_badge = :badge,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :oid
                """),
                {
                    "reason": reason,
                    "otp": return_otp,
                    "firm": agent["firm"],
                    "agent": agent["name"],
                    "phone": agent["phone"],
                    "badge": agent["badge_id"],
                    "oid": order["id"],
                },
            )

            # Add tracking log
            conn.execute(
                text("""
                    INSERT INTO commerce_tracking_logs (order_id, status, description, location)
                    VALUES (:oid, 'return_requested', :desc, 'Customer Doorstep Dispatch')
                """),
                {
                    "oid": order["id"],
                    "desc": (
                        f"Return requested by customer under 10-day policy (Reason: {reason}). "
                        f"Pickup associate {agent['name']} ({agent['firm']}, Badge #{agent['badge_id']}) assigned. "
                        f"Doorstep Inspection OTP: {return_otp}."
                    ),
                },
            )
            conn.commit()

        return self.get_order_details(order_number)

    # -------------------------------------------------------------
    # DOORSTEP RETURN INSPECTION & PHONE APPROVAL (By Delivery Boy)
    # -------------------------------------------------------------

    def approve_doorstep_return(
        self,
        order_number: str,
        delivery_agent_name: str = "Rajesh Kumar",
        notes: str = "Doorstep physical inspection passed. Original packaging and accessories verified.",
        entered_otp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delivery boy visits customer house, inspects item condition,
        and approves return directly from their mobile phone.
        Triggers INSTANT REFUND to customer's Amazon Wallet!
        """
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_orders WHERE order_number = :onum"),
                {"onum": order_number},
            ).mappings().first()

            if not row:
                raise ValueError(f"Order #{order_number} not found.")

            order = dict(row)

            if order.get("return_status") == "approved":
                raise ValueError("Return has already been approved and refunded.")

            # Validate OTP if provided
            expected_otp = str(order.get("return_otp") or "")
            if entered_otp and str(entered_otp).strip() != expected_otp:
                raise ValueError(f"Invalid doorstep Return OTP '{entered_otp}'. Customer must provide OTP '{expected_otp}'.")

            order_id = order["id"]
            user_id = order["user_id"]
            refund_amt = Decimal(str(order.get("total_inr") or 0))
            firm = order.get("logistics_firm") or "Amazon Transportation Services (ATS)"

            # 1. Update order status to returned & approved
            conn.execute(
                text("""
                    UPDATE commerce_orders
                    SET return_status = 'approved',
                        status = 'returned',
                        return_notes = :notes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :oid
                """),
                {"notes": notes, "oid": order_id},
            )

            # 2. INSTANT WALLET REFUND to customer
            conn.execute(
                text("UPDATE commerce_users SET wallet_balance = wallet_balance + :amt WHERE id = :uid"),
                {"amt": refund_amt, "uid": user_id},
            )

            # 3. Log wallet transaction
            conn.execute(
                text("""
                    INSERT INTO commerce_wallet_transactions (user_id, amount, transaction_type, description, order_id)
                    VALUES (:uid, :amt, 'refund', :desc, :oid)
                """),
                {
                    "uid": user_id,
                    "amt": refund_amt,
                    "desc": (
                        f"Doorstep Return Approved by Delivery Associate {delivery_agent_name} ({firm}) "
                        f"- Instant Refund for Order #{order_number}"
                    ),
                    "oid": order_id,
                },
            )

            # 4. Insert tracking log
            conn.execute(
                text("""
                    INSERT INTO commerce_tracking_logs (order_id, status, description, location)
                    VALUES (:oid, 'return_approved', :desc, 'Customer Residence')
                """),
                {
                    "oid": order_id,
                    "desc": (
                        f"Doorstep item inspection approved by delivery associate {delivery_agent_name}. "
                        f"{notes} Instant refund of ₹{refund_amt:,.2f} credited to customer Amazon Wallet."
                    ),
                },
            )

            conn.commit()

        return self.get_order_details(order_number)

    def reject_doorstep_return(
        self,
        order_number: str,
        delivery_agent_name: str = "Rajesh Kumar",
        rejection_reason: str = "Physical damage or serial number mismatch identified during doorstep inspection.",
    ) -> Dict[str, Any]:
        """Delivery boy rejects return during doorstep inspection from phone."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_orders WHERE order_number = :onum"),
                {"onum": order_number},
            ).mappings().first()

            if not row:
                raise ValueError(f"Order #{order_number} not found.")

            order_id = row["id"]

            conn.execute(
                text("""
                    UPDATE commerce_orders
                    SET return_status = 'rejected',
                        return_notes = :notes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :oid
                """),
                {"notes": rejection_reason, "oid": order_id},
            )

            conn.execute(
                text("""
                    INSERT INTO commerce_tracking_logs (order_id, status, description, location)
                    VALUES (:oid, 'return_rejected', :desc, 'Customer Residence')
                """),
                {
                    "oid": order_id,
                    "desc": (
                        f"Doorstep return inspection failed: {rejection_reason}. "
                        f"Rejected by delivery associate {delivery_agent_name}."
                    ),
                },
            )
            conn.commit()

        return self.get_order_details(order_number)

    # -------------------------------------------------------------
    # OUTBOUND DELIVERIES (Mark Delivered from Phone)
    # -------------------------------------------------------------

    def mark_outbound_delivered(
        self,
        order_number: str,
        delivery_agent_name: str = "Rajesh Kumar",
        entered_otp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delivery boy delivers package to customer doorstep."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_orders WHERE order_number = :onum"),
                {"onum": order_number},
            ).mappings().first()

            if not row:
                raise ValueError(f"Order #{order_number} not found.")

            order = dict(row)
            order_id = order["id"]

            expected_otp = str(order.get("delivery_otp") or "")
            if entered_otp and entered_otp.strip() != expected_otp:
                raise ValueError(f"Invalid Delivery OTP '{entered_otp}'. Customer must provide OTP '{expected_otp}'.")

            conn.execute(
                text("""
                    UPDATE commerce_orders
                    SET status = 'delivered',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :oid
                """),
                {"oid": order_id},
            )

            conn.execute(
                text("""
                    INSERT INTO commerce_tracking_logs (order_id, status, description, location)
                    VALUES (:oid, 'delivered', :desc, 'Customer Doorstep')
                """),
                {
                    "oid": order_id,
                    "desc": f"Package safely delivered to customer by associate {delivery_agent_name}. Verified with delivery OTP.",
                },
            )
            conn.commit()

        return self.get_order_details(order_number)

    # -------------------------------------------------------------
    # LISTING QUERIES FOR DELIVERY PORTAL
    # -------------------------------------------------------------

    def list_delivery_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List orders for delivery associates."""
        with engine.connect() as conn:
            if status:
                rows = conn.execute(
                    text("SELECT * FROM commerce_orders WHERE status = :st ORDER BY id DESC"),
                    {"st": status},
                ).mappings().all()
            else:
                rows = conn.execute(
                    text("SELECT * FROM commerce_orders ORDER BY id DESC LIMIT 50")
                ).mappings().all()

        return [self._format_order_row(r) for r in rows]

    def list_return_pickups(self, return_status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List return requests for delivery associates to inspect at customer house."""
        with engine.connect() as conn:
            if return_status:
                rows = conn.execute(
                    text("SELECT * FROM commerce_orders WHERE return_status = :rst ORDER BY id DESC"),
                    {"rst": return_status},
                ).mappings().all()
            else:
                rows = conn.execute(
                    text("SELECT * FROM commerce_orders WHERE return_status != 'none' ORDER BY id DESC")
                ).mappings().all()

        return [self._format_order_row(r) for r in rows]

    def get_order_details(self, order_number: str) -> Optional[Dict[str, Any]]:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_orders WHERE order_number = :onum"),
                {"onum": order_number},
            ).mappings().first()

            if not row:
                return None

            ord_data = self._format_order_row(row)

            logs = conn.execute(
                text("SELECT status, description, location, timestamp FROM commerce_tracking_logs WHERE order_id = :oid ORDER BY id ASC"),
                {"oid": ord_data["id"]},
            ).mappings().all()

            ord_data["tracking_logs"] = [
                {
                    "status": l["status"],
                    "description": l["description"],
                    "location": l["location"],
                    "time": l["timestamp"].strftime("%b %d, %I:%M %p") if l.get("timestamp") else "",
                }
                for l in logs
            ]

            return ord_data

    def _format_order_row(self, row: Any) -> Dict[str, Any]:
        d = dict(row)
        import json
        d["subtotal_inr"] = float(d.get("subtotal_inr") or 0)
        d["discount_inr"] = float(d.get("discount_inr") or 0)
        d["total_inr"] = float(d.get("total_inr") or 0)
        d["created_at_fmt"] = d["created_at"].strftime("%B %d, %Y at %I:%M %p") if d.get("created_at") else ""
        d["items"] = d.get("items_json") if isinstance(d.get("items_json"), list) else json.loads(d.get("items_json") or "[]")
        d["shipping_address"] = d.get("shipping_address_json") if isinstance(d.get("shipping_address_json"), dict) else json.loads(d.get("shipping_address_json") or "{}")

        # Calculate return eligibility (under 10 days)
        if d.get("created_at"):
            age_days = (datetime.now() - d["created_at"]).total_seconds() / (24 * 3600)
            d["age_days"] = round(age_days, 1)
            d["is_return_eligible"] = (age_days <= 10.0) and (d.get("status") not in ["cancelled", "returned"]) and (d.get("return_status") in ["none", None])
            d["return_window_days_left"] = max(0, round(10.0 - age_days, 1))
        else:
            d["age_days"] = 0
            d["is_return_eligible"] = True
            d["return_window_days_left"] = 10.0

        return d


# Singleton instance
_delivery_logistics_service = None

def get_delivery_logistics_service() -> DeliveryLogisticsService:
    global _delivery_logistics_service
    if _delivery_logistics_service is None:
        _delivery_logistics_service = DeliveryLogisticsService()
    return _delivery_logistics_service
