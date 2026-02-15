#!/usr/bin/env python3
"""
qr-backup - takes a binary file, and outputs a paper backup.

A paper backup is a printable PDF full of QR codes.

## License

Copyright (c) 2025 Whinyaan

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the “Software”), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following
conditions:
- The above copyright notice and this permission notice shall be included in all copies
  or substantial portions of the Software.
- THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
  INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
  PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
  HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
  CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
  OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Attribution

The program is based on the following works:

### qr-backup

#### Modifications from Original Work

- Fixed linter errors (at strictest settings)
- Added type annotations throughout the codebase
- Renamed symbols

#### License

This project is based on qr-backup (https://github.com/za3k/qr-backup) by Zachary "za3k"
Vance, originally released under the Creative Commons License Zero CC0 1.0
<https://creativecommons.org/share-your-work/public-domain/cc0/>.

### QR Code Generator Library

#### Modifications from Original Work

- Fixed linter errors (at strictest settings)
- Added type annotations throughout the codebase
- Renamed symbols

#### License

MIT LICENSE

Original work Copyright (c) 2024-2025 Project Nayuki
  https://www.nayuki.io/page/qr-code-generator-library

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the “Software”), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following
conditions:
- The above copyright notice and this permission notice shall be included in all copies
  or substantial portions of the Software.
- THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
  INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
  PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
  HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
  CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
  OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

# ==================================================================================== #

from __future__ import annotations

import atexit
import base64
import collections
import copy
import datetime
import gzip
import hashlib
import io
import itertools
import logging
import math
import os
import os.path
import random
import re
import subprocess
import sys
import tarfile
import tempfile
import textwrap
from collections.abc import Callable, Sequence
from typing import Union

import PIL
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import PIL.ImageOps
import PIL.PdfParser
import qrcode
import reedsolo

# ==================================================================================== #

assert sys.version_info >= (
    3,
    6,
), "Python 3.6 is required. Submit a patch removing f-strings to fix it, sucka!"
VERSION = "0.1.0"

# ==================================================================================== #

# ---- QR Code symbol class ----


class QRCode:
    """
    A QR Code symbol, which is a type of two-dimension barcode.

    Invented by Denso Wave and described in the ISO/IEC 18004 standard. Instances of
    this class represent an immutable square grid of dark and light cells. The class
    provides static factory functions to create a QR Code from text or binary data. The
    class covers the QR Code Model 2 specification, supporting all versions (sizes) from
    1 to 40, all 4 error correction levels, and 4 character encoding modes.

    Ways to create a QR Code object:
    - High level: Take the payload data and call QrCode.encode_text() or
      QrCode.encode_binary().
    - Mid level: Custom-make the list of segments and call QrCode.encode_segments().
    - Low level: Custom-make the array of data codeword bytes (including
      segment headers and final padding, excluding error correction codewords),
      supply the appropriate version number, and call the QrCode() constructor.

    (Note that all ways require supplying the desired error correction level.)
    """

    # ---- Static factory functions (high level) ----

    @staticmethod
    def encode_text(text: str, ecl: QRCode.ECC) -> QRCode:
        """
        Returns a QR Code representing the given Unicode text string at the given error
        correction level.

        As a conservative upper bound, this function is guaranteed to succeed for strings that have 738 or fewer Unicode code points (not UTF-16 code units) if the low error correction level is used. The smallest possible QR Code version is automatically chosen for the output. The ECC level of the result may be higher than the `ecl` argument if it can be done without increasing the version.
        """
        segs: list[QRSegment] = QRSegment.make_segments(text)
        return QRCode.encode_segments(segs, ecl)

    @staticmethod
    def encode_binary(data: Union[bytes, Sequence[int]], ecl: QRCode.ECC) -> QRCode:
        """
        Returns a QR Code representing the given binary data at the given error correction level.

        This function always encodes using the binary segment mode, not any text mode. The maximum number of bytes allowed is 2953. The smallest possible QR Code version is automatically chosen for the output. The ECC level of the result may be higher than the ecl argument if it can be done without increasing the version.
        """
        return QRCode.encode_segments([QRSegment.make_bytes(data)], ecl)

    # ---- Static factory functions (mid level) ----

    @staticmethod
    def encode_segments(  # noqa: C901
        segs: Sequence[QRSegment],
        ecl: QRCode.ECC,
        minversion: int = 1,
        maxversion: int = 40,
        mask: int = -1,
        boostecl: bool = True,
    ) -> QRCode:
        """
        Returns a QR Code representing the given segments with the given encoding parameters.

        The smallest possible QR Code version within the given range is automatically chosen for the output. Iff boostecl is true, then the ECC level of the result may be higher than the ecl argument if it can be done without increasing the version. The mask number is either between 0 to 7 (inclusive) to force that mask, or -1 to automatically choose an appropriate mask (which may be slow). This function allows the user to create a custom sequence of segments that switches between modes (such as alphanumeric and byte) to encode text in less space. This is a mid-level API; the high-level API is encode_text() and encode_binary().
        """

        if not (
            QRCode.MIN_VERSION <= minversion <= maxversion <= QRCode.MAX_VERSION
        ) or not (-1 <= mask <= 7):
            raise ValueError("Invalid value")

        # Find the minimal version number to use
        for version in range(minversion, maxversion + 1):
            datacapacitybits: int = (
                QRCode._get_num_data_codewords(version, ecl) * 8
            )  # Number of data bits available
            datausedbits: int | None = QRSegment.get_total_bits(segs, version)
            if (datausedbits is not None) and (datausedbits <= datacapacitybits):
                break  # This version number is found to be suitable
            if (
                version >= maxversion
            ):  # All versions in the range could not fit the given data
                msg: str = "Segment too long"
                if datausedbits is not None:
                    msg = f"Data length = {datausedbits} bits, Max capacity = {datacapacitybits} bits"
                raise DataTooLongError(msg)
        assert datausedbits is not None

        # Increase the error correction level while the data still fits in the current version number
        for newecl in (
            QRCode.ECC.MEDIUM,
            QRCode.ECC.QUARTILE,
            QRCode.ECC.HIGH,
        ):  # From low to high
            if boostecl and (
                datausedbits <= QRCode._get_num_data_codewords(version, newecl) * 8
            ):
                ecl = newecl

        # Concatenate all segments to create the data bit string
        bb = _BitBuffer()
        for seg in segs:
            bb.append_bits(seg.get_mode().get_mode_bits(), 4)
            bb.append_bits(
                seg.get_num_chars(),
                seg.get_mode().num_char_count_bits(version),
            )
            bb.extend(seg._bitdata)
        assert len(bb) == datausedbits

        # Add terminator and pad up to a byte if applicable
        datacapacitybits = QRCode._get_num_data_codewords(version, ecl) * 8
        assert len(bb) <= datacapacitybits
        bb.append_bits(0, min(4, datacapacitybits - len(bb)))
        bb.append_bits(
            0,
            -len(bb) % 8,
        )  # Note: Python's modulo on negative numbers behaves better than C family languages
        assert len(bb) % 8 == 0

        # Pad with alternating bytes until data capacity is reached
        for padbyte in itertools.cycle((0xEC, 0x11)):
            if len(bb) >= datacapacitybits:
                break
            bb.append_bits(padbyte, 8)

        # Pack bits into bytes in big endian
        datacodewords = bytearray([0] * (len(bb) // 8))
        for i, bit in enumerate(bb):
            datacodewords[i >> 3] |= bit << (7 - (i & 7))

        # Create the QR Code object
        return QRCode(version, ecl, datacodewords, mask)

    # ---- Private fields ----

    # The version number of this QR Code, which is between 1 and 40 (inclusive).
    # This determines the size of this barcode.
    _version: int

    # The width and height of this QR Code, measured in modules, between
    # 21 and 177 (inclusive). This is equal to version * 4 + 17.
    _size: int

    # The error correction level used in this QR Code.
    _errcorlvl: QRCode.ECC

    # The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    # Even if a QR Code is created with automatic masking requested (mask = -1),
    # the resulting object still has a mask value between 0 and 7.
    _mask: int

    # The modules of this QR Code (False = light, True = dark).
    # Immutable after constructor finishes. Accessed through get_module().
    _modules: list[list[bool]]

    # Indicates function modules that are not subjected to masking. Discarded when constructor finishes.
    _isfunction: list[list[bool]]

    # ---- Constructor (low level) ----

    def __init__(  # noqa: C901
        self,
        version: int,
        errcorlvl: QRCode.ECC,
        datacodewords: Union[bytes, Sequence[int]],
        msk: int,
    ) -> None:
        """
        Creates a new QR Code with the given version number, error correction level, data codeword bytes, and mask number.

        This is a low-level API that most users should not use directly.
        A mid-level API is the encode_segments() function.
        """

        # Check scalar arguments and set fields
        if not (QRCode.MIN_VERSION <= version <= QRCode.MAX_VERSION):
            raise ValueError("Version value out of range")
        if not (-1 <= msk <= 7):
            raise ValueError("Mask value out of range")

        self._version = version
        self._size = version * 4 + 17
        self._errcorlvl = errcorlvl

        # Initialize both grids to be size*size arrays of Boolean false
        self._modules = [
            [False] * self._size for _ in range(self._size)
        ]  # Initially all light
        self._isfunction = [[False] * self._size for _ in range(self._size)]

        # Compute ECC, draw modules
        self._draw_function_patterns()
        allcodewords: bytes = self._add_ecc_and_interleave(bytearray(datacodewords))
        self._draw_codewords(allcodewords)

        # Do masking
        if msk == -1:  # Automatically choose best mask
            minpenalty: int = 1 << 32
            for i in range(8):
                self._apply_mask(i)
                self._draw_format_bits(i)
                penalty = self._get_penalty_score()
                if penalty < minpenalty:
                    msk = i
                    minpenalty = penalty
                self._apply_mask(i)  # Undoes the mask due to XOR
        assert 0 <= msk <= 7
        self._mask = msk
        self._apply_mask(msk)  # Apply the final choice of mask
        self._draw_format_bits(msk)  # Overwrite old format bits

        del self._isfunction

    # ---- Accessor methods ----

    def get_version(self) -> int:
        """Returns this QR Code's version number, in the range [1, 40]."""
        return self._version

    def get_size(self) -> int:
        """Returns this QR Code's size, in the range [21, 177]."""
        return self._size

    def get_error_correction_level(self) -> QRCode.ECC:
        """Returns this QR Code's error correction level."""
        return self._errcorlvl

    def get_mask(self) -> int:
        """Returns this QR Code's mask, in the range [0, 7]."""
        return self._mask

    def get_module(self, x: int, y: int) -> bool:
        """
        Returns the color of the module (pixel) at the given coordinates, which is False for light or True for dark.

        The top left corner has the coordinates (x=0, y=0).
        If the given coordinates are out of bounds, then False (light) is returned.
        """
        return (0 <= x < self._size) and (0 <= y < self._size) and self._modules[y][x]

    # ---- Private helper methods for constructor: Drawing function modules ----

    def _draw_function_patterns(self) -> None:
        """Reads this object's version field, and draws and marks all function modules."""
        # Draw horizontal and vertical timing patterns
        for i in range(self._size):
            self._set_function_module(6, i, i % 2 == 0)
            self._set_function_module(i, 6, i % 2 == 0)

        # Draw 3 finder patterns (all corners except bottom right; overwrites some timing modules)
        self._draw_finder_pattern(3, 3)
        self._draw_finder_pattern(self._size - 4, 3)
        self._draw_finder_pattern(3, self._size - 4)

        # Draw numerous alignment patterns
        alignpatpos: list[int] = self._get_alignment_pattern_positions()
        numalign: int = len(alignpatpos)
        skips: Sequence[tuple[int, int]] = (
            (0, 0),
            (0, numalign - 1),
            (numalign - 1, 0),
        )
        for i in range(numalign):
            for j in range(numalign):
                if (i, j) not in skips:  # Don't draw on the three finder corners
                    self._draw_alignment_pattern(alignpatpos[i], alignpatpos[j])

        # Draw configuration data
        self._draw_format_bits(
            0,
        )  # Dummy mask value; overwritten later in the constructor
        self._draw_version()

    def _draw_format_bits(self, mask: int) -> None:  # noqa: C901
        """Draws two copies of the format bits (with its own error correction code) based on the given mask and this object's error correction level field."""
        # Calculate error correction code and pack bits
        data: int = (
            self._errcorlvl.formatbits << 3 | mask
        )  # errCorrLvl is uint2, mask is uint3
        rem: int = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits: int = (data << 10 | rem) ^ 0x5412  # uint15
        assert bits >> 15 == 0

        # Draw first copy
        for i in range(6):
            self._set_function_module(8, i, _get_bit(bits, i))
        self._set_function_module(8, 7, _get_bit(bits, 6))
        self._set_function_module(8, 8, _get_bit(bits, 7))
        self._set_function_module(7, 8, _get_bit(bits, 8))
        for i in range(9, 15):
            self._set_function_module(14 - i, 8, _get_bit(bits, i))

        # Draw second copy
        for i in range(8):
            self._set_function_module(self._size - 1 - i, 8, _get_bit(bits, i))
        for i in range(8, 15):
            self._set_function_module(8, self._size - 15 + i, _get_bit(bits, i))
        self._set_function_module(8, self._size - 8, True)  # Always dark

    def _draw_version(self) -> None:
        """Draws two copies of the version bits (with its own error correction code), based on this object's version field, iff 7 <= version <= 40."""
        if self._version < 7:
            return

        # Calculate error correction code and pack bits
        rem: int = self._version  # version is uint6, in the range [7, 40]
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits: int = self._version << 12 | rem  # uint18
        assert bits >> 18 == 0

        # Draw two copies
        for i in range(18):
            bit: bool = _get_bit(bits, i)
            a: int = self._size - 11 + i % 3
            b: int = i // 3
            self._set_function_module(a, b, bit)
            self._set_function_module(b, a, bit)

    def _draw_finder_pattern(self, x: int, y: int) -> None:
        """Draws a 9*9 finder pattern including the border separator, with the center module at (x, y). Modules can be out of bounds."""
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = x + dx, y + dy
                if (0 <= xx < self._size) and (0 <= yy < self._size):
                    # Chebyshev/infinity norm
                    self._set_function_module(
                        xx,
                        yy,
                        max(abs(dx), abs(dy)) not in (2, 4),
                    )

    def _draw_alignment_pattern(self, x: int, y: int) -> None:
        """Draws a 5*5 alignment pattern, with the center module at (x, y). All modules must be in bounds."""
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self._set_function_module(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)

    def _set_function_module(self, x: int, y: int, isdark: bool) -> None:
        """Sets the color of a module and marks it as a function module. Only used by the constructor. Coordinates must be in bounds."""
        assert type(isdark) is bool
        self._modules[y][x] = isdark
        self._isfunction[y][x] = True

    # ---- Private helper methods for constructor: Codewords and masking ----

    def _add_ecc_and_interleave(self, data: bytearray) -> bytes:  # noqa: C901
        """Returns a new byte string representing the given data with the appropriate error correction codewords appended to it, based on this object's version and error correction level."""
        version: int = self._version
        assert len(data) == QRCode._get_num_data_codewords(version, self._errcorlvl)

        # Calculate parameter numbers
        numblocks: int = QRCode._NUM_ERROR_CORRECTION_BLOCKS[self._errcorlvl.ordinal][
            version
        ]
        block_ecc_len: int = QRCode._ECC_CODEWORDS_PER_BLOCK[self._errcorlvl.ordinal][
            version
        ]
        rawcodewords: int = QRCode._get_num_raw_data_modules(version) // 8
        numshortblocks: int = numblocks - rawcodewords % numblocks
        shortblocklen: int = rawcodewords // numblocks

        # Split data into blocks and append ECC to each block
        blocks: list[bytes] = []
        rsdiv: bytes = QRCode._reed_solomon_compute_divisor(block_ecc_len)
        k: int = 0
        for i in range(numblocks):
            dat: bytearray = data[
                k : k + shortblocklen - block_ecc_len + (0 if i < numshortblocks else 1)
            ]
            k += len(dat)
            ecc: bytes = QRCode._reed_solomon_compute_remainder(dat, rsdiv)
            if i < numshortblocks:
                dat.append(0)
            blocks.append(dat + ecc)
        assert k == len(data)

        # Interleave (not concatenate) the bytes from every block into a single sequence
        result = bytearray()
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                # Skip the padding byte in short blocks
                if (i != shortblocklen - block_ecc_len) or (j >= numshortblocks):
                    result.append(blk[i])
        assert len(result) == rawcodewords
        return result

    def _draw_codewords(self, data: bytes) -> None:  # noqa: C901
        """Draws the given sequence of 8-bit codewords (data and error correction) onto the entire data area of this QR Code. Function modules need to be marked off before this is called."""
        assert len(data) == QRCode._get_num_raw_data_modules(self._version) // 8

        i: int = 0  # Bit index into the data
        # Do the funny zigzag scan
        for right in range(
            self._size - 1,
            0,
            -2,
        ):  # Index of right column in each column pair
            if right <= 6:
                right -= 1
            for vert in range(self._size):  # Vertical counter
                for j in range(2):
                    x: int = right - j  # Actual x coordinate
                    upward: bool = (right + 1) & 2 == 0
                    y: int = (
                        (self._size - 1 - vert) if upward else vert
                    )  # Actual y coordinate
                    if (not self._isfunction[y][x]) and (i < len(data) * 8):
                        self._modules[y][x] = _get_bit(data[i >> 3], 7 - (i & 7))
                        i += 1
                    # If this QR Code has any remainder bits (0 to 7), they were assigned as
                    # 0/false/light by the constructor and are left unchanged by this method
        assert i == len(data) * 8

    def _apply_mask(self, mask: int) -> None:
        """
        XORs the codeword modules in this QR Code with the given mask pattern.

        The function modules must be marked and the codeword bits must be drawn before masking. Due to the arithmetic of XOR, calling _apply_mask() with the same mask value a second time will undo the mask. A final well-formed QR Code needs exactly one (not zero, two, etc.) mask applied.
        """
        if not (0 <= mask <= 7):
            raise ValueError("Mask value out of range")
        masker: Callable[[int, int], int] = QRCode._MASK_PATTERNS[mask]
        for y in range(self._size):
            for x in range(self._size):
                self._modules[y][x] ^= (masker(x, y) == 0) and (
                    not self._isfunction[y][x]
                )

    def _get_penalty_score(self) -> int:  # noqa: C901
        """Calculates and returns the penalty score based on state of this QR Code's current modules. This is used by the automatic mask choice algorithm to find the mask pattern that yields the lowest score."""
        result: int = 0
        size: int = self._size
        modules: list[list[bool]] = self._modules

        # Adjacent modules in row having same color, and finder-like patterns
        for y in range(size):
            runcolor: bool = False
            runx: int = 0
            runhistory = collections.deque([0] * 7, 7)
            for x in range(size):
                if modules[y][x] == runcolor:
                    runx += 1
                    if runx == 5:
                        result += QRCode._PENALTY_N1
                    elif runx > 5:
                        result += 1
                else:
                    self._finder_penalty_add_history(runx, runhistory)
                    if not runcolor:
                        result += (
                            self._finder_penalty_count_patterns(runhistory)
                            * QRCode._PENALTY_N3
                        )
                    runcolor = modules[y][x]
                    runx = 1
            result += (
                self._finder_penalty_terminate_and_count(runcolor, runx, runhistory)
                * QRCode._PENALTY_N3
            )
        # Adjacent modules in column having same color, and finder-like patterns
        for x in range(size):
            runcolor = False
            runy: int = 0
            runhistory = collections.deque([0] * 7, 7)
            for y in range(size):
                if modules[y][x] == runcolor:
                    runy += 1
                    if runy == 5:
                        result += QRCode._PENALTY_N1
                    elif runy > 5:
                        result += 1
                else:
                    self._finder_penalty_add_history(runy, runhistory)
                    if not runcolor:
                        result += (
                            self._finder_penalty_count_patterns(runhistory)
                            * QRCode._PENALTY_N3
                        )
                    runcolor = modules[y][x]
                    runy = 1
            result += (
                self._finder_penalty_terminate_and_count(runcolor, runy, runhistory)
                * QRCode._PENALTY_N3
            )

        # 2*2 blocks of modules having same color
        for y in range(size - 1):
            for x in range(size - 1):
                if (
                    modules[y][x]
                    == modules[y][x + 1]
                    == modules[y + 1][x]
                    == modules[y + 1][x + 1]
                ):
                    result += QRCode._PENALTY_N2

        # Balance of dark and light modules
        dark: int = sum((1 if cell else 0) for row in modules for cell in row)
        total: int = size**2  # Note that size is odd, so dark/total != 1/2
        # Compute the smallest integer k >= 0 such that (45-5k)% <= dark/total <= (55+5k)%
        k: int = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        assert 0 <= k <= 9
        result += k * QRCode._PENALTY_N4
        assert (
            0 <= result <= 2568888
        )  # Non-tight upper bound based on default values of PENALTY_N1, ..., N4
        return result

    # ---- Private helper functions ----

    def _get_alignment_pattern_positions(self) -> list[int]:
        """Returns an ascending list of positions of alignment patterns for this version number. Each position is in the range [0,177), and are used on both the x and y axes. This could be implemented as lookup table of 40 variable-length lists of integers."""
        if self._version == 1:
            return []
        numalign: int = self._version // 7 + 2
        step: int = (self._version * 8 + numalign * 3 + 5) // (numalign * 4 - 4) * 2
        result: list[int] = [
            (self._size - 7 - i * step) for i in range(numalign - 1)
        ] + [6]
        return list(reversed(result))

    @staticmethod
    def _get_num_raw_data_modules(ver: int) -> int:
        """Returns the number of data bits that can be stored in a QR Code of the given version number, after all function modules are excluded. This includes remainder bits, so it might not be a multiple of 8. The result is in the range [208, 29648]. This could be implemented as a 40-entry lookup table."""
        if not (QRCode.MIN_VERSION <= ver <= QRCode.MAX_VERSION):
            raise ValueError("Version number out of range")
        result: int = (16 * ver + 128) * ver + 64
        if ver >= 2:
            numalign: int = ver // 7 + 2
            result -= (25 * numalign - 10) * numalign - 55
            if ver >= 7:
                result -= 36
        assert 208 <= result <= 29648
        return result

    @staticmethod
    def _get_num_data_codewords(ver: int, ecl: QRCode.ECC) -> int:
        """Returns the number of 8-bit data (i.e. not error correction) codewords contained in any QR Code of the given version number and error correction level, with remainder bits discarded. This stateless pure function could be implemented as a (40*4)-cell lookup table."""
        return (
            QRCode._get_num_raw_data_modules(ver) // 8
            - QRCode._ECC_CODEWORDS_PER_BLOCK[ecl.ordinal][ver]
            * QRCode._NUM_ERROR_CORRECTION_BLOCKS[ecl.ordinal][ver]
        )

    @staticmethod
    def _reed_solomon_compute_divisor(degree: int) -> bytes:
        """Returns a Reed-Solomon ECC generator polynomial for the given degree. This could be implemented as a lookup table over all possible parameter values, instead of as an algorithm."""
        if not (1 <= degree <= 255):
            raise ValueError("Degree out of range")
        # Polynomial coefficients are stored from highest to lowest power, excluding the leading term which is always 1.
        # For example the polynomial x^3 + 255x^2 + 8x + 93 is stored as the uint8 array [255, 8, 93].
        result = bytearray([0] * (degree - 1) + [1])  # Start off with the monomial x^0

        # Compute the product polynomial (x - r^0) * (x - r^1) * (x - r^2) * ... * (x - r^{degree-1}),
        # and drop the highest monomial term which is always 1x^degree.
        # Note that r = 0x02, which is a generator element of this field GF(2^8/0x11D).
        root: int = 1
        for _ in range(degree):  # Unused variable i
            # Multiply the current product by (x - r^i)
            for j in range(degree):
                result[j] = QRCode._reed_solomon_multiply(result[j], root)
                if j + 1 < degree:
                    result[j] ^= result[j + 1]
            root = QRCode._reed_solomon_multiply(root, 0x02)
        return result

    @staticmethod
    def _reed_solomon_compute_remainder(data: bytes, divisor: bytes) -> bytes:
        """Returns the Reed-Solomon error correction codeword for the given data and divisor polynomials."""
        result = bytearray([0] * len(divisor))
        for b in data:  # Polynomial division
            factor: int = b ^ result.pop(0)
            result.append(0)
            for i, coef in enumerate(divisor):
                result[i] ^= QRCode._reed_solomon_multiply(coef, factor)
        return result

    @staticmethod
    def _reed_solomon_multiply(x: int, y: int) -> int:
        """Returns the product of the two given field elements modulo GF(2^8/0x11D). The arguments and result are unsigned 8-bit integers. This could be implemented as a lookup table of 256*256 entries of uint8."""
        if (x >> 8 != 0) or (y >> 8 != 0):
            raise ValueError("Byte out of range")
        # Russian peasant multiplication
        z: int = 0
        for i in reversed(range(8)):
            z = (z << 1) ^ ((z >> 7) * 0x11D)
            z ^= ((y >> i) & 1) * x
        assert z >> 8 == 0
        return z

    def _finder_penalty_count_patterns(self, runhistory: collections.deque[int]) -> int:
        """Can only be called immediately after a light run is added, and returns either 0, 1, or 2. A helper function for _get_penalty_score()."""
        n: int = runhistory[1]
        assert n <= self._size * 3
        core: bool = (
            n > 0
            and (runhistory[2] == runhistory[4] == runhistory[5] == n)
            and runhistory[3] == n * 3
        )
        return (
            1 if (core and runhistory[0] >= n * 4 and runhistory[6] >= n) else 0
        ) + (1 if (core and runhistory[6] >= n * 4 and runhistory[0] >= n) else 0)

    def _finder_penalty_terminate_and_count(
        self,
        currentruncolor: bool,
        currentrunlength: int,
        runhistory: collections.deque[int],
    ) -> int:
        """Must be called at the end of a line (row or column) of modules. A helper function for _get_penalty_score()."""
        if currentruncolor:  # Terminate dark run
            self._finder_penalty_add_history(currentrunlength, runhistory)
            currentrunlength = 0
        currentrunlength += self._size  # Add light border to final run
        self._finder_penalty_add_history(currentrunlength, runhistory)
        return self._finder_penalty_count_patterns(runhistory)

    def _finder_penalty_add_history(
        self,
        currentrunlength: int,
        runhistory: collections.deque[int],
    ) -> None:
        if runhistory[0] == 0:
            currentrunlength += self._size  # Add light border to initial run
        runhistory.appendleft(currentrunlength)

    # ---- Constants and tables ----

    MIN_VERSION: int = (
        1  # The minimum version number supported in the QR Code Model 2 standard
    )
    MAX_VERSION: int = (
        40  # The maximum version number supported in the QR Code Model 2 standard
    )

    # For use in _get_penalty_score(), when evaluating which mask is best.
    _PENALTY_N1: int = 3
    _PENALTY_N2: int = 3
    _PENALTY_N3: int = 40
    _PENALTY_N4: int = 10

    # pylint: disable=all
    # fmt: off

    _ECC_CODEWORDS_PER_BLOCK: Sequence[Sequence[int]] = ( # type: ignore[syntax]
        # Note that index 0 is for padding, and is set to an illegal value

        # Error correction level:
        #    0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13,
        #   14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
        #   28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40

        # Versions:
        ( # Low
            -1,  7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26,
            30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30,
            30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30,
        ),  
        ( # Medium
            -1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22,
            24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28,
            28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28,
        ),  
        ( # Quartile
            -1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24,
            20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30,
            30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30,
        ),
        ( # High
            -1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22,
            24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30,
            30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30,
        ),
    )

    _NUM_ERROR_CORRECTION_BLOCKS: Sequence[Sequence[int]] = ( # type: ignore[syntax]
        # Note that index 0 is for padding, and is set to an illegal value

        # Error correction level:
        #    0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13,
        #   14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
        #   28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40
        
        # Versions:
        ( # Low
            -1,  1,  1,  1,  1,  1,  2,  2,  2,  2,  4,  4,  4,  4,
             4,  6,  6,  6,  6,  7,  8,  8,  9,  9, 10, 12, 12, 12,
            13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25,
        ),
        ( # Medium
            -1,  1,  1,  1,  2,  2,  4,  4,  4,  5,  5,  5,  8,  9,
             9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25,
            26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49,
        ),
        ( # Quartile
            -1,  1,  1,  2,  2,  4,  4,  6,  6,  8,  8,  8, 10, 12,
            16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34,
            35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68,
        ),
        ( # High
            -1,  1,  1,  2,  4,  4,  4,  5,  6,  8,  8, 11, 11, 16,
            16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40,
            42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81,
        ),
    )
    
    _MASK_PATTERNS: Sequence[Callable[[int,int],int]] = ( # type: ignore[syntax]
        (lambda x, y:  (x + y) % 2                  ),
        (lambda x, y:  y % 2                        ),
        (lambda x, y:  x % 3                        ),
        (lambda x, y:  (x + y) % 3                  ),
        (lambda x, y:  (x // 3 + y // 2) % 2        ),
        (lambda x, y:  x * y % 2 + x * y % 3        ),
        (lambda x, y:  (x * y % 2 + x * y % 3) % 2  ),
        (lambda x, y:  ((x + y) % 2 + x * y % 3) % 2),
    )

    # fmt: on
    # pylint: enable=all

    # ---- Public helper enumeration ----

    class ECC:
        ordinal: int  # (Public) In the range 0 to 3 (unsigned 2-bit integer)
        formatbits: (
            int  # (Package-private) In the range 0 to 3 (unsigned 2-bit integer)
        )

        """The error correction level in a QR Code symbol. Immutable."""

        # Private constructor
        def __init__(self, i: int, fb: int) -> None:
            self.ordinal = i
            self.formatbits = fb

        # Placeholders
        LOW: QRCode.ECC
        MEDIUM: QRCode.ECC
        QUARTILE: QRCode.ECC
        HIGH: QRCode.ECC

    # Public constants. Create them outside the class.
    ECC.LOW = ECC(0, 1)  # The QR Code can tolerate about  7% erroneous codewords
    ECC.MEDIUM = ECC(1, 0)  # The QR Code can tolerate about 15% erroneous codewords
    ECC.QUARTILE = ECC(2, 3)  # The QR Code can tolerate about 25% erroneous codewords
    ECC.HIGH = ECC(3, 2)  # The QR Code can tolerate about 30% erroneous codewords


# ---- Data segment class ----
class QRSegment:
    """
    A segment of character/binary/control data in a QR Code symbol.

    Instances of this class are immutable. The mid-level way to create a segment is to take the payload data and call a static factory function such as QrSegment.make_numeric(). The low-level way to create a segment is to custom-make the bit buffer and call the QrSegment() constructor with appropriate values. This segment class imposes no length restrictions, but QR Codes have restrictions. Even in the most favorable conditions, a QR Code can only hold 7089 characters of data. Any segment longer than this is meaningless for the purpose of generating QR Codes.
    """

    # ---- Static factory functions (mid level) ----

    @staticmethod
    def make_bytes(data: Union[bytes, Sequence[int]]) -> QRSegment:
        """Returns a segment representing the given binary data encoded in byte mode. All input byte lists are acceptable. Any text string can be converted to UTF-8 bytes (s.encode("UTF-8")) and encoded as a byte mode segment."""
        bb = _BitBuffer()
        for b in data:
            bb.append_bits(b, 8)
        return QRSegment(QRSegment.Mode.BYTE, len(data), bb)

    @staticmethod
    def make_numeric(digits: str) -> QRSegment:
        """Returns a segment representing the given string of decimal digits encoded in numeric mode."""
        if not QRSegment.is_numeric(digits):
            raise ValueError("String contains non-numeric characters")
        bb = _BitBuffer()
        i: int = 0
        while i < len(digits):  # Consume up to 3 digits per iteration
            n: int = min(len(digits) - i, 3)
            bb.append_bits(int(digits[i : i + n]), n * 3 + 1)
            i += n
        return QRSegment(QRSegment.Mode.NUMERIC, len(digits), bb)

    @staticmethod
    def make_alphanumeric(text: str) -> QRSegment:
        """Returns a segment representing the given text string encoded in alphanumeric mode. The characters allowed are: 0 to 9, A to Z (uppercase only), space, dollar, percent, asterisk, plus, hyphen, period, slash, colon."""
        if not QRSegment.is_alphanumeric(text):
            raise ValueError(
                "String contains unencodable characters in alphanumeric mode",
            )
        bb = _BitBuffer()
        for i in range(0, len(text) - 1, 2):  # Process groups of 2
            temp: int = QRSegment._ALPHANUMERIC_ENCODING_TABLE[text[i]] * 45
            temp += QRSegment._ALPHANUMERIC_ENCODING_TABLE[text[i + 1]]
            bb.append_bits(temp, 11)
        if len(text) % 2 > 0:  # 1 character remaining
            bb.append_bits(QRSegment._ALPHANUMERIC_ENCODING_TABLE[text[-1]], 6)
        return QRSegment(QRSegment.Mode.ALPHANUMERIC, len(text), bb)

    @staticmethod
    def make_segments(text: str) -> list[QRSegment]:
        """Returns a new mutable list of zero or more segments to represent the given Unicode text string. The result may use various segment modes and switch modes to optimize the length of the bit stream."""

        # Select the most efficient segment encoding automatically
        if text == "":
            return []
        if QRSegment.is_numeric(text):
            return [QRSegment.make_numeric(text)]
        if QRSegment.is_alphanumeric(text):
            return [QRSegment.make_alphanumeric(text)]
        return [QRSegment.make_bytes(text.encode("UTF-8"))]

    @staticmethod
    def make_eci(assignval: int) -> QRSegment:
        """Returns a segment representing an Extended Channel Interpretation (ECI) designator with the given assignment value."""
        bb = _BitBuffer()
        if assignval < 0:
            raise ValueError("ECI assignment value out of range")
        if assignval < (1 << 7):
            bb.append_bits(assignval, 8)
        elif assignval < (1 << 14):
            bb.append_bits(0b10, 2)
            bb.append_bits(assignval, 14)
        elif assignval < 1000000:
            bb.append_bits(0b110, 3)
            bb.append_bits(assignval, 21)
        else:
            raise ValueError("ECI assignment value out of range")
        return QRSegment(QRSegment.Mode.ECI, 0, bb)

    # Tests whether the given string can be encoded as a segment in numeric mode.
    # A string is encodable iff each character is in the range 0 to 9.
    @staticmethod
    def is_numeric(text: str) -> bool:
        return QRSegment._NUMERIC_REGEX.fullmatch(text) is not None

    # Tests whether the given string can be encoded as a segment in alphanumeric mode.
    # A string is encodable iff each character is in the following set: 0 to 9, A to Z
    # (uppercase only), space, dollar, percent, asterisk, plus, hyphen, period, slash, colon.
    @staticmethod
    def is_alphanumeric(text: str) -> bool:
        return QRSegment._ALPHANUMERIC_REGEX.fullmatch(text) is not None

    # ---- Private fields ----

    # The mode indicator of this segment. Accessed through get_mode().
    _mode: QRSegment.Mode

    # The length of this segment's unencoded data. Measured in characters for
    # numeric/alphanumeric/kanji mode, bytes for byte mode, and 0 for ECI mode.
    # Always zero or positive. Not the same as the data's bit length.
    # Accessed through get_num_chars().
    _numchars: int

    # The data bits of this segment. Accessed through get_data().
    _bitdata: list[int]

    # ---- Constructor (low level) ----

    def __init__(
        self,
        mode: QRSegment.Mode,
        numch: int,
        bitdata: Sequence[int],
    ) -> None:
        """Creates a new QR Code segment with the given attributes and data. The character count (numch) must agree with the mode and the bit buffer length, but the constraint isn't checked. The given bit buffer is cloned and stored."""
        if numch < 0:
            raise ValueError
        self._mode = mode
        self._numchars = numch
        self._bitdata = list(bitdata)  # Make defensive copy

    # ---- Accessor methods ----

    def get_mode(self) -> QRSegment.Mode:
        """Returns the mode field of this segment."""
        return self._mode

    def get_num_chars(self) -> int:
        """Returns the character count field of this segment."""
        return self._numchars

    def get_data(self) -> list[int]:
        """Returns a new copy of the data bits of this segment."""
        return list(self._bitdata)  # Make defensive copy

    # Package-private function
    @staticmethod
    def get_total_bits(segs: Sequence[QRSegment], version: int) -> int | None:
        """Calculates the number of bits needed to encode the given segments at the given version. Returns a non-negative number if successful. Otherwise returns None if a segment has too many characters to fit its length field."""
        result = 0
        for seg in segs:
            ccbits: int = seg.get_mode().num_char_count_bits(version)
            if seg.get_num_chars() >= (1 << ccbits):
                return None  # The segment's length doesn't fit the field's bit width
            result += 4 + ccbits + len(seg._bitdata)
        return result

    # ---- Constants ----

    # Describes precisely all strings that are encodable in numeric mode.
    _NUMERIC_REGEX: re.Pattern[str] = re.compile(r"[0-9]*")

    # Describes precisely all strings that are encodable in alphanumeric mode.
    _ALPHANUMERIC_REGEX: re.Pattern[str] = re.compile(r"[A-Z0-9 $%*+./:-]*")

    # Dictionary of "0"->0, "A"->10, "$"->37, etc.
    _ALPHANUMERIC_ENCODING_TABLE: dict[str, int] = {  # noqa: RUF012
        ch: i for (i, ch) in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:")
    }

    # ---- Public helper enumeration ----

    class Mode:
        """Describes how a segment's data bits are interpreted. Immutable."""

        _modebits: (
            int  # The mode indicator bits, which is a uint4 value (range 0 to 15)
        )
        _charcounts: tuple[
            int,
            int,
            int,
        ]  # Number of character count bits for three different version ranges

        # Private constructor
        def __init__(self, modebits: int, charcounts: tuple[int, int, int]) -> None:
            self._modebits = modebits
            self._charcounts = charcounts

        # Package-private method
        def get_mode_bits(self) -> int:
            """Returns an unsigned 4-bit integer value (range 0 to 15) representing the mode indicator bits for this mode object."""
            return self._modebits

        # Package-private method
        def num_char_count_bits(self, ver: int) -> int:
            """Returns the bit width of the character count field for a segment in this mode in a QR Code at the given version number. The result is in the range [0, 16]."""
            return self._charcounts[(ver + 7) // 17]

        # Placeholders
        NUMERIC: QRSegment.Mode
        ALPHANUMERIC: QRSegment.Mode
        BYTE: QRSegment.Mode
        KANJI: QRSegment.Mode
        ECI: QRSegment.Mode

    # Public constants. Create them outside the class.
    Mode.NUMERIC = Mode(0x1, (10, 12, 14))
    Mode.ALPHANUMERIC = Mode(0x2, (9, 11, 13))
    Mode.BYTE = Mode(0x4, (8, 16, 16))
    Mode.KANJI = Mode(0x8, (8, 10, 12))
    Mode.ECI = Mode(0x7, (0, 0, 0))


# ---- Private helper class ----


class _BitBuffer(list[int]):
    """An appendable sequence of bits (0s and 1s). Mainly used by QrSegment."""

    def append_bits(self, val: int, n: int) -> None:
        """
        Appends the given number of low-order bits of the given value to this buffer.
        Requires n >= 0 and 0 <= val < 2^n.
        """
        if (n < 0) or (val >> n != 0):
            raise ValueError("Value out of range")
        self.extend(((val >> i) & 1) for i in reversed(range(n)))


def _get_bit(x: int, i: int) -> bool:
    """Returns true iff the i'th bit of x is set to 1."""
    return (x >> i) & 1 != 0


class DataTooLongError(ValueError):
    """
    Raised when the supplied data does not fit any QR Code version.

    Ways to handle this exception include:
    - Decrease the error correction level if it was greater than ECC.LOW.
    - If the encode_segments() function was called with a maxversion argument, then increase
      it if it was less than QrCode.MAX_VERSION. (This advice does not apply to the other
      factory functions because they search all versions up to QrCode.MAX_VERSION.)
    - Split the text data into better or optimal segments in order to reduce the number of bits required.
    - Change the text or binary data to be shorter.
    - Change the text to fit the character set of a particular segment mode (e.g. alphanumeric).
    - Propagate the error upward to the caller/user.
    """


# ==================================================================================== #

# Option(s), Default, Description
BACKUP_OPTIONS = [
    (
        ("--compress", "--no-compress"),
        "compressed",
        "This gives a more compact backup, but partial recovery is impossible.",
    ),
    (("--dpi DPI",), "300", "Sets the print resolution of your printer."),
    (
        ("--encrypt generate", "--encrypt PASSPHRASE"),
        "disabled",
        "Password-protect the backup. If the passphrase is 'generate', a passphrase is automatically generated for you, which you would need to store securely or you will be unable to unlock the data.",
    ),
    (
        ("--encrypt-print-passphrase", "--no-encrypt-print-passphrase"),
        "print if generated by qr-code, don't print if passed in",
        "Print the passphrase on a sheet by itself.",
    ),
    (
        ("--erasure-coding", "--no-erasure-coding"),
        "enabled",
        "This allows restoring if some QR codes are lost. Restore with lost codes is only possible using qr-backup.",
    ),
    (
        ("--error-correction CORRECTION",),
        "M (15%)",
        "Sets the error correction level. Options are L (7%), M (15%), Q (25%), and H (30%).",
    ),
    (
        ("--filename FILENAME",),
        "same as FILE",
        "Set the restored filename. Max 32 chars.",
    ),
    (
        ("--instructions page|cover|both|none",),
        "page",
        "Sets how frequently the instructions are printed. If 'cover' or 'both' is selected, more verbose instructions will be printed on the cover page.",
    ),
    (
        ("--note TEXT",),
        "no note",
        "Add a special note to the printout instructions. Can be anything.",
    ),
    (
        ("--num-copies NUMBER",),
        "1",
        "Print multiple copies of each QR code for redundancy.",
    ),
    (
        ("--output FILENAME", "-o FILENAME"),
        "FILE.qr.pdf",
        "Set the output pdf path (redirecting stdout also works).",
    ),
    (
        ("--page WIDTH_POINTS HEIGHT_POINTS",),
        "500px x 600px",
        "Sets the usable size of the paper on your printer. This should NOT be 8.5 x 11 -- make sure to include margins.",
    ),
    (
        ("--qr-version VERSION",),
        "10",
        "Uses QR codes, version VERSION. Versions range from 1-40. The bigger the version, the harder to scan but the more data per code.",
    ),
    (
        ("--scale SCALE",),
        "5px",
        "Scale QR codes so that each small square in the QR code is SCALE x SCALE pixels.",
    ),
    (
        ("--shuffle", "--no-shuffle"),
        "yes if erasure coding is enabled (default), no otherwise",
        "Spread QR codes across pages. This can help prevent data loss.",
    ),
    (
        ("--skip-checks", "--no-skip-checks"),
        "not skipped",
        "Skip erasure code checks, self-restore checks.",
    ),
]
RESTORE_OPTIONS = [
    (
        ("--code-count-erasure COUNT",),
        "automatic",
        "Specify the number of erasure QR codes.",
    ),
    (
        ("--code-count-normal COUNT",),
        "automatic",
        "Specify the number of normal QR codes.",
    ),
    (("--compress", "--no-compress"), "automatic", "Force decompression (on/off)."),
    (
        ("--display", "--no-display"),
        "display",
        "For webcam scanning, (display/don't display) a webcam preview.",
    ),
    (
        ("--encrypt PASSPHRASE", "--no-encrypt"),
        "automatic",
        "Force decryption (on/off) and give the passphrase if decrypting.",
    ),
    (("--image-restore",), "automatic", "Force image-based (scanner) restore."),
    (("--output FILENAME", "-o FILENAME"), "stdout", "Set the restore file path."),
    (
        ("--sha256 SHA256",),
        "no check, prints checksum to stderr",
        "Include a sha256sum to check the file. Giving the initial part of the sha256sum does a partial check.",
    ),
    (("--webcam-restore",), "automatic", "Force webcam-based restore."),
]
BOTH_OPTIONS = [
    (("--help", "-h"), None, "Print a help message."),
    (("--verbose", "-v"), None, "Print more detailed information during run."),
    (("--version", "-V"), None, "Print the verison and immediately exit."),
]

HELP = """Usage: qr-backup [OPTIONS] FILE [FILE...]
       qr-backup --restore [OPTIONS]
       qr-backup --restore [OPTIONS] IMAGE [IMAGE ...]
Convert a binary file to a paper .pdf backup of QR codes. With '--restore', read the QR codes in the paper backup using a webcam or scanner, to re-create the original file.

Restore directions are included in the PDF, and do not require qr-backup. Make sure to test that you can actually read the QR size you select.

Options:
{both_options}

Backup options:
{backup_options}

Restore options:
{restore_options}"""

MAN_MD = """% QR-BACKUP(1) qr-backup {VERSION}
% Zachary Vance
% {MAN_MONTH}

# NAME
qr-backup - back up file(s) to a series of QR codes on paper

# SYNOPSIS
**qr-backup** [*OPTIONS*] *FILE* [*FILE*...]\\
**qr-backup** --restore [*OPTIONS*]\\
**qr-backup** --restore [*OPTIONS*] *IMAGE* [*IMAGE*...]

# DESCRIPTION
**qr-backup** converts a binary file to a backup suitable for printing.
The backup is a .pdf file containing several barcodes.

**qr-backup --restore** restores a paper backup and outputs the original file.
Restore is done using a webcam or scanner.

Restore is possible without **qr-backup**. Restore directions are included in the
paper backup.

# OPTIONS
{both_options}

# BACKUP OPTIONS
{backup_options}

# RESTORE OPTIONS
{restore_options}

# EXIT VALUES
**0**
: Success. This includes certain self-test failures which sometimes fail by chance.

**1**
: Invalid command line option

**2**
: File missing or access failed

**3**
: Self-test restore failed

**4**
: Restore failed

**5**
: **convert** subcommand failed

**6**
: **zbarimg** or **zbarcam** subcommand failed

**7**
: **gpg** subcommand failed

# BUGS
Please report any bugs at https://github.com/za3k/qr-backup/issues .

Sometimes scanned images, including the original PDF, cannot be read successfully and
the restore self-check fails. This appears to be a bug in **zbar**.

On Debian, Ubuntu and certain other systems, the default system imagemagick policy
prevents reading or writing PDFs. Since **qr-backup** depends on both, it will fail.
**qr-backup** does its best to report this problem clearly.

It is possible to print barcodes so large or small your webcam or scanner cannot read
them. Make sure to test your restore process when using non-default settings.

# COPYRIGHT
**qr-backup** was written by Zachary Vance, and is released into the public domain and
under CC0 <https://creativecommons.org/share-your-work/public-domain/cc0/>. The
generated PDF includes the DejaVu Sans Mono font, which has a separate license
<https://dejavu-fonts.github.io/License.html>.

The **qr-backup** source code is available at <https://github.com/za3k/qr-backup>.
"""


def underline_man_part(p):
    overrides = {"page|cover|both|none": "page|cover|both|none"}
    return overrides.get(p, "*{}*".format(p))


def man_options(options):
    parts = []
    for args, default, description in options:
        args2 = []
        for arg in args:
            arg_parts = arg.split()
            args2.append(
                " ".join(
                    [arg_parts[0]] + [underline_man_part(p) for p in arg_parts[1:]],
                ),
            )
        arg_line = "{}\n".format(", ".join("**{}**".format(arg) for arg in args2))
        if default is None:
            rest_line = ": {}".format(description)
        else:
            rest_line = ": {} Default: {}".format(description, default)
        parts.append(arg_line + rest_line)
    return "\n\n".join(parts)


def cli_options(options):
    parts = []
    for args, default, description in options:
        arg_line = "    {}\n".format(", ".join(args))
        desc_line = "        {}\n".format(description)
        if default is None:
            default_line = ""
        else:
            default_line = "        Default: {}\n".format(default)
        parts.append(arg_line + desc_line + default_line)
    return "".join(parts)


HELP = HELP.format(
    backup_options=cli_options(BACKUP_OPTIONS),
    restore_options=cli_options(RESTORE_OPTIONS),
    both_options=cli_options(BOTH_OPTIONS),
)


def wrap_keeping_indent(text, width):
    lines = []
    for line in text.split("\n"):
        if line.strip() == "":
            lines.append("")
            continue
        orig_line = line
        new_line = line.lstrip(" ")
        indent = " " * (len(orig_line) - len(new_line))
        wrapped_lines = textwrap.wrap(
            new_line,
            initial_indent=indent,
            subsequent_indent=indent,
            width=width,
            replace_whitespace=False,
        )
        lines.extend(wrapped_lines)
    return "\n".join(lines)


HELP = wrap_keeping_indent(HELP, 80)
assert all(len(line) <= 80 for line in HELP.split("\n"))

# Temporary reproducibility hack, hopefully.
# See: https://github.com/python-pillow/Pillow/issues/9175
orig = PIL.PdfParser.PdfParser.write_comment


def monkey_patch(s, a):
    if a.startswith("created by Pillow "):
        a = "created by Pillow 11.1.0 PDF driver"
    return orig(s, a)


PIL.PdfParser.PdfParser.write_comment = monkey_patch

COVER = """
DO NOT THROW OUT

This backup was generated using qr-backup, a program to back up computer files to physical paper. The person who made the backup went through a lot of work to make and print this document, and will probably be mad at you if you throw it out. They will also end up with big problems if/when their important file goes missing.

To learn more about qr-backup, visit https://github.com/za3k/qr-backup.

== Information about this backup ==

File: {restore_file}
Backup created on: {backup_date}
Size (bytes): {original_len}
SHA256: {sha256sum}
Command used: {nice_cmd}
{notes}
== How to restore ==

You will need access to a Linux, BSD, or Mac/OSX computer and a command line. You will also need to install 'zbar' and imagemagick.

To restore using a webcam and the command line:
  Step 1 (scan): zbarcam --raw | tee /tmp/qrs | cut -c1-{code_end}
    Scan each code at least once in any order'
  Step 2 (restore): {howto_restore_cmd} >{restore_file}'
  Step 3 (verify): sha256sum {restore_file} # Check against SHA256 above

To restore using a webcam and qr-backup:
  Step 1: qr-backup --restore

To restore using a scanner and the command line:
  Step 1 (scan): Scan the images with your scanner. Save them as any image format, it doesn't matter.
  Step 2 (scan): zbarimg -q --raw *.png >/tmp/qrs
  Step 3 (restore): {howto_restore_cmd} >{restore_file}
  Step 4 (verify): sha256sum {restore_file} # Check against SHA256 above

To restore using a scanner and qr-backup:
  qr-backup --restore IMAGE1 IMAGE2 ...

== Dear future archivists ==

(You can probably ignore this section)

If you don't have access to the command line, and you don't have access to qr-backup, here is an explanation of how the backup is structured.
You will need a computing device and a great deal of technical expertise to restore this way.

- First, each QR code is scanned. QR is a 2D "bar"code in common use.
  QR is too complex to explain here. It is designed by Denso Wave. Each QR code holds 7 to 2953 bytes as binary data (depends on the settings)
  The error correction level (L/M/Q/H) and version (size, 1-40) are given in "command" under the backup information above.
  Many common devices can scan QR codes, such as 2012-2020 "smart" cell phones.
- Each QR code is labeled--the label matches the data written under the QR code.
  This data only used to label which code is which. It is removed.
- The non-label contents of each QR-code are base64.
  Base64 holds 6 bits per character. The full character set is:
    ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/
    = is used as padding so the final size is a multiple of 24 bits
  base64 is detailed in RFC 4648 (base16, base32, and base64). The string "ZXhhbXBsZQ==" is decoded as "example".
  The command-line tool base64 or many commonly-available internet tools provide this function.
  It is reasonable to program a tool to decode base64 yourself. Convert from base-64 given above to base-256 (bytes).
- (*) The decoded base64 from every 'N' QR code is appended together in order.
- At the start of the file is the size (as an ascii decimal) after the space. Remove the length and end padding.
- If the --encrypt option is given, the file must be decrypted.
  The details of GPG decryption are too long to include here, but the algorithm used was AES256.
- If the --compress option is given, the file must be gzip-decompressed.
  The details of gzip are too long to include here, see RFC 1951 (DEFLATE).
  Naming a file "XXX.gz" allows it to be decompressed on Windows, Mac/Apple, BSD, Linux, and Unix.
- The file is now assembled.
- The file is checksummed using sha256, which verifies the file is perfectly restored.
  The checksum is detailed in United States NIST standard FIPS PUB 180-2 (SHA2)
  Many standard tools like sha256 perform this checksum.
- The 'P' codes are reed-solomon erasure codes, used to restore missing 'N' codes at step (*)
  To learn about reed-solomon erasure codes, consult a book about erasure coding. Codes are formed using the first byte of each 'N' code, then the second, and so on. If there are more than 177 N codes, they are broken into groups of 177.
  The parameters chosen are 1 < k < n < 255. n-k is likely to be 177 for all blocks except the last. The polynomial is chosen by an underlying library, but will be the same for each k and n. Use brute-force guessing on good data.
"""
COVER = wrap_keeping_indent(COVER, 150)

WEBCAM_MESSAGE = """
==Webcam Restore==

In a second, a second window with a webcam preview will appear on screen.
You may need to resize or move the window to see this terminal.

Progress and hints will appear in the terminal.

Press Enter to start scanning codes.
"""

# BIP 39 wordlist for mnemonic keys
bip39_words = """
abandon ability able about above absent absorb abstract absurd abuse access 
accident account accuse achieve acid acoustic acquire across act action actor 
actress actual adapt add addict address adjust admit adult advance advice 
aerobic affair afford afraid again age agent agree ahead aim air airport aisle 
alarm album alcohol alert alien all alley allow almost alone alpha already also 
alter always amateur amazing among amount amused analyst anchor ancient anger 
angle angry animal ankle announce annual another answer antenna antique anxiety 
any apart apology appear apple approve april arch arctic area arena argue arm 
armed armor army around arrange arrest arrive arrow art artefact artist artwork 
ask aspect assault asset assist assume asthma athlete atom attack attend 
attitude attract auction audit august aunt author auto autumn average avocado 
avoid awake aware away awesome awful awkward axis baby bachelor bacon badge bag 
balance balcony ball bamboo banana banner bar barely bargain barrel base basic 
basket battle beach bean beauty because become beef before begin behave behind 
believe below belt bench benefit best betray better between beyond bicycle bid 
bike bind biology bird birth bitter black blade blame blanket blast bleak bless 
blind blood blossom blouse blue blur blush board boat body boil bomb bone bonus 
book boost border boring borrow boss bottom bounce box boy bracket brain brand 
brass brave bread breeze brick bridge brief bright bring brisk broccoli broken 
bronze broom brother brown brush bubble buddy budget buffalo build bulb bulk 
bullet bundle bunker burden burger burst bus business busy butter buyer buzz 
cabbage cabin cable cactus cage cake call calm camera camp can canal cancel 
candy cannon canoe canvas canyon capable capital captain car carbon card cargo 
carpet carry cart case cash casino castle casual cat catalog catch category 
cattle caught cause caution cave ceiling celery cement census century cereal 
certain chair chalk champion change chaos chapter charge chase chat cheap check 
cheese chef cherry chest chicken chief child chimney choice choose chronic 
chuckle chunk churn cigar cinnamon circle citizen city civil claim clap clarify 
claw clay clean clerk clever click client cliff climb clinic clip clock clog 
close cloth cloud clown club clump cluster clutch coach coast coconut code 
coffee coil coin collect color column combine come comfort comic common company 
concert conduct confirm congress connect consider control convince cook cool 
copper copy coral core corn correct cost cotton couch country couple course 
cousin cover coyote crack cradle craft cram crane crash crater crawl crazy 
cream credit creek crew cricket crime crisp critic crop cross crouch crowd 
crucial cruel cruise crumble crunch crush cry crystal cube culture cup cupboard 
curious current curtain curve cushion custom cute cycle dad damage damp dance 
danger daring dash daughter dawn day deal debate debris decade december decide 
decline decorate decrease deer defense define defy degree delay deliver demand 
demise denial dentist deny depart depend deposit depth deputy derive describe 
desert design desk despair destroy detail detect develop device devote diagram 
dial diamond diary dice diesel diet differ digital dignity dilemma dinner 
dinosaur direct dirt disagree discover disease dish dismiss disorder display 
distance divert divide divorce dizzy doctor document dog doll dolphin domain 
donate donkey donor door dose double dove draft dragon drama drastic draw dream 
dress drift drill drink drip drive drop drum dry duck dumb dune during dust 
dutch duty dwarf dynamic eager eagle early earn earth easily east easy echo 
ecology economy edge edit educate effort egg eight either elbow elder electric 
elegant element elephant elevator elite else embark embody embrace emerge 
emotion employ empower empty enable enact end endless endorse enemy energy 
enforce engage engine enhance enjoy enlist enough enrich enroll ensure enter 
entire entry envelope episode equal equip era erase erode erosion error erupt 
escape essay essence estate eternal ethics evidence evil evoke evolve exact 
example excess exchange excite exclude excuse execute exercise exhaust exhibit 
exile exist exit exotic expand expect expire explain expose express extend 
extra eye eyebrow fabric face faculty fade faint faith fall false fame family 
famous fan fancy fantasy farm fashion fat fatal father fatigue fault favorite 
feature february federal fee feed feel female fence festival fetch fever few 
fiber fiction field figure file film filter final find fine finger finish fire 
firm first fiscal fish fit fitness fix flag flame flash flat flavor flee flight 
flip float flock floor flower fluid flush fly foam focus fog foil fold follow 
food foot force forest forget fork fortune forum forward fossil foster found 
fox fragile frame frequent fresh friend fringe frog front frost frown frozen 
fruit fuel fun funny furnace fury future gadget gain galaxy gallery game gap 
garage garbage garden garlic garment gas gasp gate gather gauge gaze general 
genius genre gentle genuine gesture ghost giant gift giggle ginger giraffe girl 
give glad glance glare glass glide glimpse globe gloom glory glove glow glue 
goat goddess gold good goose gorilla gospel gossip govern gown grab grace grain 
grant grape grass gravity great green grid grief grit grocery group grow grunt 
guard guess guide guilt guitar gun gym habit hair half hammer hamster hand 
happy harbor hard harsh harvest hat have hawk hazard head health heart heavy 
hedgehog height hello helmet help hen hero hidden high hill hint hip hire 
history hobby hockey hold hole holiday hollow home honey hood hope horn horror 
horse hospital host hotel hour hover hub huge human humble humor hundred hungry 
hunt hurdle hurry hurt husband hybrid ice icon idea identify idle ignore ill 
illegal illness image imitate immense immune impact impose improve impulse inch 
include income increase index indicate indoor industry infant inflict inform 
inhale inherit initial inject injury inmate inner innocent input inquiry insane 
insect inside inspire install intact interest into invest invite involve iron 
island isolate issue item ivory jacket jaguar jar jazz jealous jeans jelly 
jewel job join joke journey joy judge juice jump jungle junior junk just 
kangaroo keen keep ketchup key kick kid kidney kind kingdom kiss kit kitchen 
kite kitten kiwi knee knife knock know lab label labor ladder lady lake lamp 
language laptop large later latin laugh laundry lava law lawn lawsuit layer 
lazy leader leaf learn leave lecture left leg legal legend leisure lemon lend 
length lens leopard lesson letter level liar liberty library license life lift 
light like limb limit link lion liquid list little live lizard load loan 
lobster local lock logic lonely long loop lottery loud lounge love loyal lucky 
luggage lumber lunar lunch luxury lyrics machine mad magic magnet maid mail 
main major make mammal man manage mandate mango mansion manual maple marble 
march margin marine market marriage mask mass master match material math matrix 
matter maximum maze meadow mean measure meat mechanic medal media melody melt 
member memory mention menu mercy merge merit merry mesh message metal method 
middle midnight milk million mimic mind minimum minor minute miracle mirror 
misery miss mistake mix mixed mixture mobile model modify mom moment monitor 
monkey monster month moon moral more morning mosquito mother motion motor 
mountain mouse move movie much muffin mule multiply muscle museum mushroom 
music must mutual myself mystery myth naive name napkin narrow nasty nation 
nature near neck need negative neglect neither nephew nerve nest net network 
neutral never news next nice night noble noise nominee noodle normal north nose 
notable note nothing notice novel now nuclear number nurse nut oak obey object 
oblige obscure observe obtain obvious occur ocean october odor off offer office 
often oil okay old olive olympic omit once one onion online only open opera 
opinion oppose option orange orbit orchard order ordinary organ orient original 
orphan ostrich other outdoor outer output outside oval oven over own owner 
oxygen oyster ozone pact paddle page pair palace palm panda panel panic panther 
paper parade parent park parrot party pass patch path patient patrol pattern 
pause pave payment peace peanut pear peasant pelican pen penalty pencil people 
pepper perfect permit person pet phone photo phrase physical piano picnic 
picture piece pig pigeon pill pilot pink pioneer pipe pistol pitch pizza place 
planet plastic plate play please pledge pluck plug plunge poem poet point polar 
pole police pond pony pool popular portion position possible post potato 
pottery poverty powder power practice praise predict prefer prepare present 
pretty prevent price pride primary print priority prison private prize problem 
process produce profit program project promote proof property prosper protect 
proud provide public pudding pull pulp pulse pumpkin punch pupil puppy purchase 
purity purpose purse push put puzzle pyramid quality quantum quarter question 
quick quit quiz quote rabbit raccoon race rack radar radio rail rain raise 
rally ramp ranch random range rapid rare rate rather raven raw razor ready real 
reason rebel rebuild recall receive recipe record recycle reduce reflect reform 
refuse region regret regular reject relax release relief rely remain remember 
remind remove render renew rent reopen repair repeat replace report require 
rescue resemble resist resource response result retire retreat return reunion 
reveal review reward rhythm rib ribbon rice rich ride ridge rifle right rigid 
ring riot ripple risk ritual rival river road roast robot robust rocket romance 
roof rookie room rose rotate rough round route royal rubber rude rug rule run 
runway rural sad saddle sadness safe sail salad salmon salon salt salute same 
sample sand satisfy satoshi sauce sausage save say scale scan scare scatter 
scene scheme school science scissors scorpion scout scrap screen script scrub 
sea search season seat second secret section security seed seek segment select 
sell seminar senior sense sentence series service session settle setup seven 
shadow shaft shallow share shed shell sheriff shield shift shine ship shiver 
shock shoe shoot shop short shoulder shove shrimp shrug shuffle shy sibling 
sick side siege sight sign silent silk silly silver similar simple since sing 
siren sister situate six size skate sketch ski skill skin skirt skull slab slam 
sleep slender slice slide slight slim slogan slot slow slush small smart smile 
smoke smooth snack snake snap sniff snow soap soccer social sock soda soft 
solar soldier solid solution solve someone song soon sorry sort soul sound soup 
source south space spare spatial spawn speak special speed spell spend sphere 
spice spider spike spin spirit split spoil sponsor spoon sport spot spray 
spread spring spy square squeeze squirrel stable stadium staff stage stairs 
stamp stand start state stay steak steel stem step stereo stick still sting 
stock stomach stone stool story stove strategy street strike strong struggle 
student stuff stumble style subject submit subway success such sudden suffer 
sugar suggest suit summer sun sunny sunset super supply supreme sure surface 
surge surprise surround survey suspect sustain swallow swamp swap swarm swear 
sweet swift swim swing switch sword symbol symptom syrup system table tackle 
tag tail talent talk tank tape target task taste tattoo taxi teach team tell 
ten tenant tennis tent term test text thank that theme then theory there they 
thing this thought three thrive throw thumb thunder ticket tide tiger tilt 
timber time tiny tip tired tissue title toast tobacco today toddler toe 
together toilet token tomato tomorrow tone tongue tonight tool tooth top topic 
topple torch tornado tortoise toss total tourist toward tower town toy track 
trade traffic tragic train transfer trap trash travel tray treat tree trend 
trial tribe trick trigger trim trip trophy trouble truck true truly trumpet 
trust truth try tube tuition tumble tuna tunnel turkey turn turtle twelve 
twenty twice twin twist two type typical ugly umbrella unable unaware uncle 
uncover under undo unfair unfold unhappy uniform unique unit universe unknown 
unlock until unusual unveil update upgrade uphold upon upper upset urban urge 
usage use used useful useless usual utility vacant vacuum vague valid valley 
valve van vanish vapor various vast vault vehicle velvet vendor venture venue 
verb verify version very vessel veteran viable vibrant vicious victory video 
view village vintage violin virtual virus visa visit visual vital vivid vocal 
voice void volcano volume vote voyage wage wagon wait walk wall walnut want 
warfare warm warrior wash wasp waste water wave way wealth weapon wear weasel 
weather web wedding weekend weird welcome west wet whale what wheat wheel when 
where whip whisper wide width wife wild will win window wine wing wink winner 
winter wire wisdom wise wish witness wolf woman wonder wood wool word work 
world worry worth wrap wreck wrestle wrist write wrong yard year yellow you 
young youth zebra zero zone zoo
""".split()
assert len(bip39_words) == 2048

# Greyscale is required to work around https://github.com/python-pillow/Pillow/issues/6149
IMAGE_MODE = "L"
WHITE = 255
BLACK = 0

# Zbar and imagemagick constants
CONVERSION_DENSITY = 600  # pdf to pixel-based format conversion hack
ZBAR_WARNING_THRESHOLD = (
    0.9  # do we want to accept that zbar just can't scan the perfect original?
)

# Erasure coding constants
DEFAULT_ALLOWABLE_LOSS = 0.3
ERASURE_SPLIT = 177  # with allowable_loss_fraction=0.3, hits ERASURE_LIMIT of 254. TODO: Have it depend on allowable_loss_fraction instead of assuming DEFAULT_ALLOWABLE_LOSS?
ERASURE_LIMIT = 254

# Logging constants
LOGGING_FORMAT = "%(levelname)s: %(message)s"

# QR constants
L = qrcode.constants.ERROR_CORRECT_L
M = qrcode.constants.ERROR_CORRECT_M  # default, 25%
Q = qrcode.constants.ERROR_CORRECT_Q
H = qrcode.constants.ERROR_CORRECT_H
QR_MODE = (
    qrcode.util.MODE_8BIT_BYTE
)  # not settable. and no, base64 encoded data doesn't bit in alphanumeric (there are only 44 chars)

VERSIONS_BITS = {
    # Binary bits for each version size, 1-40
    # Source: qrcode.com (DENSO WAVE)
    # Order is L,M,Q,H on right
    1: [152, 128, 104, 72],
    2: [272, 224, 176, 128],
    3: [440, 352, 272, 208],
    4: [640, 512, 384, 288],
    5: [864, 688, 496, 368],
    6: [1088, 864, 608, 480],
    7: [1248, 992, 704, 528],
    8: [1552, 1232, 880, 688],
    9: [1856, 1456, 1056, 800],
    10: [2192, 1728, 1232, 976],
    11: [2592, 2032, 1440, 1120],
    12: [2960, 2320, 1648, 1264],
    13: [3424, 2672, 1952, 1440],
    14: [3688, 2920, 2088, 1576],
    15: [4184, 3320, 2360, 1784],
    16: [4712, 3624, 2600, 2024],
    17: [5176, 4056, 2936, 2264],
    18: [5768, 4504, 3176, 2504],
    19: [6360, 5016, 3560, 2728],
    20: [6888, 5352, 3880, 3080],
    21: [7456, 5712, 4096, 3248],
    22: [8048, 6256, 4544, 3536],
    23: [8752, 6880, 4912, 3712],
    24: [9392, 7312, 5312, 4112],
    25: [10208, 8000, 5744, 4304],
    26: [10960, 8496, 6032, 4768],
    27: [11744, 9024, 6464, 5024],
    28: [12248, 9544, 6968, 5288],
    29: [13048, 10136, 7288, 5608],
    30: [13880, 10984, 7880, 5960],
    31: [14744, 11640, 8264, 6344],
    32: [15640, 12328, 8920, 6760],
    33: [16568, 13048, 9368, 7208],
    34: [17528, 13800, 9848, 7688],
    35: [18448, 14496, 10288, 7888],
    36: [19472, 15312, 10832, 8432],
    37: [20528, 15936, 11408, 8768],
    38: [21616, 16816, 12016, 9136],
    39: [22496, 17728, 12656, 9776],
    40: [23648, 18672, 13328, 10208],
}


class QR:
    def __init__(self, qr, label):
        self.qr = qr
        self.label = label


def qr_size_chars(version, mode, quality):
    assert mode not in [qrcode.util.MODE_NUMBER, qrcode.util.MODE_KANJI]
    assert mode in [qrcode.util.MODE_ALPHA_NUM, qrcode.util.MODE_8BIT_BYTE]

    bits = VERSIONS_BITS[version][[L, M, Q, H].index(quality)]
    data_bits = bits - 4 - qrcode.util.length_in_bits(mode, version)
    if mode == qrcode.util.MODE_NUMBER:  # Not verified
        return (data_bits // 10) * 3 + [0, 0, 0, 0, 1, 1, 1, 2, 2, 2][data_bits % 10]
    if mode == qrcode.util.MODE_ALPHA_NUM:  # Not verified
        return (data_bits // 11) * 2 + [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1][data_bits % 11]
    if mode == qrcode.util.MODE_8BIT_BYTE:  # Verified
        return math.floor(data_bits / 8)
    if mode == qrcode.util.MODE_KANJI:  # Not verified
        return math.floor(data_bits / 13)


def qr_grid_size(version):
    return version * 4 + 17


def program_present(program):
    """Return True or False depending on whether the program is found in the environment"""
    return (
        subprocess.call(
            ["which", program], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        == 0
    )


def ubuntu_policy_problem():
    """Tests for Debian/Ubuntu's policy of disabling all PDF conversion using ImageMagick"""
    command = [
        "grep",
        "-F",
        "-s",
        "-q",
        """<policy domain="coder" rights="none" pattern="PDF" />""",
        "/etc/ImageMagick-6/policy.xml",
        "/etc/ImageMagick-7/policy.xml",
    ]
    return (
        subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        == 0
    )


def length_encode(data):
    length = len(data)
    prefix = str(length).encode("ascii") + b" "  # encode the length at the start
    return (prefix + data), (len(prefix), length)


def length_decode(data):
    length, rest = data.split(b" ", maxsplit=1)
    length = int(length)
    return rest[:length]


def shuffle(qrs):
    # Ideally we would feed in the page size, and figure out how to do this optimially.
    # But random is also pretty good, and this way we don't have to figure out the number
    # of QRs per page in advance
    # Note: if we do the optimal way, avoid problems with losing a page or one corner of
    # whole stack tearing off. Remember duplex.
    ret = copy.copy(qrs)
    det = random.Random(1)
    det.shuffle(ret)
    return ret


def _calculate_chunk_digits(len_data, chunk_size, allowable_loss_fraction):
    # Figure out the number of digits in the number of QR codes (which is circular)
    for chunk_digits in range(1, 10):
        prefix_normal_format = (
            "N{:0>" + str(chunk_digits) + "}/{:0>" + str(chunk_digits) + "} "
        )
        prefix_parity_format = (
            "P{:0>" + str(chunk_digits) + "}/{:0>" + str(chunk_digits) + "} "
        )
        payload_size_base64 = chunk_size - len(prefix_normal_format.format(0, 0))
        payload_size_bytes = (
            math.floor(payload_size_base64 / 4) * 3
        )  # groups of 4 base-64 digits encode 3 bytes each
        num_qrs = math.ceil(len_data / payload_size_bytes)
        if num_qrs > 10**chunk_digits - 1:
            continue
        num_parity_chunks = erasure_count(num_qrs, allowable_loss_fraction)
        if num_parity_chunks > 10**chunk_digits - 1:
            continue
        return (
            chunk_digits,
            payload_size_base64,
            payload_size_bytes,
            {b"N": num_qrs, b"P": num_parity_chunks},
            {b"N": prefix_normal_format, b"P": prefix_parity_format},
        )
    assert False


def generate_chunks(data, chunk_size_base64, do_checks, allowable_loss_fraction=0):
    """
    Return a bunch of chunks to put in QRs.
    The returned values must not contain "\n" due to the use of zbarimg/zbarcam, so we base-64 encode everything at the QR level
    Note that the data may be zero-padded on the right during this process.

    data: data to return, as Bytes
    chunk_size_base64: maximum size of each chunk, in QR-safe characters
    """

    (
        chunk_digits,
        payload_size_base64,
        payload_size_bytes,
        num_chunks,
        format_strings,
    ) = _calculate_chunk_digits(len(data), chunk_size_base64, allowable_loss_fraction)
    assert (
        math.ceil(len(data) / payload_size_bytes)
        == num_chunks[b"N"]
        <= 10**chunk_digits - 1
    )

    # Pad to even chunk length
    padding_size = -len(data) % payload_size_bytes
    data += b"\0" * padding_size
    assert len(data) % payload_size_bytes == 0

    # Split into chunks
    chunks = {}
    chunks[b"N"] = [
        data[start : start + payload_size_bytes]
        for start in range(0, len(data), payload_size_bytes)
    ]
    assert all(
        len(chunk_data_bytes) == payload_size_bytes for chunk_data_bytes in chunks[b"N"]
    )
    assert len(chunks[b"N"]) == num_chunks[b"N"]

    # Generate erasure codes
    chunks[b"P"] = generate_erasure(
        chunks[b"N"], allowable_loss_fraction, self_test=do_checks,
    )
    assert all(
        len(chunk_data_bytes) == payload_size_bytes for chunk_data_bytes in chunks[b"P"]
    )
    assert len(chunks[b"P"]) == num_chunks[b"P"]

    # Output the chunks
    ascii_chunks = []
    for chunk_type in (b"N", b"P"):
        for i, chunk_data_bytes in enumerate(chunks[chunk_type]):
            prefix = (
                format_strings[chunk_type]
                .format(i + 1, num_chunks[chunk_type])
                .encode("ascii")
            )
            chunk_data_base64 = base64.b64encode(chunk_data_bytes)
            assert len(chunk_data_base64) <= payload_size_base64
            chunk_content = prefix + chunk_data_base64
            assert len(chunk_content) <= chunk_size_base64
            label = prefix.decode("ascii").split("/")[0]
            ascii_chunks.append((chunk_content, label))

    assert len(ascii_chunks) == sum(num_chunks.values())
    assert all(len(chunk) <= chunk_size_base64 for chunk, label in ascii_chunks)

    return chunk_digits, ascii_chunks


def erasure_count(num_normal_pieces, allowable_loss_fraction):
    if allowable_loss_fraction == 0:
        return 0

    simple_erasures = lambda n: math.ceil(
        n * allowable_loss_fraction / (1 - allowable_loss_fraction),
    )
    assert simple_erasures(0) == 0
    num_erasures = simple_erasures(num_normal_pieces)
    if num_erasures + num_normal_pieces <= ERASURE_LIMIT:
        return num_erasures

    num_erasures_max = simple_erasures(ERASURE_SPLIT)
    last_piece_size = num_normal_pieces % ERASURE_SPLIT
    num_erasures_last = simple_erasures(last_piece_size)
    return num_erasures_max * (num_normal_pieces // ERASURE_SPLIT) + num_erasures_last


def generate_erasure(binary_chunks, allowable_loss_fraction, self_test=True):
    """
    Given data chunks (as equal-length bytes objects), generate parity chunks for k-of-n restore.
    k = len(binary_chunks)
    n = len(binary_chunks)+erasure_count
    """
    if allowable_loss_fraction == 0:
        return []
    num_erasures = erasure_count(len(binary_chunks), allowable_loss_fraction)
    chunk_size = len(binary_chunks[0])
    assert all(len(chunk) == chunk_size for chunk in binary_chunks)
    num_total_chunks = len(binary_chunks) + num_erasures

    if num_total_chunks > ERASURE_LIMIT:
        # Chunk manually, rather than using reedsolo's default chunking.
        # Reedsolo has fencepost errors
        # Reedsolo outputs nnnppnnnpp. We want nnnnnnpppp. (n=normal, p=parity)
        # Ideally this would be an interleaved reedsolomon code, but it was too complicated for me to figure out, so instead we just do a simple chunked version, then shuffle and hope.
        assert allowable_loss_fraction == DEFAULT_ALLOWABLE_LOSS
        erasure_codes = []
        for start in range(0, len(binary_chunks), ERASURE_SPLIT):
            new_erasure = generate_erasure(
                binary_chunks[start : start + ERASURE_SPLIT],
                allowable_loss_fraction,
                self_test=False,
            )
            erasure_codes.extend(new_erasure)
        symbols = binary_chunks + erasure_codes
    else:
        assert (
            num_total_chunks <= ERASURE_LIMIT
        ), "Support for erasure codes on >20KB files not yet implemented"

        codec = reedsolo.RSCodec(num_erasures)
        groups = [bytes(x) for x in zip(*binary_chunks)]
        assert len(binary_chunks) == len(groups[0])
        assert chunk_size == len(groups)
        symbols = [bytes(a) for a in zip(*(codec.encode(group) for group in groups))]
        assert len(symbols) != 0
        assert all(len(symbol) == chunk_size for symbol in symbols)
        assert all(binary_chunks[i] == symbols[i] for i in range(len(binary_chunks)))
        assert len(symbols) == num_total_chunks

        erasure_codes = symbols[-num_erasures:]
    assert len(erasure_codes) == num_erasures

    if self_test:
        # Self-test of restore
        logging.info("generate_erasure: perform self-test")
        num_erased = (
            num_erasures if (num_total_chunks <= ERASURE_LIMIT) else num_erasures // 2
        )
        symbols = copy.copy(symbols)

        for i in random.Random(1).sample(range(len(symbols)), num_erased):
            symbols[i] = None
        self_check = restore_erasure(
            symbols[:-num_erasures], symbols[-num_erasures:], allowable_loss_fraction,
        )
        data = b"".join(binary_chunks)
        assert self_check == data, "Self-check failed in generate_erasure"
        logging.info("generate_erasure: deleted first few symbols, restore works fine")

    return erasure_codes


def restore_erasure(normal_codes, erasure_codes, allowable_loss_fraction):
    """Restores erasure-coded content. Note that this will still be padded after"""
    symbols = normal_codes + erasure_codes
    assert any(symbol is not None for symbol in symbols)

    chunk_size = max(len(symbol) for symbol in symbols if symbol is not None)
    missing_symbols = [i for i, symbol in enumerate(symbols) if symbol is None]
    for i in missing_symbols:
        symbols[i] = (
            b" " * chunk_size
        )  # Doesn't really matter what we set this to as long as it's the right length.
    assert all(isinstance(symbol, bytes) for symbol in symbols)
    assert all(len(symbol) == chunk_size for symbol in symbols)

    num_erasures = erasure_count(len(normal_codes), allowable_loss_fraction)
    assert len(erasure_codes) == num_erasures, "{} != {}".format(
        len(erasure_codes), num_erasures,
    )

    if len(symbols) > ERASURE_LIMIT:
        assert allowable_loss_fraction == DEFAULT_ALLOWABLE_LOSS
        # Decode multiple blocks
        num_erasures_per_split = erasure_count(ERASURE_SPLIT, allowable_loss_fraction)
        decoded = b""
        fixed = []
        for block_num in range(math.ceil(len(normal_codes) / ERASURE_SPLIT)):
            local_normal = normal_codes[
                block_num * ERASURE_SPLIT : (block_num + 1) * ERASURE_SPLIT
            ]
            local_erasure = erasure_codes[
                block_num
                * num_erasures_per_split : (block_num + 1)
                * num_erasures_per_split
            ]
            restored_binary = restore_erasure(
                local_normal, local_erasure, allowable_loss_fraction,
            )
            fixed.append(restored_binary)
        decoded = b"".join(fixed)
        assert len(decoded) == len(normal_codes) * chunk_size
        return decoded
    # Decode single block
    codec = reedsolo.RSCodec(num_erasures)
    broken_strings = list(zip(*symbols))
    fixed_strings = [
        codec.decode(x, erase_pos=missing_symbols, only_erasures=True)[0]
        for x in broken_strings
    ]
    simple_restore = b"".join(bytes(x) for x in zip(*fixed_strings))
    assert len(simple_restore) == len(normal_codes) * chunk_size
    return simple_restore


def qr_for(data, version, error_correction, scale):
    naive_chunk_size = qr_size_chars(version, QR_MODE, error_correction)
    assert len(data) <= naive_chunk_size

    qr = qrcode.QRCode(
        version=version,
        error_correction=error_correction,
        box_size=scale,
        border=0,
    )
    qr.add_data(qrcode.util.QRData(data, mode=QR_MODE), optimize=0)
    qr.make(fit=False)
    return qr


def qr_codes(
    data, error_correction, version, scale, do_checks, allowable_loss_fraction=0,
):
    naive_chunk_size = qr_size_chars(version, QR_MODE, error_correction)
    chunk_digits, chunks = generate_chunks(
        data,
        naive_chunk_size,
        do_checks=do_checks,
        allowable_loss_fraction=allowable_loss_fraction,
    )

    qr_pad = scale * 4

    assert all(len(data) <= naive_chunk_size for data, label in chunks)
    qrs = [
        QR(qr_for(data, version, error_correction, scale), label)
        for data, label in chunks
    ]

    return chunk_digits, qr_pad, qrs


def generate_passphrase():
    return " ".join(random.choices(bip39_words, k=8))


# I took a look at the python 'gnupg' library... it doesn't support bytes, and it isn't really designed to do symmetric encryption/decryption either.
def encrypt(content_bytes, passphrase, armor=False, cipher="AES256"):
    # I chose to hardcode an encryption cipher, to make documenting the restore easier. This does make it harder to futureproof, and some people may distrust AES already.
    command = [
        "gpg",
        "--symmetric",
        "--no-symkey-cache",
        "--passphrase",
        passphrase,
        "--batch",
        "--cipher-algo",
        cipher,
    ] + (["--armor"] if armor else [])
    result = subprocess.run(command, capture_output=True, input=content_bytes)
    if result.returncode != 0:
        logging.info("gpg command: {}".format(" ".join(command)))
        logging.fatal("[gpg stdout] {}".format(result.stdout))
        logging.fatal("[gpg stderr] {}".format(result.stderr))
        logging.fatal("[gpg exit] {}".format(result.returncode))
        sys.exit(7)
    return result.stdout


def decrypt(content_bytes, passphrase):
    command = [
        "gpg",
        "--decrypt",
        "--no-symkey-cache",
        "--passphrase",
        passphrase,
        "--batch",
    ]
    result = subprocess.run(command, capture_output=True, input=content_bytes)
    if result.returncode != 0:
        logging.info("gpg command: {}".format(" ".join(command)))
        logging.error("[gpg stdout] {}".format(result.stdout))
        logging.error("[gpg stderr] {}".format(result.stderr))
        logging.fatal("[gpg exit] {}".format(result.returncode))
        sys.exit(7)
    return result.stdout


def create_tar(input_paths):
    fh = io.BytesIO()
    tf = tarfile.open(fileobj=fh, mode="w")
    for input_path in input_paths:
        tf.add(input_path)
    tf.close()
    fh.seek(0)
    return fh


def show_help(error=None, special_error=None):
    if error:
        print(HELP, file=sys.stderr, end="")
        print(file=sys.stderr)
        print("ERROR: {}".format(error), file=sys.stderr)
        if isinstance(special_error, int):
            sys.exit(error)
        else:
            sys.exit(1)
    else:
        print(HELP, end="")
        sys.exit(0)


def add_label(image, text, side="bottom", max_fontsize=24, max_width=None, label=None):
    """
    Add a label. The fontsize is max_fontsize if possible, otherwise it's shrunk down.
    The label is aligned to the bounding box of the image (lines up with margins).
    """
    # Figure out the size and position of the original image
    bbox = PIL.ImageOps.invert(image.copy().convert("L")).getbbox()
    if bbox is None:
        left, upper, right, lower = 0, 0, 0, 0
        if max_width is None:
            max_width = image.size[0]
    elif max_width is None:
        left, upper, right, lower = bbox
        max_width = right - left
    else:
        left, upper, right, lower = bbox
        right, max_width = max(right, max_width), max_width - left

    # Generate a label that fits. The fontsize will be reduced if needed. No word wrap is performed.
    if label is None:
        label = generate_label(text, max_width=max_width, max_fontsize=max_fontsize)
    else:
        assert label.size[0] <= max_width, "Premade label is too wide"
    label_bbox = PIL.ImageOps.invert(image.copy().convert("L")).getbbox()

    # Layout
    width, combined_height = (
        max(image.size[0], left + label.size[0]),
        image.size[1] + label.size[1],
    )
    labeled = PIL.Image.new(
        mode=IMAGE_MODE, size=(width, combined_height), color=WHITE,
    )  # B+W
    if side == "bottom":
        labeled.paste(image, (0, 0))
        labeled.paste(label, (left, image.size[1]))
    elif side == "top":
        labeled.paste(label, (left, 0))
        labeled.paste(image, (0, label.size[1]))
    else:
        assert False, "Unknown side for label: {}".format(side)
    return labeled


def generate_label(text, max_width, max_fontsize=24, min_fontsize=4):
    # to do, maybe some fancy word wrap
    test_im = PIL.Image.new(mode=IMAGE_MODE, size=(1, 1), color=WHITE)
    test_draw = PIL.ImageDraw.Draw(test_im)

    for fontsize in range(max_fontsize, min_fontsize - 1, -1):
        font = PIL.ImageFont.truetype("DejaVuSansMono.ttf", fontsize)
        _, _, width, height = test_draw.multiline_textbbox((0, 0), text, font=font)
        height += 4
        if width <= max_width:
            im = PIL.Image.new(
                mode=IMAGE_MODE, size=(width, height), color=WHITE,
            )  # black-and-white
            draw = PIL.ImageDraw.Draw(im)
            draw.multiline_text(
                (0, -2), text, font=font,
            )  # Eurgh, hardcoding an offset.
            return im
        logging.debug("Reducing label size to {}".format(fontsize))
    # assert False
    logging.error("Label cannot fit in the requested width. Forcing output...")

    font = PIL.ImageFont.truetype("DejaVuSansMono.ttf", min_fontsize)
    _, _, width, height = test_draw.multiline_textbbox((0, 0), text, font=font)
    height += 4
    im = PIL.Image.new(
        mode=IMAGE_MODE, size=(max_width, height), color=WHITE,
    )  # black-and-white
    draw = PIL.ImageDraw.Draw(im)
    draw.multiline_text((0, -2), text, font=font)  # Eurgh, hardcoding an offset.
    return im


def h_merge(images, padding=0):
    # Alignment is top-aligned
    combined_width = sum(image.size[0] for image in images) + padding * (
        len(images) - 1
    )
    max_height = max(image.size[1] for image in images)
    im = PIL.Image.new(
        mode=IMAGE_MODE, size=(combined_width, max_height), color=WHITE,
    )  # B+W
    width = 0
    for source_image in images:
        im.paste(source_image, (width, 0))
        width += source_image.size[0] + padding
    return im


def v_merge(images, padding=0):
    # Alignment is left-aligned
    max_width = max(image.size[0] for image in images)
    combined_height = sum(image.size[1] for image in images) + padding * (
        len(images) - 1
    )
    im = PIL.Image.new(
        mode=IMAGE_MODE, size=(max_width, combined_height), color=WHITE,
    )  # B+W
    height = 0
    for source_image in images:
        im.paste(source_image, (0, height))
        height += source_image.size[1] + padding
    return im


def main_backup(args):
    # default settings
    qr_version = 10
    error_correction = M  # default, 25%
    scale = 5
    dpi = 300
    page_w_points, page_h_points = 500, 600
    restore_file = None
    use_compression = True
    output_path = None
    GENERATE_DOCS = (
        False  # Manually generate example.png for the README when qr-backup changes
    )
    backup_date = None  # Secret hidden option for tests
    add_page_instructions = True
    add_cover_instructions = False
    notes = []
    use_encryption = False
    encryption_passphrase = None
    print_passphrase = None
    use_erasure_coding = True
    use_shuffle = None
    use_tar = False
    num_copies = 1
    do_checks = False  # Disabled until zbar is less flaky (aka never)
    verbose = False

    # parse arguments
    pargs = []
    while len(args) > 0:
        arg, args = args[0], args[1:]
        if arg in ["-h", "--help"]:
            show_help()
        elif arg == "--backup-date":
            if len(args) < 1:
                show_help("--backup-date requires a date")
            backup_date, args = args[0], args[1:]
        elif arg == "--compress":
            use_compression = True
        elif arg == "--dpi":
            if len(args) < 1:
                show_help("--dpi requires one argument (an integer dots-per-inch)")
            dpi, args = int(args[0]), args[1:]
        elif arg == "--encrypt":
            # Note: --encrypt inherently makes the output nondeterministic. AES256 uses both a random IV and a salt.
            if len(args) < 1 or args[0].startswith("-"):
                show_help("--encrypt requires either 'generate' or a passphrase")
            use_encryption = True
            if args[0] == "generate":
                args = args[1:]
            else:
                encryption_passphrase, args = args[0], args[1:]
        elif arg == "--encrypt-print-passphrase":
            print_passphrase = True
        elif arg == "--erasure-coding":
            use_erasure_coding = True
        elif arg == "--error-correction":
            if len(args) < 1:
                show_help("--error-correction requires one of: L M Q H")
            error_correction, args = {"L": L, "M": M, "Q": Q, "H": H}[
                args[0].upper()
            ], args[1:]
        elif arg == "--filename":
            if len(args) < 1:
                show_help("--filename requires one argument")
            restore_file, args = args[0], args[1:]
            assert len(restore_file) > 0 and not restore_file.startswith("-")
        elif (
            arg == "--generate-docs"
        ):  # Development only. Don't document or use please.
            GENERATE_DOCS = True
        elif arg == "--instructions":
            if len(args) < 1:
                show_help("--instructions requires one argument")
            instruction_type, args = args[0], args[1:]
            if instruction_type == "page":
                add_page_instructions = True
                add_cover_instructions = False
            elif instruction_type == "cover":
                add_page_instructions = False
                add_cover_instructions = True
            elif instruction_type == "none":
                add_page_instructions = False
                add_cover_instructions = False
            elif instruction_type == "both":
                add_page_instructions = True
                add_cover_instructions = True
            else:
                show_help("--instructions requires one of: page cover both none")
        elif arg == "--no-compress":
            use_compression = False
        elif arg == "--no-erasure-coding":
            use_erasure_coding = False
        elif arg == "--no-shuffle":
            use_shuffle = False
        elif arg == "--no-skip-checks":
            do_checks = True
        elif arg == "--note":
            if len(args) < 1:
                show_help("--note requires one argument")
            note, args = args[0], args[1:]
            note = "Additional note: " + note
            for i, note_line in enumerate(note.split("\n")):
                initial_indent = " " * 4
                if i == 0:
                    initial_indent = ""
                for line in textwrap.wrap(
                    note_line,
                    width=80,
                    replace_whitespace=False,
                    subsequent_indent=" " * 4,
                    initial_indent=initial_indent,
                ):
                    notes.append(line)
        elif arg == "--num-copies":
            if len(args) < 1:
                show_help("--num-copies requires one argument (integer >= 1)")
            num_copies, args = int(args[0]), args[1:]
            assert num_copies >= 1
        elif arg == "--page":
            if len(args) < 2:
                show_help(
                    "--page requires two arguments (decimal page width and height in inches)",
                )
            page_w_points, page_h_points, args = (
                float(args[0]),
                float(args[1]),
                args[2:],
            )
            # passing in 500 and 500.0 should not change the output.
            # this prevents string formatting from changing in nice_cmd
            if page_w_points == math.floor(page_w_points):
                page_w_points = int(page_w_points)
            if page_h_points == math.floor(page_h_points):
                page_h_points = int(page_h_points)
        elif arg in ["-o", "--output"]:
            if len(args) < 1:
                show_help("{} requires one argument".format(arg))
            output_path, args = args[0], args[1:]
        elif arg == "--qr-version":
            if len(args) < 1:
                show_help(
                    "--qr-version requires one argument (integer version between 2 and 40)",
                )
            qr_version, args = int(args[0]), args[1:]
        elif arg == "--scale":
            if len(args) == 0:
                show_help("--scale requires one argument (integer scale in pixels)")
            scale, args = int(args[0]), args[1:]
        elif arg == "--skip-checks":
            do_checks = False
        elif arg == "--shuffle":
            use_shuffle = True
        elif arg in ["-v", "--verbose"]:
            verbose = True
        elif arg == "-":
            pargs.append(arg)
        elif arg == "--":
            # Stop parsing arguments
            pargs, args = pargs + args, []
        elif arg.startswith("-"):
            show_help("Unknown argument: {}".format(arg))
        else:
            pargs.append(arg)

    if verbose:
        logging.basicConfig(format=LOGGING_FORMAT, level=logging.INFO)
    else:
        logging.basicConfig(format=LOGGING_FORMAT, level=logging.WARNING)
    # Figure out input paths, output paths, and restore filename

    # Input: stdin, tarfile, or single file?
    if len(pargs) == 0 and sys.stdin.isatty():
        show_help("Please supply a filename to backup")
    elif pargs == ["-"] or (len(pargs) == 0 and not sys.stdin.isatty()):
        use_stdin, use_tar = True, False
        input_paths = ["-"]
    elif len(pargs) > 1 or os.path.isdir(pargs[0]):
        use_stdin, use_tar = False, True
        input_paths = pargs
    else:
        use_stdin, use_tar = False, False
        input_paths = pargs
    input_paths = [ip.rstrip("/") for ip in input_paths]

    # Restore filename
    if restore_file is None:
        if len(input_paths) == 1:
            input_filename = input_paths[0].split("/")[-1]
        else:
            input_filename = "file.tar"

        if not use_stdin and len(input_filename) <= 32:
            restore_file = input_filename
        else:
            restore_file = "file"

    # Output: stdout or single file?
    if output_path == "-":
        use_stdout = True
        output_path = "-"
    else:
        use_stdout = (
            output_path is None or output_path == "-"
        ) and not sys.stdout.isatty()
    if output_path is None:
        if use_stdout:
            output_path = "-"
        elif use_stdin:
            output_path = f"{restore_file or 'stdin'}.qr.pdf"  # Local directory
        elif len(input_paths) == 1:
            output_path = f"{input_paths[0]}.qr.pdf"  # Same directory
        elif use_tar:
            output_path = f"{restore_file}.qr.pdf"  # Local directory
        else:
            assert False

    # Set more complicated default options
    if use_shuffle is None:
        use_shuffle = use_erasure_coding

    if use_encryption and print_passphrase is None:
        print_passphrase = encryption_passphrase is None

    if use_encryption and not program_present("gpg"):
        show_help(
            "gpg must be installed to use --encrypt. could not find gpg in the PATH", 7,
        )

    if GENERATE_DOCS and not program_present("pandoc"):
        show_help(
            "pandoc must be installed to use undocumented option --generate-docs.",
        )

    if use_erasure_coding:
        allowable_loss_fraction = DEFAULT_ALLOWABLE_LOSS
    else:
        allowable_loss_fraction = 0

    if GENERATE_DOCS:  # example.png should be reproducible
        backup_date = "2022-10-01"

    if backup_date is None:
        backup_date = datetime.date.today().strftime("%Y-%m-%d")

    nice_cmd = " ".join(
        [
            x
            for x in [
                "qr-backup",
                "--qr-version",
                str(qr_version),
                "--dpi",
                str(dpi),
                "--scale",
                str(scale),
                "--error-correction",
                "LMQH"[error_correction],
                "--page",
                str(page_w_points),
                str(page_h_points),
                "--compress" if use_compression else "--no-compress",
                "--filename",
                restore_file,
                "--encrypt ???" if use_encryption else None,
                "--use-erasure-coding" if use_erasure_coding else None,
                "--shuffle" if use_shuffle else "--no-shuffle" "-o",
                output_path,
            ]
            if x is not None
        ],
    )
    logging.info("Original arguments were: {}".format(repr(args)))
    logging.info("Command arguments parsed. Equivalent command: {}".format(nice_cmd))

    # ---------------- Argument parsing done --------------

    # open the file (or stdin, if "-" is passed as the file)
    if use_tar:
        logging.info("Creating tar file")
        f = create_tar(input_paths)
    elif use_stdin:
        f = sys.stdin.buffer
    else:
        assert len(input_paths) == 1
        try:
            f = open(input_paths[0], "rb")
        except FileNotFoundError:
            logging.fatal("File does not exist: {}".format(input_paths[0]))
            sys.exit(2)

    # read the entire file into memory
    try:
        original_content = f.read()
    finally:
        f.close()

    sha256sum = hashlib.sha256(original_content).hexdigest()
    original_len = len(original_content)
    logging.info(f"read file {restore_file} (sha {sha256sum}, {original_len/1000}KB)")

    content = original_content

    # (Gzip) Compression
    if use_compression:
        content = gzip.compress(content, mtime=0)
        # This makes CI tests pass, see https://github.com/python/cpython/issues/112346
        content = bytearray(content)
        content[9] = 255
        content = bytes(content)

    # Encryption
    if use_encryption:
        if encryption_passphrase is None:
            encryption_passphrase = generate_passphrase()
            print(
                "Your secret encryption passphrase is: {}".format(
                    encryption_passphrase,
                ),
                file=sys.stderr,
            )
            print(
                "Back this up somewhere secure or you will be unable to access your data",
                file=sys.stderr,
            )
        content = encrypt(content, encryption_passphrase)

    # Add a length at the start
    content, range_ = length_encode(content)

    # Generate QR codes
    code_digits, qr_padding, qrs = qr_codes(
        content,
        error_correction=error_correction,
        version=qr_version,
        scale=scale,
        do_checks=do_checks,
        allowable_loss_fraction=allowable_loss_fraction,
    )

    # Additional copies
    qrs = qrs * num_copies

    # Shuffle order of QR codes
    if use_shuffle:
        qrs = shuffle(qrs)

    # Re-write labels to be clearer to the end user
    for i, qr in enumerate(qrs):
        label = f"code {i+1:0>{code_digits}}/{len(qrs):0>{code_digits}} ({qr.label})"
        qr.label = label

    # How to restore
    restore_cmd = f'sort -u | grep "^N" | cut -c{code_digits*2+4}- | base64 -d | tail -c +{range_[0]+1} | head -c {range_[1]}'
    if use_encryption:
        restore_cmd += " | gpg --decrypt"
    if use_compression:
        restore_cmd += " | gunzip"
        nice_cmd = nice_cmd
    logging.info(f"Restore command is: {restore_cmd}")

    # Instructions depend on the command line options, and the content of the file
    #
    # NOTE: Changing any of the below will mean you need to re-bless the
    # reproducibility results. For safety split the changes in half -- make sure
    # the test pass without updated instructions, then change the instructions and
    # tests and nothing else in a second commit.
    HOWTO = f"This is a paper backup of a computer file called: {restore_file}"
    HOWTO += "\nTo restore this file using qr-backup:"
    HOWTO += "\n  Step 1 (webcam): qr-backup --restore"
    HOWTO += "\n  Step 1 (scanner): qr-backup --restore IMAGE1 IMAGE2 ..."
    HOWTO += "\nTo restore this file from the command line:"
    HOWTO += f"\n  Step 1 (webcam option): zbarcam --raw | tee /tmp/qrs | cut -c1-{code_digits+1} # Scan each code at least once in any order"
    HOWTO += "\n  Step 1 (scanner option): zbarimg -q --raw *.png >/tmp/qrs"
    howto_restore_cmd = restore_cmd.replace("sort -u", "sort -u /tmp/qrs")
    HOWTO += f"\n  Step 2 (restore): {howto_restore_cmd} >{restore_file}"
    HOWTO += f"\n  Step 3 (verify): sha256sum {restore_file} # {sha256sum}, {original_len} bytes"
    nice_doc = f"\nThis backup was generated on {backup_date} with: {nice_cmd}"
    HOWTO += "\n".join(
        textwrap.wrap(
            nice_doc, subsequent_indent="    ", width=150, replace_whitespace=False,
        ),
    )
    if len(notes) > 0:
        HOWTO += "\n" + "\n".join(notes)

    # Print encyrption passphrase
    if encryption_passphrase is None:
        passphrase_instructions = None
    else:
        passphrase_instructions = "File: {}\nDate: {}\nYour secret passphrase is: {}\n\nMake sure to hide this sheet somewhere secure, not with your backup!".format(
            restore_file, backup_date, encryption_passphrase,
        )

    cover_txt = COVER.format(
        backup_date=backup_date,
        restore_file=restore_file,
        original_len=original_len,
        sha256sum=sha256sum,
        nice_cmd="\n".join(
            textwrap.wrap(
                nice_cmd, subsequent_indent="    ", width=130, replace_whitespace=False,
            ),
        ),
        notes=(
            "\n".join(["Additional note: " + note for note in notes]) + "\n"
            if len(notes) > 0
            else ""
        ),
        code_end=code_digits + 1,
        howto_restore_cmd=howto_restore_cmd,
    )

    pages = generate_pdf(
        qrs=qrs,
        dpi=dpi,
        page_w_points=page_w_points,
        page_h_points=page_h_points,
        qr_padding=qr_padding,
        page_instructions=HOWTO if add_page_instructions else None,
        cover_instructions=cover_txt if add_cover_instructions else None,
        passphrase_instructions=passphrase_instructions,
        minimize_size=GENERATE_DOCS,
        _qr_version=qr_version,  # logging only
        _original_len=original_len,  # logging only
        _len_content=len(content),  # logging only
    )

    # PIL's pdf writer needs to mmap, so it can't accept sys.stdout directly
    tmp_pdf = io.BytesIO()
    pages[0].save(
        tmp_pdf,
        format="pdf",
        save_all=True,
        append_images=pages[1:],
        resolution=dpi,
        producer="qr-backup",
        title=f"qr-backup paper backup of {restore_file} with sha256 {sha256sum} and length {original_len}",
        creationDate=backup_date,
        modDate=backup_date,
    )

    if GENERATE_DOCS:
        do_checks = False
    elif use_stdout:
        logging.info("Outputting to stdout")
        # Write PDF to stdout
        sys.stdout.buffer.write(tmp_pdf.getbuffer())
    else:
        logging.info("Outputting: {}".format(output_path))
        # Write PDF to file
        with open(output_path, "wb") as f:
            f.write(tmp_pdf.getbuffer())

    # Self-test
    if do_checks:
        self_test_restore(
            restore_cmd,
            input_path=input_paths[0],
            output_path=output_path,
            output_buffer=tmp_pdf.getbuffer(),
            original_content=original_content,
            use_buffers=use_tar or use_stdout or use_stdin,
            sha256sum=sha256sum,
            use_encryption=use_encryption,
            encryption_passphrase=encryption_passphrase,
            expected_qrs=len(qrs),
        )
    else:
        logging.info("Skipping checks (--skip-checks passed).")

    # --generate-docs secret flag
    if GENERATE_DOCS:
        generate_docs(pages)


def generate_pdf(
    qrs,
    dpi,
    page_w_points,
    page_h_points,
    page_instructions,
    cover_instructions,
    qr_padding,
    passphrase_instructions,
    minimize_size,
    _qr_version,
    _len_content,
    _original_len,
):
    # Calculate QR padding produced by qrcode module
    example_qr = qrs[0].qr.make_image().get_image().copy()
    qr_raw_w_pixel, qr_raw_h_pixel = example_qr.size

    # Output QR codes with labels to Pillow Image objects
    labeled = []
    for i, qr in enumerate(qrs):
        img = qr.qr.make_image().get_image()
        labeled.append(add_label(img, qr.label))
    logging.info(f"{len(qrs)} qr codes (at version {_qr_version}) total")

    # Figure out page layout now that we know the size and number of QR codes. Output to the user.
    qr_w_pixel, qr_h_pixel = labeled[0].size
    logging.info(f"QR code (including label) is: {qr_w_pixel}x{qr_w_pixel}px")

    page_w_pixel, page_h_pixel = math.floor(page_w_points / 72.0 * dpi), math.floor(
        page_h_points / 72.0 * dpi,
    )  # 1 "dot" = 1 pixel. !!important note, DPI is not used yet, which is probably some config bug in Pillow
    logging.info(f"Page is: {page_w_pixel}x{page_h_pixel}px")

    if page_instructions is not None:
        howto_label = generate_label(page_instructions, page_w_pixel)
        howto_height = howto_label.size[1]
    else:
        howto_height = 0

    def max_units_with_padding(total_size, unit_size, padding_size):
        """Calculate the (whole) number of units of width UNIT_SIZE with required padding PADDING_SIZE fit in a layout of width TOTAL_SIZE"""
        # (qr_width*qrs) + (qr_padding*(qrs-1)) <= page_width
        # (qr_width+qr_padding)qrs - qr_padding <= page_width
        # qrs <= (page_width+qr_padding)/(qr_width+qr_padding)
        return int((total_size + padding_size) / (unit_size + padding_size))

    page_w_qr, page_h_qr = max_units_with_padding(
        page_w_pixel - 2, qr_w_pixel, qr_padding,
    ), max_units_with_padding(page_h_pixel - 2 - howto_height, qr_h_pixel, qr_padding)
    qr_per_page = page_w_qr * page_h_qr
    if qr_per_page == 0:
        logging.error("Not even 1 QR fits on the given page. Forcing output anyway...")
        page_w_qr, page_h_qr, qr_per_page = 1, 1, 1
    num_qr_pages = math.ceil(len(qrs) / qr_per_page)
    logging.info(
        f"{page_w_qr} x {page_h_qr} qr codes (at version {_qr_version}) per page. {num_qr_pages} pages total",
    )

    uncompressed_density = _len_content / num_qr_pages
    compressed_density = _original_len / num_qr_pages
    logging.info(
        f"{_len_content} compressed bytes in {num_qr_pages} page(s). {compressed_density/1000:.2f}KB/page including compression, {uncompressed_density/1000:.2f}KB/page without compression",
    )
    theory_density_per_qr = _original_len / len(qrs)
    theory_density = theory_density_per_qr * qr_per_page
    logging.info(f"{theory_density/1000:.2f}KB/page theory without compression)")

    qr_min_padded_height = max(qr_h_pixel, qr_raw_h_pixel + qr_padding)
    qr_v_padding = qr_min_padded_height - qr_h_pixel

    # Combine rows, adding horizontal padding
    rows = []
    for row_start in range(0, len(qrs), page_w_qr):
        row_qrs = labeled[row_start : row_start + page_w_qr]
        rows.append(h_merge(row_qrs, padding=qr_padding))

    # Use imagemagick to make one png file per page-side
    unnumbered_images = []
    if passphrase_instructions is not None:
        passphrase_image = generate_label(
            passphrase_instructions, max_width=page_w_pixel - 2,
        )
        unnumbered_images.append((False, passphrase_image))
    if cover_instructions:
        cover_img = generate_label(
            cover_instructions, page_w_pixel - 2, max_fontsize=24, min_fontsize=24,
        )
        assert cover_img.size[0] <= page_w_pixel - 2
        unnumbered_images.append((True, cover_img))
    for page_start in range(0, len(rows), page_h_qr):
        page_rows = rows[page_start : page_start + page_h_qr]
        page_qrs = v_merge(page_rows, padding=qr_v_padding)
        if page_instructions is not None:
            page_complete = add_label(
                page_qrs,
                page_instructions,
                side="top",
                max_fontsize=24,
                max_width=page_w_pixel - 2,
            )
            unnumbered_images.append((True, page_complete))
        else:
            unnumbered_images.append((True, page_qrs))

    # Add a rectangle border and pad any small ones to full-page size
    unnumbered_pages = []
    for should_number, img in unnumbered_images:
        # assert img.size[0] <= page_w_pixel-2 and img.size[1] <= page_h_pixel-2
        if minimize_size:
            page_h_pixel = img.size[1] + 2  # minimize size for example.png
        page = PIL.Image.new(
            mode=IMAGE_MODE, size=(page_w_pixel, page_h_pixel), color=WHITE,
        )
        page_draw = PIL.ImageDraw.Draw(page)
        page_draw.rectangle(
            ((0, 0), (page_w_pixel - 1, page_h_pixel - 1)),
            outline=BLACK,
            fill=WHITE,
            width=1,
        )  # Rectangle for debugging print cutoff, and to look nice.
        page.paste(img, (1, 1))  # Main contents
        unnumbered_pages.append((should_number, page))

    # Add page numbers after. Currently page-numbering is perfectly reliable, but we're about to add more complicated layout options.
    pages = []
    num_pages = len(unnumbered_pages)
    for page_num, (should_number, page) in enumerate(unnumbered_pages):
        if should_number:
            page_num = generate_label(
                "page {}/{}".format(page_num + 1, num_pages),
                max_width=example_qr.size[0] / 2,
            )
            page.paste(
                page_num,
                (
                    page.size[0] - page_num.size[0] - 1,
                    page.size[1] - page_num.size[1] - 11,
                ),
            )  # Page num in bottom-right
        pages.append(page)

    return pages


def generate_docs(pages):
    """
    Secret --generate-docs flag updates
    - docs/example.png
    - docs/qr-backup.1.man (a groff man file)
    - docs/MAN.txt (easy-to-read man page)
    """
    pages[0].save("docs/example.png")

    man_md = MAN_MD.format(
        VERSION=VERSION,
        MAN_MONTH=datetime.datetime.now().strftime("%B %Y"),
        both_options=man_options(BOTH_OPTIONS),
        backup_options=man_options(BACKUP_OPTIONS),
        restore_options=man_options(RESTORE_OPTIONS),
    ).replace(
        "--", r"-\-",
    )  # avoid en-dash in converted man page
    with open("docs/qr-backup.1.man", "w") as f:
        subprocess.run(
            ["pandoc", "-s", "-t", "man"], input=man_md.encode("utf8"), stdout=f,
        )

    with open("docs/MAN.txt", "w") as f:
        subprocess.run(
            ["man", "-l", "docs/qr-backup.1.man"], stdout=f, env={"MANWIDTH": "80"},
        )

    with open("docs/USAGE.md", "w") as f:
        f.write("Output of `qr-backup --help`:\n\n```\n")
        f.flush()
        subprocess.run(["./qr-backup", "--help"], stdout=f)
        f.write("```\n")


def self_test_restore(
    restore_cmd,
    input_path,
    output_path,
    output_buffer,
    original_content,
    use_buffers,
    sha256sum,
    use_encryption,
    encryption_passphrase,
    expected_qrs,
):
    if use_encryption:
        test_restore_cmd = restore_cmd.replace(
            "gpg --decrypt",
            "gpg --decrypt --no-symkey-cache --batch --passphrase '{}'".format(
                encryption_passphrase,
            ),
        )
        logging.info("Restore command used in command-line test: " + test_restore_cmd)
    else:
        test_restore_cmd = restore_cmd

    if not program_present("zbarimg"):
        logging.warning(
            "Skipping digital restore verification, because zbarimg is not available.",
        )
        # sys.exit(6)
    elif not program_present("convert"):
        # convert is needed to work around a bug in zbarimg
        logging.warning(
            "Skipping digital restore verification, because 'convert' is not available.",
        )
        # sys.exit(5)
    elif ubuntu_policy_problem():
        logging.warning(
            "Skipping digital restore verification, because 'convert' forbids PDF conversion. More information at: https://github.com/za3k/qr-backup/blob/master/docs/FAQ.md#my-self-test-is-failing-on-ubuntu",
        )
        # sys.exit(5)
    else:
        if use_buffers:
            logging.info("self-test using buffers")
            logging.info("Performing command-line restore check...")
            # convert -density 300 is to work around errors in zbarimg. I offered an upstream patch as https://github.com/mchehab/zbar/pull/227
            linux_test_command = "convert -density {} pdf:- tif:- | zbarimg --raw -q -Sdisable -Sqrcode.enable - | {}".format(
                CONVERSION_DENSITY, test_restore_cmd,
            )
            linux_test_rate_command = "convert -density {} pdf:- tif:- | zbarimg --raw -q -Sdisable -Sqrcode.enable - | wc -l".format(
                CONVERSION_DENSITY )
            logging.info("Command-line command was: {}".format(linux_test_command))
            linux_test = subprocess.run(
                linux_test_command, shell=True, capture_output=True, input=output_buffer,
            )
            linux_success = (
                linux_test.returncode == 0 and linux_test.stdout == original_content
            )
            logging.info("Command-line exit code was: {}".format(linux_test.returncode))
            logging.info("Test command was: {}".format(linux_test_rate_command))
            linux_test_rate = subprocess.run(
                linux_test_rate_command,
                shell=True,
                capture_output=True,
                input=output_buffer,
            )

            logging.info("Performing qr-backup restore check...")
            self_test_command = [
                "python3",
                sys.argv[0],
                "--restore",
                "--sha256",
                sha256sum,
                "-",
            ]
            if use_encryption:
                self_test_command += ["--encrypt", encryption_passphrase]
            self_test = subprocess.run(
                self_test_command, capture_output=True, input=output_buffer,
            )
            self_test_success = self_test.returncode == 0
            logging.info("Self-test command was: {}".format(self_test_command))
            logging.info("Self-test exit code was: {}".format(self_test.returncode))
        else:
            logging.info("self-test using files")
            logging.info("Performing command-line restore check...")
            linux_test_command = "convert -density {} {} tif:- | zbarimg --raw -q -Sdisable -Sqrcode.enable - | {} | cmp {}".format(
                CONVERSION_DENSITY, output_path, test_restore_cmd, input_path,
            )
            linux_test_rate_command = "convert -density {} {} tif:- | zbarimg --raw -q -Sdisable -Sqrcode.enable - | wc -l".format(
                CONVERSION_DENSITY, output_path )
            logging.info("Command-line command was: {}".format(linux_test_command))
            linux_returncode = subprocess.call(
                linux_test_command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            linux_success = linux_returncode == 0
            logging.info("Command-line exit code was: {}".format(linux_returncode))
            logging.info("Test command was: {}".format(linux_test_rate_command))
            linux_test_rate = subprocess.run(
                linux_test_rate_command, shell=True, capture_output=True,
            )

            logging.info("Performing qr-backup restore check...")
            self_test_command = [
                "python3",
                sys.argv[0],
                "--restore",
                "--sha256",
                sha256sum,
                output_path,
            ]
            if use_encryption:
                self_test_command += ["--encrypt", encryption_passphrase]
            self_test_returncode = subprocess.call(
                self_test_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self_test_success = self_test_returncode == 0
            logging.info("Self-test command was: {}".format(self_test_command))
            logging.info("Self-test exit code was: {}".format(self_test_returncode))

        qrs_read = int(linux_test_rate.stdout)
        qrs_fraction_read = qrs_read / expected_qrs
        logging.info(
            "Read {}/{} qrs ({:.2f}%)".format(
                qrs_read, expected_qrs, qrs_fraction_read * 100,
            ),
        )
        if not self_test_success:
            logging.error(
                "!!Automatic digital restore verification FAILED (self-test). This indicates a bug in qr-backup. Please report this to the author at https://github.com/za3k/qr-backup/issues",
            )
            sys.exit(3)
        elif not linux_success:
            if qrs_fraction_read < ZBAR_WARNING_THRESHOLD:
                logging.info(
                    "!!Automatic digital restore verification FAILED (command-line). This indicates a bug in zbarimg, most likely. Please report this to the author at https://github.com/za3k/qr-backup/issues",
                )
            else:
                logging.info(
                    "!!Automatic digital restore verification FAILED (command-line). This indicates a bug in qr-backup (more likely) or zbarimg. Please report this to the author at https://github.com/za3k/qr-backup/issues",
                )
            # sys.exit(3)
        else:
            logging.info("Automatic digital restore verification succeeded.")


def image_restore(image_paths):
    # Special note: image_paths can include "-", in which case zbarimg will magically do the right thing
    if not program_present("zbarimg"):
        logging.fatal("zbarimg not found. install 'zbar' to scan files.")
        sys.exit(6)

    # Special workaround hack while zbarimg doesn't deal with pdfs
    def _remove_file(t):
        try:
            os.unlink(t)
        except FileNotFoundError:
            pass

    def _is_pdf(path):
        return path.endswith(".pdf") or path == "-"

    if any(_is_pdf(path) for path in image_paths):
        if ubuntu_policy_problem():
            logging.fatal(
                "Restore is not available for PDFs. Your system forbids converting a PDF to an image with imagemagick. More information at: https://github.com/za3k/qr-backup/blob/master/docs/FAQ.md#my-self-test-is-failing-on-ubuntu",
            )
            sys.exit(5)

        temporary = []
        new_image_paths = []
        for image in image_paths:
            if _is_pdf(image):
                logging.info("Converting to tif: {}".format(image))
                handle, temp_tif = tempfile.mkstemp(suffix=".tif")
                temporary.append((handle, temp_tif))
                atexit.register(_remove_file, temp_tif)
                result = subprocess.run(
                    ["convert", "-density", str(CONVERSION_DENSITY), image, temp_tif],
                    capture_output=True,
                )
                if result.returncode != 0:
                    logging.info("[convert stdout] {}".format(result.stdout))
                    logging.info("[convert stderr] {}".format(result.stderr))
                    logging.fatal("Conversion from PDF to TIF failed: {}".format(image))
                    sys.exit(5)
                new_image_paths.append(temp_tif)
            else:
                logging.info("Directly reading: {}".format(image))
                new_image_paths.append(image)
        for line in image_restore(new_image_paths):
            yield line
        for handle, temp_tif in temporary:
            os.close(handle)
            _remove_file(temp_tif)
        atexit.unregister(_remove_file)

    scan_command = [
        "zbarimg",
        "--raw",
        "-q",
        "-Sdisable",
        "-Sqrcode.enable",
    ] + image_paths
    result = subprocess.run(scan_command, capture_output=True)
    for line in result.stdout.split(b"\n"):
        if line != b"":
            yield line
    logging.info("[zbarimg stderr] {}".format(result.stderr))


def webcam_restore(use_display):
    if not program_present("zbarcam"):
        logging.fatal("zbarcam not found. install 'zbar' to scan using your camera.")
        sys.exit(6)

    scan_command = ["zbarcam", "--raw", "-Sdisable", "-Sqrcode.enable"]
    if use_display:
        input(WEBCAM_MESSAGE)
    else:
        scan_command.append("--nodisplay")

    with subprocess.Popen(
        scan_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ) as proc:
        while True:
            line = proc.stdout.readline()
            if line == b"":
                return
            if (yield line.strip()):  # Exit early on request
                return


def expected_codes_type(_, counts, code_type):  # Returns a list of binary strings
    num_normal = counts[b"N"]
    assert num_normal is not None
    code_digits = math.ceil(math.log(num_normal + 1, 10))

    num_type = counts[code_type]
    if code_type == b"P" and num_type is None:
        num_type = erasure_count(DEFAULT_ALLOWABLE_LOSS)
    return [
        code_type + f"{i:>0{code_digits}}".encode("ascii")
        for i in range(1, num_type + 1)
    ]


def expected_codes(_, counts, use_erasure=None):  # Returns a list of binary strings
    num_normal = counts[b"N"]
    if num_normal is None:
        return None
    if use_erasure is None:
        use_erasure = counts[b"P"] is not None

    code_digits = math.ceil(math.log(num_normal + 1, 10))
    normal, erasure = expected_codes_type(_, counts, b"N"), []
    if use_erasure:
        erasure = expected_codes_type(_, counts, b"P")
    else:
        erasure = []
    return normal + erasure


def restore_status(codes, counts, use_erasure=None):
    if counts[b"N"] is None:
        return f"{len(codes)}/??? codes read"
    expected = expected_codes(codes, counts, use_erasure=use_erasure)
    missing = [x.decode("ascii") for x in expected if x not in codes]
    return (
        f"Missing {len(missing)}/{len(expected)} codes: "
        + " ".join(x for x in missing[:5])
        + (" ..." if len(missing) > 5 else "")
    )


def is_complete(codes, totals, extra_wanted=0, use_erasure=None):
    # TODO: Logic is wrong for >256 block codes.
    # The correct solution is to carefully lay out: you need any 177 codes out of these 256, 177 out of these 256, and 120 out of these 150.
    # Instead, we just say "yes" once it's even vaguely plausible. If we try to restore and it fails, we up the number.
    if totals[b"N"] is None:
        return False
    logging.info("{}/{}? complete".format(len(codes), totals[b"N"]))
    return len(codes) >= totals[b"N"] + extra_wanted


def do_restore(
    codes, totals, use_erasure, use_compression, use_encryption, encryption_passphrase,
):
    assert is_complete(codes, totals, use_erasure=use_erasure)

    # Base-64 decode (per qr-code)
    decoded = {k: base64.b64decode(v) for k, v in codes.items()}

    if use_erasure:
        # Erasure decode
        normal_codes = [
            decoded.get(expected_code)
            for expected_code in expected_codes_type(codes, totals, b"N")
        ]
        erasure_codes = [
            decoded.get(expected_code)
            for expected_code in expected_codes_type(codes, totals, b"P")
        ]
        content = restore_erasure(normal_codes, erasure_codes, DEFAULT_ALLOWABLE_LOSS)
    else:
        # Concat
        content = b"".join(decoded[x] for x in expected_codes(codes, totals))

    # Remove padding
    content = length_decode(content)

    # Decrypt
    if use_encryption is None:
        use_encryption = content.startswith(b"-----BEGIN PGP MESSAGE-----")
    if use_encryption is True:
        content = decrypt(content, encryption_passphrase)

    # Decompress
    if use_compression is True:
        content = gzip.decompress(content)
    elif use_compression is None:  # automatic determination
        try:
            content = gzip.decompress(content)
            use_compression = True
        except gzip.BadGzipFile:
            use_compression = False

    return content


def content_matches_checksum(content, expected_sha256sum):
    sha256sum = hashlib.sha256(content).hexdigest()
    return checksum_matches(sha256sum, expected_sha256sum)


def checksum_matches(sha256sum, expected_sha256sum):
    logging.info("restored sha256sum: {}".format(sha256sum))
    if expected_sha256sum is None:
        logging.debug("no expected sha256sum was given")
        print(
            f"sha256sum was as follows, please check against your paper backup: {sha256sum}",
            file=sys.stderr,
        )
    elif expected_sha256sum == sha256sum:
        logging.debug("sha256sum matched")
        # print("File verified using sha256 checksum.", file=sys.stderr)
    elif sha256sum.startswith(expected_sha256sum):
        logging.debug("sha256sum partial matched")
        print(
            f"The actual sha256sum begins with checksum given on the command line, but it was not complete. The full checksum was: {sha256sum}",
            file=sys.stderr,
        )
    else:
        logging.error("sha256sum did not match")
        print(
            "!!The restored file does NOT match the expected checksum. Restoring anyway.",
            file=sys.stderr,
        )
        return False
    return True


def main_restore(args):
    # Default config
    restore_method = None  # Should be one of: None, "webcam", "images"

    output_path = None  # Should be one of: None (for use_stdout), file path
    use_stdout = False
    totals = {
        b"N": None,
        b"P": None,
    }  # Values should be one of: None (infer) or a number
    use_display = True

    expected_sha256sum = None
    use_compression = None
    use_encryption = None
    encryption_passphrase = None
    use_erasure = None
    verbose = False

    # Parse command-line arguments
    pargs = []
    while len(args) > 0:
        arg, args = args[0], args[1:]
        if arg in ["-h", "--help"]:
            show_help()
        elif arg == "--code-count-erasure":
            if len(args) < 1:
                show_help("{} requires one argument".format(arg))
            totals[b"P"], args = int(args[0]), args[1:]
        elif arg == "--code-count-normal":
            if len(args) < 1:
                show_help("{} requires one argument".format(arg))
            totals[b"N"], args = int(args[0]), args[1:]
        elif arg == "--compress":
            use_compression = True
        elif arg == "--display":
            use_display = True
        elif arg == "--encrypt":
            if len(args) < 1:
                show_help("{} requires one argument".format(arg))
            use_encryption = True
            encryption_passphrase, args = args[0], args[1:]
        elif arg == "--image-restore":
            restore_method = "images"
        elif arg == "--no-compress":
            use_compression = False
        elif arg == "--no-display":
            use_display = False
        elif arg == "--no-encrypt":
            use_encryption = False
        elif arg in ["-o", "--output"]:
            if len(args) < 1:
                show_help("{} requires one argument".format(arg))
            output_path, args = args[0], args[1:]
        elif arg == "--sha256":
            if len(args) < 1:
                show_help("{} requires one argument".format(arg))
            expected_sha256sum, args = args[0].lower(), args[1:]
            if (
                not all(x in "0123456789abcdef" for x in expected_sha256sum)
                or len(expected_sha256sum) > 64
            ):
                show_help("Not a valid SHA256: {}".format(expected_sha256sum))
        elif arg in ["-v", "--verbose"]:
            verbose = True
        elif arg == "--webcam-restore":
            restore_method = "webcam"
        elif arg == "-":
            pargs.append(arg)
        elif arg == "--":
            # Stop parsing arguments
            pargs, args = pargs + args, []
        elif arg.startswith("-"):
            show_help()
        else:
            pargs.append(arg)

    if verbose:
        logging.basicConfig(format=LOGGING_FORMAT, level=logging.INFO)
    else:
        logging.basicConfig(format=LOGGING_FORMAT, level=logging.FATAL)

    assert (
        len([x for x in pargs if x == "-"]) <= 1
    ), "stdin can be listed as an image only once"
    if restore_method is None and len(pargs) == 0 and not sys.stdin.isatty():
        logging.debug("Reading from stdin")
        restore_method = "images"
        pargs = ["-"]
    elif restore_method is None and len(pargs) == 0:
        restore_method = "webcam"
    elif restore_method is None and len(pargs) > 0:
        restore_method = "images"

    if output_path is None:
        use_stdout = True
    if use_stdout and sys.stdout.isatty():
        logging.fatal(
            "WARNING: Printing file directly to interactive stdout. You probably want to run qr-backup >filename. Press Control-C to exit.",
        )

    if use_encryption and not program_present("gpg"):
        show_help(
            "gpg must be installed to use --encrypt. could not find gpg in the PATH",
        )

    # ---------------- Argument parsing done --------------

    # Call a subprocess to do the restore
    if restore_method == "images":
        logging.info("image restore selected")
        restore_generator = image_restore(pargs)
    elif restore_method == "webcam":
        logging.info("webcam restore selected")
        restore_generator = webcam_restore(use_display=use_display)
    else:
        assert False

    # Scan codes one at a time until done
    codes = {}
    codes_by_type = {b"N": set(), b"P": set()}
    extra_wanted = 0
    while True:
        # Print status line
        if restore_method == "webcam":
            if totals[b"N"] is None:
                print("Hold up QR codes to the webcam in any order.", file=sys.stderr)
            else:
                print(
                    restore_status(codes, totals, use_erasure=use_erasure),
                    file=sys.stderr,
                )

        # Read the next code as binary data
        try:
            # TODO: Is there any reason not to just read every code from the image immediately? Re-re do this logic to be simpler post-erasure, I think.
            read_code = next(restore_generator)
        except StopIteration:
            logging.fatal(
                "Not enough codes could be read to restore the file. Exiting.",
            )
            sys.exit(4)

        # Parse the label out
        assert b"\n" not in read_code
        code_label, content = read_code.split(b" ", maxsplit=1)
        code_type, (code_num, total) = code_label[0:1], code_label[1:].split(b"/")
        code_num = code_type + code_num
        total = int(total.decode("ascii"))

        if totals[code_type] is None:
            totals[code_type] = total
        elif totals[code_type] == total:
            pass
        elif (
            totals[code_type] != total and len(codes_by_type[code_type]) == 0
        ):  # xxx: len(normal_codes) == 0
            option = {b"N": "--code-count-normal", b"P": "--code-count-erasure"}
            logging.fatal(
                "Code count disagrees with {option} option (Code={}, {option}={})".format(
                    code_label.decode("ascii"), totals[code_type], option=option,
                ),
            )
            sys.exit(4)
        elif totals[code_type] != total and len(codes_by_type[code_type]) != 0:
            logging.fatal(
                "Code count disagrees for codes: {} & {}".format(
                    code_label, next(iter(codes_by_type[code_type])),
                ),
            )
            sys.exit(4)
        else:
            assert False
        assert totals[code_type] is not None

        # Add the code
        if code_num in codes and codes[code_num] == content:
            logging.info(f"Read duplicate code {code_num}: IDENTICAL")
        elif code_num in codes and codes[code_num] != content:
            logging.error(f"Read duplicate code {code_num}: DIVERGES")
        elif code_num not in codes:
            logging.info(f"Read new code {code_num}")
        else:
            assert False
        codes[code_num] = content
        codes_by_type[code_type].add(code_num)

        if is_complete(
            codes, totals, extra_wanted, use_erasure=use_erasure,
        ):  # More complicated - no specific set of codes
            # Erasure coding
            if use_erasure is None:
                use_erasure = totals[b"P"] is not None

            # Do the restore
            try:
                content = do_restore(
                    codes,
                    totals,
                    use_compression=use_compression,
                    use_encryption=use_encryption,
                    encryption_passphrase=encryption_passphrase,
                    use_erasure=use_erasure,
                )
                break
            except reedsolo.ReedSolomonError:
                logging.info("Tried decoding. Requesting more codes")
                # Request more codes
                assert totals[b"N"] is not None
                max_extra_wanted = erasure_count(totals[b"N"], DEFAULT_ALLOWABLE_LOSS)
                if extra_wanted == max_extra_wanted:
                    logging.fatal("Invalid number of parity codes expected")
                    sys.exit(4)
                extra_wanted = min(extra_wanted + 10, max_extra_wanted)

    # Close subprocess
    try:
        restore_generator.send(True)
    except StopIteration:
        pass

    # Check the checksum
    if content_matches_checksum(content, expected_sha256sum):
        exit_status = 0
    else:
        exit_status = 4

    # Write the output
    if use_stdout:
        sys.stdout.buffer.write(content)
    else:
        with open(output_path, "wb") as f:
            f.write(content)

    sys.exit(exit_status)


def main_version():
    print("qr-backup v{}".format(VERSION))
    sys.exit(0)


# TODO: Split out argument parsing
if __name__ == "__main__":
    # parse command-line arguments
    args = sys.argv[1:]
    if len(args) == 1 and args[0] in ["-V", "--version"]:
        main_version()
    elif len(args) >= 1 and args[0] in ["-r", "--restore"]:
        main_restore(args[1:])
    else:
        main_backup(args)
