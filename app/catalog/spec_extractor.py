import re

from sqlalchemy import text

from app.db.database import engine


class ProductSpecExtractor:
    # RAM

    @staticmethod
    def extract_ram(text_value):

        patterns = [

            # 16GB RAM
            r"\b(\d+(?:\.\d+)?)\s*GB\s*(?:RAM|MEMORY)\b",

            # 16GB DDR4 / DDR5 / LPDDR5
            r"\b(\d+(?:\.\d+)?)\s*GB\s*(?:DDR\d|LPDDR\d)\b",

            # RAM: 16GB
            r"\b(?:RAM|MEMORY)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*GB\b",

            # 16 GB
            r"\b(\d+(?:\.\d+)?)\s*GB\b"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text_value,
                re.IGNORECASE
            )

            if match:

                return float(
                    match.group(1)
                )

        return None

    # STORAGE

    @staticmethod
    def extract_storage(text_value):

        # First look for TB because
        # 1TB should be preferred over
        # unrelated GB values.

        tb_patterns = [

            r"\b(\d+(?:\.\d+)?)\s*TB\s*(?:SSD|HDD|STORAGE)\b",

            r"\b(\d+(?:\.\d+)?)\s*TB\b"
        ]

        for pattern in tb_patterns:

            match = re.search(
                pattern,
                text_value,
                re.IGNORECASE
            )

            if match:

                return (
                    float(match.group(1))
                    * 1024
                )

        gb_patterns = [

            r"\b(\d+(?:\.\d+)?)\s*GB\s*(?:SSD|HDD|STORAGE)\b",

            r"\b(\d+(?:\.\d+)?)\s*GB\s*(?:PCIe|NVMe)\b",

            r"\b(?:SSD|HDD|STORAGE)\s*[:\-]?\s*"
            r"(\d+(?:\.\d+)?)\s*GB\b"
        ]

        for pattern in gb_patterns:

            match = re.search(
                pattern,
                text_value,
                re.IGNORECASE
            )

            if match:

                return float(
                    match.group(1)
                )

        return None

    # GPU

    @staticmethod
    def extract_gpu(text_value):

        patterns = [

            r"\b(NVIDIA\s+GeForce\s+RTX(?:[™®]|\s)+\d+\w*)",

            r"\b(GeForce\s+RTX(?:[™®]|\s)+\d+\w*)",

            r"\b(RTX(?:[™®]|\s)+\d+\w*)",

            r"\b(NVIDIA\s+GeForce\s+GTX\s+\d+\w*)",

            r"\b(GeForce\s+GTX\s+\d+\w*)",

            r"\b(Radeon\s+\d+\w*)",

            r"\b(AMD\s+Radeon\s+\d+\w*)"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text_value,
                re.IGNORECASE
            )

            if match:

                return match.group(1)

        return None
    # CPU

    @staticmethod
    def extract_cpu(text_value):

        patterns = [

            r"\b(Intel\s+Core\s+Ultra\s+\d+"
            r"(?:\s+\d+\w*)?)",

            r"\b(Intel\s+Core\s+i[3579]"
            r"(?:[-\s]\d+\w*)?)",

            r"\b(AMD\s+Ryzen\s+[3579]"
            r"(?:\s+\d+\w*)?)",

            r"\b(Apple\s+M[1-5]"
            r"(?:\s+\w+)?)"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text_value,
                re.IGNORECASE
            )

            if match:

                return match.group(1).strip()

        return None

    # SCREEN

    @staticmethod
    def extract_screen_size(text_value):

        patterns = [

            r"\b(\d+(?:\.\d+)?)\s*(?:inch|inches)\b",

            r"\b(\d+(?:\.\d+)?)\s*[\"″]"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text_value,
                re.IGNORECASE
            )

            if match:

                return float(
                    match.group(1)
                )

        return None

    # BUILD PRODUCT TEXT

    def build_product_text(
        self,
        product_id
    ):

        query = text(
            """
            SELECT
                p.title,
                p.description,
                p.breadcrumbs,

                COALESCE(
                    json_agg(
                        json_build_object(
                            'name',
                            pa.attribute_name,
                            'value',
                            pa.attribute_value
                        )
                    )
                    FILTER (
                        WHERE pa.attribute_id IS NOT NULL
                    ),
                    '[]'::json
                ) AS attributes

            FROM products p

            LEFT JOIN product_attributes pa
                ON p.product_id =
                   pa.product_id

            WHERE p.product_id =
                  :product_id

            GROUP BY p.product_id
            """
        )

        with engine.connect() as conn:

            row = conn.execute(
                query,
                {
                    "product_id":
                        product_id
                }
            ).fetchone()

        if not row:

            return ""

        parts = [

            str(
                row.title or ""
            ),

            str(
                row.description or ""
            ),

            str(
                row.breadcrumbs or ""
            )
        ]

        for attribute in row.attributes:

            name = attribute.get(
                "name"
            )

            value = attribute.get(
                "value"
            )

            if name:

                parts.append(
                    f"{name}: {value}"
                )

        return " ".join(parts)

    # EXTRACT PRODUCT

    def extract_product(
        self,
        product_id
    ):

        text_value = (
            self.build_product_text(
                product_id
            )
        )

        return {

            "product_id":
                product_id,

            "ram_gb":
                self.extract_ram(
                    text_value
                ),

            "storage_gb":
                self.extract_storage(
                    text_value
                ),

            "gpu":
                self.extract_gpu(
                    text_value
                ),

            "cpu":
                self.extract_cpu(
                    text_value
                ),

            "screen_size_inches":
                self.extract_screen_size(
                    text_value
                )
        }

    # SAVE

    def save_product_specs(
        self,
        specs
    ):

        query = text(
            """
            INSERT INTO product_specs (
                product_id,
                ram_gb,
                storage_gb,
                gpu,
                cpu,
                screen_size_inches,
                updated_at
            )

            VALUES (
                :product_id,
                :ram_gb,
                :storage_gb,
                :gpu,
                :cpu,
                :screen_size_inches,
                CURRENT_TIMESTAMP
            )

            ON CONFLICT (
                product_id
            )

            DO UPDATE SET

                ram_gb =
                    EXCLUDED.ram_gb,

                storage_gb =
                    EXCLUDED.storage_gb,

                gpu =
                    EXCLUDED.gpu,

                cpu =
                    EXCLUDED.cpu,

                screen_size_inches =
                    EXCLUDED.screen_size_inches,

                updated_at =
                    CURRENT_TIMESTAMP
            """
        )

        with engine.begin() as conn:

            conn.execute(
                query,
                specs
            )

    # BUILD ALL

    def build_all(self):

        query = text(
            """
            SELECT product_id
            FROM products
            ORDER BY product_id
            """
        )

        with engine.connect() as conn:

            product_ids = [
                row.product_id
                for row in conn.execute(
                    query
                )
            ]

        print(
            f"Products found: "
            f"{len(product_ids)}"
        )

        for index, product_id in enumerate(
            product_ids,
            start=1
        ):

            specs = self.extract_product(
                product_id
            )

            self.save_product_specs(
                specs
            )

            if index % 100 == 0:

                print(
                    f"Processed "
                    f"{index}/"
                    f"{len(product_ids)}"
                )
