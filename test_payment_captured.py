import os
import json
import hmac
import hashlib
import requests

from dotenv import load_dotenv


load_dotenv()


secret = os.getenv(
    "RAZORPAY_WEBHOOK_SECRET"
)


# Replace this with the order ID
# from your transactions table.
order_id = "order_TVtZsvLLELan8p"


payment_id = "pay_test_001"

amount = 7000000

currency = "INR"


payload = {
    "event": "payment.captured",

    "payload": {
        "payment": {
            "entity": {
                "id": payment_id,
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "status": "captured"
            }
        }
    }
}


body = json.dumps(
    payload,
    separators=(",", ":")
).encode("utf-8")


signature = hmac.new(
    secret.encode("utf-8"),
    body,
    hashlib.sha256
).hexdigest()


headers = {
    "Content-Type": "application/json",

    "X-Razorpay-Signature": signature,

    "x-razorpay-event-id":
        "evt_payment_test_001"
}


response = requests.post(
    "http://127.0.0.1:8000/webhooks/razorpay",
    data=body,
    headers=headers
)


print(
    response.status_code
)

print(
    response.json()
)