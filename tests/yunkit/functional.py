#!/usr/bin/env python3
"""云匣功能自测（不需要屏幕）：压缩包浏览/取出/压缩/解压、回收站、复制移动、批量重命名逻辑、缩略图生成。
用法：QT_QPA_PLATFORM=offscreen python3 tests/yunkit/functional.py"""
import os, shutil, sys, tempfile, zipfile, tarfile, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../config/includes.chroot/usr/lib/serenecloud/yunkit"))
tmp = tempfile.mkdtemp()
os.environ["HOME"] = tmp
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, ".local/share")
os.environ["XDG_CACHE_HOME"] = os.path.join(tmp, ".cache")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QColor
app = QApplication(sys.argv)
from yunkit import vfs, thumbs, ops, util

ok = 0
def check(cond, msg):
    global ok
    if not cond:
        print("✗", msg); sys.exit(1)
    ok += 1; print("✓", msg)

d = os.path.join(tmp, "work"); os.makedirs(os.path.join(d, "子文件夹"))
open(os.path.join(d, "a.txt"), "w").write("你好")
open(os.path.join(d, "子文件夹", "b.txt"), "w").write("b")
img = QImage(300, 200, QImage.Format.Format_RGB32); img.fill(QColor("#4F8CC9")); img.save(os.path.join(d, "p.png"))
# 压缩成 zip / tar.gz / 7z，再当文件夹浏览
for fmt in ("zip", "tar.gz", "7z"):
    if fmt == "7z" and not vfs._seven():
        print("- 跳过 7z（没装）"); continue
    out = os.path.join(tmp, "test." + fmt)
    vfs.compress([os.path.join(d, "a.txt"), os.path.join(d, "子文件夹")], out, fmt)
    names = sorted(e.name for e in vfs.list_loc(vfs.make_archive_loc(out, "")))
    check(names == ["a.txt", "子文件夹"], f"{fmt} 当文件夹看：{names}")
    inner = [e.name for e in vfs.list_loc(vfs.make_archive_loc(out, "子文件夹"))]
    check(inner == ["b.txt"], f"{fmt} 进子文件夹")
    p = vfs.extract_member(out, "a.txt")
    check(open(p).read() == "你好", f"{fmt} 取出单个文件")
    dst = os.path.join(tmp, "x-" + fmt)
    vfs.extract_all(out, dst)
    check(os.path.exists(os.path.join(dst, "子文件夹", "b.txt")), f"{fmt} 全部解压")
# 位置和面包屑
loc = vfs.make_archive_loc("/x/y.zip", "res/a")
check(vfs.parent_of(loc) == vfs.make_archive_loc("/x/y.zip", "res"), "压缩包里的上一级")
check(vfs.parent_of(vfs.make_archive_loc("/x/y.zip", "")) == "/x", "压缩包根的上一级是所在文件夹")
# 复制 / 移动 / 回收站 / 还原
def run(op, entries, dest=None):
    t = ops.FileOp(op, entries, dest); t.run()
d2 = os.path.join(tmp, "dest"); os.makedirs(d2)
run("copy", [vfs.local_entry(os.path.join(d, "子文件夹"))], d2)
check(os.path.exists(os.path.join(d2, "子文件夹", "b.txt")), "复制文件夹")
run("copy", [vfs.local_entry(os.path.join(d, "a.txt"))], d2)
run("copy", [vfs.local_entry(os.path.join(d, "a.txt"))], d2)
check(os.path.exists(os.path.join(d2, "a (2).txt")), "同名自动改成 a (2).txt")
run("move", [vfs.local_entry(os.path.join(d2, "a (2).txt"))], d)
check(os.path.exists(os.path.join(d, "a (2).txt")) and not os.path.exists(os.path.join(d2, "a (2).txt")), "移动")
zipp = os.path.join(tmp, "test.zip")
run("copy", [e for e in vfs.list_loc(vfs.make_archive_loc(zipp, "")) if e.name == "a.txt"], d2 + "/子文件夹")
check(os.path.exists(os.path.join(d2, "子文件夹", "a.txt")), "从压缩包复制到文件夹")
os.environ.pop("PATH_NO_GIO", None)
vfs.trash.__globals__["shutil"].which = (lambda real: (lambda c: None if c == "gio" else real(c)))(shutil.which)
run("trash", [vfs.local_entry(os.path.join(d, "a (2).txt"))])
tr = vfs.list_trash()
check(any(e.name == "a (2).txt" for e in tr), "放进回收站")
vfs.restore_trash([e for e in tr if e.name == "a (2).txt"][0])
check(os.path.exists(os.path.join(d, "a (2).txt")), "从回收站还原")
run("delete", [vfs.local_entry(os.path.join(d, "a (2).txt"))])
check(not os.path.exists(os.path.join(d, "a (2).txt")), "彻底删除")
# 缩略图
check(thumbs.generate(os.path.join(d, "p.png"), "image") is not None, "图片缩略图")
z = os.path.join(d, "app.apk")
with zipfile.ZipFile(z, "w") as zf:
    zf.write(os.path.join(d, "p.png"), "res/mipmap-xxhdpi-v4/ic_launcher.png")
check(thumbs.generate(z, "apk") is not None, "APK 图标")
if util.have("ffmpeg"):
    v = os.path.join(d, "v.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:d=2", "-pix_fmt", "yuv420p", v])
    check(thumbs.generate(v, "video") is not None, "视频缩略图")
    a = os.path.join(d, "s.mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", "-i", os.path.join(d, "p.png"),
                    "-map", "0", "-map", "1", "-c:v", "mjpeg", "-disposition:v", "attached_pic", "-id3v2_version", "3", a])
    check(thumbs.generate(a, "audio") is not None, "歌曲封面")
if util.have("pdftoppm"):
    from PyQt6.QtGui import QPdfWriter, QPainter
    pdf = os.path.join(d, "x.pdf"); w = QPdfWriter(pdf); pp = QPainter(w); pp.drawText(100, 100, "PDF"); pp.end()
    check(thumbs.generate(pdf, "pdf") is not None, "PDF 第一页")
print(f"全部通过：{ok} 项")
shutil.rmtree(tmp, ignore_errors=True)
