"""
Gradio Web Application for tire-measurement-tool
"""
import math
import gradio as gr
from PIL import Image, ImageDraw

UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
COLORS = {
    "Calibrate": "#F5A524",
    "Distance": "#3DDC84",
    "Bead contour": "#FF7A3D",
    "Polygon area": "#2EC4F1",
}

def render(img, measurements, pending):
    if img is None:
        return None

    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)

    for item in measurements or []:
        pts = item["points"]
        color = item["color"]

        if item["kind"] in ("Distance", "Bead contour"):
            if len(pts) >= 2:
                d.line(pts, fill=color, width=4)
        elif item["kind"] == "Polygon area":
            if len(pts) >= 3:
                d.line(pts + [pts[0]], fill=color, width=4)

        for x, y in pts:
            d.ellipse((x-4, y-4, x+4, y+4),
                      fill=color, outline="white", width=1)

        x, y = pts[0]
        d.text((x+7, y+7), item["label"],
               fill="white", stroke_width=2, stroke_fill="black")

    if pending:
        if len(pending) >= 2:
            d.line(pending, fill="#FFFFFF", width=2)
        for x, y in pending:
            d.ellipse((x-4, y-4, x+4, y+4),
                      fill="#F5A524", outline="white")

    return out

def on_upload(img):
    if img is None:
        return None, None, [], None, [], "Upload an image to start."
    img = img.convert("RGB")
    return img, img, [], None, [], (
        "Image loaded. Select Calibrate and click two points "
        "with a known distance between them."
    )

def on_click(img, mode, known, unit, scale, pending, measurements, evt: gr.SelectData):
    if img is None:
        return None, pending, scale, measurements, "Upload an image first."

    if evt.index is None:
        return render(img, measurements, pending), pending, scale, measurements, "Could not read click position."

    x, y = map(int, evt.index)
    pending = list(pending or [])
    measurements = list(measurements or [])

    if mode != "Calibrate" and mode != "Distance" and mode != "Bead contour" and mode != "Polygon area":
        return render(img, measurements, pending), pending, scale, measurements, "Choose a tool."

    # Start a fresh operation if changing tool.
    pending.append((x, y))
    status = f"{mode}: {len(pending)} point(s) selected."

    if mode == "Calibrate" and len(pending) == 2:
        if known is None or float(known) <= 0:
            pending = []
            status = "Enter a reference distance greater than zero, then calibrate again."
        else:
            (x1, y1), (x2, y2) = pending
            pixel_distance = math.hypot(x2-x1, y2-y1)
            if pixel_distance == 0:
                status = "The points must be different. Click two separate points."
            else:
                scale = pixel_distance / (float(known) * UNIT_TO_MM[unit])
                status = (
                    f"Calibrated: {scale:.5f} pixels/mm. "
                    "You can now measure distances and areas."
                )
                pending = []

    elif mode == "Distance" and len(pending) == 2:
        (x1, y1), (x2, y2) = pending
        px = math.hypot(x2-x1, y2-y1)
        if not scale:
            status = "Calibrate first using two points and a known distance."
        else:
            mm = px / scale
            value = mm / UNIT_TO_MM[unit]
            label = f"{value:.3f} {unit}"
            measurements.append({
                "kind": mode,
                "points": list(pending),
                "color": COLORS[mode],
                "label": label,
                "value": value,
                "unit": unit,
            })
            status = f"Distance: {label}"
            pending = []

    return render(img, measurements, pending), pending, scale, measurements, status

