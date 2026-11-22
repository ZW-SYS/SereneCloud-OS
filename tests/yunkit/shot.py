#!/usr/bin/env python3
"""云匣离线截图自测：QT_QPA_PLATFORM=offscreen HOME=/某个测试目录 python3 tests/yunkit/shot.py 输出目录"""
import os, sys, time, faulthandler
if os.environ.get("YK_TRACE"): faulthandler.dump_traceback_later(int(os.environ["YK_TRACE"]), exit=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../config/includes.chroot/usr/lib/serenecloud/yunkit"))
from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMessageBox
for _n in ("warning", "information", "question", "about"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, _n=_n: print("MSGBOX", _n, a[1:], flush=True) or QMessageBox.StandardButton.Yes))
from yunkit import main as M, theme, viewers, vfs, thumbs

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/yunkit-shots"
os.makedirs(out, exist_ok=True)
app = QApplication(sys.argv)
for f in os.environ.get("YK_FONTS", "").split(":"):
    if f:
        fid = QFontDatabase.addApplicationFont(f)
        fam = QFontDatabase.applicationFontFamilies(fid)
        if fam:
            app.setFont(QFont(fam[0], 10))
theme.settings().clear()
theme.settings().setValue("theme", os.environ.get("YK_THEME", "dark"))
theme.apply(app)
home = os.path.expanduser("~")


def wait(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def snap(w, name):
    wait(0.3)
    w.grab().save(os.path.join(out, "yunkit-" + name))
    print("saved", name, flush=True)


w = M.MainWindow(home)
w.resize(1400, 860)
w.show()
L, R = w.panes
L.open_loc(os.path.join(home, "图片"))
R.open_loc(os.path.join(home, "音乐"))
wait(3)
snap(w, "01-dual.png")
R.new_tab(os.path.join(home, "视频"))
L.new_tab(os.path.join(home, "下载"))
wait(3)
snap(w, "02-tabs.png")
L.open_loc(vfs.make_archive_loc(os.path.join(home, "下载/云匣.apk"), "res/mipmap-xxxhdpi-v4"))
R.open_loc(os.path.join(home, "文档"))
wait(3)
snap(w, "03-archive.png")
w.view_btns.button(2).click()
L.open_loc(os.path.join(home, "下载"))
wait(2)
snap(w, "04-detail.png")
w.view_btns.button(0).click()
w.split_btn.click()
L.open_loc(home)
w.search.setText("云")
w.deep_search()
wait(2)
snap(w, "05-search.png")
w.search.clear()
wait(1)
for name, path in (("10-image.png", "图片/分形.png"), ("11-pdf.png", "文档/云安OS说明书.pdf"),
                   ("12-novel.png", "文档/云端之下.txt"), ("13-code.png", "文档/hello.py"),
                   ("14-markdown.png", "文档/笔记.md"), ("15-video.png", "视频/测试视频.mp4")):
    try:
        win = viewers.open_file(os.path.join(home, path))
        win.resize(1100, 720)
        wait(4 if "pdf" in name or "video" in name else 1.5)
        snap(win, name)
        win.close()
    except Exception as e:
        import traceback; traceback.print_exc()
w.split_btn.click()
w.toggle_theme()
L.open_loc(os.path.join(home, "图片"))
wait(2)
snap(w, "20-light.png")
w.toggle_theme()
print("done")
