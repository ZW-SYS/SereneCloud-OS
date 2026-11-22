# 云匣 · 缩略图：图片、视频、PDF 第一页、歌曲封面、APK 图标
# 在后台线程里生成，存到 ~/.cache/yunkit/thumbs，下次秒开。
import hashlib, io, os, re, subprocess, tempfile, zipfile

from PyQt6.QtCore import (QObject, QRunnable, QThreadPool, QSize, Qt, pyqtSignal, QRectF,
                          QPointF, QByteArray, QBuffer)
from PyQt6.QtGui import QImage, QImageReader, QPainter, QPainterPath, QPixmap, QColor, QPolygonF

from . import util

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "yunkit", "thumbs")
TSIZE = 256
THUMB_KINDS = {"image", "video", "pdf", "audio", "apk"}
MAX_IMAGE_BYTES = 200 * 1024 * 1024


def cache_path(path, st):
    h = hashlib.md5(f"{path}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()
    return os.path.join(CACHE, h + ".png")


def _scaled(img):
    if img.isNull():
        return img
    if img.width() > TSIZE or img.height() > TSIZE:
        img = img.scaled(TSIZE, TSIZE, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img


def _image(path):
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid() and (sz.width() > TSIZE or sz.height() > TSIZE):
        r.setScaledSize(sz.scaled(TSIZE, TSIZE, Qt.AspectRatioMode.KeepAspectRatio))
    return _scaled(r.read())


def _from_cmd(args, out):
    try:
        subprocess.run(args, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
    except Exception:
        return QImage()
    img = QImage(out) if os.path.exists(out) else QImage()
    try:
        os.remove(out)
    except OSError:
        pass
    return _scaled(img)


def _video(path):
    fd, out = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    if util.have("ffmpegthumbnailer"):
        img = _from_cmd(["ffmpegthumbnailer", "-i", path, "-o", out, "-s", str(TSIZE), "-t", "15%",
                         "-c", "png"], out)
        if not img.isNull():
            return img
    if util.have("ffmpeg"):
        for ss in ("3", "0"):
            img = _from_cmd(["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", path, "-frames:v", "1",
                             "-vf", f"scale={TSIZE}:-2", out], out)
            if not img.isNull():
                return img
    return QImage()


def _pdf(path):
    if not util.have("pdftoppm"):
        return QImage()
    d = tempfile.mkdtemp()
    base = os.path.join(d, "p")
    img = _from_cmd(["pdftoppm", "-png", "-f", "1", "-l", "1", "-singlefile", "-scale-to", str(TSIZE),
                     path, base], base + ".png")
    try:
        os.rmdir(d)
    except OSError:
        pass
    return img


def _audio(path):
    data = None
    try:
        import mutagen
        f = mutagen.File(path)
        if f is not None:
            tags = getattr(f, "tags", None)
            pics = getattr(f, "pictures", None)
            if pics:
                data = pics[0].data
            elif tags is not None:
                if hasattr(tags, "getall"):  # ID3
                    ap = tags.getall("APIC")
                    data = ap[0].data if ap else None
                if data is None and "covr" in tags:  # MP4
                    data = bytes(tags["covr"][0])
                if data is None and "metadata_block_picture" in tags:  # Ogg
                    import base64
                    from mutagen.flac import Picture
                    data = Picture(base64.b64decode(tags["metadata_block_picture"][0])).data
                if data is None:
                    for k in list(tags.keys()):
                        if str(k).lower().startswith("wm/picture"):
                            v = tags[k][0].value
                            data = v[v.find(b"\xff\xd8"):] if b"\xff\xd8" in v else None
                            break
    except Exception:
        data = None
    if data:
        img = QImage()
        img.loadFromData(data)
        if not img.isNull():
            return _scaled(img)
    if util.have("ffmpeg"):
        fd, out = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img = _from_cmd(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-an", "-frames:v", "1", out], out)
        if not img.isNull():
            return img
    folder = os.path.dirname(path)
    for n in ("cover.jpg", "cover.png", "folder.jpg", "Folder.jpg", "front.jpg", "AlbumArt.jpg"):
        p = os.path.join(folder, n)
        if os.path.exists(p):
            return _image(p)
    return QImage()


DENS = {"xxxhdpi": 6, "xxhdpi": 5, "xhdpi": 4, "hdpi": 3, "mdpi": 2, "anydpi": 1}


def _apk(path):
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return QImage()
    with z:
        names = set(z.namelist())
        cands = []
        # 1) aapt 能直接读出图标路径（最准）
        if util.have("aapt"):
            try:
                out = subprocess.run(["aapt", "dump", "badging", path], capture_output=True, text=True,
                                     timeout=20).stdout
                for m in re.finditer(r"application-icon-(\d+):'([^']+)'", out):
                    cands.append((int(m.group(1)), m.group(2)))
                cands.sort(reverse=True)
            except Exception:
                pass
        icon_files = [c[1] for c in cands if c[1].endswith((".png", ".webp")) and c[1] in names]
        # 2) 按名字猜
        if not icon_files:
            scored = []
            for n in names:
                m = re.match(r"res/(mipmap|drawable)-?([a-z]*dpi)?[^/]*/([^/]+)\.(png|webp)$", n)
                if not m:
                    continue
                base = m.group(3)
                score = DENS.get(m.group(2) or "", 0)
                if base in ("ic_launcher", "app_icon", "icon", "ic_launcher_round", "logo"):
                    score += 20 if base == "ic_launcher" else 15
                elif "launcher" in base and "foreground" not in base and "background" not in base:
                    score += 10
                elif "launcher_foreground" in base:
                    score += 5
                else:
                    continue
                scored.append((score, n))
            icon_files = [n for s, n in sorted(scored, reverse=True)]
        for n in icon_files[:3]:
            img = QImage()
            img.loadFromData(z.read(n))
            if not img.isNull():
                return _scaled(img)
    return QImage()


GEN = {"image": _image, "video": _video, "pdf": _pdf, "audio": _audio, "apk": _apk}


def generate(path, kind):
    try:
        st = os.stat(path)
    except OSError:
        return None
    if kind == "image" and st.st_size > MAX_IMAGE_BYTES:
        return None
    cp = cache_path(path, st)
    if os.path.exists(cp):
        img = QImage(cp)
        if not img.isNull():
            return img
    img = GEN[kind](path)
    if img is None or img.isNull():
        return None
    os.makedirs(CACHE, exist_ok=True)
    img.save(cp, "PNG")
    return img


class _Signals(QObject):
    done = pyqtSignal(str, QImage)


class _Job(QRunnable):
    def __init__(self, path, kind, sig):
        super().__init__()
        self.path, self.kind, self.sig = path, kind, sig

    def run(self):
        img = generate(self.path, self.kind)
        self.sig.done.emit(self.path, img if img is not None else QImage())


class ThumbManager(QObject):
    """全局唯一：请求缩略图，好了发 ready(path) 信号。"""
    ready = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(2, min(4, os.cpu_count() or 2)))
        self.images = {}      # path -> QImage
        self.failed = set()
        self.pending = set()
        self.pix = {}         # (path, size) -> QPixmap
        self.sig = _Signals()
        self.sig.done.connect(self._done)
        self.enabled = True

    def request(self, path, kind):
        if not self.enabled or kind not in THUMB_KINDS:
            return None
        if path in self.images:
            return self.images[path]
        if path in self.failed or path in self.pending:
            return None
        self.pending.add(path)
        self.pool.start(_Job(path, kind, self.sig))
        return None

    def _done(self, path, img):
        self.pending.discard(path)
        if img.isNull():
            self.failed.add(path)
            return
        self.images[path] = img
        self.ready.emit(path)

    def pixmap(self, path, kind, size):
        key = (path, size)
        if key in self.pix:
            return self.pix[key]
        img = self.request(path, kind)
        if img is None:
            return None
        pm = decorate(img, kind, size)
        self.pix[key] = pm
        return pm

    def clear(self):
        self.images.clear()
        self.pix.clear()
        self.failed.clear()


def decorate(img, kind, size):
    """把缩略图做成圆角卡片；视频加播放键，歌曲加小音符。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    src = QPixmap.fromImage(img)
    if kind == "apk":
        # 图标本来就有形状，放大居中不裁剪
        s = src.scaled(int(size * .86), int(size * .86), Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((size - s.width()) // 2, (size - s.height()) // 2, s)
    else:
        mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if kind in ("audio", "video") else \
            Qt.AspectRatioMode.KeepAspectRatio
        s = src.scaled(size, size, mode, Qt.TransformationMode.SmoothTransformation)
        w, h = min(s.width(), size), min(s.height(), size)
        if kind == "video":
            h = min(h, int(size * .72))
        x, y = (size - w) / 2, (size - h) / 2
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), size * .08, size * .08)
        p.setClipPath(path)
        p.drawPixmap(int(x), int(y), s, int((s.width() - w) / 2), int((s.height() - h) / 2), int(w), int(h))
        p.setClipping(False)
        if kind == "pdf":
            p.setPen(QColor(0, 0, 0, 40))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        if kind == "video":
            r = size * .13
            c = QPointF(size / 2, size / 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawEllipse(c, r, r)
            p.setBrush(QColor("white"))
            p.drawPolygon(QPolygonF([QPointF(c.x() - r * .35, c.y() - r * .5),
                                     QPointF(c.x() - r * .35, c.y() + r * .5),
                                     QPointF(c.x() + r * .55, c.y())]))
        if kind == "pdf":
            badge = util.kind_pixmap(kind, max(14, int(size * .32)), "pdf")
            p.drawPixmap(int(size - badge.width() * .95), int(size - badge.height() * .95), badge)
        if kind == "audio":
            r = max(7, size * .12)
            c = QPointF(size - r * 1.25, size - r * 1.25)
            p.setPen(QColor(255, 255, 255, 200))
            p.setBrush(QColor(util.KIND_COLOR["audio"]))
            p.drawEllipse(c, r, r)
            f = p.font()
            f.setPixelSize(int(r * 1.3))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return pm


_mgr = None


def manager():
    global _mgr
    if _mgr is None:
        _mgr = ThumbManager()
    return _mgr
