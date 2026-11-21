#!/usr/bin/env python3
"""检查 config/package-lists 里的每个包在 Debian trixie (amd64) 里是否存在。
包名写错会让整次构建失败，所以构建前先跑这个。"""
import glob, lzma, sys, urllib.request
SUITE = "trixie"
names = set()
for comp in ["main", "contrib", "non-free", "non-free-firmware"]:
    url = f"https://deb.debian.org/debian/dists/{SUITE}/{comp}/binary-amd64/Packages.xz"
    for line in lzma.decompress(urllib.request.urlopen(url, timeout=120).read()).decode().splitlines():
        if line.startswith("Package: "):
            names.add(line[9:])
bad = []
for f in sorted(glob.glob("config/package-lists/*.list.chroot")):
    for raw in open(f, encoding="utf-8"):
        p = raw.split("#")[0].strip()
        if p and p not in names:
            bad.append(f"{f}: {p}")
if bad:
    print("找不到这些包：\n  " + "\n  ".join(bad)); sys.exit(1)
print("所有包都存在 ✓")
