#
# QR Code generator demo (Python)
#
# Run this command-line program with no arguments. The program computes a bunch of demonstration
# QR Codes and prints them to the console. Also, the SVG code for one QR Code is printed as a sample.
#
# Copyright (c) Project Nayuki. (MIT License)
# https://www.nayuki.io/page/qr-code-generator-library
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - The Software is provided "as is", without warranty of any kind, express or
#   implied, including but not limited to the warranties of merchantability,
#   fitness for a particular purpose and noninfringement. In no event shall the
#   authors or copyright holders be liable for any claim, damages or other
#   liability, whether in an action of contract, tort or otherwise, arising from,
#   out of or in connection with the Software or the use or other dealings in the
#   Software.
#

from __future__ import annotations

from backup import QRCode, QRSegment


def main() -> None:
    """The main application program."""
    do_basic_demo()
    do_variety_demo()
    do_segment_demo()
    do_mask_demo()


# ---- Demo suite ----


def do_basic_demo() -> None:
    """Creates a single QR Code, then prints it to the console."""
    text = "Hello, world!"  # User-supplied Unicode text
    errcorlvl = QRCode.ECC.LOW  # Error correction level

    # Make and print the QR Code symbol
    qr = QRCode.encode_text(text, errcorlvl)
    print_qr(qr)
    print(to_svg_str(qr, 4))


def do_variety_demo() -> None:
    """Creates a variety of QR Codes that exercise different features of the library, and prints each one to the console."""

    # Numeric mode encoding (3.33 bits per digit)
    qr = QRCode.encode_text(
        "314159265358979323846264338327950288419716939937510", QRCode.ECC.MEDIUM,
    )
    print_qr(qr)

    # Alphanumeric mode encoding (5.5 bits per character)
    qr = QRCode.encode_text(
        "DOLLAR-AMOUNT:$39.87 PERCENTAGE:100.00% OPERATIONS:+-*/", QRCode.ECC.HIGH,
    )
    print_qr(qr)

    # Unicode text as UTF-8
    qr = QRCode.encode_text(
        "\u3053\u3093\u306b\u3061\u0077\u0061\u3001\u4e16\u754c\uff01\u0020\u03b1\u03b2\u03b3\u03b4",
        QRCode.ECC.QUARTILE,
    )
    print_qr(qr)

    # Moderately large QR Code using longer text (from Lewis Carroll's Alice in Wonderland)
    qr = QRCode.encode_text(
        "Alice was beginning to get very tired of sitting by her sister on the bank, "
        "and of having nothing to do: once or twice she had peeped into the book her sister was reading, "
        "but it had no pictures or conversations in it, 'and what is the use of a book,' thought Alice "
        "'without pictures or conversations?' So she was considering in her own mind (as well as she could, "
        "for the hot day made her feel very sleepy and stupid), whether the pleasure of making a "
        "daisy-chain would be worth the trouble of getting up and picking the daisies, when suddenly "
        "a White Rabbit with pink eyes ran close by her.",
        QRCode.ECC.HIGH,
    )
    print_qr(qr)


