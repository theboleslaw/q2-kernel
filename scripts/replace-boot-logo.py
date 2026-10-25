#!/usr/bin/env python3
"""Replace the two boot logos inside a Q2 boot.img without rebuilding the kernel.

The Rockchip resource.img stored in boot.img's second section holds two
480x272 24-bit BMPs (U-Boot logo and kernel logo). This script swaps both for
a new BMP of exactly the same byte size and recomputes the Android boot header
id, so the result can be written back to the boot partition in place.

Usage:
  python3 replace-boot-logo.py original-boot.img new-logo.bmp output-boot.img

The new BMP must be 480x272, 24-bit, uncompressed (file size 391734 bytes).
Create one with:
  ffmpeg -i logo.png -f lavfi -i color=black:s=480x272 ... (see README.md)
"""
import hashlib
import struct
import sys

LOGO_OFFSETS = (57344, 449536)  # U-Boot logo, kernel logo inside resource.img
PAGE = 2048


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, logo_path, dst = sys.argv[1:]

    d = open(src, "rb").read()
    logo = open(logo_path, "rb").read()
    if len(logo) != 391734 or logo[:2] != b"BM":
        sys.exit("logo must be a 480x272 24-bit BMP of 391734 bytes")
    if d[:8] != b"ANDROID!":
        sys.exit("not an Android boot image")

    kernel_size, _, ramdisk_size, _, second_size, _, _, _ = struct.unpack("<8I", d[8:40])
    kp = PAGE
    kernel = d[kp:kp + kernel_size]
    rp = kp + ((kernel_size + PAGE - 1) // PAGE) * PAGE
    ramdisk = d[rp:rp + ramdisk_size]
    sp = rp + ((ramdisk_size + PAGE - 1) // PAGE) * PAGE

    res = bytearray(d[sp:sp + second_size])
    if res[:4] != b"RSCE":
        sys.exit("second section is not a Rockchip resource image")
    for off in LOGO_OFFSETS:
        if res[off:off + 2] != b"BM" or struct.unpack("<I", res[off + 2:off + 6])[0] != len(logo):
            sys.exit(f"unexpected logo layout at offset {off}")
        res[off:off + len(logo)] = logo

    new = bytearray(d)
    new[sp:sp + second_size] = res

    h = hashlib.sha1()
    h.update(kernel); h.update(struct.pack("<I", kernel_size))
    h.update(ramdisk); h.update(struct.pack("<I", ramdisk_size))
    h.update(bytes(res)); h.update(struct.pack("<I", second_size))
    new[576:576 + 32] = h.digest() + b"\x00" * 12

    open(dst, "wb").write(new)
    print(f"wrote {dst} ({len(new)} bytes)")


if __name__ == "__main__":
    main()
