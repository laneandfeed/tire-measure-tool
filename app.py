"""
app.py - Tire Measure Tool, web version (Gradio)
------------------------------------------------
Same measuring ideas as the desktop app (measure_tool.py), but it runs in a browser,
so it works on Google Colab, Hugging Face Spaces, or locally. No PyQt needed.

Run locally:      pip install -r requirements-web.txt && python app.py
Run in Colab:     !pip -q install gradio pillow numpy
                  !python app.py          (prints a public link; open it)

How to use:
  1. Upload a photo.
  2. Mode = Calibrate: click two marks of known distance, type the real distance,
     press "Apply calibration".
  3. Pick Line / Bead contour / Polygon and click on the image.
     Bead and Polygon: press "Finish" (or click the first point to close a polygon).
  4. Rename / recolour / reorder / delete from the "Edit" box, then export.

Differences from the desktop app: no loupe, no drag-to-move labels, no sub-pixel snap.
Large photos are shrunk to MAX_SIDE pixels so clicks stay fast (the scale is calibrated
on the shrunk image, so accuracy is unaffected).
"""

import argparse
import csv
import math
import os
import re
import tempfile

import gradio as gr
from PIL import Image, ImageColor, ImageDraw, ImageFont

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
DISPLAY_UNITS = ["mm", "cm", "in", "px"]
MODES = ["Calibrate", "Line", "Bead contour", "Polygon"]
MAX_SIDE = 2600

AMBER, GREEN, CYAN, ORANGE = "#F5A524", "#3DDC84", "#2EC4F1", "#FF7A3D"
POLY_COLORS = ["#B388FF", "#FF6FB5", "#4DD0E1", "#FFD54F", "#C6FF4D", "#7C8CFF"]
DEFAULT_COLOR = {"line": GREEN, "bead": ORANGE}
PANEL = (16, 19, 22, 225)


# ── PURE HELPERS (no UI; copy these anywhere) ─────────────────────────────────
def path_length(pts, closed=False) -> float:
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    if closed and len(pts) > 2:
        total += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    return total


