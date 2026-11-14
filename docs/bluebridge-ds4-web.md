# BlueBridge DS4 controls in Companion Remote

The web interface at http://<MiSTer>:9191/bluebridge exposes optional DS4
settings when the connected firmware advertises touch_mouse, ds4_gyro or
ds4_lightbar. Older firmware hides unsupported controls. This change applies
to the bundled Companion Remote web daemon, not the desktop controller panel.

Mouse and gyro default off in firmware. Enable mouse output, optionally enable
gyro, then save and allow the adapter to restart. Gyro settings cover sensitivity,
touchpad/L2/always activation, horizontal/vertical inversion, hold-to-pause and
zero, and optional R2 mouse fire. The firmware's saved/default values populate
the page. Existing touchpad movement remains available with gyro enabled.
Mouse output requires single-controller MiSTer mode. Exit Controller Tester
before checking movement in a mouse-capable core; capture suppresses USB output.

Light-bar themes are Nintendo (P1 red/P2 green), Sega (blue/orange), or Custom.
Edit four RGB presets and select a per-controller slot/preset/custom override.
Auto follows BlueBridge connection slots, not MiSTer player assignment. Each
adapter supports two connected controllers; P3/P4 remain explicit presets.
Themes retain P3/P4. Colour changes apply live without restarting.
The firmware handles low-battery blinking automatically, without a GUI setting.

The daemon reads settings with TOUCH_MOUSE_GET, DS4_AIM_GET and LIGHTBAR_GET.
POST /api/bluebridge/touch-mouse saves the mouse flag and optional ds4_aim
object through TOUCH_MOUSE_SET or DS4_AIM_SET. POST /api/bluebridge/lightbar/palette
and /api/bluebridge/lightbar/controller save through LIGHTBAR_PALETTE_SET and
LIGHTBAR_SET. Existing adapter selection and locking wrap these routes.
Routes reject unsupported capabilities, invalid types/ranges and non-POST
methods. Controller colour writes include the saved controller ID so firmware
can reject stale selections. Errors preserve unsaved edits for retry.

Firmware implementation: https://github.com/Anime0t4ku/MC-BlueBridge/pull/4
The web integration is native source; no patch installer is required after
this version of Companion Remote is deployed and its daemon regenerated.
Existing installations need the usual Companion Remote update/restart flow.

From the mister-companion directory, run:

    python -m unittest discover -s tests -p test_remote_ds4.py
    node tests/test_remote_ds4_pointer.cjs
    node tests/test_remote_ds4_lightbar.cjs

Python tests extract functions from the actual bundled daemon without starting
services or accessing hardware. They cover status/capability fallback and read
failures, strict validation, command encoding and selected-adapter HTTP routes.
JavaScript tests read the shipped asset directly and cover dirty edits during
refresh, save/validation, adapter changes, capability fallback, palette themes,
P3/P4 retention and controller identity. The entire embedded Python and web
JavaScript also pass syntax checks. Physical touchpad, gyro and red player
colour were verified previously with the equivalent local integration; this
native source revision has not been deployed to the user's MiSTer.
