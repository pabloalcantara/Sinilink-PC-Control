# Sinilink - PC Control

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration to control a PC's power state
(**on / off / force off**) through a **Sinilink XY-WPCE** class PC power
controller.

Maintained by [@pabloalcantara](https://github.com/pabloalcantara).

> **Note:** HACS supports only **one integration per repository**, so each of my
> integrations lives in its own repository. This one ships the `sinilink_pc`
> integration only.

---

## Installation via HACS

1. Make sure [HACS](https://hacs.xyz) is installed.
2. In Home Assistant go to **HACS → Integrations**.
3. Open the three-dot menu (top right) → **Custom repositories**.
4. Add this repository URL:

   ```
   https://github.com/pabloalcantara/Sinilink-PC-Control
   ```

5. Set **Type** to `Integration` and click **Add**.
6. Search for **Sinilink - PC Control** in HACS and click **Download**.
7. Restart Home Assistant.
8. Go to **Settings → Devices & Services → Add Integration** and search for
   **Sinilink PC Power**.

## Manual installation

Copy the `custom_components/sinilink_pc` folder into your Home Assistant
`config/custom_components/` directory, restart Home Assistant, and add the
integration from **Settings → Devices & Services**.

---

## ⚠️ Scope: PC power control only

**At this moment this integration only works with the Sinilink PC power on/off
controllers** — the module wired to the motherboard's power button, e.g. the
XY-WPCE.

It does **not** support other Sinilink devices. In particular it does **not**
handle temperature/humidity sensors (`wenshidu`), plain relay boards, power
supplies (`dianyuan`), dimmers or PWM devices, even though they share the same
cloud account and MQTT broker.

Support for other device types may be added later; they are simply not
implemented today.

## How it works

The controller sits on the PC's power-button pin. It is powered from the ATX
5 V standby rail, so the module stays online even while the PC is off — which is
what allows it to switch the PC back on.

The integration talks directly to the **Sinilink MQTT broker** (anonymous, plain
TCP on port 1884), the same one the devices use. Account login is only needed
once, to discover the devices (and it stores the resulting token, never the
password).

## Entities

For every controller found on the account:

| Entity | Type | Description |
|---|---|---|
| `button.<device>_power_on` | Button | Refreshes the state and powers the PC **on**, but only when it is currently off. |
| `button.<device>_power_off` | Button | Refreshes the state and shuts the PC **down** cleanly (OS-driven), but only when it is currently on. |
| `button.<device>_force_power_off` | Button | Hold the power button (~10 s) for an immediate ATX cut. No OS cooperation. |
| `button.<device>_refresh_state` | Button | Ask the controller for its current state. |
| `switch.<device>_power_on_after_power_loss` | Switch | Auto power-on when the module is re-energised while the PC is off. |
| `number.<device>_refresh_interval` | Number | How often the PC state is refreshed, from **60 s to 1800 s** (1 to 30 minutes). |
| `sensor.<device>_pc_status` | Sensor (diagnostic) | Raw state reported by the controller (`on`, `off`, `shutting_down`, `forcing_off`). |

**Power on and power off are separate commands**, and each button checks the
current state first, so a button never does the opposite of its label:

* `power_on` sends the short-press command, which powers a PC **on**. On an
  already-running PC it does nothing at the OS level, so the integration first
  confirms the PC is off.
* `power_off` sends the dedicated clean-shutdown command, which the OS honours.
  It is only sent when the PC is confirmed to be on.

After either command the integration keeps refreshing the state until the change
is confirmed (every 5 s, up to 3 minutes), so the dashboard updates on its own.

## Requirements

* Home Assistant 2024.6 or newer.
* A Sinilink account with at least one PC power controller registered in the
  official Sinilink app (`com.xydc`).
* The `pycryptodome` Python package (installed automatically by Home Assistant
  from the integration manifest).

## Configuration

The integration is configured entirely through the UI:

1. **Settings → Devices & Services → Add Integration → Sinilink - PC Control**.
2. Enter the account **e-mail or phone number** used by the Sinilink mobile app.
3. Enter the **password**.
4. Set the **dial code** to match the country of the account (default `+55`).
5. Leave **Backend locale** as `en_US`.

The credentials are used once to obtain a login token. The token is what gets
stored — the integration never keeps your password.

## Languages

The UI is translated and follows your Home Assistant language automatically:

| Language | File |
|---|---|
| English (default/fallback) | `translations/en.json` |
| Português (Brasil) | `translations/pt-BR.json` |

If your Home Assistant is set to a language that has no translation yet, it
falls back to English.

**Note:** the *Backend locale* option is not the UI language — it is a value the
Sinilink servers require and must stay `en_US`.

> **Note:** the Sinilink broker is an open, anonymous MQTT broker. Anyone who
> knows a device's MAC address can see and control that device. Reflashing the
> controller with ESPHome is the recommended option if you want fully local,
> private control.

## Troubleshooting

* **Entities show `unavailable`** — the controller is offline (not connected to
  the broker). Check the device's power and its connection in the Sinilink app.
* **PC state does not update on its own** — lower the refresh interval using the
  *Refresh interval* number entity.
* **Power off seems to do nothing** — the shutdown is OS-driven and can take a
  couple of minutes before the module reports the PC as off.

---

## Disclaimer

This is an unofficial, community-maintained integration. It is not affiliated
with, endorsed by, or supported by Sinilink or Home Assistant.
