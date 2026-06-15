# channel_service/app.py
"""
Stubbed Channel Service.

Receives message dispatch requests from Xeno CRM at POST /send.
Asynchronously simulates communication statuses and executes receipt callbacks sequentially:
pending -> sent -> (failed or delivered -> read -> clicked -> ordered)
with randomized delays and real-world outcomes.

To handle volume and protect the CRM database from locks, callbacks are queued
and processed by a rate-limited background worker with automatic retries.
"""

import logging
import random
import threading
import time
import queue
import requests
from flask import Flask, jsonify, request

# Set up logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("channel_service")

app = Flask(__name__)

# Thread-safe queue for processing CRM callbacks sequentially
callback_queue = queue.Queue()

def callback_worker():
    """
    Background worker that serializes and rate-limits callbacks back to the CRM.
    This prevents concurrent SQLite locks and handles retries under volume.
    """
    logger.info("Callback worker thread started.")
    while True:
        item = callback_queue.get()
        if item is None:
            break
        
        receipt_url = item.get("receipt_url")
        payload = item.get("payload")
        retries = item.get("retries", 0)
        
        success = False
        try:
            logger.info("Posting callback (attempt %d): URL=%s, JSON=%s", retries + 1, receipt_url, payload)
            resp = requests.post(
                receipt_url,
                json=payload,
                timeout=5
            )
            logger.info("Callback response: %s", resp.status_code)
            if resp.status_code in (200, 201):
                success = True
            else:
                logger.warning("CRM returned status %s for callback: %s", resp.status_code, payload)
        except Exception as exc:
            logger.error("Failed to send callback to CRM: %s", exc)

        if not success:
            if retries < 3:
                # Put back in the queue to retry after a short delay
                item["retries"] = retries + 1
                logger.info("Re-queueing callback for retry: %s", payload)
                # Sleep a bit before re-enqueuing to avoid busy loop
                time.sleep(0.5)
                callback_queue.put(item)
            else:
                logger.error("Max retries reached. Dropping callback: %s", payload)
        
        callback_queue.task_done()
        
        # Pacing rate-limit: 15ms sleep between callbacks to protect Django's SQLite database from locks
        time.sleep(0.015)

# Start callback worker thread
threading.Thread(target=callback_worker, daemon=True).start()

def queue_callback(receipt_url, message_id, status_value):
    """Enqueue a status callback request to be processed by the worker."""
    callback_queue.put({
        "receipt_url": receipt_url,
        "payload": {
            "message_id": message_id,
            "status": status_value
        },
        "retries": 0
    })

def simulate_delivery(payload):
    """
    Simulates outcomes for a single message in a separate thread.
    Transitions statuses sequentially to respect the monotonic rules in CRM.
    """
    message_id = payload.get("message_id")
    receipt_url = payload.get("receipt_url")
    to_recipient = payload.get("to")
    channel = payload.get("channel")

    if not message_id or not receipt_url:
        logger.error("Missing message_id or receipt_url in payload: %s", payload)
        return

    logger.info("Starting simulation for message %s to %s via %s", message_id, to_recipient, channel)

    # 1. Transitions to 'sent'
    time.sleep(random.uniform(0.1, 0.4))
    queue_callback(receipt_url, message_id, "sent")

    # 10% chance of delivery failure
    if random.random() < 0.10:
        time.sleep(random.uniform(0.2, 0.6))
        queue_callback(receipt_url, message_id, "failed")
        return

    # 2. Transitions to 'delivered'
    time.sleep(random.uniform(0.5, 1.5))
    queue_callback(receipt_url, message_id, "delivered")

    # 20% chance the user doesn't open/read it
    if random.random() < 0.20:
        return

    # 3. Transitions to 'read'
    time.sleep(random.uniform(0.5, 2.0))
    queue_callback(receipt_url, message_id, "read")

    # 40% chance of link click (only if read)
    if random.random() > 0.40:
        return

    # 4. Transitions to 'clicked'
    time.sleep(random.uniform(0.5, 2.0))
    queue_callback(receipt_url, message_id, "clicked")

    # 25% chance of placing an order (only if clicked)
    if random.random() > 0.25:
        return

    # 5. Transitions to 'ordered'
    time.sleep(random.uniform(0.5, 2.0))
    queue_callback(receipt_url, message_id, "ordered")


@app.route("/send", methods=["POST"])
def send():
    payload = request.get_json() or {}
    logger.info("Received send request: %s", payload)

    # Run the simulation asynchronously in a separate thread so Flask responds immediately
    threading.Thread(target=simulate_delivery, args=(payload,), daemon=True).start()

    return jsonify({"status": "accepted", "message_id": payload.get("message_id")}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    # Run server on port (fallback to 5001 for local dev, 5000 is used by macOS AirPlay)
    app.run(host="0.0.0.0", port=port)
