"""Constants for the Sinilink PC Power integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sinilink_pc"
NAME: Final = "Sinilink PC Power"
VERSION: Final = "0.3.0"

# --- Cloud API (account login / device list) ---------------------------------
API_BASE: Final = "https://app.sinilink.com"
API_LOGIN_PATH: Final = "/api/user/login"
API_CLASSIFY_PATH: Final = "/api/userDevice/getAllUserDeviceClassify"
API_DEVICES_PATH: Final = "/api/userDevice/getDevicesByClassifyId"

# The Android app (com.xydc) builds the login body as a plain-text pseudo-JSON
# with UNQUOTED keys, then TripleDES-ECB/Pkcs7 encrypts it and base64-encodes it
# into a multipart field named "params".
#
#   {dianHuaQuHao:"<dial_code>",phone:"<login>",password:"<pw>",locale:"en_US"}
#
# The 3DES key is hard-coded in the app bundle; it is NOT a secret of the user.
TRIBLE_DES_KEY: Final = b"0123456789abcd0123456789"

# The backend matches `locale` against an exact list; "en_US" is what the app
# sends. Close-but-different values ("en", "en-us") make it answer a misleading
# "System exception please contact customer service".
DEFAULT_LOCALE: Final = "en_US"

# The device MQTT broker. Discovered from the device firmware via
# GET /api/mqtt/getMqttInfo -> {mqttUrl, mqttPort: 1884, mqttUser: "", mqttPassword: ""}.
# MQTT over plain TCP, anonymous. NOTE: this is NOT the app's websocket endpoint
# (wss://mq.sinilink.com:443/mqtt) — the APP talks to :443, the DEVICES listen on :1884.
MQTT_HOST: Final = "mq.sinilink.com"
MQTT_PORT: Final = 1884
MQTT_KEEPALIVE: Final = 60

# --- MQTT topics (flat, MAC appended uppercased with colons) -----------------
# to command  : ServerProducerToClient<MAC>
# from device : ClientProducerToServer<MAC>, returnisonline<MAC>
TOPIC_TO_DEVICE: Final = "ServerProducerToClient"
TOPIC_FROM_DEVICE: Final = "ClientProducerToServer"
TOPIC_RETURN_ONLINE: Final = "returnisonline"

# --- Device commands (payloads verified against real hardware) ---------------

# Read: harmless, makes the device publish its current state on
# ClientProducerToServer<MAC>. This is the ONLY refresh command — `boot` also
# WRITES (it sets the power-boot flag), so never use it to read.
CMD_READ: Final = '{"method":"find"}'

# The module sits on the motherboard's power-button pin. The commands are NOT
# symmetric, and only one of them actually shuts the PC down:
#
#   CMD_POWER_PRESS (poweron) -> short press: at the OS level this is the same as
#                                tapping the case button. Verified live: when the
#                                PC is OFF it powers it on. When the PC is ON it
#                                does NOT shut it down - the module briefly
#                                reports state 2 and falls back to 1, the OS
#                                keeps running. So this is the "power on" command.
#
#   CMD_SOFT_OFF (softoff)    -> the actual clean shutdown. Verified live: the
#                                module goes to state 3 and then 0, and the host
#                                stops answering ping. This is the "power off"
#                                command.
#
#   CMD_FORCE_OFF (forceoff)  -> hold the power button (~10s): immediate ATX cut.
CMD_POWER_PRESS: Final = '{"method":"poweron","param":""}'
CMD_SOFT_OFF: Final = '{"method":"softoff","param":""}'

# Hold the power button (~10s) until the ATX supply cuts: immediate hard off,
# no OS cooperation. Kept as its own button.
CMD_FORCE_OFF: Final = '{"method":"forceoff","param":""}'

# power-boot flag (auto power-on when the module is re-energised with the PC off)
CMD_POWER_BOOT_ON: Final = '{"method":"boot","param":"1"}'
CMD_POWER_BOOT_OFF: Final = '{"method":"boot","param":"0"}'

# --- State array -------------------------------------------------------------
# The device publishes {"param":[A,B,C,D,E,F],"timestamp":...} on
# ClientProducerToServer<MAC>. Field meaning, verified by toggling one setting
# at a time in the app and diffing:
IDX_PC_STATE: Final = 0  # 0 = off, 1 = on, 2/3 = shutting down, 4 = forcing off
IDX_POWER_BOOT: Final = 1  # 1 = enabled, 0 = disabled
IDX_PROHIBIT_KEY: Final = 3  # 1 = physical button locked, 0 = free

PC_STATE_OFF: Final = 0
PC_STATE_ON: Final = 1
# Observed live while the PC powers down, after a `softoff`: the module reports
# 2 or 3 as intermediate values and then settles on 0. Both must count as
# "still on" when gating a button, otherwise a second press during the shutdown
# would turn the PC back on.
PC_STATE_SHUTTING_DOWN: Final = 2
PC_STATE_SHUTTING_DOWN_ALT: Final = 3
PC_STATE_FORCING_OFF: Final = 4

# States in which the PC is considered powered on.
PC_STATES_ON: Final = (
    PC_STATE_ON,
    PC_STATE_SHUTTING_DOWN,
    PC_STATE_SHUTTING_DOWN_ALT,
    PC_STATE_FORCING_OFF,
)

# --- Config entry keys -------------------------------------------------------
CONF_LOGIN: Final = "login"
CONF_PASSWORD: Final = "password"
CONF_DIAL_CODE: Final = "dial_code"
CONF_LOCALE: Final = "locale"
CONF_TOKEN: Final = "app_login_token"
CONF_REFRESH_INTERVAL: Final = "refresh_interval"

DEFAULT_DIAL_CODE: Final = "+55"

# --- Refresh interval (the "timer" number entity) ----------------------------
# How often the integration asks every device for its current state. The device
# only publishes on change, so without this polling the PC state can sit stale.
REFRESH_MIN: Final = 60  # 1 minute
REFRESH_MAX: Final = 1800  # 30 minutes
REFRESH_STEP: Final = 30
DEFAULT_REFRESH_INTERVAL: Final = 300  # 5 minutes

# How long a button waits for a fresh state after asking for a refresh before
# giving up and refusing to act (avoids pressing blind).
STATE_WAIT_TIMEOUT: Final = 6.0

# After a press, the PC takes a while to change state (measured: a clean
# shutdown took ~2 minutes from the press to the module reporting "off"), so the
# integration refreshes repeatedly until the state actually changes, giving up
# after this long.
CONFIRM_INTERVAL: Final = 5.0  # ask for a fresh state every 5s
CONFIRM_TIMEOUT: Final = 180.0  # for up to 3 minutes
