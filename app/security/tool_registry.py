from enum import Enum


class AllowedTool(str, Enum):
    CREATE_ORDER = "create_order"
    VERIFY_PAYMENT = "verify_payment"
    REFUND_PAYMENT = "refund_payment"


ALLOWED_TOOLS = {
    AllowedTool.CREATE_ORDER,
}