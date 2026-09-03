import os
import hmac
import hashlib
import requests

from dotenv import load_dotenv


load_dotenv()


secret = os.getenv(
    "RAZORPAY_WEBHOOK_SECRET"
)


payload = b'{"event":"payment.captured"}'


signature = hmac.new(
    secret.encode("utf-8"),
    payload,
    hashlib.sha256
).hexdigest()


headers = {
    "Content-Type": "application/json",
    "X-Razorpay-Signature": signature,
    "x-razorpay-event-id": "test-event-001"
}


response = requests.post(
    "http://127.0.0.1:8000/webhooks/razorpay",
    data=payload,
    headers=headers
)


print(response.status_code)
print(response.json())