def do_segment_demo() -> None:
    """Creates QR Codes with manually specified segments for better compactness."""

    # Illustration "silver"
    silver0 = "THE SQUARE ROOT OF 2 IS 1."
    silver1 = "41421356237309504880168872420969807856967187537694807317667973799"
    qr = QRCode.encode_text(silver0 + silver1, QRCode.ECC.LOW)
    print_qr(qr)

    segs = [QRSegment.make_alphanumeric(silver0), QRSegment.make_numeric(silver1)]
    qr = QRCode.encode_segments(segs, QRCode.ECC.LOW)
    print_qr(qr)

    # Illustration "golden"
    golden0 = "Golden ratio \u03c6 = 1."
    golden1 = "6180339887498948482045868343656381177203091798057628621354486227052604628189024497072072041893911374"
    golden2 = "......"
    qr = QRCode.encode_text(golden0 + golden1 + golden2, QRCode.ECC.LOW)
    print_qr(qr)

    segs = [
        QRSegment.make_bytes(golden0.encode("UTF-8")),
        QRSegment.make_numeric(golden1),
        QRSegment.make_alphanumeric(golden2),
    ]
    qr = QRCode.encode_segments(segs, QRCode.ECC.LOW)
    print_qr(qr)

    # Illustration "Madoka": kanji, kana, Cyrillic, full-width Latin, Greek characters
    madoka = "\u300c\u9b54\u6cd5\u5c11\u5973\u307e\u3069\u304b\u2606\u30de\u30ae\u30ab\u300d\u3063\u3066\u3001\u3000\u0418\u0410\u0418\u3000\uff44\uff45\uff53\uff55\u3000\u03ba\u03b1\uff1f"
    qr = QRCode.encode_text(madoka, QRCode.ECC.LOW)
    print_qr(qr)

    kanjicharbits = [  # Kanji mode encoding (13 bits per character)
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        1,
        0,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        1,
        1,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        1,
        1,
        1,
        0,
        1,
        1,
        0,
        1,
        0,
        1,
        0,
        1,
        0,
        1,
        1,
        0,
        1,
        0,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        1,
        1,
        1,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        0,
        0,
        1,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
    ]
    segs = [QRSegment(QRSegment.Mode.KANJI, len(kanjicharbits) // 13, kanjicharbits)]
    qr = QRCode.encode_segments(segs, QRCode.ECC.LOW)
    print_qr(qr)


def do_mask_demo() -> None:
    """Creates QR Codes with the same size and contents but different mask patterns."""

    # Project Nayuki URL
    segs = QRSegment.make_segments("https://www.nayuki.io/")
    print_qr(QRCode.encode_segments(segs, QRCode.ECC.HIGH, mask=-1))  # Automatic mask
    print_qr(QRCode.encode_segments(segs, QRCode.ECC.HIGH, mask=3))  # Force mask 3

    # Chinese text as UTF-8
    segs = QRSegment.make_segments(
        "\u7dad\u57fa\u767e\u79d1\uff08\u0057\u0069\u006b\u0069\u0070\u0065\u0064\u0069\u0061\uff0c"
        "\u8046\u807d\u0069\u002f\u02cc\u0077\u026a\u006b\u1d7b\u02c8\u0070\u0069\u02d0\u0064\u0069"
        "\u002e\u0259\u002f\uff09\u662f\u4e00\u500b\u81ea\u7531\u5167\u5bb9\u3001\u516c\u958b\u7de8"
        "\u8f2f\u4e14\u591a\u8a9e\u8a00\u7684\u7db2\u8def\u767e\u79d1\u5168\u66f8\u5354\u4f5c\u8a08"
        "\u756b",
    )
    print_qr(QRCode.encode_segments(segs, QRCode.ECC.MEDIUM, mask=0))  # Force mask 0
    print_qr(QRCode.encode_segments(segs, QRCode.ECC.MEDIUM, mask=1))  # Force mask 1
    print_qr(QRCode.encode_segments(segs, QRCode.ECC.MEDIUM, mask=5))  # Force mask 5
    print_qr(QRCode.encode_segments(segs, QRCode.ECC.MEDIUM, mask=7))  # Force mask 7


# ---- Utilities ----


def to_svg_str(qr: QRCode, border: int) -> str:
    r"""
    Returns a string of SVG code for an image depicting the given QR Code, with the given number
    of border modules. The string always uses Unix newlines (\n), regardless of the platform.
    """
    if border < 0:
        raise ValueError("Border must be non-negative")
    parts: list[str] = []
    for y in range(qr.get_size()):
        for x in range(qr.get_size()):
            if qr.get_module(x, y):
                parts.append(f"M{x+border},{y+border}h1v1h-1z")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 {qr.get_size()+border*2} {qr.get_size()+border*2}" stroke="none">
    <rect width="100%" height="100%" fill="#FFFFFF"/>
    <path d="{" ".join(parts)}" fill="#000000"/>
</svg>
"""


def print_qr(qrcode: QRCode) -> None:
    """Prints the given QRCode object to the console."""
    border = 4
    for y in range(-border, qrcode.get_size() + border):
        for x in range(-border, qrcode.get_size() + border):
            print("\u2588 "[1 if qrcode.get_module(x, y) else 0] * 2, end="")
        print()
    print()


# Run the main program
if __name__ == "__main__":
    main()
