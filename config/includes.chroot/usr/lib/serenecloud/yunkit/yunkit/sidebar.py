# 云匣 · 侧栏：常用位置、U 盘/硬盘、手机（MTP）
import json, os, re, subprocess

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox, QVBoxLayout,
                             QWidget, QScrollArea, QFrame, QProgressBar, QHBoxLayout)

from . import util, vfs, theme

HOME = os.path.expanduser("~")


def user_dir(key, fallback):
    try:
        for line in open(os.path.join(HOME, ".config/user-dirs.dirs"), encoding="utf-8"):
            if line.startswith(f"XDG_{key}_DIR="):
                p = line.split("=", 1)[1].strip().strip('"').replace("$HOME", HOME)
                if os.path.isdir(p):
                    return p
    except OSError:
        pass
    for f in fallback:
        p = os.path.join(HOME, f)
        if os.path.isdir(p):
            return p
    return None


def emoji_icon(ch, color, size=28):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    c = QColor(color)
    c.setAlpha(60)
    p.setBrush(c)
    p.drawRoundedRect(0, 0, size, size, 8, 8)
    if ch == "trash":  # 自己画一个垃圾桶
        from PyQt6.QtCore import QRectF
        p.setBrush(QColor(color))
        s = size
        p.drawRoundedRect(QRectF(s * .28, s * .22, s * .44, s * .08), 1.5, 1.5)
        p.drawRect(QRectF(s * .43, s * .17, s * .14, s * .06))
        p.drawRoundedRect(QRectF(s * .32, s * .33, s * .36, s * .45), 2.5, 2.5)
    else:
        f = QFont()
        f.setPixelSize(int(size * .55))
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, ch)
    p.end()
    return QIcon(pm)


PLACES = [
    ("⌂", "主文件夹", None, ()),
    ("▣", "桌面", "DESKTOP", ("Desktop", "桌面")),
    ("↓", "下载", "DOWNLOAD", ("Downloads", "下载")),
    ("☰", "文档", "DOCUMENTS", ("Documents", "文档")),
    ("◩", "图片", "PICTURES", ("Pictures", "图片")),
    ("♪", "音乐", "MUSIC", ("Music", "音乐")),
    ("▶", "视频", "VIDEOS", ("Videos", "视频")),
]


class DeviceScan(QThread):
    found = pyqtSignal(list, list)

    def run(self):
        drives, phones = [], []
        try:
            out = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,PATH,LABEL,SIZE,MOUNTPOINT,RM,HOTPLUG,TYPE,FSTYPE,TRAN,MODEL"],
                                 capture_output=True, text=True, timeout=5).stdout
            data = json.loads(out or "{}")

            def walk(devs, parent=None):
                for d in devs:
                    kids = d.get("children") or []
                    if kids:
                        walk(kids, d)
                        continue
                    if d.get("type") not in ("part", "disk", "crypt", "lvm") or not d.get("fstype"):
                        continue
                    if d.get("fstype") in ("swap", "LVM2_member", "crypto_LUKS"):
                        continue
                    mp = d.get("mountpoint")
                    if mp in ("/boot", "/boot/efi", "[SWAP]") or (mp or "").startswith("/run/live"):
                        continue
                    removable = bool(d.get("rm") or d.get("hotplug") or (parent or {}).get("rm") or
                                     (parent or {}).get("tran") == "usb")
                    drives.append(dict(path=d["path"], label=d.get("label") or "", size=int(d.get("size") or 0),
                                       mount=mp or "", removable=removable, fstype=d.get("fstype"),
                                       model=(parent or {}).get("model") or d.get("model") or ""))
            walk(data.get("blockdevices", []))
        except Exception:
            pass
        # 手机（MTP）：gvfs 挂载后在 /run/user/UID/gvfs 下面
        gv = f"/run/user/{os.getuid()}/gvfs"
        try:
            for n in os.listdir(gv):
                if n.startswith("mtp:") or n.startswith("gphoto2:"):
                    nice = re.sub(r"^mtp:host=", "", n)
                    phones.append(dict(name=nice.replace("_", " "), path=os.path.join(gv, n), uri=""))
        except OSError:
            pass
        if util.have("gio"):
            try:
                out = subprocess.run(["gio", "mount", "-li"], capture_output=True, text=True, timeout=5).stdout
                cur = None
                for line in out.splitlines():
                    m = re.match(r"\s*Volume\(\d+\):\s*(.*)", line)
                    if m:
                        cur = {"name": m.group(1)}
                    m = re.match(r"\s*activation_root=(mtp://\S+|gphoto2://\S+)", line)
                    if m and cur is not None:
                        uri = m.group(1)
                        if not any(p["name"].lower() in uri.lower() or cur["name"] in p["name"] for p in phones):
                            phones.append(dict(name=cur["name"], path="", uri=uri))
            except Exception:
                pass
        self.found.emit(drives, phones)


