# 云匣 · 小工具：文件类型、大小、图标（自己画，深色浅色都好看）
import os, shutil, subprocess, time
from functools import lru_cache

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap,
                         QLinearGradient, QPen)

EXT_KIND = {}
for k, exts in {
    "image": "png jpg jpeg gif webp bmp svg svgz heic heif avif ico tif tiff jxl",
    "video": "mp4 mkv webm avi mov flv wmv m4v 3gp ts mpg mpeg",
    "audio": "mp3 flac wav aac m4a alac ogg oga opus ape wma aiff aif dsf dff mid midi wv",
    "pdf": "pdf",
    "word": "doc docx odt rtf wps",
    "excel": "xls xlsx ods csv et",
    "ppt": "ppt pptx odp dps",
    "text": "txt log ini conf cfg nfo",
    "markdown": "md markdown",
    "html": "html htm xhtml",
    "code": "py c h cpp hpp cc cxx java kt kts js mjs ts tsx jsx json xml yml yaml toml sh bash "
            "zsh go rs rb php lua pl swift dart css scss less sql gradle properties smali cs vue "
            "cmake mk makefile dockerfile bat ps1 asm s",
    "archive": "zip 7z rar tar gz tgz bz2 tbz xz txz zst tzst lz4 cab iso",
    "apk": "apk apks xapk aab",
    "jar": "jar war aar",
    "exe": "exe msi dll",
    "deb": "deb rpm appimage",
    "font": "ttf otf woff woff2",
}.items():
    for e in exts.split():
        EXT_KIND[e] = k

# 这些压缩格式可以像文件夹一样点进去
BROWSABLE = {"zip", "apk", "jar", "aar", "war", "apks", "xapk", "aab", "7z", "rar", "tar",
             "tgz", "tbz", "txz", "tzst", "gz", "bz2", "xz", "zst", "iso", "cab"}

KIND_COLOR = {
    "folder": "#4F8CC9", "image": "#E0A04B", "video": "#D9627A", "audio": "#B07CE0",
    "pdf": "#E05A4F", "word": "#3F7FD8", "excel": "#3FA66A", "ppt": "#E07A3F",
    "text": "#8A97AA", "markdown": "#5FA8A0", "html": "#E8763A", "code": "#56B6C2",
    "archive": "#C9A24F", "apk": "#7CB342", "jar": "#C0703F", "exe": "#6A7FDB",
    "deb": "#B5485D", "font": "#9C8ADE", "file": "#7D8899",
}
KIND_NAME = {
    "folder": "文件夹", "image": "图片", "video": "视频", "audio": "音乐", "pdf": "PDF 文档",
    "word": "Word 文档", "excel": "表格", "ppt": "演示文稿", "text": "文本", "markdown": "Markdown",
    "html": "网页", "code": "代码", "archive": "压缩包", "apk": "安卓安装包", "jar": "Java 包",
    "exe": "Windows 程序", "deb": "软件包", "font": "字体", "file": "文件",
}


def ext_of(name):
    n = name.lower()
    for double in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"):
        if n.endswith(double):
            return "tar"
    if "." not in n.strip("."):
        return n if n in ("makefile", "dockerfile") else ""
    return n.rsplit(".", 1)[1]


def kind_of(name, is_dir=False):
    if is_dir:
        return "folder"
    return EXT_KIND.get(ext_of(name), "file")


def is_browsable_archive(name):
    return ext_of(name) in BROWSABLE


def human_size(n):
    if n is None:
        return ""
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def human_time(t):
    if not t:
        return ""
    lt = time.localtime(t)
    now = time.localtime()
    if lt.tm_year == now.tm_year and lt.tm_yday == now.tm_yday:
        return time.strftime("今天 %H:%M", lt)
    return time.strftime("%Y-%m-%d %H:%M", lt)


