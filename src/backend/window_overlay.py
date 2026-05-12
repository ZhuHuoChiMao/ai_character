import argparse
import tkinter as tk


TRANSPARENT_COLOR = "#ff00ff"


def rounded_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def add_strip(root, x, y, width, height, color, text=None):
    window = tk.Toplevel(root)
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    window.configure(bg=TRANSPARENT_COLOR)
    window.attributes("-transparentcolor", TRANSPARENT_COLOR)
    window.geometry(f"{max(1, width)}x{max(1, height)}+{x}+{y}")
    canvas = tk.Canvas(
        window,
        width=max(1, width),
        height=max(1, height),
        highlightthickness=0,
        bd=0,
        bg=TRANSPARENT_COLOR,
    )
    canvas.pack(fill="both", expand=True)
    rounded_rectangle(canvas, 0, 0, max(1, width), max(1, height), min(width, height) // 2, fill=color, outline=color)
    if text:
        canvas.create_text(
            max(1, width) // 2,
            max(1, height) // 2,
            text=text,
            fill="#1f2933",
            font=("Microsoft YaHei", 14, "normal"),
        )
    return window


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--color", default="#f4efe6")
    parser.add_argument("--side", type=int, default=39)
    parser.add_argument("--top", type=int, default=47)
    parser.add_argument("--bottom", type=int, default=55)
    parser.add_argument("--outset", type=int, default=28)
    parser.add_argument("--bottom-outset", type=int, default=44)
    parser.add_argument("--text", default="")
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()

    x = args.x - args.outset
    y = args.y - args.outset
    width = args.width + args.outset * 2
    height = args.height + args.outset + args.bottom_outset

    add_strip(root, x, y, width, args.top + args.outset, args.color, text=args.text)
    add_strip(root, x, y, args.side, height, args.color)
    add_strip(root, x + width - args.side, y, args.side, height, args.color)
    add_strip(root, x, y + height - args.bottom, width, args.bottom, args.color)

    root.mainloop()


if __name__ == "__main__":
    main()