class Sidebar(QWidget):
    go = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 8, 0, 8)
        v.setSpacing(0)
        logo = QLabel("  ☁  云匣")
        f = logo.font(); f.setPointSize(15); f.setBold(True); logo.setFont(f)
        logo.setStyleSheet(f"color: {theme.BLUE}; padding: 8px 12px 10px 12px; background: transparent;")
        v.addWidget(logo)
        self.lists = []
        self.places = self._section(v, "位置")
        c = theme.colors()
        for ch, name, key, fb in PLACES:
            p = HOME if key is None else user_dir(key, fb)
            if p:
                self._add(self.places, emoji_icon(ch, theme.BLUE), name, p)
        self._add(self.places, emoji_icon("trash", c["text2"]), "回收站", vfs.TRASH)
        self._add(self.places, emoji_icon("/", c["text2"]), "根目录", "/")
        self.drives = self._section(v, "硬盘和 U 盘")
        self.phones = self._section(v, "手机")
        v.addStretch(1)
        self.disk = QLabel()
        self.disk.setObjectName("Muted")
        self.disk.setStyleSheet("padding: 0 16px; background: transparent;")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        wrap = QWidget(); wl = QVBoxLayout(wrap); wl.setContentsMargins(16, 4, 16, 4); wl.addWidget(self.bar)
        v.addWidget(self.disk)
        v.addWidget(wrap)
        self.update_disk(HOME)
        self.scan = None
        self.timer = QTimer(self, interval=4000)
        self.timer.timeout.connect(self.rescan)
        self.timer.start()
        self.rescan()
        self._last = None

    def _section(self, v, title):
        t = QLabel(title)
        t.setObjectName("SideTitle")
        v.addWidget(t)
        lw = QListWidget()
        lw.setObjectName("SideList")
        lw.setIconSize(QSize(24, 24))
        lw.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lw.setFrameShape(QFrame.Shape.NoFrame)
        lw.itemClicked.connect(self._clicked)
        lw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        lw.customContextMenuRequested.connect(lambda pos, lw=lw: self._menu(lw, pos))
        v.addWidget(lw)
        self.lists.append(lw)
        lw._title = t
        return lw

    def _fit(self, lw):
        n = lw.count()
        lw.setFixedHeight(max(0, n * 38 + 4))
        lw._title.setVisible(n > 0)

    def _add(self, lw, icon, name, target, data=None):
        it = QListWidgetItem(icon, name)
        it.setData(Qt.ItemDataRole.UserRole, target)
        it.setData(Qt.ItemDataRole.UserRole + 1, data)
        it.setToolTip(target if isinstance(target, str) else name)
        it.setSizeHint(QSize(0, 36))
        lw.addItem(it)
        self._fit(lw)
        return it

    def rescan(self):
        if self.scan and self.scan.isRunning():
            return
        self.scan = DeviceScan()
        self.scan.found.connect(self._found)
        self.scan.start()

    def _found(self, drives, phones):
        key = json.dumps([drives, phones], sort_keys=True)
        if key == self._last:
            return
        self._last = key
        self.drives.clear()
        for d in drives:
            if d["mount"] == "/":
                name = "系统盘"
            else:
                name = d["label"] or d["model"] or os.path.basename(d["path"])
            name += f"  ({util.human_size(d['size'])})"
            icon = emoji_icon("⏏" if d["removable"] else "◉", "#E0A04B" if d["removable"] else theme.BLUE)
            self._add(self.drives, icon, name, d["mount"] or "", d)
        self._fit(self.drives)
        self.phones.clear()
        for p in phones:
            self._add(self.phones, emoji_icon("▯", "#7CB342"), p["name"], p["path"], p)
        self._fit(self.phones)

    def _clicked(self, it):
        for lw in self.lists:
            if lw is not it.listWidget():
                lw.clearSelection()
        target = it.data(Qt.ItemDataRole.UserRole)
        data = it.data(Qt.ItemDataRole.UserRole + 1) or {}
        if not target and data.get("path", "").startswith("/dev/"):
            target = self.mount_drive(data)
        elif not target and data.get("uri"):
            target = self.mount_phone(data)
        if target:
            self.go.emit(target)
            self.update_disk(target)

    def mount_drive(self, d):
        r = subprocess.run(["udisksctl", "mount", "-b", d["path"], "--no-user-interaction"],
                           capture_output=True, text=True, timeout=30)
        m = re.search(r" at (.+?)\.?$", r.stdout.strip())
        if r.returncode != 0 or not m:
            QMessageBox.warning(self, "云匣", "挂载失败：" + (r.stderr.strip() or r.stdout.strip()))
            return None
        self._last = None
        self.rescan()
        return m.group(1)

    def mount_phone(self, p):
        r = subprocess.run(["gio", "mount", p["uri"]], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            QMessageBox.information(self, "云匣", "连不上手机。请在手机上把 USB 用途选成「传输文件」，"
                                    "然后解锁手机再试。\n\n" + r.stderr.strip())
            return None
        gv = f"/run/user/{os.getuid()}/gvfs"
        for n in os.listdir(gv):
            if n.startswith("mtp:"):
                return os.path.join(gv, n)
        return None

    def _menu(self, lw, pos):
        it = lw.itemAt(pos)
        if not it:
            return
        data = it.data(Qt.ItemDataRole.UserRole + 1) or {}
        if not data.get("path", "").startswith("/dev/"):
            return
        m = QMenu(self)
        if data.get("mount"):
            m.addAction("卸载", lambda: self._unmount(data, False))
            if data.get("removable"):
                m.addAction("安全弹出", lambda: self._unmount(data, True))
        else:
            m.addAction("挂载", lambda: self.mount_drive(data))
        m.exec(lw.viewport().mapToGlobal(pos))

    def _unmount(self, d, eject):
        r = subprocess.run(["udisksctl", "unmount", "-b", d["path"]], capture_output=True, text=True)
        if r.returncode != 0:
            QMessageBox.warning(self, "云匣", "卸载失败（可能有文件还开着）：\n" + r.stderr.strip())
            return
        if eject:
            parent = re.sub(r"p?\d+$", "", d["path"])
            subprocess.run(["udisksctl", "power-off", "-b", parent], capture_output=True)
            QMessageBox.information(self, "云匣", "可以拔掉了 ✓")
        self._last = None
        self.rescan()

    def update_disk(self, path):
        if not path or not os.path.isdir(path) or path.startswith("trash:"):
            return
        try:
            st = os.statvfs(path)
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            if total:
                self.bar.setValue(int(100 * (total - free) / total))
                self.disk.setText(f"剩余 {util.human_size(free)}，共 {util.human_size(total)}")
        except OSError:
            pass