def finish_shape(img, mode, unit, scale, pending, measurements):
    pending = list(pending or [])
    measurements = list(measurements or [])

    if img is None:
        return None, pending, measurements, "Upload an image first."
    if not scale:
        return render(img, measurements, pending), pending, measurements, "Calibrate first."
    if mode == "Bead contour" and len(pending) < 2:
        return render(img, measurements, pending), pending, measurements, "Select at least two points."
    if mode == "Polygon area" and len(pending) < 3:
        return render(img, measurements, pending), pending, measurements, "Select at least three vertices."

    if mode == "Bead contour":
        px = sum(math.hypot(
            pending[i][0] - pending[i-1][0],
            pending[i][1] - pending[i-1][1]
        ) for i in range(1, len(pending)))
        value = px / scale / UNIT_TO_MM[unit]
        label = f"Length {value:.3f} {unit}"
    else:
        twice_area = abs(sum(
            pending[i][0] * pending[(i+1) % len(pending)][1]
            - pending[(i+1) % len(pending)][0] * pending[i][1]
            for i in range(len(pending))
        ))
        area_mm2 = (twice_area / 2) / (scale ** 2)
        value = area_mm2 / (UNIT_TO_MM[unit] ** 2)
        label = f"Area {value:.3f} {unit}²"

    measurements.append({
        "kind": mode,
        "points": list(pending),
        "color": COLORS[mode],
        "label": label,
        "value": value,
        "unit": unit,
    })
    return render(img, measurements, []), [], measurements, f"Completed: {label}"

def clear_points(img, measurements):
    return render(img, measurements or [], []), [], "Pending points cleared."

def reset_all(img):
    return render(img, [], []), [], None, [], "Reset. Upload or calibrate to begin again."

def export_image(img, measurements, pending):
    if img is None:
        raise gr.Error("Upload an image first.")
    out = render(img, measurements or [], pending or [])
    path = "/tmp/tire_measurement_annotated.png"
    out.save(path)
    return path

with gr.Blocks(title="Tire Measure Tool", theme=gr.themes.Base()) as demo:
    gr.Markdown(
        "# TIRE MEASURE TOOL\n"
        "Calibrate against a known distance, then measure tire features in your image."
    )

    original = gr.State(None)
    scale_state = gr.State(None)
    pending_state = gr.State([])
    measurements_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=3):
            canvas = gr.Image(
                label="Image — click here to place measurement points",
                type="pil",
                height=650
            )
            status = gr.Markdown("Upload an image to begin.")
        with gr.Column(scale=1):
            upload = gr.Image(label="Upload tire image", type="pil")
            tool = gr.Radio(
                ["Calibrate", "Distance", "Bead contour", "Polygon area"],
                value="Calibrate",
                label="Measurement tool"
            )
            known = gr.Number(value=10, label="Known reference distance")
            unit = gr.Dropdown(
                ["mm", "cm", "m", "in"],
                value="mm",
                label="Unit"
            )
            gr.Markdown(
                "**How to use**\n"
                "1. Upload an image.\n"
                "2. Calibrate: click two known reference points.\n"
                "3. Distance: click two points.\n"
                "4. Bead contour: click along a curve, then finish.\n"
                "5. Polygon area: click vertices, then finish."
            )
            finish = gr.Button("Finish contour / polygon", variant="primary")
            clear = gr.Button("Clear pending points")
            reset = gr.Button("Reset all measurements")
            export = gr.Button("Prepare annotated PNG")
            download = gr.File(label="Download annotated image")

    upload.upload(
        on_upload,
        inputs=upload,
        outputs=[original, canvas, pending_state, scale_state, measurements_state, status]
    )

    canvas.select(
        on_click,
        inputs=[original, tool, known, unit, scale_state, pending_state, measurements_state],
        outputs=[canvas, pending_state, scale_state, measurements_state, status]
    )

    finish.click(
        finish_shape,
        inputs=[original, tool, unit, scale_state, pending_state, measurements_state],
        outputs=[canvas, pending_state, measurements_state, status]
    )

    clear.click(
        clear_points,
        inputs=[original, measurements_state],
        outputs=[canvas, pending_state, status]
    )

    reset.click(
        reset_all,
        inputs=[original],
        outputs=[canvas, pending_state, scale_state, measurements_state, status]
    )

    export.click(
        export_image,
        inputs=[original, measurements_state, pending_state],
        outputs=download
    )

if __name__ == "__main__":
    demo.launch(share=True, debug=True)