def polygon_area_centroid(pts):
    """Shoelace area and centroid (vertex mean for degenerate shapes)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return 0.0, (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return abs(a), (cx / (6 * a), cy / (6 * a))


def length_text(px, px_per_mm, unit) -> str:
    """Lengths are stored in pixels and converted for display."""
    if unit == "px" or not px_per_mm:
        return f"{px:.1f} px"
    mm = px / px_per_mm
    return {"cm": f"{mm / 10:.2f} cm", "in": f"{mm / 25.4:.3f} in"}.get(unit, f"{mm:.2f} mm")


def area_text(area_px, px_per_mm, unit) -> str:
    if unit == "px" or not px_per_mm:
        return f"{area_px:,.0f} px²"
    mm2 = area_px / px_per_mm ** 2
    return {"cm": f"{mm2 / 100:.2f} cm²", "in": f"{mm2 / 645.16:.3f} in²"}.get(unit, f"{mm2:,.1f} mm²")


def parse_color(value, fallback=GREEN) -> str:
    """Accepts '#rrggbb', names, or 'rgba(r,g,b,a)' (what some Gradio versions return)."""
    try:
        r, g, b = ImageColor.getrgb(value)[:3]
    except (ValueError, TypeError):
        nums = re.findall(r"[\d.]+", str(value))
        if len(nums) < 3:
            return fallback
        r, g, b = (int(float(n)) for n in nums[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def get_font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "C:/Windows/Fonts/consolab.ttf", "/Library/Fonts/Arial Bold.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ── STATE ─────────────────────────────────────────────────────────────────────
def new_state():
    return {"orig": None, "k": 1.0, "px_per_mm": None, "cal_text": "not calibrated",
            "draft": [], "measures": []}


def label_text(m, idx, px_per_mm, unit):
    head = f"#{idx}" + (f"  {m['name']}" if m["name"] else "")
    if m["type"] == "polygon":
        return (f"{head}\nA {area_text(m['area_px'], px_per_mm, unit)}   "
                f"P {length_text(m['dist_px'], px_per_mm, unit)}")
    return f"{head}  {length_text(m['dist_px'], px_per_mm, unit)}"


# ── DRAWING ───────────────────────────────────────────────────────────────────
def render(state, unit, draft_color=None):
    """Draw every finished measurement and the draft on a copy of the original image."""
    base = state["orig"].convert("RGBA")
    k = state["k"]
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = get_font(int(13 * k))
    ppm = state["px_per_mm"]

    def dot(p, color, r):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color + "AA", outline=color,
                  width=max(1, int(1.6 * k)))

    def pill(text, cx, cy, color):
        l, t, r, b = d.multiline_textbbox((0, 0), text, font=font, align="center")
        w, h, pad = r - l, b - t, 6 * k
        x0 = min(max(cx - w / 2 - pad, 0), base.width - w - 2 * pad)
        y0 = min(max(cy - h / 2 - pad / 2, 0), base.height - h - pad)
        d.rounded_rectangle([x0, y0, x0 + w + 2 * pad, y0 + h + pad], radius=3 * k, fill=PANEL,
                            outline=color, width=max(1, int(1.2 * k)))
        d.multiline_text((x0 + pad - l, y0 + pad / 2 - t), text, font=font, fill="white", align="center")

    def dashed(a, b, color):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        step = 14 * k
        n = int(length // step)
        for i in range(0, n + 1, 2):
            s, e = i * step / max(length, 1e-6), min((i + 1) * step, length) / max(length, 1e-6)
            d.line([(a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s),
                    (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e)], fill=color, width=max(1, int(2 * k)))

    for idx, m in enumerate(state["measures"], 1):
        color, pts = m["color"], m["pts"]
        w = max(1, int((3 if m["type"] == "bead" else 2) * k))
        if m["type"] == "polygon":
            d.polygon(pts, fill=color + "3C", outline=color, width=w)
            for p in pts:
                dot(p, color, 4.5 * k)
            _, (ax, ay) = polygon_area_centroid(pts)
        else:
            d.line(pts, fill=color, width=w, joint="curve")
            for p in (pts if m["type"] == "bead" else (pts[0], pts[-1])):
                dot(p, color, 5 * k)
            mid = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2) if m["type"] == "line" \
                else pts[len(pts) // 2]
            ax, ay = mid[0], mid[1] - 22 * k
        pill(label_text(m, idx, ppm, unit), ax, ay, color)

    draft, mode = state["draft"], state.get("mode", "Line")
    if draft:
        col = draft_color or CYAN
        d.line(draft, fill=col, width=max(1, int(2 * k)))
        for i, p in enumerate(draft, 1):
            dot(p, col, 6 * k if mode != "Polygon" else 4.5 * k)
        if mode == "Polygon" and len(draft) >= 3:
            dashed(draft[-1], draft[0], AMBER)       # hint of the closing edge
            dot(draft[0], AMBER, 10 * k)
        if mode == "Bead contour" and len(draft) >= 2:
            pill(f"Bead: {length_text(path_length(draft), ppm, unit)}", draft[-1][0] + 40 * k,
                 draft[-1][1] - 30 * k, ORANGE)
        if mode == "Calibrate" and len(draft) == 2:
            pill(f"{path_length(draft):.1f} px", (draft[0][0] + draft[1][0]) / 2,
                 (draft[0][1] + draft[1][1]) / 2 - 22 * k, AMBER)
    return Image.alpha_composite(base, layer).convert("RGB")


# ── TABLE / STATUS ────────────────────────────────────────────────────────────
def table_rows(state, unit):
    ppm, rows = state["px_per_mm"], []
    for i, m in enumerate(state["measures"], 1):
        if m["type"] == "polygon":
            value = area_text(m["area_px"], ppm, unit)
            extra = "perimeter " + length_text(m["dist_px"], ppm, unit)
        else:
            value = length_text(m["dist_px"], ppm, unit)
            extra = f"{m['dist_px']:.1f} px"
        rows.append([i, m["name"], m["type"], value, extra, m["color"]])
    return rows


def ui(state, unit, msg, clear_name=False):
    """Standard return for every handler: image, state, status, table, name box."""
    img = render(state, unit) if state["orig"] is not None else gr.update()
    status = f"**Scale:** {state['cal_text']}  \n{msg}"
    return (img, state, status, table_rows(state, unit),
            gr.update(value="") if clear_name else gr.update())


def need_image(state, unit):
    return ui(state, unit, "Upload an image first.") if state["orig"] is None else None


# ── HANDLERS ──────────────────────────────────────────────────────────────────
def on_upload(img, unit):
    state = new_state()
    if img is None:
        return (gr.update(),) + ui(state, unit, "Upload an image to start.")[1:]
    img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        s = MAX_SIDE / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    state["orig"], state["k"] = img, max(1.0, img.width / 900.0)
    state["mode"] = "Calibrate"
    return (img,) + ui(state, unit, "Mode **Calibrate**: click two marks of known distance.")[1:]


def add_measure(state, mtype, pts, name, **extra):
    n_poly = sum(1 for m in state["measures"] if m["type"] == "polygon")
    color = DEFAULT_COLOR.get(mtype) or POLY_COLORS[n_poly % len(POLY_COLORS)]
    dist = path_length(pts, closed=(mtype == "polygon"))
    state["measures"].append({"type": mtype, "pts": pts, "dist_px": dist, "name": name.strip(),
                              "color": color, **extra})


def finish_draft(state, mode, name):
    """Turn the current bead/polygon draft into a measurement. Returns (done, message)."""
    pts = list(state["draft"])
    if mode == "Bead contour":
        if len(pts) < 2:
            return False, "Bead needs at least 2 points."
        add_measure(state, "bead", pts, name)
    elif mode == "Polygon":
        if len(pts) < 3:
            return False, "Polygon needs at least 3 points."
        add_measure(state, "polygon", pts, name, area_px=polygon_area_centroid(pts)[0])
    else:
        return False, "Finish applies to Bead contour and Polygon modes."
    state["draft"] = []
    return True, f"Added measurement #{len(state['measures'])}."


def on_click(state, mode, unit, name, evt: gr.SelectData):
    if (r := need_image(state, unit)) is not None:
        return r
    x, y = float(evt.index[0]), float(evt.index[1])
    state["mode"] = mode
    draft = state["draft"]

    if mode == "Calibrate":
        if len(draft) >= 2:
            draft.clear()
        draft.append((x, y))
        msg = ("Click the **second** mark." if len(draft) == 1 else
               "Now enter the real distance and press **Apply calibration**.")
        return ui(state, unit, msg)

    if mode in ("Line", "Bead contour") and not state["px_per_mm"]:
        return ui(state, unit, "Calibrate first (mode **Calibrate**).")

    if mode == "Line":
        draft.append((x, y))
        if len(draft) == 2:
            add_measure(state, "line", list(draft), name)
            state["draft"] = []
            return ui(state, unit, f"Added measurement #{len(state['measures'])}.", clear_name=True)
        return ui(state, unit, "Click **point B**.")

    if mode == "Bead contour":
        draft.append((x, y))
        return ui(state, unit, f"{len(draft)} points. Keep clicking, then press **Finish**.")

    # Polygon: clicking next to the first point closes it (labelme-style snap)
    if len(draft) >= 3 and math.hypot(x - draft[0][0], y - draft[0][1]) <= max(10, state["orig"].width * 0.012):
        ok, msg = finish_draft(state, mode, name)
        return ui(state, unit, msg, clear_name=ok)
    draft.append((x, y))
    hint = "Click the **first point** to close, or press **Finish**." if len(draft) >= 3 else "Keep clicking."
    return ui(state, unit, f"{len(draft)} vertices. {hint}")


def on_finish(state, mode, unit, name):
    if (r := need_image(state, unit)) is not None:
        return r
    ok, msg = finish_draft(state, mode, name)
    return ui(state, unit, msg, clear_name=ok)


def on_cancel(state, unit):
    if (r := need_image(state, unit)) is not None:
        return r
    state["draft"] = []
    return ui(state, unit, "Cancelled the current drawing.")


def on_undo_point(state, unit):
    if (r := need_image(state, unit)) is not None:
        return r
    if state["draft"]:
        state["draft"].pop()
    return ui(state, unit, "Removed the last point.")


def on_undo_measure(state, unit):
    if (r := need_image(state, unit)) is not None:
        return r
    if state["measures"]:
        state["measures"].pop()
    return ui(state, unit, "Removed the last measurement.")


def on_clear(state, unit):
    if (r := need_image(state, unit)) is not None:
        return r
    state["draft"], state["measures"] = [], []
    return ui(state, unit, "Cleared all measurements.")


def on_mode_change(state, mode, unit):
    state["mode"] = mode
    state["draft"] = []
    return ui(state, unit, f"Mode **{mode}**.")


def on_unit_change(state, unit):
    return ui(state, unit, f"Showing values in **{unit}**.")


def on_apply_calibration(state, dist, cal_unit, unit):
    if (r := need_image(state, unit)) is not None:
        return (*r, gr.update())
    if state.get("mode") != "Calibrate" or len(state["draft"]) != 2:
        return (*ui(state, unit, "Click two marks in **Calibrate** mode first."), gr.update())
    if not dist or dist <= 0:
        return (*ui(state, unit, "Enter a distance greater than 0."), gr.update())
    px = path_length(state["draft"])
    if px < 2:
        state["draft"] = []
        return (*ui(state, unit, "Marks are too close. Try again."), gr.update())
    state["px_per_mm"] = px / (dist * UNIT_TO_MM[cal_unit])
    state["cal_text"] = f"{state['px_per_mm']:.3f} px/mm ({px:.1f} px = {dist:g} {cal_unit})"
    state["draft"] = []
    new_unit = cal_unit if cal_unit in DISPLAY_UNITS else "mm"
    state["mode"] = "Line"
    return (*ui(state, new_unit, "Calibrated. Pick **Line**, **Bead contour** or **Polygon**."),
            gr.update(value=new_unit), gr.update(value="Line"))


def pick(state, idx):
    i = int(idx or 0) - 1
    return state["measures"][i] if 0 <= i < len(state["measures"]) else None


def on_edit(state, unit, idx, new_name, color):
    if (r := need_image(state, unit)) is not None:
        return r
    m = pick(state, idx)
    if m is None:
        return ui(state, unit, "Enter a valid measurement number.")
    if new_name and new_name.strip():
        m["name"] = new_name.strip()
    if color:
        m["color"] = parse_color(color, m["color"])
    return ui(state, unit, f"Updated #{int(idx)}.")


def on_delete(state, unit, idx):
    if (r := need_image(state, unit)) is not None:
        return r
    m = pick(state, idx)
    if m is None:
        return ui(state, unit, "Enter a valid measurement number.")
    state["measures"].remove(m)
    return ui(state, unit, "Deleted.")


def on_move(state, unit, idx, delta):
    if (r := need_image(state, unit)) is not None:
        return r
    i = int(idx or 0) - 1
    j = i + delta
    if not (0 <= i < len(state["measures"]) and 0 <= j < len(state["measures"])):
        return ui(state, unit, "Can't move that measurement.")
    ms = state["measures"]
    ms[i], ms[j] = ms[j], ms[i]
    return ui(state, unit, f"Moved to #{j + 1}. Numbers follow the list order.")


def on_export(state, unit):
    if state["orig"] is None:
        return None, None
    tmp = tempfile.mkdtemp()
    png, csv_path = os.path.join(tmp, "measured_output.png"), os.path.join(tmp, "measurements.csv")
    render(state, unit).save(png)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "name", "type", "value", "extra", "colour"])
        w.writerows(table_rows(state, unit))
    return png, csv_path


# ── UI ────────────────────────────────────────────────────────────────────────
def build_demo():
    with gr.Blocks(title="Tire Measure Tool") as demo:
        gr.Markdown("# Tire Measure Tool\nCalibrate against a ruler in the photo, then measure "
                    "lines, curved contours and polygon areas.")
        state = gr.State(new_state())

        with gr.Row():
            with gr.Column(scale=3):
                img = gr.Image(type="pil", label="Click on the image", sources=["upload", "clipboard"],
                               interactive=True)
                status = gr.Markdown("Upload an image to start.")
            with gr.Column(scale=2):
                mode = gr.Radio(MODES, value="Calibrate", label="Mode")
                unit = gr.Radio(DISPLAY_UNITS, value="mm", label="Display unit")
                name = gr.Textbox(label="Name for the next shape (optional)")
                with gr.Row():
                    finish = gr.Button("Finish (bead / polygon)", variant="primary")
                    cancel = gr.Button("Cancel drawing")
                with gr.Row():
                    undo_pt = gr.Button("Undo point")
                    undo_m = gr.Button("Undo measurement")
                    clear = gr.Button("Clear all")
                with gr.Accordion("Calibration", open=True):
                    with gr.Row():
                        dist = gr.Number(value=15.0, label="Real distance between the two marks")
                        cal_unit = gr.Dropdown(["cm", "mm", "in", "m"], value="cm", label="Unit")
                    apply_cal = gr.Button("Apply calibration")

        table = gr.Dataframe(headers=["#", "name", "type", "value", "extra", "colour"],
                             interactive=False, label="Measurements")

        with gr.Accordion("Edit a measurement", open=False):
            with gr.Row():
                idx = gr.Number(value=1, precision=0, label="Measurement #")
                new_name = gr.Textbox(label="New name")
                color = gr.ColorPicker(label="Colour")
            with gr.Row():
                apply_edit = gr.Button("Apply name / colour")
                up, down = gr.Button("Move up"), gr.Button("Move down")
                delete = gr.Button("Delete")

        with gr.Row():
            export = gr.Button("Export annotated image + CSV")
            out_img = gr.File(label="Annotated image")
            out_csv = gr.File(label="Measurements CSV")

        outs = [img, state, status, table, name]
        img.upload(on_upload, [img, unit], outs)
        img.select(on_click, [state, mode, unit, name], outs)
        mode.change(on_mode_change, [state, mode, unit], outs)
        unit.change(on_unit_change, [state, unit], outs)
        finish.click(on_finish, [state, mode, unit, name], outs)
        cancel.click(on_cancel, [state, unit], outs)
        undo_pt.click(on_undo_point, [state, unit], outs)
        undo_m.click(on_undo_measure, [state, unit], outs)
        clear.click(on_clear, [state, unit], outs)
        apply_cal.click(on_apply_calibration, [state, dist, cal_unit, unit], outs + [unit, mode])
        apply_edit.click(on_edit, [state, unit, idx, new_name, color], outs)
        delete.click(on_delete, [state, unit, idx], outs)
        up.click(lambda s, u, i: on_move(s, u, i, -1), [state, unit, idx], outs)
        down.click(lambda s, u, i: on_move(s, u, i, 1), [state, unit, idx], outs)
        export.click(on_export, [state, unit], [out_img, out_csv])
    return demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="create a public gradio.live link")
    args = parser.parse_args()
    in_colab = bool(os.environ.get("COLAB_RELEASE_TAG"))
    build_demo().launch(share=args.share or in_colab)


if __name__ == "__main__":
    main()
