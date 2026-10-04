"""The Windows app icon: the art of the Mac icon (tools/art/app_icon.py: the ASTRA Navy's eight-pointed star over deep space) without the
Mac's margin and drop shadow, in every size Windows asks for. The engine puts Build/Windows/Application.ico on ASTRA.exe.

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/app_icon_windows.py
  -> Build/Windows/Application.ico (256, 128, 64, 48, 32, 24 and 16 px)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app_icon  # noqa: E402

OUT = os.path.join(app_icon.ROOT, "Build", "Windows", "Application.ico")


def main() -> None:
    plate = app_icon.icon().crop((100, 100, 924, 924))          # the rounded plate (824 px on the Mac's 1024 grid) without the shadow around it
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    plate.save(OUT, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    print("ICO_OK", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
