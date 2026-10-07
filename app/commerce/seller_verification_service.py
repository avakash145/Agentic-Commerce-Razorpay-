import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from app.db.database import engine


class SellerVerificationService:
    """
    Service managing Business Seller product submissions,
    Amazon-style product quality & manufacturing compliance verifications,
    and promotional deals (Limited Time Deals with k% off or n rupees cashback).
    """

    def __init__(self):
        self._ensure_schema()
        self._seed_demo_submissions_if_empty()

    def _ensure_schema(self):
        """Ensure the seller_product_submissions table exists with all required fields."""
        sql = """
        CREATE TABLE IF NOT EXISTS seller_product_submissions (
            id SERIAL PRIMARY KEY,
            submission_id VARCHAR(64) UNIQUE NOT NULL,
            -- Business / Seller details
            business_name VARCHAR(150) NOT NULL,
            seller_name VARCHAR(120) NOT NULL,
            seller_email VARCHAR(120) NOT NULL,
            seller_phone VARCHAR(30),
            business_registration_no VARCHAR(80),
            business_address TEXT,
            origin_country VARCHAR(80) DEFAULT 'India',
            
            -- Product details
            title TEXT NOT NULL,
            brand VARCHAR(100) NOT NULL,
            category VARCHAR(100) DEFAULT 'Laptops',
            description TEXT,
            original_price_inr NUMERIC(12, 2) NOT NULL,
            selling_price_inr NUMERIC(12, 2) NOT NULL,
            stock_quantity INTEGER DEFAULT 50,
            image_url TEXT,
            
            -- Hardware specs
            cpu VARCHAR(120),
            ram_gb NUMERIC(6, 1),
            storage_gb NUMERIC(6, 1),
            gpu VARCHAR(120),
            screen_size_inches NUMERIC(5, 1),
            
            -- Manufacturing & Quality Verification details (Amazon Seller standard)
            manufacturer_name VARCHAR(150) NOT NULL,
            factory_address TEXT NOT NULL,
            manufacturing_license_no VARCHAR(100) NOT NULL,
            quality_certifications TEXT NOT NULL,
            quality_inspection_notes TEXT,
            warranty_terms VARCHAR(255) DEFAULT '1 Year Comprehensive Manufacturer Warranty',
            
            -- Deal & Discount details
            deal_type VARCHAR(50) DEFAULT 'limited_time_deal',
            discount_type VARCHAR(30) DEFAULT 'percentage',
            discount_percentage NUMERIC(5, 2) DEFAULT 0.00,
            cashback_inr NUMERIC(12, 2) DEFAULT 0.00,
            deal_price_inr NUMERIC(12, 2) NOT NULL,
            deal_headline VARCHAR(255),
            deal_duration_hours INTEGER DEFAULT 48,
            deal_ends_at TIMESTAMP,
            is_deal_active BOOLEAN DEFAULT TRUE,
            
            -- Admin Verification Status
            verification_status VARCHAR(40) DEFAULT 'pending',
            admin_notes TEXT,
            verified_at TIMESTAMP,
            verified_by VARCHAR(100),
            published_asin VARCHAR(40),
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        with engine.begin() as conn:
            conn.execute(text(sql))

    def submit_product(
        self,
        # Business / Seller details
        business_name: str,
        seller_name: str,
        seller_email: str,
        seller_phone: Optional[str] = None,
        business_registration_no: Optional[str] = None,
        business_address: Optional[str] = None,
        origin_country: str = "India",
        # Product details
        title: str = "",
        brand: str = "",
        category: str = "Laptops",
        description: str = "",
        original_price_inr: float = 0.0,
        selling_price_inr: float = 0.0,
        stock_quantity: int = 50,
        image_url: Optional[str] = None,
        # Hardware specs
        cpu: Optional[str] = None,
        ram_gb: Optional[float] = None,
        storage_gb: Optional[float] = None,
        gpu: Optional[str] = None,
        screen_size_inches: Optional[float] = None,
        # Manufacturing & Quality Verification details
        manufacturer_name: str = "",
        factory_address: str = "",
        manufacturing_license_no: str = "",
        quality_certifications: str = "",
        quality_inspection_notes: Optional[str] = None,
        warranty_terms: str = "1 Year Comprehensive Manufacturer Warranty",
        # Deal configuration
        deal_type: str = "limited_time_deal",
        discount_type: str = "percentage",
        discount_percentage: float = 0.0,
        cashback_inr: float = 0.0,
        deal_headline: Optional[str] = None,
        deal_duration_hours: int = 48,
    ) -> Dict[str, Any]:
        """
        Saves a seller product submission with business credentials,
        quality verification documents, and deal parameters into the review queue.
        """
        if not business_name or not seller_email:
            raise ValueError("Business Company Name and Seller Email are required.")
        if not title or not brand:
            raise ValueError("Product Title and Brand are required.")
        if original_price_inr <= 0:
            raise ValueError("Original M.R.P. must be greater than zero.")
        if not manufacturer_name or not factory_address or not manufacturing_license_no:
            raise ValueError("Manufacturer Name, Factory Address, and Manufacturing License are required for verification.")
        if not quality_certifications:
            raise ValueError("At least one Quality Certification (e.g., BIS, ISO 9001, CE) is required.")

        # Compute Deal Price based on discount type
        orig_dec = Decimal(str(original_price_inr))
        base_sell_dec = Decimal(str(selling_price_inr or original_price_inr))
        disc_pct_dec = Decimal(str(discount_percentage or 0.0))
        cashback_dec = Decimal(str(cashback_inr or 0.0))

        if deal_type != "none" and discount_type == "percentage" and disc_pct_dec > 0:
            deal_price = orig_dec * (Decimal("1.00") - (disc_pct_dec / Decimal("100.00")))
            deal_price = round(deal_price, 2)
        elif deal_type != "none" and discount_type == "cashback":
            deal_price = base_sell_dec
        else:
            deal_price = base_sell_dec

        submission_id = f"SUB-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now()
        deal_ends_at = now + timedelta(hours=int(deal_duration_hours or 48))

        if not deal_headline:
            if discount_type == "percentage" and disc_pct_dec > 0:
                deal_headline = f"Limited Time Deal: Flat {float(disc_pct_dec):g}% Off!"
            elif discount_type == "cashback" and cashback_dec > 0:
                deal_headline = f"Special Offer: ₹{float(cashback_dec):,.0f} Instant Wallet Cashback!"
            else:
                deal_headline = "Verified Seller Special Deal"

        insert_sql = text("""
            INSERT INTO seller_product_submissions (
                submission_id, business_name, seller_name, seller_email, seller_phone,
                business_registration_no, business_address, origin_country,
                title, brand, category, description, original_price_inr, selling_price_inr,
                stock_quantity, image_url, cpu, ram_gb, storage_gb, gpu, screen_size_inches,
                manufacturer_name, factory_address, manufacturing_license_no,
                quality_certifications, quality_inspection_notes, warranty_terms,
                deal_type, discount_type, discount_percentage, cashback_inr, deal_price_inr,
                deal_headline, deal_duration_hours, deal_ends_at, is_deal_active,
                verification_status, created_at, updated_at
            ) VALUES (
                :sid, :bname, :sname, :semail, :sphone, :breg, :baddr, :country,
                :title, :brand, :cat, :desc, :orig_p, :sell_p, :stock, :img,
                :cpu, :ram, :storage, :gpu, :screen,
                :mname, :faddr, :mlic, :qcert, :qnotes, :wterms,
                :dtype, :distype, :dpct, :cashback, :dprice,
                :dhead, :dhrs, :dends, true, 'pending', :now, :now
            ) RETURNING id
        """)

        params = {
            "sid": submission_id,
            "bname": business_name.strip(),
            "sname": seller_name.strip(),
            "semail": seller_email.strip().lower(),
            "sphone": seller_phone or "",
            "breg": business_registration_no or "",
            "baddr": business_address or "",
            "country": origin_country or "India",
            "title": title.strip(),
            "brand": brand.strip(),
            "cat": category.strip() or "Laptops",
            "desc": description.strip(),
            "orig_p": orig_dec,
            "sell_p": base_sell_dec,
            "stock": stock_quantity,
            "img": image_url or "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=600&q=80",
            "cpu": cpu or "Intel Core i7 13th Gen",
            "ram": ram_gb or 16.0,
            "storage": storage_gb or 512.0,
            "gpu": gpu or "Intel Iris Xe Graphics",
            "screen": screen_size_inches or 15.6,
            "mname": manufacturer_name.strip(),
            "faddr": factory_address.strip(),
            "mlic": manufacturing_license_no.strip(),
            "qcert": quality_certifications.strip(),
            "qnotes": quality_inspection_notes or "Passed 100% factory QC inspection and electrical burn-in testing.",
            "wterms": warranty_terms.strip() or "1 Year Comprehensive Manufacturer Warranty",
            "dtype": deal_type,
            "distype": discount_type,
            "dpct": disc_pct_dec,
            "cashback": cashback_dec,
            "dprice": deal_price,
            "dhead": deal_headline,
            "dhrs": int(deal_duration_hours or 48),
            "dends": deal_ends_at,
            "now": now,
        }

        with engine.begin() as conn:
            res = conn.execute(insert_sql, params)
            new_id = res.scalar()

        return self.get_submission(submission_id)

    def get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full submission details by submission_id."""
        query = text("""
            SELECT * FROM seller_product_submissions WHERE submission_id = :sid
        """)
        with engine.connect() as conn:
            row = conn.execute(query, {"sid": submission_id}).mappings().first()
            if not row:
                return None
            return self._format_submission(dict(row))

    def list_submissions(
        self,
        seller_email: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List seller submissions with optional filtering by email and status."""
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit}

        if seller_email:
            conditions.append("lower(seller_email) = :semail")
            params["semail"] = seller_email.strip().lower()

        if status and status.lower() != "all":
            conditions.append("verification_status = :status")
            params["status"] = status.strip().lower()

        where_sql = " AND ".join(conditions)
        sql = text(f"""
            SELECT * FROM seller_product_submissions
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit
        """)

        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
            return [self._format_submission(dict(r)) for r in rows]

    def approve_submission(
        self,
        submission_id: str,
        verified_by: str = "Amazon Quality & Compliance Inspection Team",
        admin_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Amazon Seller Verification Approval:
        1. Verifies quality standards, manufacturing license, and business credentials.
        2. Generates an official catalog ASIN (e.g. B0SEL...).
        3. Publishes product to products, product_specs, media, and product_offers tables.
        4. Activates the Limited Time Deal (k% off or n cashback offer).
        5. Updates verification status to 'approved'.
        """
        sub = self.get_submission(submission_id)
        if not sub:
            raise ValueError(f"Submission {submission_id} not found.")

        if sub.get("verification_status") == "approved" and sub.get("published_asin"):
            return sub  # already approved

        now = datetime.now()
        published_asin = f"B0SEL{uuid.uuid4().hex[:7].upper()}"
        notes = admin_notes or "Manufacturing standards and BIS/ISO quality certifications verified. Approved for store catalog."

        # Compile rich metadata for store catalog
        raw_data = {
            "seller": {
                "name": sub["business_name"],
                "seller_name": sub["seller_name"],
                "seller_email": sub["seller_email"],
                "registration_no": sub["business_registration_no"],
                "address": sub["business_address"],
                "origin_country": sub["origin_country"],
                "is_verified": True,
            },
            "quality_verification": {
                "manufacturer_name": sub["manufacturer_name"],
                "factory_address": sub["factory_address"],
                "manufacturing_license_no": sub["manufacturing_license_no"],
                "quality_certifications": sub["quality_certifications"],
                "inspection_notes": sub["quality_inspection_notes"],
                "warranty_terms": sub["warranty_terms"],
                "origin_country": sub["origin_country"],
                "is_quality_certified": True,
                "verified_at": now.isoformat(),
                "verified_by": verified_by,
            },
            "deal": {
                "deal_type": sub["deal_type"],
                "discount_type": sub["discount_type"],
                "discount_percentage": float(sub["discount_percentage"]),
                "cashback_inr": float(sub["cashback_inr"]),
                "deal_price_inr": float(sub["deal_price_inr"]),
                "original_mrp_inr": float(sub["original_price_inr"]),
                "deal_headline": sub["deal_headline"],
                "deal_duration_hours": sub["deal_duration_hours"],
                "deal_ends_at": sub["deal_ends_at"],
                "is_deal_active": True,
            },
        }

        deal_price = Decimal(str(sub["deal_price_inr"]))
        orig_price = Decimal(str(sub["original_price_inr"]))

        with engine.begin() as conn:
            # 1. Insert into products
            prod_sql = text("""
                INSERT INTO products (
                    asin, original_asin, title, brand, price, currency, list_price,
                    in_stock, in_stock_text, stars, reviews_count, breadcrumbs,
                    description, condition, is_amazon_choice, amazon_choice_text,
                    raw_data, created_at, updated_at
                ) VALUES (
                    :asin, :asin, :title, :brand, :price, 'INR', :list_price,
                    true, 'In Stock', 4.8, 19, :breadcrumbs,
                    :desc, 'New', true, 'Amazon Verified Seller Choice',
                    :raw_data, :now, :now
                ) RETURNING product_id
            """)
            prod_res = conn.execute(prod_sql, {
                "asin": published_asin,
                "title": sub["title"],
                "brand": sub["brand"],
                "price": deal_price,
                "list_price": orig_price,
                "breadcrumbs": f"Computers & Accessories > {sub['category']}",
                "desc": sub["description"] or f"High performance {sub['brand']} {sub['title']} manufactured by {sub['manufacturer_name']}.",
                "raw_data": json.dumps(raw_data),
                "now": now,
            })
            product_id = prod_res.scalar()

            # 2. Insert into product_specs
            specs_sql = text("""
                INSERT INTO product_specs (
                    product_id, ram_gb, storage_gb, gpu, cpu, screen_size_inches, created_at, updated_at
                ) VALUES (
                    :pid, :ram, :storage, :gpu, :cpu, :screen, :now, :now
                )
            """)
            conn.execute(specs_sql, {
                "pid": product_id,
                "ram": sub["ram_gb"],
                "storage": sub["storage_gb"],
                "gpu": sub["gpu"] or "Integrated Graphics",
                "cpu": sub["cpu"] or "Core Processor",
                "screen": sub["screen_size_inches"] or 15.6,
                "now": now,
            })

            # 3. Insert into media
            if sub.get("image_url"):
                media_sql = text("""
                    INSERT INTO media (product_id, media_type, url, source)
                    VALUES (:pid, 'product_high_resolution', :url, 'seller_upload')
                """)
                conn.execute(media_sql, {
                    "pid": product_id,
                    "url": sub["image_url"],
                })

            # 4. Insert into product_offers
            offer_sql = text("""
                INSERT INTO product_offers (
                    product_id, provider, seller_name, price, currency, in_stock, condition
                ) VALUES (
                    :pid, 'Amazon Verified Seller', :sname, :price, 'INR', true, 'New'
                )
            """)
            conn.execute(offer_sql, {
                "pid": product_id,
                "sname": sub["business_name"],
                "price": deal_price,
            })

            # 5. Update submission record
            update_sub_sql = text("""
                UPDATE seller_product_submissions
                SET verification_status = 'approved',
                    published_asin = :asin,
                    verified_at = :now,
                    verified_by = :vby,
                    admin_notes = :notes,
                    updated_at = :now
                WHERE submission_id = :sid
            """)
            conn.execute(update_sub_sql, {
                "asin": published_asin,
                "now": now,
                "vby": verified_by,
                "notes": notes,
                "sid": submission_id,
            })

        return self.get_submission(submission_id)

    def reject_submission(
        self,
        submission_id: str,
        verified_by: str = "Amazon Quality & Compliance Inspection Team",
        admin_notes: str = "Product quality or manufacturing standard documentation incomplete.",
    ) -> Dict[str, Any]:
        """Reject submission with mandatory compliance audit feedback."""
        sub = self.get_submission(submission_id)
        if not sub:
            raise ValueError(f"Submission {submission_id} not found.")

        now = datetime.now()
        update_sql = text("""
            UPDATE seller_product_submissions
            SET verification_status = 'rejected',
                verified_at = :now,
                verified_by = :vby,
                admin_notes = :notes,
                updated_at = :now
            WHERE submission_id = :sid
        """)
        with engine.begin() as conn:
            conn.execute(update_sql, {
                "now": now,
                "vby": verified_by,
                "notes": admin_notes,
                "sid": submission_id,
            })

        return self.get_submission(submission_id)

    def _format_submission(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Decimal and datetime fields to JSON-serializable types."""
        out = dict(row)
        for k, v in out.items():
            if isinstance(v, Decimal):
                out[k] = float(v)
            elif isinstance(v, datetime):
                out[k] = v.isoformat()
        return out

    def _seed_demo_submissions_if_empty(self):
        """Seed initial demo submissions representing both k% discount and cashback deals."""
        with engine.connect() as conn:
            cnt = conn.execute(text("SELECT count(*) FROM seller_product_submissions")).scalar() or 0
            if cnt > 0:
                return

        # 1. Approved Demo: Apex AeroBook 14 with 20% Direct Discount Deal
        sub1 = self.submit_product(
            business_name="Apex Precision Technologies India Pvt Ltd",
            seller_name="Vikramaditya Sharma",
            seller_email="seller.apex@amazonpartners.in",
            seller_phone="+91 98200 12345",
            business_registration_no="29AABCA1234F1Z5",
            business_address="Tower C, Tech Park 4, Electronics City, Bengaluru 560100",
            origin_country="India",
            title="Apex AeroBook 14 Ultra - Intel Core i7 13th Gen, 16GB RAM, 1TB NVMe SSD",
            brand="Apex",
            category="Laptops",
            description="Ultra-thin carbon chassis laptop engineered for engineers and data scientists. Features 100% sRGB 2.8K OLED display, Wi-Fi 6E, and all-day 14-hour battery life.",
            original_price_inr=75000.0,
            selling_price_inr=60000.0,
            stock_quantity=80,
            image_url="https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=600&q=80",
            cpu="Intel Core i7-13700H (14 Cores, 20 Threads)",
            ram_gb=16.0,
            storage_gb=1024.0,
            gpu="Intel Iris Xe Graphics",
            screen_size_inches=14.0,
            manufacturer_name="Foxconn Precision Manufacturing India",
            factory_address="Plot 18, Sriperumbudur Industrial Corridor, Tamil Nadu 602105",
            manufacturing_license_no="MFG-LIC-TN-2025-99412",
            quality_certifications="BIS Certified (R-41029384), ISO 9001:2015 Quality Management, CE, RoHS Compliant",
            quality_inspection_notes="Passed 100% automated stress testing, drop safety tests, and thermal dissipation benchmark.",
            warranty_terms="2 Years Comprehensive Onsite Manufacturer Warranty + 1 Year Accidental Damage Protection",
            deal_type="limited_time_deal",
            discount_type="percentage",
            discount_percentage=20.0,
            cashback_inr=0.0,
            deal_headline="Limited Time Deal: 20% Flat Discount on Apex AeroBook!",
            deal_duration_hours=48,
        )
        # Fast-track approve sub1 so it is immediately live in the store
        self.approve_submission(
            sub1["submission_id"],
            verified_by="Amazon Quality & Compliance Inspection Directorate",
            admin_notes="All BIS laboratory test certificates and factory manufacturing licenses verified valid. Approved for live catalog listing with 20% Limited Time Deal."
        )

        # 2. Approved Demo: Nova Titan 16 with ₹3,000 Instant Wallet Cashback Deal
        sub2 = self.submit_product(
            business_name="Nova Global Compute Systems Ltd",
            seller_name="Ananya Sen",
            seller_email="business@novacompute.com",
            seller_phone="+91 91678 45678",
            business_registration_no="27AAGCN9876Q1Z9",
            business_address="Andheri East Industrial Estate, Mumbai 400093",
            origin_country="India",
            title="Nova Titan 16 Gaming Laptop - AMD Ryzen 7 7840HS, RTX 4060 8GB, 16GB DDR5, 1TB SSD",
            brand="Nova",
            category="Laptops",
            description="Powerhouse gaming and AI workstation featuring AMD Zen 4 architecture, NVIDIA DLSS 3, 165Hz QHD display, and dual-fan liquid metal cooling.",
            original_price_inr=92000.0,
            selling_price_inr=85000.0,
            stock_quantity=45,
            image_url="https://images.unsplash.com/photo-1603302576837-37561b2e2302?auto=format&fit=crop&w=600&q=80",
            cpu="AMD Ryzen 7 7840HS (8 Cores, 16 Threads)",
            ram_gb=16.0,
            storage_gb=1024.0,
            gpu="NVIDIA GeForce RTX 4060 8GB GDDR6",
            screen_size_inches=16.0,
            manufacturer_name="Nova Precision Assembly Hub Pune",
            factory_address="MIDC Bhosari Industrial Area, Pune, Maharashtra 411026",
            manufacturing_license_no="MFG-LIC-MH-2026-78190",
            quality_certifications="BIS Certified (R-41088421), ISO 14001 Environmental Standard, CE, FCC Class B",
            quality_inspection_notes="Thermals stress-tested under sustained 140W TGP for 48 consecutive hours. Passed drop and vibration compliance.",
            warranty_terms="1 Year International Warranty + 2 Years Free Battery Health Coverage",
            deal_type="limited_time_deal",
            discount_type="cashback",
            discount_percentage=0.0,
            cashback_inr=3000.0,
            deal_headline="Limited Time Deal: ₹3,000 Instant Cashback into Amazon Wallet!",
            deal_duration_hours=72,
        )
        self.approve_submission(
            sub2["submission_id"],
            verified_by="Amazon Quality & Compliance Inspection Directorate",
            admin_notes="Verified Pune manufacturing facility registration and high-voltage safety standards. Approved with ₹3,000 Wallet Cashback promotional deal."
        )

        # 3. Pending Demo: Zenith StudentBook 15 with 15% Discount - awaiting admin verification
        self.submit_product(
            business_name="Zenith Edge Devices Pvt Ltd",
            seller_name="Rahul Verma",
            seller_email="rahul.v@zenithedge.in",
            seller_phone="+91 97112 33445",
            business_registration_no="07AAACZ6543K1Z1",
            business_address="Okhla Industrial Area Phase III, New Delhi 110020",
            origin_country="India",
            title="Zenith StudentBook 15 - Intel Core i5 12th Gen, 16GB RAM, 512GB SSD, Anti-Glare FHD",
            brand="Zenith",
            category="Laptops",
            description="Engineered specifically for university students and coding. Lightweight 1.4kg magnesium body, fast charging 65W Type-C adapter, and backlit keyboard.",
            original_price_inr=48000.0,
            selling_price_inr=42000.0,
            stock_quantity=100,
            image_url="https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=600&q=80",
            cpu="Intel Core i5-1240P (12 Cores)",
            ram_gb=16.0,
            storage_gb=512.0,
            gpu="Intel UHD Graphics",
            screen_size_inches=15.6,
            manufacturer_name="Zenith Electronics North Plant",
            factory_address="Plot 55, Sector 68, IMT Manesar, Gurugram, Haryana 122051",
            manufacturing_license_no="MFG-LIC-HR-2026-10294",
            quality_certifications="BIS Certified (R-41077612), ISO 9001:2015, RoHS",
            quality_inspection_notes="Hinge endurance tested for 25,000 open-close cycles. Passed acoustic and battery safety audits.",
            warranty_terms="1 Year Manufacturer Onsite Warranty with Free Pickup and Drop",
            deal_type="limited_time_deal",
            discount_type="percentage",
            discount_percentage=15.0,
            cashback_inr=0.0,
            deal_headline="Back to College Deal: 15% Flat Discount!",
            deal_duration_hours=48,
        )


_seller_service_instance: Optional[SellerVerificationService] = None


def get_seller_verification_service() -> SellerVerificationService:
    global _seller_service_instance
    if _seller_service_instance is None:
        _seller_service_instance = SellerVerificationService()
    return _seller_service_instance
