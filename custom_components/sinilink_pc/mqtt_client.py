"""MQTT client for Sinilink devices (cloud broker, anonymous, plain TCP).

The official app talks to the broker over WebSocket+TLS on :443, but the
*devices* connect to the plain-TCP listener on :1884 (discovered in the device
firmware via /api/mqtt/getMqttInfo). We use the same listener the devices use.

Topics are "flat": the MAC is appended uppercased, with colons, no separator.

    ServerProducerToClient<MAC>   -> commands  (app/HA -> device)
    ClientProducerToServer<MAC>   -> state     (device -> app/HA)
    returnisonline<MAC>           -> liveness  (device -> app/HA)

The broker drops a session as soon as another client connects with the same
client id ("Session taken over"), so the id must be unique per Home Assistant
instance. On every (re)connect the subscriptions are re-issued, because
subscriptions do not survive a session that the broker discarded.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .const import (
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    TOPIC_FROM_DEVICE,
    TOPIC_RETURN_ONLINE,
    TOPIC_TO_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

StateCallback = Callable[[str, list[int]], None]
OnlineCallback = Callable[[str, bool], None]
ConnectionCallback = Callable[[bool], None]


def _is_success(reason_code) -> bool:
    """True when an MQTTv5 reason code (or legacy int) means success."""
    if hasattr(reason_code, "is_failure"):
        return not reason_code.is_failure
    return reason_code == 0


class SinilinkMqtt:
    """Small wrapper around paho-mqtt for the Sinilink broker.

    One client serves every device of the account: state topics are subscribed
    per MAC and messages are dispatched back through the callbacks.
    """

    def __init__(
        self,
        on_state: StateCallback,
        on_online: OnlineCallback,
        client_id: str,
        on_connection: ConnectionCallback | None = None,
    ) -> None:
        self._on_state = on_state
        self._on_online = on_online
        self._on_connection = on_connection
        self._macs: set[str] = set()
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
        # Reconnect on our own with a short backoff; the default is 1-120s.
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._handle_connect
        self._client.on_message = self._handle_message
        self._client.on_disconnect = self._handle_disconnect

    # -- lifecycle ----------------------------------------------------------
    def connect(self) -> None:
        """Blocking TCP connect; call it from an executor thread."""
        self._client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
        self._client.loop_start()

    def disconnect(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # pragma: no cover - best effort
            _LOGGER.debug("Error while disconnecting MQTT", exc_info=True)

    def set_devices(self, macs: list[str]) -> None:
        """Track the MACs we care about (subscribe now if connected)."""
        self._macs = {mac.upper() for mac in macs}
        if self._client.is_connected():
            self._subscribe_all()

    def _subscribe_all(self) -> None:
        for mac in self._macs:
            self._client.subscribe(f"{TOPIC_FROM_DEVICE}{mac}", qos=1)
            self._client.subscribe(f"{TOPIC_RETURN_ONLINE}{mac}", qos=1)

    # -- paho callbacks -----------------------------------------------------
    def _handle_connect(self, client, userdata, flags, reason_code, properties=None):
        if not _is_success(reason_code):
            _LOGGER.error("MQTT connect failed: %s", reason_code)
            return
        _LOGGER.debug("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
        # A discarded session starts clean: subscriptions and any retained
        # liveness message have to be re-acquired.
        self._subscribe_all()
        if self._on_connection is not None:
            self._on_connection(True)

    def _handle_disconnect(self, client, userdata, flags, reason_code, properties=None):
        _LOGGER.warning("MQTT disconnected: %s", reason_code)
        if self._on_connection is not None:
            self._on_connection(False)

    def _handle_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload)
        except (ValueError, UnicodeDecodeError):
            return

        if topic.startswith(TOPIC_RETURN_ONLINE):
            mac = topic[len(TOPIC_RETURN_ONLINE):].upper()
            self._on_online(mac, bool(payload.get("isOnLine")))
        elif topic.startswith(TOPIC_FROM_DEVICE):
            mac = topic[len(TOPIC_FROM_DEVICE):].upper()
            state = payload.get("param")
            if isinstance(state, list):
                self._on_state(mac, state)

    # -- outbound -----------------------------------------------------------
    def send(self, mac: str, payload: str) -> None:
        """Publish a raw command payload to a device."""
        topic = f"{TOPIC_TO_DEVICE}{mac.upper()}"
        _LOGGER.debug("MQTT -> %s: %s", topic, payload)
        self._client.publish(topic, payload, qos=1)

    def request_state(self, mac: str) -> None:
        """Ask the device to publish its current state (harmless)."""
        self.send(mac, '{"method":"find"}')
