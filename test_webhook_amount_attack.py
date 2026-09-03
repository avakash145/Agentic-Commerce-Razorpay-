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


payload = {
    "event": "payment.captured",

    "payload": {
        "payment": {
            "entity": {
                "id": "pay_attack_test",

                "order_id":
                    "order_TVuSFJSaPpUjBD",

                # ATTACK:
                # Actual transaction is 7000000 paise
                # We pretend it is 8000000.
                "amount": 8000000,

                "currency": "INR",

                "status": "captured"
            }
        }
    }
}


body = json.dumps(
    payload,
    separators=(",", ":")
).encode()


signature = hmac.new(
    secret.encode(),
    body,
    hashlib.sha256
).hexdigest()


headers = {
    "Content-Type": "application/json",

    "X-Razorpay-Signature":
        signature,

    "x-razorpay-event-id":
        "evt_amount_attack_001"
}


response = requests.post(
    "http://127.0.0.1:8000/webhooks/razorpay",
    data=body,
    headers=headers
)


print(
    "Status:",
    response.status_code
)

print(
    "Response:",
    response.text
)