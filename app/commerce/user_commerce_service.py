import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from app.db.database import engine


def _hash_password(password: str) -> str:
    """Generate SHA-256 hash with salt for secure password storage."""
    salt = "agentic_commerce_salt_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class UserCommerceService:
    """
    Central service managing user accounts, shopping cart CRUD,
    orders with live tracking logs, wallet balance, and diamond rewards.
    """

    def __init__(self):
        self._ensure_schema()
        self._seed_demo_data_if_needed()

    def _ensure_schema(self):
        """Ensure all required PostgreSQL tables exist."""
        sql = """
        CREATE TABLE IF NOT EXISTS commerce_users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(128) NOT NULL,
            full_name VARCHAR(120) NOT NULL,
            wallet_balance NUMERIC(12, 2) DEFAULT 5000.00,
            diamonds_balance INTEGER DEFAULT 500,
            is_prime BOOLEAN DEFAULT TRUE,
            address_line1 VARCHAR(255) DEFAULT '221B Baker Street, Tech Park',
            city VARCHAR(100) DEFAULT 'Bengaluru',
            state VARCHAR(100) DEFAULT 'Karnataka',
            postal_code VARCHAR(20) DEFAULT '560001',
            country VARCHAR(50) DEFAULT 'India',
            phone VARCHAR(20) DEFAULT '+91 98765 43210',
            persona_info TEXT DEFAULT '',
            last_daily_claim TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE commerce_users ADD COLUMN IF NOT EXISTS persona_info TEXT DEFAULT '';

        CREATE TABLE IF NOT EXISTS commerce_cart_items (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES commerce_users(id) ON DELETE CASCADE,
            asin VARCHAR(40) NOT NULL,
            title TEXT NOT NULL,
            price_inr NUMERIC(12, 2) NOT NULL,
            price_usd NUMERIC(12, 2),
            image_url TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_user_asin UNIQUE(user_id, asin)
        );

        CREATE TABLE IF NOT EXISTS commerce_orders (
            id SERIAL PRIMARY KEY,
            order_number VARCHAR(64) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES commerce_users(id) ON DELETE CASCADE,
            items_json JSONB NOT NULL,
            subtotal_inr NUMERIC(12, 2) NOT NULL,
            discount_inr NUMERIC(12, 2) DEFAULT 0.00,
            delivery_fee_inr NUMERIC(12, 2) DEFAULT 0.00,
            total_inr NUMERIC(12, 2) NOT NULL,
            diamonds_earned INTEGER DEFAULT 0,
            diamonds_used INTEGER DEFAULT 0,
            payment_method VARCHAR(40) NOT NULL DEFAULT 'razorpay',
            razorpay_order_id VARCHAR(100),
            razorpay_payment_id VARCHAR(100),
            status VARCHAR(40) NOT NULL DEFAULT 'confirmed',
            shipping_address_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS commerce_tracking_logs (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES commerce_orders(id) ON DELETE CASCADE,
            status VARCHAR(40) NOT NULL,
            description TEXT NOT NULL,
            location VARCHAR(120) DEFAULT 'Fulfillment Hub',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS commerce_wallet_transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES commerce_users(id) ON DELETE CASCADE,
            amount NUMERIC(12, 2) NOT NULL,
            transaction_type VARCHAR(20) NOT NULL,
            description TEXT NOT NULL,
            order_id INTEGER REFERENCES commerce_orders(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

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
        """
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()

    def _seed_demo_data_if_needed(self):
        """Seed demo user and initial orders if none exist."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM commerce_users WHERE email = :email"),
                {"email": "alex@amazon.com"},
            ).first()

            if not row:
                # Create demo user
                pass_hash = _hash_password("amazon123")
                res = conn.execute(
                    text("""
                        INSERT INTO commerce_users (
                            username, email, password_hash, full_name, wallet_balance, diamonds_balance, is_prime
                        ) VALUES (
                            'alex_johnson', 'alex@amazon.com', :pwd, 'Alex Johnson', 5000.00, 500, TRUE
                        ) RETURNING id
                    """),
                    {"pwd": pass_hash},
                )
                user_id = res.scalar()

                # Add initial sample orders for tracking logs & buy again
                sample_items = [
                    {
                        "asin": "B0G78Y2ZG8",
                        "title": "15.6-inch laptop, 8GB DDR 256GB SSD Windows 11 Pro",
                        "price_inr": 25036.00,
                        "quantity": 1,
                        "image_url": "https://m.media-amazon.com/images/I/71srEXqpxAL._AC_SY300_SX300_QL70_FMwebp_.jpg",
                    }
                ]
                order_num = f"OD-{uuid.uuid4().hex[:8].upper()}"
                shipping_addr = {
                    "full_name": "Alex Johnson",
                    "address_line1": "221B Baker Street, Tech Park",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "postal_code": "560001",
                    "phone": "+91 98765 43210",
                }
                ord_res = conn.execute(
                    text("""
                        INSERT INTO commerce_orders (
                            order_number, user_id, items_json, subtotal_inr, discount_inr, total_inr,
                            diamonds_earned, diamonds_used, payment_method, razorpay_payment_id,
                            status, shipping_address_json, created_at
                        ) VALUES (
                            :ord_num, :uid, :items, 25036.00, 0.00, 25036.00,
                            250, 0, 'razorpay', 'pay_TkSample9182',
                            'shipped', :addr, :dt
                        ) RETURNING id
                    """),
                    {
                        "ord_num": order_num,
                        "uid": user_id,
                        "items": json.dumps(sample_items),
                        "addr": json.dumps(shipping_addr),
                        "dt": datetime.now() - timedelta(days=1),
                    },
                )
                order_id = ord_res.scalar()

                # Sample tracking logs
                conn.execute(
                    text("""
                        INSERT INTO commerce_tracking_logs (order_id, status, description, location, timestamp)
                        VALUES
                        (:oid, 'confirmed', 'Order placed & Payment verified via Razorpay', 'Bengaluru Hub', :t1),
                        (:oid, 'processing', 'Package packed and checked at Amazon Fulfillment Center', 'Bengaluru FC-04', :t2),
                        (:oid, 'shipped', 'Dispatched with Amazon Agentic Express AWB #AGY-98217', 'Bengaluru Sort Facility', :t3)
                    """),
                    {
                        "oid": order_id,
                        "t1": datetime.now() - timedelta(days=1, hours=3),
                        "t2": datetime.now() - timedelta(days=1, hours=1),
                        "t3": datetime.now() - timedelta(hours=14),
                    },
                )
                conn.commit()

    # ---------------------------------------------------------
    # USER AUTH & PROFILE CRUD
    # ---------------------------------------------------------

    def get_default_user(self) -> Dict[str, Any]:
        """Fetch the default demo user."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_users ORDER BY id ASC LIMIT 1")
            ).mappings().first()
            if row:
                data = dict(row)
                data.pop("password_hash", None)
                data["wallet_balance"] = float(data.get("wallet_balance") or 0)
                return data
        return {}

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM commerce_users WHERE id = :id"),
                {"id": user_id},
            ).mappings().first()
            if row:
                data = dict(row)
                data.pop("password_hash", None)
                data["wallet_balance"] = float(data.get("wallet_balance") or 0)
                return data
        return None

    def signup(self, username: str, email: str, password: str, full_name: str) -> Dict[str, Any]:
        username = username.strip().lower()
        email = email.strip().lower()
        full_name = full_name.strip() or username.title()

        with engine.connect() as conn:
            existing = conn.execute(
                text("SELECT id FROM commerce_users WHERE email = :e OR username = :u"),
                {"e": email, "u": username},
            ).first()
            if existing:
                raise ValueError("User with this email or username already exists.")

            pwd_hash = _hash_password(password)
            res = conn.execute(
                text("""
                    INSERT INTO commerce_users (
                        username, email, password_hash, full_name, wallet_balance, diamonds_balance, is_prime
                    ) VALUES (
                        :u, :e, :p, :fn, 2500.00, 250, TRUE
                    ) RETURNING id
                """),
                {"u": username, "e": email, "p": pwd_hash, "fn": full_name},
            )
            user_id = res.scalar()
            conn.commit()

        return self.get_user_by_id(user_id) or {}

    def login(self, email_or_username: str, password: str) -> Optional[Dict[str, Any]]:
        key = email_or_username.strip().lower()
        pwd_hash = _hash_password(password)

        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id FROM commerce_users
                    WHERE (email = :k OR username = :k) AND password_hash = :p
                """),
                {"k": key, "p": pwd_hash},
            ).first()

            if row:
                return self.get_user_by_id(row[0])
        return None

    def update_profile(self, user_id: int, full_name: str, address_line1: str,
                       city: str, state: str, postal_code: str, phone: str) -> Dict[str, Any]:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE commerce_users
                    SET full_name = :fn, address_line1 = :a1, city = :c,
                        state = :s, postal_code = :pc, phone = :ph
                    WHERE id = :uid
                """),
                {
                    "fn": full_name, "a1": address_line1, "c": city,
                    "s": state, "pc": postal_code, "ph": phone, "uid": user_id,
                },
            )
            conn.commit()
        return self.get_user_by_id(user_id) or {}

    def get_user_persona(self, user_id: int) -> str:
        with engine.connect() as conn:
            val = conn.execute(
                text("SELECT persona_info FROM commerce_users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar()
            return (val or "").strip()

    def update_user_persona(self, user_id: int, persona_text: str) -> str:
        words = persona_text.split()
        if len(words) > 800:
            persona_text = " ".join(words[:800])
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE commerce_users SET persona_info = :info WHERE id = :uid"),
                {"info": persona_text, "uid": user_id},
            )
            conn.commit()
        return persona_text

    # ---------------------------------------------------------
    # CART CRUD OPERATIONS (Window for Quantity, Add, Update, Remove)
    # ---------------------------------------------------------

    def get_cart(self, user_id: int) -> Dict[str, Any]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, asin, title, price_inr, price_usd, image_url, quantity, updated_at
                    FROM commerce_cart_items
                    WHERE user_id = :uid
                    ORDER BY id ASC
                """),
                {"uid": user_id},
            ).mappings().all()

        items = []
        subtotal = Decimal("0.00")
        total_quantity = 0

        for r in rows:
            it = dict(r)
            price_inr = Decimal(str(it.get("price_inr") or 0))
            qty = int(it.get("quantity") or 1)
            line_total = price_inr * qty
            subtotal += line_total
            total_quantity += qty

            it["price_inr"] = float(price_inr)
            it["line_total_inr"] = float(line_total)
            it["quantity"] = qty
            items.append(it)

        # Rewards calculation: 10% diamonds back
        diamonds_earn = int(float(subtotal) * 0.1)

        return {
            "items": items,
            "total_items": total_quantity,
            "subtotal_inr": float(subtotal),
            "delivery_fee_inr": 0.00 if subtotal > 499 or len(items) == 0 else 40.00,
            "total_inr": float(subtotal) if subtotal > 499 or len(items) == 0 else float(subtotal + Decimal("40.00")),
            "diamonds_to_earn": diamonds_earn,
        }

    def add_to_cart(self, user_id: int, asin: str, title: str,
                    price_inr: float, price_usd: Optional[float] = None,
                    image_url: Optional[str] = None, quantity: int = 1) -> Dict[str, Any]:
        qty = max(1, int(quantity))
        price_inr_dec = round(Decimal(str(price_inr)), 2)
        price_usd_dec = round(Decimal(str(price_usd)), 2) if price_usd else None

        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO commerce_cart_items (
                        user_id, asin, title, price_inr, price_usd, image_url, quantity, updated_at
                    ) VALUES (
                        :uid, :asin, :title, :price_inr, :price_usd, :img, :qty, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (user_id, asin)
                    DO UPDATE SET
                        quantity = commerce_cart_items.quantity + EXCLUDED.quantity,
                        price_inr = EXCLUDED.price_inr,
                        image_url = COALESCE(EXCLUDED.image_url, commerce_cart_items.image_url),
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "uid": user_id, "asin": asin, "title": title,
                    "price_inr": price_inr_dec, "price_usd": price_usd_dec,
                    "img": image_url, "qty": qty,
                },
            )
            conn.commit()

        return self.get_cart(user_id)

    def update_cart_quantity(self, user_id: int, asin: str, quantity: int) -> Dict[str, Any]:
        with engine.connect() as conn:
            if quantity <= 0:
                conn.execute(
                    text("DELETE FROM commerce_cart_items WHERE user_id = :uid AND asin = :asin"),
                    {"uid": user_id, "asin": asin},
                )
            else:
                conn.execute(
                    text("""
                        UPDATE commerce_cart_items
                        SET quantity = :qty, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :uid AND asin = :asin
                    """),
                    {"uid": user_id, "asin": asin, "qty": quantity},
                )
            conn.commit()

        return self.get_cart(user_id)

    def remove_from_cart(self, user_id: int, asin: str) -> Dict[str, Any]:
        with engine.connect() as conn:
            conn.execute(
                text("DELETE FROM commerce_cart_items WHERE user_id = :uid AND asin = :asin"),
                {"uid": user_id, "asin": asin},
            )
            conn.commit()

        return self.get_cart(user_id)

    def clear_cart(self, user_id: int) -> Dict[str, Any]:
        with engine.connect() as conn:
            conn.execute(
                text("DELETE FROM commerce_cart_items WHERE user_id = :uid"),
                {"uid": user_id},
            )
            conn.commit()

        return self.get_cart(user_id)

    # ---------------------------------------------------------
    # WALLET & DIAMONDS REWARDS SYSTEM
    # ---------------------------------------------------------

    def get_wallet_info(self, user_id: int) -> Dict[str, Any]:
        with engine.connect() as conn:
            user = conn.execute(
                text("SELECT wallet_balance, diamonds_balance, is_prime, last_daily_claim FROM commerce_users WHERE id = :uid"),
                {"uid": user_id},
            ).mappings().first()

            txs = conn.execute(
                text("""
                    SELECT id, amount, transaction_type, description, created_at
                    FROM commerce_wallet_transactions
                    WHERE user_id = :uid
                    ORDER BY id DESC LIMIT 20
                """),
                {"uid": user_id},
            ).mappings().all()

        if not user:
            return {"wallet_balance": 0.00, "diamonds_balance": 0, "transactions": []}

        # Check daily claim status
        last_claim = user.get("last_daily_claim")
        can_claim_daily = True
        if last_claim:
            can_claim_daily = (datetime.now() - last_claim) > timedelta(hours=20)

        transactions = [
            {
                "id": t["id"],
                "amount": float(t["amount"]),
                "type": t["transaction_type"],
                "description": t["description"],
                "created_at": t["created_at"].strftime("%b %d, %Y, %I:%M %p") if t.get("created_at") else "",
            }
            for t in txs
        ]

        return {
            "wallet_balance": float(user.get("wallet_balance") or 0),
            "diamonds_balance": int(user.get("diamonds_balance") or 0),
            "is_prime": bool(user.get("is_prime")),
            "can_claim_daily": can_claim_daily,
            "transactions": transactions,
        }

    def topup_wallet(self, user_id: int, amount: float) -> Dict[str, Any]:
        amount_dec = round(Decimal(str(amount)), 2)
        if amount_dec <= 0:
            raise ValueError("Amount must be greater than zero.")

        with engine.connect() as conn:
            conn.execute(
                text("UPDATE commerce_users SET wallet_balance = wallet_balance + :amt WHERE id = :uid"),
                {"amt": amount_dec, "uid": user_id},
            )
            conn.execute(
                text("""
                    INSERT INTO commerce_wallet_transactions (user_id, amount, transaction_type, description)
                    VALUES (:uid, :amt, 'credit', 'Added Money to Amazon Agentic Wallet')
                """),
                {"uid": user_id, "amt": amount_dec},
            )
            conn.commit()

        return self.get_wallet_info(user_id)

    def claim_daily_diamonds(self, user_id: int) -> Dict[str, Any]:
        bonus_diamonds = 50
        with engine.connect() as conn:
            user = conn.execute(
                text("SELECT last_daily_claim, diamonds_balance FROM commerce_users WHERE id = :uid"),
                {"uid": user_id},
            ).mappings().first()

            if not user:
                raise ValueError("User not found")

            last_claim = user.get("last_daily_claim")
            if last_claim and (datetime.now() - last_claim) < timedelta(hours=20):
                return {
                    "claimed": False,
                    "message": "Daily streak bonus already claimed today! Check back tomorrow.",
                    "diamonds_balance": int(user.get("diamonds_balance") or 0),
                }

            conn.execute(
                text("""
                    UPDATE commerce_users
                    SET diamonds_balance = diamonds_balance + :bonus,
                        last_daily_claim = CURRENT_TIMESTAMP
                    WHERE id = :uid
                """),
                {"bonus": bonus_diamonds, "uid": user_id},
            )
            conn.commit()

        wallet_info = self.get_wallet_info(user_id)
        wallet_info["claimed"] = True
        wallet_info["message"] = f"🎉 Claimed +{bonus_diamonds} Diamonds daily streak reward!"
        return wallet_info

    # ---------------------------------------------------------
    # ORDERS & LIVE TRACKING LOGS (Amazon-like)
    # ---------------------------------------------------------

    def create_order(
        self,
        user_id: int,
        items: List[Dict[str, Any]],
        payment_method: str = "razorpay",
        shipping_address: Optional[Dict[str, Any]] = None,
        razorpay_order_id: Optional[str] = None,
        razorpay_payment_id: Optional[str] = None,
        diamonds_to_use: int = 0,
        from_cart: bool = True,
    ) -> Dict[str, Any]:
        """
        Creates an Amazon-style confirmed order with audit/tracking logs,
        updates diamond balance and wallet balance if used.
        """
        if not items:
            raise ValueError("Order must contain at least one item.")

        subtotal = Decimal("0.00")
        processed_items = []
        for it in items:
            price = Decimal(str(it.get("price_inr") or 0))
            qty = max(1, int(it.get("quantity") or 1))
            subtotal += price * qty
            processed_items.append({
                "asin": it.get("asin"),
                "title": it.get("title"),
                "price_inr": float(price),
                "quantity": qty,
                "image_url": it.get("image_url") or it.get("image"),
            })

        # Calculate discount from Diamonds (100 diamonds = ₹100 discount)
        discount_inr = Decimal("0.00")
        diamonds_used = 0
        if diamonds_to_use > 0:
            user = self.get_user_by_id(user_id)
            current_diamonds = user.get("diamonds_balance", 0) if user else 0
            diamonds_used = min(diamonds_to_use, current_diamonds, int(subtotal))
            discount_inr = Decimal(str(diamonds_used))

        total_inr = max(Decimal("0.00"), subtotal - discount_inr)
        diamonds_earned = int(float(total_inr) * 0.1)

        # Default shipping address if none provided
        if not shipping_address:
            user = self.get_user_by_id(user_id) or {}
            shipping_address = {
                "full_name": user.get("full_name") or "Alex Johnson",
                "address_line1": user.get("address_line1") or "221B Baker Street, Tech Park",
                "city": user.get("city") or "Bengaluru",
                "state": user.get("state") or "Karnataka",
                "postal_code": user.get("postal_code") or "560001",
                "country": user.get("country") or "India",
                "phone": user.get("phone") or "+91 98765 43210",
            }

        order_number = f"OD-{uuid.uuid4().hex[:8].upper()}"

        with engine.connect() as conn:
            # If paid with wallet, deduct wallet balance
            if payment_method == "wallet":
                user = conn.execute(
                    text("SELECT wallet_balance FROM commerce_users WHERE id = :uid"),
                    {"uid": user_id},
                ).mappings().first()
                curr_balance = Decimal(str(user.get("wallet_balance") or 0)) if user else Decimal("0")
                if curr_balance < total_inr:
                    raise ValueError(f"Insufficient wallet balance (₹{curr_balance}) for order total (₹{total_inr}).")
                conn.execute(
                    text("UPDATE commerce_users SET wallet_balance = wallet_balance - :amt WHERE id = :uid"),
                    {"amt": total_inr, "uid": user_id},
                )
                conn.execute(
                    text("""
                        INSERT INTO commerce_wallet_transactions (user_id, amount, transaction_type, description)
                        VALUES (:uid, :amt, 'debit', :desc)
                    """),
                    {"uid": user_id, "amt": total_inr, "desc": f"Payment for Order #{order_number}"},
                )

            # Update diamonds (deduct used, add earned)
            net_diamonds = diamonds_earned - diamonds_used
            conn.execute(
                text("UPDATE commerce_users SET diamonds_balance = diamonds_balance + :net WHERE id = :uid"),
                {"net": net_diamonds, "uid": user_id},
            )

            # Assign logistics courier partner and generate 4-digit Delivery OTP
            courier_pool = [
                {"firm": "Amazon Transportation Services (ATS)", "name": "Rajesh Kumar", "phone": "+91 98765 12044", "badge": "ATS-8821"},
                {"firm": "Blue Dart Express Logistics", "name": "Vikram Singh", "phone": "+91 98234 56789", "badge": "BD-4091"},
                {"firm": "Delhivery Surface & Express", "name": "Amit Sharma", "phone": "+91 98111 22334", "badge": "DLV-5512"},
                {"firm": "Amazon Transportation Services (ATS)", "name": "Pooja Verma", "phone": "+91 99096 65466", "badge": "ATS-9909"},
            ]
            assigned_courier = random.choice(courier_pool)
            delivery_otp = f"{random.randint(1000, 9999)}"

            # Insert order
            ord_res = conn.execute(
                text("""
                    INSERT INTO commerce_orders (
                        order_number, user_id, items_json, subtotal_inr, discount_inr, total_inr,
                        diamonds_earned, diamonds_used, payment_method, razorpay_order_id,
                        razorpay_payment_id, status, shipping_address_json,
                        logistics_firm, delivery_agent_name, delivery_agent_phone, delivery_agent_badge,
                        delivery_otp, return_status
                    ) VALUES (
                        :ord_num, :uid, :items, :subtotal, :disc, :total,
                        :d_earned, :d_used, :pmethod, :rzp_oid,
                        :rzp_pid, 'shipped', :addr,
                        :firm, :d_agent, :d_phone, :d_badge,
                        :d_otp, 'none'
                    ) RETURNING id
                """),
                {
                    "ord_num": order_number,
                    "uid": user_id,
                    "items": json.dumps(processed_items),
                    "subtotal": subtotal,
                    "disc": discount_inr,
                    "total": total_inr,
                    "d_earned": diamonds_earned,
                    "d_used": diamonds_used,
                    "pmethod": payment_method,
                    "rzp_oid": razorpay_order_id,
                    "rzp_pid": razorpay_payment_id or ("wallet_paid" if payment_method == "wallet" else None),
                    "addr": json.dumps(shipping_address),
                    "firm": assigned_courier["firm"],
                    "d_agent": assigned_courier["name"],
                    "d_phone": assigned_courier["phone"],
                    "d_badge": assigned_courier["badge"],
                    "d_otp": delivery_otp,
                },
            )
            order_id = ord_res.scalar()

            # Check and process Deal Cashback (n rupees cashback offer)
            total_cashback = Decimal("0.00")
            for it in items:
                asin = it.get("asin")
                qty = max(1, int(it.get("quantity") or 1))
                item_cb = Decimal(str(it.get("cashback_inr") or 0))
                if item_cb <= 0 and asin:
                    prod_row = conn.execute(
                        text("SELECT raw_data FROM products WHERE asin = :a"),
                        {"a": asin},
                    ).mappings().first()
                    if prod_row and prod_row.get("raw_data"):
                        rd = prod_row["raw_data"]
                        if isinstance(rd, dict) and rd.get("deal", {}).get("cashback_inr"):
                            item_cb = Decimal(str(rd["deal"]["cashback_inr"]))
                if item_cb > 0:
                    total_cashback += item_cb * qty

            if total_cashback > 0:
                conn.execute(
                    text("UPDATE commerce_users SET wallet_balance = wallet_balance + :cb WHERE id = :uid"),
                    {"cb": total_cashback, "uid": user_id},
                )
                conn.execute(
                    text("""
                        INSERT INTO commerce_wallet_transactions (user_id, amount, transaction_type, description, order_id)
                        VALUES (:uid, :cb, 'credit', :desc, :oid)
                    """),
                    {
                        "uid": user_id,
                        "cb": total_cashback,
                        "desc": f"Limited Time Deal Cashback: ₹{total_cashback:,.2f} credited for Order #{order_number}",
                        "oid": order_id,
                    },
                )

            # Insert initial Amazon-style tracking logs
            now = datetime.now()
            conn.execute(
                text("""
                    INSERT INTO commerce_tracking_logs (order_id, status, description, location, timestamp)
                    VALUES
                    (:oid, 'confirmed', :desc1, 'Bengaluru Fulfillment Center', :t1),
                    (:oid, 'processing', 'Order verified and packed by Amazon Automated Robotics', 'FC-04 Whitefield', :t2),
                    (:oid, 'shipped', :desc3, 'South Logistics Hub', :t3)
                """),
                {
                    "oid": order_id,
                    "desc1": f"Order #{order_number} confirmed. Payment of ₹{total_inr:,.2f} authorized via {payment_method.title()}.",
                    "desc3": f"Dispatched with {assigned_courier['firm']}. Assigned associate: {assigned_courier['name']} (Badge #{assigned_courier['badge']}). Delivery OTP: {delivery_otp}.",
                    "t1": now,
                    "t2": now + timedelta(minutes=15),
                    "t3": now + timedelta(hours=2),
                },
            )

            if total_cashback > 0:
                conn.execute(
                    text("""
                        INSERT INTO commerce_tracking_logs (order_id, status, description, location, timestamp)
                        VALUES (:oid, 'cashback_credited', :cb_desc, 'Amazon Rewards & Wallet Engine', :t_cb)
                    """),
                    {
                        "oid": order_id,
                        "cb_desc": f"Promotional Deal Cashback of ₹{total_cashback:,.2f} credited to your Amazon Wallet!",
                        "t_cb": now,
                    },
                )

            # Clear cart if checked out from cart
            if from_cart:
                conn.execute(
                    text("DELETE FROM commerce_cart_items WHERE user_id = :uid"),
                    {"uid": user_id},
                )

            conn.commit()

        return self.get_order(order_number) or {}

    def get_orders(self, user_id: int) -> List[Dict[str, Any]]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, order_number, items_json, subtotal_inr, discount_inr, total_inr,
                           diamonds_earned, diamonds_used, payment_method, razorpay_payment_id,
                           status, shipping_address_json, created_at,
                           return_status, return_reason, return_requested_at, return_otp,
                           delivery_otp, logistics_firm, delivery_agent_name, delivery_agent_phone,
                           delivery_agent_badge, return_notes
                    FROM commerce_orders
                    WHERE user_id = :uid
                    ORDER BY id DESC
                """),
                {"uid": user_id},
            ).mappings().all()

            order_ids = [r["id"] for r in rows]
            logs_map = {}
            if order_ids:
                placeholders = ", ".join(f":oid_{i}" for i in range(len(order_ids)))
                params = {f"oid_{i}": oid for i, oid in enumerate(order_ids)}
                log_rows = conn.execute(
                    text(f"""
                        SELECT order_id, status, description, location, timestamp
                        FROM commerce_tracking_logs
                        WHERE order_id IN ({placeholders})
                        ORDER BY id ASC
                    """),
                    params,
                ).mappings().all()
                for l in log_rows:
                    logs_map.setdefault(l["order_id"], []).append({
                        "status": l["status"],
                        "description": l["description"],
                        "location": l["location"],
                        "time": l["timestamp"].strftime("%b %d, %I:%M %p") if l.get("timestamp") else "",
                    })

        orders = []
        for r in rows:
            ord_dict = dict(r)
            ord_dict["subtotal_inr"] = float(ord_dict.get("subtotal_inr") or 0)
            ord_dict["discount_inr"] = float(ord_dict.get("discount_inr") or 0)
            ord_dict["total_inr"] = float(ord_dict.get("total_inr") or 0)
            ord_dict["created_at_fmt"] = ord_dict["created_at"].strftime("%B %d, %Y at %I:%M %p") if ord_dict.get("created_at") else ""
            ord_dict["items"] = ord_dict.get("items_json") if isinstance(ord_dict.get("items_json"), list) else json.loads(ord_dict.get("items_json") or "[]")
            ord_dict["shipping_address"] = ord_dict.get("shipping_address_json") if isinstance(ord_dict.get("shipping_address_json"), dict) else json.loads(ord_dict.get("shipping_address_json") or "{}")
            ord_dict["tracking_logs"] = logs_map.get(ord_dict["id"], [])

            # Calculate 10-day return eligibility
            if ord_dict.get("created_at"):
                age_days = (datetime.now() - ord_dict["created_at"]).total_seconds() / (24 * 3600)
                ord_dict["age_days"] = round(age_days, 1)
                ord_dict["is_return_eligible"] = (age_days <= 10.0) and (ord_dict.get("status") not in ["cancelled", "returned"]) and (ord_dict.get("return_status") in ["none", None, ""])
                ord_dict["return_window_days_left"] = max(0, round(10.0 - age_days, 1))
            else:
                ord_dict["age_days"] = 0
                ord_dict["is_return_eligible"] = True
                ord_dict["return_window_days_left"] = 10.0

            orders.append(ord_dict)

        return orders

    def get_order(self, order_number: str) -> Optional[Dict[str, Any]]:
        with engine.connect() as conn:
            r = conn.execute(
                text("""
                    SELECT id, order_number, user_id, items_json, subtotal_inr, discount_inr, total_inr,
                           diamonds_earned, diamonds_used, payment_method, razorpay_payment_id,
                           status, shipping_address_json, created_at,
                           return_status, return_reason, return_requested_at, return_otp,
                           delivery_otp, logistics_firm, delivery_agent_name, delivery_agent_phone,
                           delivery_agent_badge, return_notes
                    FROM commerce_orders
                    WHERE order_number = :onum
                """),
                {"onum": order_number},
            ).mappings().first()

            if not r:
                return None

            ord_dict = dict(r)
            logs = conn.execute(
                text("""
                    SELECT status, description, location, timestamp
                    FROM commerce_tracking_logs
                    WHERE order_id = :oid
                    ORDER BY id ASC
                """),
                {"oid": ord_dict["id"]},
            ).mappings().all()

        ord_dict["subtotal_inr"] = float(ord_dict.get("subtotal_inr") or 0)
        ord_dict["discount_inr"] = float(ord_dict.get("discount_inr") or 0)
        ord_dict["total_inr"] = float(ord_dict.get("total_inr") or 0)
        ord_dict["created_at_fmt"] = ord_dict["created_at"].strftime("%B %d, %Y at %I:%M %p") if ord_dict.get("created_at") else ""
        ord_dict["items"] = ord_dict.get("items_json") if isinstance(ord_dict.get("items_json"), list) else json.loads(ord_dict.get("items_json") or "[]")
        ord_dict["shipping_address"] = ord_dict.get("shipping_address_json") if isinstance(ord_dict.get("shipping_address_json"), dict) else json.loads(ord_dict.get("shipping_address_json") or "{}")
        ord_dict["tracking_logs"] = [
            {
                "status": l["status"],
                "description": l["description"],
                "location": l["location"],
                "time": l["timestamp"].strftime("%b %d, %I:%M %p") if l.get("timestamp") else "",
            }
            for l in logs
        ]

        if ord_dict.get("created_at"):
            age_days = (datetime.now() - ord_dict["created_at"]).total_seconds() / (24 * 3600)
            ord_dict["age_days"] = round(age_days, 1)
            ord_dict["is_return_eligible"] = (age_days <= 10.0) and (ord_dict.get("status") not in ["cancelled", "returned"]) and (ord_dict.get("return_status") in ["none", None, ""])
            ord_dict["return_window_days_left"] = max(0, round(10.0 - age_days, 1))
        else:
            ord_dict["age_days"] = 0
            ord_dict["is_return_eligible"] = True
            ord_dict["return_window_days_left"] = 10.0

        return ord_dict

    def request_return(self, user_id: int, order_number: str, reason: str = "") -> Dict[str, Any]:
        """Request doorstep pickup return adhering to strict 10-day constraint."""
        from app.commerce.delivery_logistics_service import get_delivery_logistics_service
        svc = get_delivery_logistics_service()
        return svc.request_return(user_id=user_id, order_number=order_number, reason=reason)

    def cancel_order(self, user_id: int, order_number: str) -> Dict[str, Any]:
        with engine.connect() as conn:
            ord_row = conn.execute(
                text("SELECT id, total_inr, status FROM commerce_orders WHERE order_number = :onum AND user_id = :uid"),
                {"onum": order_number, "uid": user_id},
            ).mappings().first()

            if not ord_row:
                raise ValueError("Order not found or unauthorized.")

            if ord_row["status"] == "cancelled":
                raise ValueError("Order is already cancelled.")

            refund_amt = Decimal(str(ord_row["total_inr"] or 0))

            # Update status to cancelled
            conn.execute(
                text("UPDATE commerce_orders SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = :oid"),
                {"oid": ord_row["id"]},
            )

            # Refund to user wallet
            conn.execute(
                text("UPDATE commerce_users SET wallet_balance = wallet_balance + :amt WHERE id = :uid"),
                {"amt": refund_amt, "uid": user_id},
            )
            conn.execute(
                text("""
                    INSERT INTO commerce_wallet_transactions (user_id, amount, transaction_type, description, order_id)
                    VALUES (:uid, :amt, 'credit', :desc, :oid)
                """),
                {
                    "uid": user_id, "amt": refund_amt,
                    "desc": f"Refund for Cancelled Order #{order_number}",
                    "oid": ord_row["id"],
                },
            )

            # Log tracking cancellation
            conn.execute(
                text("""
                    INSERT INTO commerce_tracking_logs (order_id, status, description, location)
                    VALUES (:oid, 'cancelled', :desc, 'Amazon Customer Support Hub')
                """),
                {
                    "oid": ord_row["id"],
                    "desc": f"Order #{order_number} cancelled by customer. Refund of ₹{refund_amt:,.2f} credited to your Amazon Wallet.",
                },
            )
            conn.commit()

        return self.get_order(order_number) or {}

    # ---------------------------------------------------------
    # BUY AGAIN RECOMMENDATIONS
    # ---------------------------------------------------------

    def get_buy_again_products(self, user_id: int) -> List[Dict[str, Any]]:
        orders = self.get_orders(user_id)
        seen_asins = set()
        buy_again = []

        for o in orders:
            for item in o.get("items", []):
                asin = item.get("asin")
                if asin and asin not in seen_asins:
                    seen_asins.add(asin)
                    buy_again.append({
                        "asin": asin,
                        "title": item.get("title"),
                        "price_inr": item.get("price_inr"),
                        "image_url": item.get("image_url"),
                        "last_ordered_at": o.get("created_at_fmt"),
                    })

        return buy_again


# Singleton instance
_user_commerce_service = None

def get_user_commerce_service() -> UserCommerceService:
    global _user_commerce_service
    if _user_commerce_service is None:
        _user_commerce_service = UserCommerceService()
    return _user_commerce_service
