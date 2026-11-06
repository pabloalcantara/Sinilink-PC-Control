# Brand assets

Source files for the integration icons, kept for re-rendering if the design
changes.

| File | Purpose |
|---|---|
| `icon-source-512.png` | 512×512 source image |

The images shipped with the integration live in
`custom_components/sinilink_pc/brand/`:

| File | Purpose |
|---|---|
| `icon.png` | 256×256 — required for HA brands |
| `icon@2x.png` | 512×512 — HiDPI variant |

Since Home Assistant 2026.3 a custom integration ships its own brand images in a
`brand/` folder inside the integration, served through
`/api/brands/integration/<domain>/` and taking priority over the brands CDN. No
pull request to `home-assistant/brands` is needed.
