"""Network Rail Train Describer listener for the Chichester TD area.

The listener is deliberately lazy: it starts only when the crossing monitor or
its status endpoint is requested. This lets an Eco web dyno sleep normally.
"""

from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
import threading
import time


LOGGER = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class TrainDescriberFeed:
    def __init__(self, environ=None, sleep=time.sleep):
        self.environ = environ if environ is not None else os.environ
        self.sleep = sleep
        self.host = self.environ.get("NETWORK_RAIL_STOMP_HOST", "publicdatafeeds.networkrail.co.uk")
        self.port = int(self.environ.get("NETWORK_RAIL_STOMP_PORT", "61618"))
        self.topic = self.environ.get("NETWORK_RAIL_TD_TOPIC", "/topic/TD_ALL_SIG_AREA")
        self.area = self.environ.get("NETWORK_RAIL_TD_AREA", "CH").upper()
        self.username = self.environ.get("NETWORK_RAIL_USERNAME", "").strip()
        self.password = self.environ.get("NETWORK_RAIL_PASSWORD", "")
        self.subscription_name = self.environ.get(
            "NETWORK_RAIL_TD_SUBSCRIPTION", "cxms-level-crossing-td-ch"
        )

        self._lock = threading.Lock()
        self._thread = None
        self._started = False
        self._connected = False
        self._last_connected_at = None
        self._last_disconnected_at = None
        self._last_frame_at = None
        self._last_message_at = None
        self._last_error = None
        self._frame_count = 0
        self._national_message_count = 0
        self._message_count = 0
        self._recent_events = deque(maxlen=50)
        self._berths = {}

    @property
    def configured(self):
        return bool(self.username and self.password)

    def start(self):
        """Start one daemon listener thread when credentials are configured."""
        if not self.configured:
            return False
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._started = True
            self._thread = threading.Thread(
                target=self._run,
                name="network-rail-td-listener",
                daemon=True,
            )
            self._thread.start()
        return True

    def snapshot(self):
        with self._lock:
            if not self.configured:
                status = "not_configured"
            elif self._connected:
                status = "connected"
            elif self._started:
                status = "connecting"
            else:
                status = "ready"

            return {
                "configured": self.configured,
                "status": status,
                "area": self.area,
                "topic": self.topic,
                "lastConnectedAt": self._last_connected_at,
                "lastDisconnectedAt": self._last_disconnected_at,
                "lastFrameAt": self._last_frame_at,
                "lastMessageAt": self._last_message_at,
                "frameCount": self._frame_count,
                "nationalMessageCount": self._national_message_count,
                "messageCount": self._message_count,
                "lastError": self._last_error,
                "recentEvents": list(self._recent_events)[:12],
                "activeBerths": dict(sorted(self._berths.items())),
            }

    def ingest(self, payload):
        """Parse a TD frame body and retain messages for the configured area."""
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            payload = json.loads(payload)

        messages = payload if isinstance(payload, list) else [payload]
        with self._lock:
            self._frame_count += 1
            self._last_frame_at = _utc_now()
            self._national_message_count += sum(isinstance(message, dict) for message in messages)
        accepted = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            body = message.get("body", message)
            if not isinstance(body, dict) or str(body.get("area_id", "")).upper() != self.area:
                continue
            self._record_event(body)
            accepted += 1
        return accepted

    def _record_event(self, body):
        message_type = str(body.get("msg_type", "UNKNOWN")).upper()
        from_berth = str(body.get("from", "")).strip()
        to_berth = str(body.get("to", "")).strip()
        descriptor = str(body.get("descr", "")).strip()
        received_at = _utc_now()

        event = {
            "receivedAt": received_at,
            "messageTime": str(body.get("time", "")),
            "type": message_type,
            "from": from_berth,
            "to": to_berth,
            "descriptor": descriptor,
        }

        with self._lock:
            if message_type == "CA":
                moved_descriptor = descriptor or self._berths.get(from_berth, "")
                if from_berth:
                    self._berths.pop(from_berth, None)
                if to_berth and moved_descriptor:
                    self._berths[to_berth] = moved_descriptor
            elif message_type == "CB" and from_berth:
                self._berths.pop(from_berth, None)
            elif message_type == "CC" and to_berth and descriptor:
                self._berths[to_berth] = descriptor

            self._message_count += 1
            self._last_message_at = received_at
            self._recent_events.appendleft(event)

    def _set_connected(self, connected):
        with self._lock:
            self._connected = connected
            if connected:
                self._last_connected_at = _utc_now()
                self._last_error = None
            else:
                self._last_disconnected_at = _utc_now()

    def _set_error(self, error, preserve_existing=False):
        detail = str(error).strip() or "Connection rejected or timed out"
        message = f"{type(error).__name__}: {detail}"
        for secret in (self.password, self.username):
            if secret:
                message = message.replace(secret, "[redacted]")
        with self._lock:
            if preserve_existing and self._last_error:
                return
            self._last_error = message[:300]

    def _run(self):
        import stomp

        retry_seconds = 2
        while True:
            connection = None
            try:
                # Network Rail's current examples negotiate STOMP 1.1.
                connection = stomp.Connection11(
                    [(self.host, self.port)],
                    heartbeats=(5000, 10000),
                    reconnect_attempts_max=1,
                    timeout=20,
                )
                listener = _TDListener(self, connection)
                connection.set_listener("cxms-td", listener)
                connection.connect(
                    self.username,
                    self.password,
                    wait=True,
                    headers={"client-id": self.username},
                )
                connection.subscribe(
                    destination=self.topic,
                    id="cxms-level-crossing",
                    ack="client-individual",
                    headers={"activemq.subscriptionName": self.subscription_name},
                )
                self._set_connected(True)
                retry_seconds = 2

                while connection.is_connected():
                    self.sleep(1)
            except Exception as error:  # pragma: no cover - exercised against the live broker
                LOGGER.warning("Network Rail TD connection unavailable: %s", type(error).__name__)
                self._set_error(error, preserve_existing=True)
            finally:
                self._set_connected(False)
                if connection and connection.is_connected():
                    try:
                        connection.disconnect()
                    except Exception:
                        pass

            self.sleep(retry_seconds)
            retry_seconds = min(retry_seconds * 2, 60)


class _TDListener:
    def __init__(self, feed, connection):
        self.feed = feed
        self.connection = connection

    def on_message(self, frame):
        try:
            self.feed.ingest(frame.body)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            self.feed._set_error(error)
        finally:
            message_id = frame.headers.get("message-id")
            subscription = frame.headers.get("subscription")
            if message_id and subscription:
                self.connection.ack(message_id, subscription)

    def on_error(self, frame):
        self.feed._set_error(RuntimeError(frame.body))

    def on_disconnected(self):
        self.feed._set_connected(False)


td_feed = TrainDescriberFeed()
