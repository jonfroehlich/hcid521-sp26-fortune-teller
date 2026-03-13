"""
PM290C Thermal Printer — BLE TSPL library module.

Provides async functions to print images and text to a PM290C thermal printer
over BLE using the TSPL protocol. Protocol reverse-engineered from PacketLogger
capture of the Labelnize iOS app.

Requirements:
    pip install bleak Pillow

Usage as a library:
    import asyncio
    from pm290c_printer import print_image, print_text

    asyncio.run(print_image("photo.png"))
    asyncio.run(print_text("Hello!", font_size=48))

Usage from command line:
    python pm290c_printer.py "Hello World!"
    python pm290c_printer.py --image photo.png
    python pm290c_printer.py --font-size 48 "Big Text"
"""

import argparse
import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner

# ========== BLE CONSTANTS ==========
# UUIDs from PacketLogger capture
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
INIT_UUID = "0000ae3b-0000-1000-8000-00805f9b34fb"
NOTIFY2_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"

# Init packet sent to ae3b before any commands (from capture)
AE3B_INIT = bytes([0xFE, 0xDC, 0xBA, 0xC0, 0x07, 0x00, 0x06, 0x00,
                   0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xEF])

CHUNK_SIZE = 500  # BLE MTU was 503

# ========== PRINT CONSTANTS ==========
PRINT_WIDTH_PX = 384       # 54mm at 203 DPI
BYTES_PER_ROW = 48         # 384 / 8
PAPER_WIDTH_MM = 54
DEFAULT_DENSITY = 10
DEFAULT_FONT_SIZE = 24
BOTTOM_PAD_ROWS = 80       # ~10mm at 203 DPI for clean paper cut


# ========== BITMAP CONVERSION ==========

