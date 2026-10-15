# Usage guide

## Tools (left rail)

| Icon | Tool | How it works |
|------|------|--------------|
| Ruler | **Calibrate** | Click two marks of known distance, enter the real distance and unit |
| Line | **Line** | Click point A, then point B |
| Curve | **Bead contour** | Click along a curved edge. Finish with Enter, double-click or right-click |
| Pentagon | **Polygon** | Click vertices. Click the first point (the cursor snaps to it) or press Enter to close, then name it |
| Lens | **Loupe** | Toggles the magnifier under the cursor |

Line and bead tools need a calibration first. The polygon tool also works uncalibrated, in pixels.

## Labels and the measurement list

- **Move**: drag a label. A dashed line links it back to its shape.
- **Rename**: double-click the label or the name cell in the list, or right-click, then Rename.
- **Colour**: click the colour square in the list, use the Colour button, or right-click a label. The picker has presets, a colour wheel, a brightness slider and a hex field.
- **Order**: select a row, then Up or Down. The `#` numbers follow the list order.
- **Delete**: select a row, then Delete. Undo Last removes the newest measurement.
- **Reset position**: right-click a label, then Reset label position.

## Keyboard and mouse

| Input | Action |
|-------|--------|
| Click | Place a point |
| Esc | Cancel the current drawing (or leave full screen) |
| Enter | Finish a bead path or close a polygon |
| Backspace | Remove the last placed point |
| Wheel | Zoom at the cursor |
| Alt + Wheel / Shift + Wheel | Scroll sideways |
| Ctrl + Drag / Middle drag | Pan |
| Ctrl+O / Ctrl+E | Open image / Export |
| Ctrl+Z | Undo last measurement |
| Ctrl+0 / Ctrl+1 | Fit to window / 1:1 |
| Ctrl+K | Recalibrate |
| L | Toggle loupe |
| F11 | Full screen |

## Tips

- Zoom in before calibrating. Longer reference spans give a more accurate scale.
- Turn on sub-pixel snapping (if `marker_snap.py` is present) and set **Mark width** to the printed line width in pixels (2-5 is typical).
- A new image resets calibration and measurements because the scale is different.
