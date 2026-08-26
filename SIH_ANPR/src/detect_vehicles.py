"""
Phase 1 - Vehicle Detection using Ultralytics YOLO
Project: SIH26127 - City-Wide AI Engine for Multi-Camera ANPR
         Trajectory Tracking and Urban Traffic Analytics

Detects vehicles (cars, buses, trucks, motorcycles) in a traffic video,
draws annotated bounding boxes, and saves the output video.
"""

import argparse
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

# COCO class IDs for vehicles we care about
VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# BGR colours per class for bounding boxes
CLASS_COLOURS = {
    2: (0, 255, 0),    # car       -> green
    3: (255, 0, 255),  # motorcycle-> magenta
    5: (0, 165, 255),  # bus       -> orange
    7: (0, 0, 255),    # truck     -> red
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Vehicle detection on a traffic video using YOLOv8."
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to the input MP4 traffic video.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path for the annotated output video. "
             "Defaults to output/<input_stem>_detected.mp4",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model weights file (default: yolov8n.pt). "
             "Ultralytics will auto-download if not present.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.4,
        help="Minimum confidence threshold (default: 0.4).",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Skip live preview window (useful for headless environments).",
    )
    return parser.parse_args()


def build_output_path(input_path: str, output_arg: str | None) -> Path:
    """Resolve the output video path."""
    if output_arg:
        out = Path(output_arg)
    else:
        stem = Path(input_path).stem
        out = Path(__file__).resolve().parents[1] / "output" / f"{stem}_detected.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def draw_annotation(frame, box, class_id: int, conf: float):
    """Draw a single bounding box with label on the frame."""
    x1, y1, x2, y2 = map(int, box)
    colour = CLASS_COLOURS.get(class_id, (200, 200, 200))
    label = f"{VEHICLE_CLASSES.get(class_id, 'vehicle')} {conf:.2f}"

    # Bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)

    # Label background
    (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(frame, (x1, y1 - th - baseline - 4), (x1 + tw, y1), colour, -1)

    # Label text
    cv2.putText(
        frame,
        label,
        (x1, y1 - baseline - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )


def process_video(args):
    input_path = args.input
    if not Path(input_path).exists():
        print(f"[ERROR] Input video not found: {input_path}")
        sys.exit(1)

    output_path = build_output_path(input_path, args.output)

    print(f"[INFO] Loading model: {args.model}")
    model = YOLO(args.model)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {input_path}")
        sys.exit(1)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    print(f"[INFO] Input  : {input_path}")
    print(f"[INFO] Output : {output_path}")
    print(f"[INFO] Frames : {total}  |  Resolution: {width}x{height}  |  FPS: {fps:.1f}")
    print("[INFO] Processing... Press 'q' in the preview window to quit early.\n")

    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        # Run inference (only on vehicle class IDs to keep it fast)
        results = model(
            frame,
            classes=list(VEHICLE_CLASSES.keys()),
            conf=args.conf,
            verbose=False,
        )[0]

        vehicle_count = 0

        # Annotate detections
        for det in results.boxes:
            class_id = int(det.cls[0])
            if class_id not in VEHICLE_CLASSES:
                continue
            conf  = float(det.conf[0])
            box   = det.xyxy[0].tolist()
            draw_annotation(frame, box, class_id, conf)
            vehicle_count += 1

        # Frame counter overlay
        cv2.putText(
            frame,
            f"Frame: {frame_idx}/{total}  Vehicles: {vehicle_count}",
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        writer.write(frame)

        if not args.no_display:
            cv2.imshow("Vehicle Detection - SIH26127", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("[INFO] Quit requested by user.")
                break

        if frame_idx % 50 == 0:
            pct = (frame_idx / total * 100) if total else 0
            print(f"  -> Frame {frame_idx}/{total}  ({pct:.1f}%)")

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    print(f"\n[DONE] Annotated video saved to: {output_path}")


def main():
    args = parse_args()
    process_video(args)


if __name__ == "__main__":
    main()
