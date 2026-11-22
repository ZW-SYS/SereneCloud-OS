#!/usr/bin/env python3
"""做一套测试文件（图片/视频/歌曲/PDF/小说/代码/压缩包/APK），给 shot.py 截图用。
用法：QT_QPA_PLATFORM=offscreen python3 tests/yunkit/make-fixtures.py 目标主文件夹"""
import os, subprocess, sys, tarfile, zipfile
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QFont, QImage, QPageSize, QPainter, QPdfWriter
from PyQt6.QtWidgets import QApplication

home = os.path.abspath(sys.argv[1])
app = QApplication(sys.argv)
for d in ("下载", "文档", "图片", "音乐", "视频", "桌面"):
    os.makedirs(os.path.join(home, d), exist_ok=True)
J = lambda *p: os.path.join(home, *p)


def ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=False)


ff("-f", "lavfi", "-i", "gradients=s=1280x800:c0=0x4F8CC9:c1=0xF7C873:duration=1", "-frames:v", "1", J("图片", "晚霞.jpg"))
ff("-f", "lavfi", "-i", "mandelbrot=s=800x600", "-frames:v", "1", J("图片", "分形.png"))
ff("-f", "lavfi", "-i", "life=s=300x200:mold=10:r=10:ratio=0.1:death_color=#4F8CC9:life_color=#FFFFFF", "-t", "2", J("图片", "生命游戏.gif"))
ff("-f", "lavfi", "-i", "cellauto=s=640x480:rule=110", "-frames:v", "1", J("图片", "元胞.webp"))
open(J("图片", "云.svg"), "w").write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 140"><rect width="200" height="140" rx="20" fill="#1B2029"/><g fill="#4F8CC9"><circle cx="70" cy="80" r="28"/><circle cx="105" cy="62" r="36"/><circle cx="140" cy="82" r="26"/><rect x="45" y="80" width="120" height="28" rx="14"/></g></svg>')
ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:d=6", "-f", "lavfi", "-i", "sine=f=440:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", J("视频", "测试视频.mp4"))
ff("-f", "lavfi", "-i", "mandelbrot=s=640x360:end_scale=0.1", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", J("视频", "分形动画.mkv"))
ff("-f", "lavfi", "-i", "gradients=s=500x500:c0=0xE06C75:c1=0x4F8CC9:duration=1", "-frames:v", "1", "/tmp/yk-cover.jpg")
ff("-f", "lavfi", "-i", "sine=f=330:d=5", "-i", "/tmp/yk-cover.jpg", "-map", "0", "-map", "1", "-c:a", "libmp3lame", "-c:v", "mjpeg", "-id3v2_version", "3", "-disposition:v", "attached_pic", J("音乐", "晴天.mp3"))
ff("-f", "lavfi", "-i", "mandelbrot=s=500x500", "-frames:v", "1", "/tmp/yk-cover2.png")
ff("-f", "lavfi", "-i", "sine=f=220:d=5", "-i", "/tmp/yk-cover2.png", "-map", "0", "-map", "1", "-c:a", "flac", "-c:v", "png", "-disposition:v", "attached_pic", J("音乐", "星空.flac"))
ff("-f", "lavfi", "-i", "sine=f=520:d=3", J("音乐", "小提示音.wav"))

w = QPdfWriter(J("文档", "云安OS说明书.pdf"))
w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
p = QPainter(w)
for i in range(3):
    if i:
        w.newPage()
    p.fillRect(QRectF(0, 0, w.width(), w.height() * 0.22), QColor("#4F8CC9"))
    f = QFont(); f.setPointSize(36); p.setFont(f); p.setPen(QColor("white"))
    p.drawText(QRectF(400, 600, w.width(), 1500), "云安 OS 说明书" if i == 0 else f"第 {i + 1} 页")
    f.setPointSize(14); p.setFont(f); p.setPen(QColor("#333"))
    for j in range(12):
        p.drawText(QRectF(400, 3000 + j * 500, w.width() - 800, 400), "这是一份用来测试缩略图的 PDF 文件。" * 2)
p.end()

ch = "一二三四五六七八九十"
s = "云端之下\n\n"
for i in range(10):
    s += f"第{ch[i]}章 云的方向\n\n" + ("　　天空很蓝，云慢慢地飘过城市。少年抬起头，想起了那个还没写完的系统。他打开电脑，敲下了第一行代码。\n\n" * 12)
open(J("文档", "云端之下.txt"), "w").write(s)
open(J("文档", "笔记.md"), "w").write("# 云安 OS 笔记\n\n今天做了 **云匣电脑版**。\n\n- 双栏\n- 缩略图\n- 压缩包当文件夹\n\n```python\nprint('你好，云安')\n```\n\n> 稳定第一。\n\n| 功能 | 状态 |\n|---|---|\n| 文件管理 | 完成 |\n| 音乐 | 下一步 |\n")
open(J("文档", "hello.py"), "w").write('#!/usr/bin/env python3\n"""云匣代码编辑器测试"""\nimport os\n\n\ndef greet(name: str) -> str:\n    # 打个招呼\n    return f"你好，{name}！"\n\n\nclass Cloud:\n    def __init__(self, size=3):\n        self.size = size\n\n    def rain(self):\n        for i in range(self.size):\n            print(greet("云安"), i)\n\n\nif __name__ == "__main__":\n    Cloud(2).rain()\n')
open(J("文档", "index.html"), "w").write("<!doctype html><html><body style='font-family:sans-serif'><h1 style='color:#4F8CC9'>你好，云安</h1><p>HTML 预览测试</p></body></html>")

icon = QImage(192, 192, QImage.Format.Format_ARGB32)
icon.fill(QColor("#4F8CC9"))
pp = QPainter(icon); pp.setPen(QColor("white")); f = QFont(); f.setPixelSize(110); f.setBold(True); pp.setFont(f)
pp.drawText(icon.rect(), 0x84, "云"); pp.end()
icon.save("/tmp/yk-ic.png")
with zipfile.ZipFile(J("下载", "云匣.apk"), "w") as z:
    z.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00")
    z.write("/tmp/yk-ic.png", "res/mipmap-xxxhdpi-v4/ic_launcher.png")
    z.write("/tmp/yk-ic.png", "res/mipmap-hdpi-v4/ic_launcher.png")
    z.writestr("classes.dex", b"dex\n035\0" + b"\0" * 100)
    z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    z.writestr("assets/readme.txt", "你好")
with zipfile.ZipFile(J("下载", "照片备份.zip"), "w") as z:
    for f in ("图片/晚霞.jpg", "图片/分形.png", "文档/笔记.md"):
        z.write(J(f), f)
with tarfile.open(J("下载", "源代码.tar.gz"), "w:gz") as t:
    t.add(J("文档"), "文档")
print("测试文件做好了：", home)