def perm_string(mode):
    s = ""
    for who in (6, 3, 0):
        bits = (mode >> who) & 7
        s += ("r" if bits & 4 else "-") + ("w" if bits & 2 else "-") + ("x" if bits & 1 else "-")
    return s


def have(cmd):
    return shutil.which(cmd) is not None


def run(args, timeout=60, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


# ---------- 图标：自己画 ----------

def _rounded(p, rect, r):
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    return path


@lru_cache(maxsize=256)
def kind_pixmap(kind, size, label=""):
    """画一个文件类型图标：文件夹是云安蓝的文件夹，文件是带折角的纸 + 彩色标签。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(KIND_COLOR.get(kind, KIND_COLOR["file"]))
    s = size
    if kind == "folder":
        back = QRectF(s * .08, s * .18, s * .84, s * .66)
        tab = QPainterPath()
        tab.addRoundedRect(QRectF(s * .08, s * .13, s * .36, s * .16), s * .05, s * .05)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col.darker(125))
        p.drawPath(tab)
        p.drawPath(_rounded(p, back, s * .07))
        front = QRectF(s * .08, s * .30, s * .84, s * .56)
        g = QLinearGradient(0, front.top(), 0, front.bottom())
        g.setColorAt(0, col.lighter(118))
        g.setColorAt(1, col)
        p.setBrush(g)
        p.drawPath(_rounded(p, front, s * .07))
        # 小云朵
        p.setBrush(QColor(255, 255, 255, 70))
        cx, cy = s * .5, s * .6
        for dx, dy, r in ((-.09, .02, .07), (0, -.02, .09), (.09, .02, .07)):
            p.drawEllipse(QPointF(cx + dx * s, cy + dy * s), r * s, r * s)
        p.drawRoundedRect(QRectF(cx - .16 * s, cy + .01 * s, .32 * s, .08 * s), .04 * s, .04 * s)
    else:
        w = s * .70
        x0, y0 = (s - w) / 2, s * .06
        h = s * .88
        fold = s * .20
        page = QPainterPath()
        page.moveTo(x0 + s * .08, y0)
        page.lineTo(x0 + w - fold, y0)
        page.lineTo(x0 + w, y0 + fold)
        page.lineTo(x0 + w, y0 + h - s * .08)
        page.quadTo(x0 + w, y0 + h, x0 + w - s * .08, y0 + h)
        page.lineTo(x0 + s * .08, y0 + h)
        page.quadTo(x0, y0 + h, x0, y0 + h - s * .08)
        page.lineTo(x0, y0 + s * .08)
        page.quadTo(x0, y0, x0 + s * .08, y0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E9EEF5"))
        p.drawPath(page)
        corner = QPainterPath()
        corner.moveTo(x0 + w - fold, y0)
        corner.lineTo(x0 + w - fold, y0 + fold * .8)
        corner.quadTo(x0 + w - fold, y0 + fold, x0 + w - fold * .8, y0 + fold)
        corner.lineTo(x0 + w, y0 + fold)
        corner.closeSubpath()
        p.setBrush(QColor("#C3CCD9"))
        p.drawPath(corner)
        band = QRectF(x0 - s * .04, y0 + h * .55, w * .78, s * .24)
        p.setBrush(col)
        p.drawRoundedRect(band, s * .05, s * .05)
        txt = (label or kind).upper()[:4]
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(6, int(s * (.15 if len(txt) <= 3 else .12))))
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(band, Qt.AlignmentFlag.AlignCenter, txt)
    p.end()
    return pm


def icon_for(name, is_dir, size=64):
    k = kind_of(name, is_dir)
    label = "" if is_dir else (ext_of(name) or "file")
    return QIcon(kind_pixmap(k, size, label))


def app_icon():
    for p in ("/usr/share/icons/hicolor/256x256/apps/yunkit.png",):
        if os.path.exists(p):
            return QIcon(p)
    return QIcon(kind_pixmap("folder", 128))
