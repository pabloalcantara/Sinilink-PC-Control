# Sinilink - PC Control

Control a PC's power state (**on / off / force off**) from Home Assistant through
a **Sinilink XY-WPCE** class power controller.

> **Scope: PC power control only.** This integration only supports the Sinilink
> PC power on/off controllers. It does not handle other Sinilink devices
> (temperature/humidity sensors, relay boards, power supplies, dimmers).

## Entities

- `button.*_power_on` — refresh the state, then power the PC on (only when off)
- `button.*_power_off` — refresh the state, then shut the PC down cleanly (only when on)
- `button.*_force_power_off` — hard ATX cut
- `button.*_refresh_state` — ask the controller for its current state
- `switch.*_power_on_after_power_loss` — auto power-on after power loss
- `number.*_refresh_interval` — how often the PC state is refreshed (60–1800 s)
- `sensor.*_pc_status` — diagnostic raw state

## Setup

1. Add this repository to HACS as a **Custom repository** (Type: *Integration*)
   and download it.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → "Sinilink - PC Control"**.
4. Sign in with the account used by the Sinilink mobile app (`com.xydc`).

The integration stores a login token, never your password.