def _text_to_bitmap(text, font_size=DEFAULT_FONT_SIZE):
    """Render text to a 1-bit bitmap suitable for TSPL BITMAP command.

    Args:
        text: The string to render.
        font_size: Font size in pixels.

    Returns:
        Tuple of (num_rows, raw_bitmap_bytes).
    """
    from PIL import Image, ImageDraw, ImageFont

    font = _load_font(font_size)

    # Measure text dimensions
    dummy = Image.new('1', (PRINT_WIDTH_PX, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    img_h = text_h + 20

    # Render centered (white background, black text)
    img = Image.new('1', (PRINT_WIDTH_PX, img_h), color=1)
    draw = ImageDraw.Draw(img)
    x = max(0, (PRINT_WIDTH_PX - text_w) // 2)
    draw.text((x, 10), text, font=font, fill=0)

    return _image_obj_to_bitmap(img)


def _image_file_to_bitmap(image_path):
    """Convert an image file to a 1-bit bitmap for printing.

    Scales the image to the printer width, converts to 1-bit with
    thresholding, and adds bottom padding for a clean paper cut.

    Args:
        image_path: Path to the image file (PNG, JPG, etc.).

    Returns:
        Tuple of (num_rows, raw_bitmap_bytes).
    """
    from PIL import Image

    img = Image.open(image_path)
    img = img.convert('L')

    # Scale to print width
    ratio = PRINT_WIDTH_PX / img.width
    new_h = int(img.height * ratio)
    img = img.resize((PRINT_WIDTH_PX, new_h))

    # Threshold to 1-bit (no dithering — clean for line art)
    img = img.point(lambda x: 0 if x < 128 else 255, '1')

    # Add bottom padding for clean paper cut
    padded = Image.new('1', (img.width, img.height + BOTTOM_PAD_ROWS), color=0)
    padded.paste(img, (0, 0))

    return _image_obj_to_bitmap(padded)


def _image_obj_to_bitmap(img):
    """Convert a Pillow 1-bit image to raw TSPL bitmap bytes.

    TSPL BITMAP format: 1 bit per pixel, MSB first, 0=white, 1=black.
    Pillow '1' mode: 0=black, 255=white.

    Args:
        img: A Pillow Image in '1' (1-bit) mode.

    Returns:
        Tuple of (num_rows, raw_bitmap_bytes).
    """
    width = img.width
    height = img.height
    bpr = width // 8

    raw = bytearray()
    for y in range(height):
        for bx in range(bpr):
            byte_val = 0
            for bit in range(8):
                px = bx * 8 + bit
                if px < width:
                    pixel = img.getpixel((px, y))
                    if pixel == 0:  # black in Pillow -> 1 in TSPL
                        byte_val |= (1 << (7 - bit))
            raw.append(byte_val)

    return height, bytes(raw)


def _load_font(font_size):
    """Load a system font with fallback to Pillow's default.

    Args:
        font_size: Font size in pixels.

    Returns:
        A PIL ImageFont instance.
    """
    from PIL import ImageFont

    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, font_size)
        except OSError:
            continue

    return ImageFont.load_default()


# ========== BLE COMMUNICATION ==========

def _notification_handler(sender, data):
    """Callback for BLE notifications from the printer."""
    try:
        text = data.decode('ascii', errors='replace').strip()
        if text:
            print(f"  [printer] {text}")
    except Exception:
        print(f"  [printer] {data.hex()}")


async def _send_chunked(client, uuid, data, chunk_size=CHUNK_SIZE):
    """Send data to a BLE characteristic in MTU-sized chunks.

    Args:
        client: Connected BleakClient.
        uuid: Target GATT characteristic UUID.
        data: Bytes to send.
        chunk_size: Maximum bytes per write.
    """
    num_chunks = (len(data) + chunk_size - 1) // chunk_size
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        await client.write_gatt_char(uuid, chunk, response=False)
        await asyncio.sleep(0.2)
    print(f"  Sent {num_chunks} chunks, {len(data)} bytes")


async def _send_print_job(num_rows, bitmap_data, density=DEFAULT_DENSITY):
    """Scan for the printer, connect, and send a TSPL print job.

    Args:
        num_rows: Number of pixel rows in the bitmap.
        bitmap_data: Raw TSPL bitmap bytes.
        density: Print darkness, 1–15.

    Raises:
        RuntimeError: If the printer is not found.
    """
    # Calculate label height in mm (203 DPI ≈ 8 dots/mm)
    height_mm = max(1, num_rows // 8)

    # Scan for printer
    print("Scanning for PM290C...")
    target = await BleakScanner.find_device_by_name("PM290C", timeout=10.0)
    if not target:
        raise RuntimeError("PM290C not found. Is it powered on and not connected elsewhere?")
    print(f"Found: {target.name} ({target.address})")

    # Connect and print
    print("Connecting...")
    async with BleakClient(target.address) as client:
        print(f"Connected (MTU={client.mtu_size})")

        # Subscribe to notifications
        await client.start_notify(NOTIFY_UUID, _notification_handler)
        try:
            await client.start_notify(NOTIFY2_UUID, _notification_handler)
        except Exception:
            pass
        await asyncio.sleep(0.3)

        # Send init packet
        await client.write_gatt_char(INIT_UUID, AE3B_INIT, response=False)
        await asyncio.sleep(0.2)

        # Query battery (confirms communication)
        await client.write_gatt_char(WRITE_UUID, b'BATTERY?\r\n', response=False)
        await asyncio.sleep(0.5)

        # Build TSPL command sequence
        tspl_header = (
            f"SIZE {PAPER_WIDTH_MM} mm,{height_mm} mm\r\n"
            f"GAP 0,0\r\n"
            f"DIRECTION 0,0\r\n"
            f"DENSITY {density}\r\n"
            f"CLS\r\n"
            f"PRINT 1,1\r\n"
            f"BITMAP 0,0,{BYTES_PER_ROW},{num_rows},1,"
        ).encode('ascii')

        payload = tspl_header + bitmap_data + b'\r\n'

        # Send print status query (as the Labelnize app does)
        await client.write_gatt_char(WRITE_UUID, b'\x1b\x21\x3f\r\n', response=False)
        await asyncio.sleep(0.3)

        # Send the payload
        print(f"Sending {len(payload)} bytes...")
        await _send_chunked(client, WRITE_UUID, payload)

        print("Waiting for printer to finish...")
        await asyncio.sleep(5.0)

        # Cleanup notifications
        try:
            await client.stop_notify(NOTIFY_UUID)
            await client.stop_notify(NOTIFY2_UUID)
        except Exception:
            pass

    print("Print complete.")


# ========== PUBLIC API ==========

async def print_image(image_path, density=DEFAULT_DENSITY):
    """Print an image file to the PM290C thermal printer.

    Args:
        image_path: Path to an image file (PNG, JPG, etc.).
        density: Print darkness, 1–15 (default 10).
    """
    print(f"Loading image: {image_path}")
    num_rows, bitmap_data = _image_file_to_bitmap(image_path)
    print(f"Bitmap: {num_rows} rows x {PRINT_WIDTH_PX}px ({len(bitmap_data)} bytes)")
    await _send_print_job(num_rows, bitmap_data, density=density)


async def print_text(text, font_size=DEFAULT_FONT_SIZE, density=DEFAULT_DENSITY):
    """Print a text string to the PM290C thermal printer.

    Args:
        text: The text to print.
        font_size: Font size in pixels (default 24).
        density: Print darkness, 1–15 (default 10).
    """
    print(f"Rendering text: {text!r} (size {font_size})")
    num_rows, bitmap_data = _text_to_bitmap(text, font_size=font_size)
    print(f"Bitmap: {num_rows} rows x {PRINT_WIDTH_PX}px ({len(bitmap_data)} bytes)")
    await _send_print_job(num_rows, bitmap_data, density=density)


# ========== CLI ==========

def main():
    """Command-line interface for printing text or images."""
    parser = argparse.ArgumentParser(
        description="Print to PM290C thermal printer via BLE (TSPL protocol)"
    )
    parser.add_argument("text", nargs="?", default=None,
                        help="Text to print")
    parser.add_argument("--image", type=str, default=None,
                        help="Image file to print")
    parser.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE,
                        help=f"Font size (default: {DEFAULT_FONT_SIZE})")
    parser.add_argument("--density", type=int, default=DEFAULT_DENSITY,
                        help=f"Print density 1-15 (default: {DEFAULT_DENSITY})")
    args = parser.parse_args()

    if args.text is None and args.image is None:
        parser.error("Provide text to print or --image")

    if args.image:
        asyncio.run(print_image(args.image, density=args.density))
    else:
        asyncio.run(print_text(args.text, font_size=args.font_size,
                               density=args.density))


if __name__ == "__main__":
    main()
