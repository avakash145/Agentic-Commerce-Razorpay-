from threading import Lock


class WebhookEventStore:

    def __init__(self):
        self._processed_events = set()
        self._lock = Lock()

    def is_processed(self, event_id: str) -> bool:
        with self._lock:
            return event_id in self._processed_events

    def mark_processed(self, event_id: str) -> None:
        with self._lock:
            self._processed_events.add(event_id)