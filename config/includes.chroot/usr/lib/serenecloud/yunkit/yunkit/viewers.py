# 云匣 · 预览和编辑：图片、PDF、Office、小说阅读、Markdown/HTML、代码编辑器、视频
import hashlib, html, os, re, subprocess, tempfile

from PyQt6.QtCore import (Qt, QPointF, QRectF, QSize, QThread, QTimer, QUrl, pyqtSignal, QEvent)
from PyQt6.QtGui import (QAction, QColor, QFont, QFontMetrics, QImage, QImageReader, QKeySequence,
                         QMovie, QPainter, QPixmap, QShortcut, QTextCursor, QTextDocument,
                         QDesktopServices, QTransform, QTextOption)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                             QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSplitter,
                             QStackedWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget, QFrame,
                             QSizePolicy, QStyle)

from . import theme, util, thumbs

try:
    from PyQt6 import Qsci
except Exception:  # 没装 QScintilla 也能用（简单版编辑器）
    Qsci = None
try:
    from PyQt6.QtPdf import QPdfDocument
    from PyQt6.QtPdfWidgets import QPdfView
except Exception:
    QPdfDocument = None
try:
    from PyQt6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "yunkit")


def read_text(path, limit=64 * 1024 * 1024):
    raw = open(path, "rb").read(limit)
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace"), "utf-8"


def small_btn(text, tip, cb, checkable=False):
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(cb)
    return b


class Bar(QWidget):
    def __init__(self, *widgets):
        super().__init__()
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(10, 6, 10, 6)
        self.lay.setSpacing(4)
        for w in widgets:
            if w is None:
                self.lay.addStretch(1)
            else:
                self.lay.addWidget(w)


# =============== 图片 ===============

class ImageCanvas(QWidget):
    zoomChanged = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.pix = None
        self.movie = None
        self.svg = None
        self.scale = 1.0
        self.fit = True
        self.offset = QPointF(0, 0)
        self.rot = 0
        self.drag = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def load(self, path):
        if self.movie:
            self.movie.stop()
        self.movie, self.svg, self.pix = None, None, None
        self.rot = 0
        ext = util.ext_of(path)
        if ext in ("svg", "svgz") and QSvgRenderer:
            self.svg = QSvgRenderer(path)
        else:
            r = QImageReader(path)
            r.setAutoTransform(True)
            if r.supportsAnimation() and r.imageCount() != 1:
                self.movie = QMovie(path)
                self.movie.frameChanged.connect(self.update)
                self.movie.start()
            else:
                img = r.read()
                if img.isNull():
                    return False, r.errorString()
                self.pix = QPixmap.fromImage(img)
        self.fit = True
        self.offset = QPointF(0, 0)
        self.update()
        return True, ""

    def base_size(self):
        if self.svg:
            s = self.svg.defaultSize()
            return QSize(max(1, s.width()), max(1, s.height()))
        if self.movie:
            return self.movie.currentPixmap().size()
        return self.pix.size() if self.pix else QSize(1, 1)

    def image_size_text(self):
        s = self.base_size()
        return f"{s.width()} × {s.height()}"

    def fit_scale(self):
        s = self.base_size()
        w, h = (s.height(), s.width()) if self.rot % 180 else (s.width(), s.height())
        return min(self.width() / max(1, w), self.height() / max(1, h), 1.0 if not self.svg else 50)

    def eff_scale(self):
        return self.fit_scale() if self.fit else self.scale

    def set_zoom(self, z, anchor=None):
        old = self.eff_scale()
        self.fit = False
        self.scale = max(0.02, min(z, 40))
        if anchor is not None:
            mid = QPointF(self.width() / 2, self.height() / 2)
            c = mid + self.offset
            k = self.scale / old
            self.offset = (anchor - (anchor - c) * k) - mid
        self.update()
        self.zoomChanged.emit(self.scale)

    def wheelEvent(self, ev):
        k = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.set_zoom(self.eff_scale() * k, ev.position())

    def mousePressEvent(self, ev):
        self.drag = (ev.position(), QPointF(self.offset))
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        if self.drag:
            self.offset = self.drag[1] + (ev.position() - self.drag[0])
            self.update()

    def mouseReleaseEvent(self, ev):
        self.drag = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, ev):
        if self.fit:
            self.set_zoom(1.0)
        else:
            self.fit = True
            self.offset = QPointF(0, 0)
            self.update()
            self.zoomChanged.emit(self.fit_scale())

    def resizeEvent(self, ev):
        if self.fit:
            self.zoomChanged.emit(self.fit_scale())

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 棋盘格背景（看透明图片）
        s = self.eff_scale()
        bs = self.base_size()
        w, h = bs.width() * s, bs.height() * s
        p.translate(self.width() / 2 + self.offset.x(), self.height() / 2 + self.offset.y())
        p.rotate(self.rot)
        target = QRectF(-w / 2, -h / 2, w, h)
        p.fillRect(target, QColor(128, 128, 128, 40))
        if self.svg:
            self.svg.render(p, target)
        elif self.movie:
            p.drawPixmap(target.toRect(), self.movie.currentPixmap())
        elif self.pix:
            p.drawPixmap(target, self.pix, QRectF(self.pix.rect()))


class ImageViewer(QWidget):
    title = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.canvas = ImageCanvas()
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setMinimumWidth(56)
        self.canvas.zoomChanged.connect(lambda z: self.zoom_lbl.setText(f"{z * 100:.0f}%"))
        bar = Bar(small_btn("◀", "上一张 (←)", lambda: self.step(-1)),
                  small_btn("▶", "下一张 (→)", lambda: self.step(1)), self.info, None,
                  small_btn("－", "缩小", lambda: self.canvas.set_zoom(self.canvas.eff_scale() / 1.25)),
                  self.zoom_lbl,
                  small_btn("＋", "放大", lambda: self.canvas.set_zoom(self.canvas.eff_scale() * 1.25)),
                  small_btn("适合", "适合窗口 (F)", self.fit),
                  small_btn("1:1", "原始大小", lambda: self.canvas.set_zoom(1.0)),
                  small_btn("↻", "旋转 (R)", self.rotate))
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(bar)
        v.addWidget(self.canvas, 1)
        for key, fn in (("Left", lambda: self.step(-1)), ("Right", lambda: self.step(1)),
                        ("F", self.fit), ("R", self.rotate), ("Ctrl+0", lambda: self.canvas.set_zoom(1.0))):
            QShortcut(QKeySequence(key), self, fn)
        folder = os.path.dirname(path)
        try:
            self.siblings = sorted([os.path.join(folder, n) for n in os.listdir(folder)
                                    if util.kind_of(n) == "image"], key=lambda x: x.lower())
        except OSError:
            self.siblings = [path]
        self.path = path
        self.show_path(path)

    def show_path(self, path):
        self.path = path
        ok, err = self.canvas.load(path)
        i = self.siblings.index(path) + 1 if path in self.siblings else 1
        if ok:
            self.info.setText(f"{i}/{len(self.siblings)}   {self.canvas.image_size_text()}   "
                              f"{util.human_size(os.path.getsize(path))}")
        else:
            self.info.setText("打不开这张图片：" + err)
        self.title.emit(os.path.basename(path))

    def step(self, d):
        if self.path in self.siblings and len(self.siblings) > 1:
            i = (self.siblings.index(self.path) + d) % len(self.siblings)
            self.show_path(self.siblings[i])

    def fit(self):
        self.canvas.fit = True
        self.canvas.offset = QPointF(0, 0)
        self.canvas.update()
        self.canvas.zoomChanged.emit(self.canvas.fit_scale())

    def rotate(self):
        self.canvas.rot = (self.canvas.rot + 90) % 360
        self.canvas.update()


# =============== PDF ===============

class PageRenderer(QThread):
    page = pyqtSignal(int, QImage)

    def __init__(self, path, pages, width):
        super().__init__()
        self.path, self.pages, self.width = path, pages, width

    def run(self):
        for n in self.pages:
            d = tempfile.mkdtemp()
            base = os.path.join(d, "p")
            subprocess.run(["pdftoppm", "-png", "-f", str(n + 1), "-l", str(n + 1), "-singlefile",
                            "-scale-to-x", str(self.width), "-scale-to-y", "-1", self.path, base],
                           capture_output=True, timeout=60)
            img = QImage(base + ".png")
            try:
                os.remove(base + ".png"); os.rmdir(d)
            except OSError:
                pass
            self.page.emit(n, img)


class PdfFallback(QScrollArea):
    """没有 QtPdf 时：用 pdftoppm 一页一页画出来。"""

    def __init__(self, path):
        super().__init__()
        self.setWidgetResizable(True)
        inner = QWidget()
        self.v = QVBoxLayout(inner)
        self.v.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.v.setSpacing(14)
        self.setWidget(inner)
        n = 1
        try:
            out = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=20).stdout
            m = re.search(r"Pages:\s+(\d+)", out)
            n = int(m.group(1)) if m else 1
        except Exception:
            pass
        self.count = n
        self.labels = []
        for i in range(min(n, 300)):
            l = QLabel(f"第 {i + 1} 页…")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setMinimumSize(800, 1000)
            l.setStyleSheet("background: white; color: #888; border-radius: 6px;")
            self.v.addWidget(l)
            self.labels.append(l)
        self.r = PageRenderer(path, range(len(self.labels)), 800)
        self.r.page.connect(self._page)
        self.r.start()

    def _page(self, i, img):
        if not img.isNull():
            self.labels[i].setPixmap(QPixmap.fromImage(img))
            self.labels[i].setMinimumSize(img.size())


class PdfViewer(QWidget):
    title = pyqtSignal(str)

    def __init__(self, path, display_name=None):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.page_lbl = QLabel()
        self.page_lbl.setObjectName("Muted")
        if QPdfDocument is not None:
            try:
                self._qtpdf(path, v)
            except Exception:
                self._fallback(path, v)
        else:
            self._fallback(path, v)
        self.title.emit(display_name or os.path.basename(path))

    def _fallback(self, path, v):
        fb = PdfFallback(path)
        self.page_lbl.setText(f"共 {fb.count} 页")
        v.addWidget(Bar(self.page_lbl, None))
        v.addWidget(fb, 1)

    def _qtpdf(self, path, v):
        if True:
            self.doc = QPdfDocument(self)
            self.doc.load(path)
            self.view = QPdfView(self)
            self.view.setDocument(self.doc)
            self.view.setPageMode(QPdfView.PageMode.MultiPage)
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.view.setPageSpacing(14)
            nav = self.view.pageNavigator()
            nav.currentPageChanged.connect(lambda p: self.page_lbl.setText(f"第 {p + 1} / {self.doc.pageCount()} 页"))
            self.page_lbl.setText(f"共 {self.doc.pageCount()} 页")
            self.zoom = 1.0
            bar = Bar(self.page_lbl, None,
                      small_btn("－", "缩小", lambda: self._z(1 / 1.2)),
                      small_btn("＋", "放大", lambda: self._z(1.2)),
                      small_btn("适合宽度", "适合宽度", lambda: self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)),
                      small_btn("整页", "整页", lambda: self.view.setZoomMode(QPdfView.ZoomMode.FitInView)))
            v.addWidget(bar)
            v.addWidget(self.view, 1)

    def _z(self, k):
        self.zoom = self.view.zoomFactor() * k
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(self.zoom)


class OfficeConvert(QThread):
    done = pyqtSignal(str, str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        st = os.stat(self.path)
        h = hashlib.md5(f"{self.path}|{st.st_mtime_ns}".encode()).hexdigest()
        out_dir = os.path.join(CACHE, "office", h)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        pdf = os.path.join(out_dir, stem + ".pdf")
        if os.path.exists(pdf):
            self.done.emit(pdf, "")
            return
        os.makedirs(out_dir, exist_ok=True)
        exe = util.have("soffice") and "soffice" or (util.have("libreoffice") and "libreoffice")
        if not exe:
            self.done.emit("", "系统里没有 LibreOffice，没法预览这种文档。")
            return
        prof = os.path.join(CACHE, "lo-profile")
        try:
            r = subprocess.run([exe, f"-env:UserInstallation=file://{prof}", "--headless", "--norestore",
                                "--convert-to", "pdf", "--outdir", out_dir, self.path],
                               capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            self.done.emit("", "转换太久了，放弃了。")
            return
        self.done.emit(pdf if os.path.exists(pdf) else "", "" if os.path.exists(pdf) else (r.stderr[-300:] or "转换失败"))


class OfficeViewer(QWidget):
    title = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.msg = QLabel("正在离线转换文档，第一次打开会慢一点…")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setObjectName("Muted")
        self.v.addWidget(self.msg)
        self.title.emit(os.path.basename(path))
        self.job = OfficeConvert(path)
        self.job.done.connect(self._done)
        self.job.start()

    def _done(self, pdf, err):
        if not pdf:
            self.msg.setText("预览失败：" + err)
            return
        self.msg.hide()
        open_btn = QPushButton("用 LibreOffice 编辑")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path)))
        pv = PdfViewer(pdf, os.path.basename(self.path))
        pv.layout().itemAt(0).widget().lay.addWidget(open_btn)
        self.v.addWidget(pv, 1)


# =============== 小说阅读模式 ===============

CHAPTER_RE = re.compile(r"^\s*(第[0-9０-９零〇一二三四五六七八九十百千万两]+[章节回卷集部篇].{0,30}|"
                        r"(序章|序言|楔子|引子|尾声|后记|番外).{0,30}|Chapter\s+\d+.{0,40})\s*$", re.M)


class NovelReader(QWidget):
    """TXT 小说阅读模式：自动分章节、目录、字号、记住读到哪里。"""
    title = pyqtSignal(str)

    def __init__(self, path, open_editor=None):
        super().__init__()
        self.path = path
        text, enc = read_text(path)
        self.enc = "UTF-8" if enc.startswith("utf-8") else enc.upper()
        self.st = theme.settings()
        self.font_size = self.st.value("reader/font", 16, int)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.chapters = QListWidget()
        self.chapters.setObjectName("SideList")
        self.chapters.setMinimumWidth(180)
        self.chapters.setMaximumWidth(260)
        self.chapters.itemClicked.connect(self._jump)
        self.chapters.setSpacing(2)
        # 分段落、找章节
        parts, self.marks = [], []
        for line in text.splitlines():
            t = line.strip()
            if not t:
                continue
            if CHAPTER_RE.match(t) and len(t) < 40:
                n = len(self.marks)
                self.marks.append(t)
                parts.append(f'<h2><a name="c{n}"></a>{html.escape(t)}</h2>')
            else:
                parts.append(f"<p>{html.escape(t)}</p>")
        if len(self.marks) < 2:
            self.chapters.hide()
        for name in self.marks:
            self.chapters.addItem(name)
        self.body = "".join(parts)
        self._render()
        self.pos_lbl = QLabel()
        self.pos_lbl.setObjectName("Muted")
        self.view.verticalScrollBar().valueChanged.connect(self._progress)
        edit_btn = small_btn("编辑", "用代码编辑器打开", lambda: open_editor and open_editor(path))
        toc = small_btn("目录", "显示/隐藏目录", lambda: self.chapters.setVisible(not self.chapters.isVisible()))
        enc_lbl = QLabel(f"编码 {self.enc}")
        enc_lbl.setObjectName("Muted")
        bar = Bar(toc, enc_lbl, self.pos_lbl, None,
                  small_btn("A－", "字小一点", lambda: self._font(-1)),
                  small_btn("A＋", "字大一点", lambda: self._font(1)), edit_btn)
        sp = QSplitter()
        sp.addWidget(self.chapters)
        sp.addWidget(self.view)
        sp.setStretchFactor(1, 1)
        sp.setSizes([220, 900])
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(bar)
        v.addWidget(sp, 1)
        self.title.emit(os.path.basename(path))
        self.key = "reader/pos/" + hashlib.md5(path.encode()).hexdigest()
        QTimer.singleShot(80, lambda: self.view.verticalScrollBar().setValue(self.st.value(self.key, 0, int)))
        QShortcut(QKeySequence("Space"), self, lambda: self._page(1))
        QShortcut(QKeySequence("PgDown"), self, lambda: self._page(1))
        QShortcut(QKeySequence("PgUp"), self, lambda: self._page(-1))

    def _render(self):
        dark = theme.current_name() == "dark"
        bg, fg, head = ("#1E232B", "#D8D2C4", "#8FB8E3") if dark else ("#F6F1E5", "#2B2620", "#2F5F93")
        self.view.setStyleSheet(f"QTextBrowser {{ background: {bg}; color: {fg}; border: none; border-radius: 0; }}")
        fs = self.font_size
        css = (f"p {{ font-size: {fs}pt; line-height: 150%; margin: 0 0 {fs // 2}px 0; text-indent: 2em; }}"
               f"h2 {{ font-size: {fs + 4}pt; color: {head}; margin: {fs * 2}px 0 {fs}px 0; text-align: center; }}")
        self.view.document().setDefaultStyleSheet(css)
        self.view.document().setDocumentMargin(max(30, self.width() // 9))
        f = QFont()
        f.setFamilies(["Noto Serif CJK SC", "Noto Sans CJK SC", "serif"])
        self.view.document().setDefaultFont(f)
        sb = self.view.verticalScrollBar()
        ratio = sb.value() / max(1, sb.maximum())
        self.view.setHtml(self.body)
        sb.setValue(int(ratio * sb.maximum()))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.view.document().setDocumentMargin(max(30, self.view.width() // 9))

    def _font(self, d):
        self.font_size = max(10, min(36, self.font_size + d))
        self.st.setValue("reader/font", self.font_size)
        self._render()

    def _jump(self, item):
        self.view.scrollToAnchor(f"c{self.chapters.row(item)}")

    def _page(self, d):
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.value() + d * (self.view.viewport().height() - 40))

    def _progress(self, v):
        sb = self.view.verticalScrollBar()
        pct = 100 * v / max(1, sb.maximum())
        self.pos_lbl.setText(f"  已读 {pct:.0f}%")
        self.st.setValue(self.key, v)


# =============== 代码编辑器（含 Markdown / HTML 预览） ===============

LEXERS = {
    "py": "Python", "c": "CPP", "h": "CPP", "cpp": "CPP", "hpp": "CPP", "cc": "CPP", "cxx": "CPP",
    "java": "Java", "kt": "Java", "kts": "Java", "gradle": "Java", "cs": "CSharp", "dart": "Java",
    "swift": "CPP", "go": "CPP", "rs": "CPP",
    "js": "JavaScript", "mjs": "JavaScript", "jsx": "JavaScript", "ts": "JavaScript", "tsx": "JavaScript",
    "json": "JSON", "xml": "XML", "html": "HTML", "htm": "HTML", "xhtml": "HTML", "vue": "HTML",
    "css": "CSS", "scss": "CSS", "less": "CSS", "sh": "Bash", "bash": "Bash", "zsh": "Bash",
    "yml": "YAML", "yaml": "YAML", "toml": "Properties", "ini": "Properties", "conf": "Properties",
    "cfg": "Properties", "properties": "Properties", "md": "Markdown", "markdown": "Markdown",
    "sql": "SQL", "lua": "Lua", "rb": "Ruby", "pl": "Perl", "php": "HTML", "cmake": "CMake",
    "makefile": "Makefile", "mk": "Makefile", "bat": "Batch", "diff": "Diff", "patch": "Diff",
    "smali": "Java", "asm": "Asm", "s": "Asm",
}


def style_lexer(lexer, c, font):
    dark = theme.current_name() == "dark"
    pal = {
        "comment": "#6A9955" if dark else "#3F7F3F",
        "string": "#CE9178" if dark else "#A31515",
        "keyword": "#6FA6DD" if dark else "#0033B3",
        "number": "#B5CEA8" if dark else "#098658",
        "operator": "#D4D4D4" if dark else "#333333",
        "preproc": "#C586C0" if dark else "#AF00DB",
        "class": "#4EC9B0" if dark else "#267F99",
        "function": "#DCDCAA" if dark else "#795E26",
        "tag": "#569CD6" if dark else "#800000",
        "attr": "#9CDCFE" if dark else "#E50000",
        "error": "#F44747",
    }
    lexer.setDefaultPaper(QColor(c["card"]))
    lexer.setDefaultColor(QColor(c["text"]))
    lexer.setDefaultFont(font)
    for s in range(128):
        d = (lexer.description(s) or "").lower()
        if not d:
            continue
        lexer.setPaper(QColor(c["card"]), s)
        lexer.setFont(font, s)
        col = c["text"]
        if "comment" in d:
            col = pal["comment"]
        elif "string" in d or "character" in d or "regex" in d or "heredoc" in d or "value" in d:
            col = pal["string"]
        elif "keyword" in d or "word" in d:
            col = pal["keyword"]
        elif "number" in d:
            col = pal["number"]
        elif "preprocessor" in d or "decorator" in d or "directive" in d:
            col = pal["preproc"]
        elif "class" in d:
            col = pal["class"]
        elif "function" in d or "method" in d:
            col = pal["function"]
        elif "tag" in d or "header" in d:
            col = pal["tag"]
        elif "attribute" in d or "key" in d or "variable" in d:
            col = pal["attr"]
        elif "operator" in d:
            col = pal["operator"]
        elif "error" in d or "unclosed" in d:
            col = pal["error"]
        lexer.setColor(QColor(col), s)


class FindBar(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.ed = editor
        self.find = QLineEdit(); self.find.setPlaceholderText("查找")
        self.repl = QLineEdit(); self.repl.setPlaceholderText("替换为")
        self.case = QCheckBox("区分大小写")
        self.regex = QCheckBox("正则")
        self.info = QLabel(); self.info.setObjectName("Muted")
        self.find.returnPressed.connect(lambda: self.go(True))
        self.find.textChanged.connect(self._count)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 10, 4)
        for w in (self.find, small_btn("↑", "上一个", lambda: self.go(False)),
                  small_btn("↓", "下一个 (Enter)", lambda: self.go(True)), self.repl):
            h.addWidget(w)
        rb = QPushButton("替换"); rb.clicked.connect(self.replace_one)
        ra = QPushButton("全部替换"); ra.clicked.connect(self.replace_all)
        for w in (rb, ra, self.case, self.regex, self.info, small_btn("✕", "关闭 (Esc)", self.hide)):
            h.addWidget(w)
        QShortcut(QKeySequence("Escape"), self, self.hide)

    def open(self, replace=False):
        self.show()
        self.repl.setVisible(True)
        sel = self.ed.selected_text()
        if sel and "\n" not in sel:
            self.find.setText(sel)
        (self.repl if replace and self.find.text() else self.find).setFocus()
        self.find.selectAll()

    def _count(self):
        t = self.find.text()
        if not t:
            self.info.setText("")
            return
        body = self.ed.text()
        try:
            if self.regex.isChecked():
                n = len(re.findall(t, body, 0 if self.case.isChecked() else re.I))
            else:
                n = body.count(t) if self.case.isChecked() else body.lower().count(t.lower())
        except re.error:
            n = 0
        self.info.setText(f"{n} 处")

    def go(self, forward=True):
        ok = self.ed.find(self.find.text(), self.case.isChecked(), self.regex.isChecked(), forward)
        self.info.setText(self.info.text() if ok else "找不到了")

    def replace_one(self):
        if self.ed.selected_text():
            self.ed.replace_selection(self.repl.text())
        self.go(True)

    def replace_all(self):
        t = self.find.text()
        if not t:
            return
        body = self.ed.text()
        flags = 0 if self.case.isChecked() else re.I
        pat = t if self.regex.isChecked() else re.escape(t)
        try:
            new, n = re.subn(pat, self.repl.text() if self.regex.isChecked() else self.repl.text().replace("\\", "\\\\"), body, flags=flags)
        except re.error as e:
            self.info.setText(f"正则有错：{e}")
            return
        if n:
            self.ed.set_text_undoable(new)
        self.info.setText(f"替换了 {n} 处")


class _Editor:
    """把 QScintilla 和 QPlainTextEdit 包成一样的接口。"""

    def __init__(self, ext):
        c = theme.colors()
        self.font = QFont()
        self.font.setFamilies(["JetBrains Mono", "Noto Sans Mono", "DejaVu Sans Mono", "Noto Sans Mono CJK SC", "monospace"])
        self.font.setPointSize(theme.settings().value("editor/font", 11, int))
        if Qsci:
            e = Qsci.QsciScintilla()
            e.setUtf8(True)
            e.setFont(self.font)
            e.setMarginsFont(self.font)
            e.setMarginType(0, Qsci.QsciScintilla.MarginType.NumberMargin)
            e.setMarginWidth(0, "000000")
            e.setMarginsBackgroundColor(QColor(c["panel"]))
            e.setMarginsForegroundColor(QColor(c["text2"]))
            e.setCaretForegroundColor(QColor(c["accent2"]))
            e.setCaretLineVisible(True)
            e.setCaretLineBackgroundColor(QColor(c["hover"]))
            e.setSelectionBackgroundColor(QColor(c["sel"]))
            e.setSelectionForegroundColor(QColor(c["text"]))
            e.setPaper(QColor(c["card"]))
            e.setColor(QColor(c["text"]))
            e.setBraceMatching(Qsci.QsciScintilla.BraceMatch.SloppyBraceMatch)
            e.setMatchedBraceBackgroundColor(QColor(c["sel"]))
            e.setAutoIndent(True)
            e.setIndentationGuides(True)
            e.setIndentationGuidesBackgroundColor(QColor(c["border"]))
            e.setIndentationGuidesForegroundColor(QColor(c["border"]))
            e.setTabWidth(4)
            e.setIndentationsUseTabs(False)
            e.setFolding(Qsci.QsciScintilla.FoldStyle.CircledTreeFoldStyle)
            e.setFoldMarginColors(QColor(c["panel"]), QColor(c["panel"]))
            e.setEdgeMode(Qsci.QsciScintilla.EdgeMode.EdgeNone)
            e.SendScintilla(Qsci.QsciScintilla.SCI_SETHSCROLLBAR, 0)
            e.setFrameShape(QFrame.Shape.NoFrame)
            name = LEXERS.get(ext)
            if name and hasattr(Qsci, "QsciLexer" + name):
                lx = getattr(Qsci, "QsciLexer" + name)(e)
                style_lexer(lx, c, self.font)
                e.setLexer(lx)
                self.lexer = lx
            self.w = e
        else:
            e = QPlainTextEdit()
            e.setFont(self.font)
            e.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.w = e

    def text(self):
        return self.w.text() if Qsci else self.w.toPlainText()

    def set_text(self, t):
        if Qsci:
            self.w.setText(t)
            self.w.setModified(False)
        else:
            self.w.setPlainText(t)
            self.w.document().setModified(False)

    def set_text_undoable(self, t):
        if Qsci:
            self.w.beginUndoAction(); self.w.selectAll(); self.w.replaceSelectedText(t); self.w.endUndoAction()
        else:
            cur = self.w.textCursor(); cur.select(QTextCursor.SelectionType.Document); cur.insertText(t)

    def selected_text(self):
        return self.w.selectedText() if Qsci else self.w.textCursor().selectedText()

    def replace_selection(self, t):
        if Qsci:
            self.w.replaceSelectedText(t)
        else:
            self.w.textCursor().insertText(t)

    def find(self, t, case, regex, forward):
        if not t:
            return False
        if Qsci:
            line, idx = self.w.getCursorPosition()
            if not forward and self.w.hasSelectedText():
                l1, i1, l2, i2 = self.w.getSelection()
                line, idx = l1, i1
            return self.w.findFirst(t, regex, case, False, True, forward, line, idx)
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        ok = self.w.find(t, flags)
        if not ok:
            cur = self.w.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.Start if forward else QTextCursor.MoveOperation.End)
            self.w.setTextCursor(cur)
            ok = self.w.find(t, flags)
        return ok

    def modified(self):
        return self.w.isModified() if Qsci else self.w.document().isModified()

    def set_modified(self, m):
        self.w.setModified(m) if Qsci else self.w.document().setModified(m)

    def zoom(self, d):
        if Qsci:
            self.w.zoomIn(d) if d > 0 else self.w.zoomOut(-d)
        else:
            f = self.w.font(); f.setPointSize(max(6, f.pointSize() + d)); self.w.setFont(f)

    def set_wrap(self, on):
        if Qsci:
            self.w.setWrapMode(Qsci.QsciScintilla.WrapMode.WrapWord if on else Qsci.QsciScintilla.WrapMode.WrapNone)
        else:
            self.w.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if on else QPlainTextEdit.LineWrapMode.NoWrap)

    def changed_signal(self):
        return self.w.textChanged

    def cursor_text(self):
        if Qsci:
            l, i = self.w.getCursorPosition()
        else:
            cur = self.w.textCursor(); l, i = cur.blockNumber(), cur.positionInBlock()
        return f"第 {l + 1} 行，第 {i + 1} 列"


MD_CSS = """
body { font-family: 'Noto Sans CJK SC', sans-serif; line-height: 1.7; padding: 18px 28px;
       background: %(bg)s; color: %(fg)s; }
a { color: %(accent)s; } code, pre { font-family: 'Noto Sans Mono', monospace; background: %(code)s;
       border-radius: 6px; } code { padding: 1px 5px; } pre { padding: 10px 14px; overflow-x: auto; }
h1, h2 { border-bottom: 1px solid %(border)s; padding-bottom: 4px; }
blockquote { border-left: 4px solid %(accent)s; margin: 0; padding-left: 14px; color: %(muted)s; }
table { border-collapse: collapse; } td, th { border: 1px solid %(border)s; padding: 5px 10px; }
img { max-width: 100%%; }
"""


def markdown_html(text, base):
    c = theme.colors()
    try:
        import markdown
        body = markdown.markdown(text, extensions=["fenced_code", "tables", "toc", "sane_lists"])
    except Exception:
        doc = QTextDocument()
        doc.setMarkdown(text)
        body = doc.toHtml()
    css = MD_CSS % dict(bg=c["card"], fg=c["text"], accent=c["accent2"], code=c["bg2"],
                        border=c["border"], muted=c["text2"])
    return f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"


def make_web_view():
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        return QWebEngineView(), True
    except Exception:
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        return tb, False


class CodeEditor(QWidget):
    title = pyqtSignal(str)

    def __init__(self, path, root_mode=False):
        super().__init__()
        self.path = path
        self.root_mode = root_mode
        ext = util.ext_of(path)
        self.ext = ext
        self.ed = _Editor(ext)
        try:
            text, self.enc = read_text(path)
        except OSError as e:
            text, self.enc = "", "utf-8"
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "云匣", f"打不开：{e}"))
        self.ed.set_text(text)
        self.findbar = FindBar(self.ed)
        self.findbar.hide()
        self.pos_lbl = QLabel(); self.pos_lbl.setObjectName("Muted")
        self.enc_lbl = QLabel(f"{'UTF-8' if self.enc.startswith('utf-8') else self.enc.upper()}  ·  {LEXERS.get(ext, '纯文本')}"); self.enc_lbl.setObjectName("Muted")
        self.preview = None
        self.can_preview = ext in ("md", "markdown", "html", "htm", "xhtml")
        self.prev_btn = small_btn("预览", "显示/隐藏预览", self.toggle_preview, True)
        self.prev_btn.setVisible(self.can_preview)
        wrap = small_btn("换行", "自动换行", lambda on: self.ed.set_wrap(on), True)
        bar = Bar(small_btn("保存", "保存 (Ctrl+S)", self.save),
                  small_btn("查找", "查找 (Ctrl+F)", lambda: self.findbar.open()),
                  small_btn("替换", "替换 (Ctrl+H)", lambda: self.findbar.open(True)),
                  wrap, self.prev_btn, None, self.pos_lbl, self.enc_lbl,
                  small_btn("A－", "缩小 (Ctrl+-)", lambda: self.ed.zoom(-1)),
                  small_btn("A＋", "放大 (Ctrl+=)", lambda: self.ed.zoom(1)))
        self.split = QSplitter()
        self.split.addWidget(self.ed.w)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(bar)
        v.addWidget(self.findbar)
        v.addWidget(self.split, 1)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.findbar.open())
        QShortcut(QKeySequence("Ctrl+H"), self, lambda: self.findbar.open(True))
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self.ed.zoom(1))
        QShortcut(QKeySequence("Ctrl++"), self, lambda: self.ed.zoom(1))
        QShortcut(QKeySequence("Ctrl+-"), self, lambda: self.ed.zoom(-1))
        QShortcut(QKeySequence("F3"), self, lambda: self.findbar.go(True))
        self.ed.changed_signal().connect(self._changed)
        if Qsci:
            self.ed.w.cursorPositionChanged.connect(lambda *a: self.pos_lbl.setText(self.ed.cursor_text()))
        else:
            self.ed.w.cursorPositionChanged.connect(lambda: self.pos_lbl.setText(self.ed.cursor_text()))
        self.pos_lbl.setText(self.ed.cursor_text())
        self.prev_timer = QTimer(singleShot=True, interval=400)
        self.prev_timer.timeout.connect(self.render_preview)
        if self.can_preview:
            self.prev_btn.setChecked(True)
            self.toggle_preview(True)
        self._title()

    def _title(self):
        self.title.emit(("● " if self.ed.modified() else "") + os.path.basename(self.path))

    def _changed(self):
        self._title()
        if self.preview and self.preview.isVisible():
            self.prev_timer.start()

    def toggle_preview(self, on):
        if on and self.preview is None:
            self.preview, self.is_web = make_web_view()
            self.split.addWidget(self.preview)
            self.split.setSizes([1, 1])
        if self.preview:
            self.preview.setVisible(on)
            if on:
                self.render_preview()

    def render_preview(self):
        text = self.ed.text()
        base = QUrl.fromLocalFile(os.path.dirname(self.path) + "/")
        html_text = markdown_html(text, base) if self.ext in ("md", "markdown") else text
        self.preview.setHtml(html_text, base) if self.is_web else self.preview.setHtml(html_text)

    def save(self):
        data = self.ed.text().encode(self.enc if self.enc not in ("utf-8-sig",) else "utf-8-sig", "replace")
        try:
            with open(self.path, "wb") as f:
                f.write(data)
        except PermissionError:
            if not self.root_mode:
                QMessageBox.warning(self, "云匣", "没有权限保存。打开 Root 模式后再试。")
                return False
            r = subprocess.run(["sudo", "-n", "tee", self.path], input=data, capture_output=True)
            if r.returncode != 0:
                QMessageBox.warning(self, "云匣", "保存失败：" + r.stderr.decode(errors="replace"))
                return False
        except OSError as e:
            QMessageBox.warning(self, "云匣", f"保存失败：{e}")
            return False
        self.ed.set_modified(False)
        self._title()
        return True

    def can_close(self):
        if not self.ed.modified():
            return True
        r = QMessageBox.question(self, "云匣", f"「{os.path.basename(self.path)}」改了还没保存，要保存吗？",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                 QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard


# =============== 视频（和暂时的音乐播放） ===============

def fmt_ms(ms):
    s = max(0, ms // 1000)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class MediaPlayer(QWidget):
    title = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PyQt6.QtMultimediaWidgets import QVideoWidget
        self.QMP = QMediaPlayer
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: black;")
        self.player.setVideoOutput(self.video)
        self.cover = QLabel()
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.video)
        self.stack.addWidget(self.cover)
        if util.kind_of(path) == "audio":
            img = thumbs.generate(path, "audio")
            pm = thumbs.decorate(img, "audio", 300) if img is not None else util.kind_pixmap("audio", 220, "♪")
            self.cover.setPixmap(pm)
            self.stack.setCurrentWidget(self.cover)
        self.play_btn = small_btn("暂停", "播放/暂停 (空格)", self.toggle)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.time = QLabel("0:00 / 0:00"); self.time.setObjectName("Muted")
        self.vol = QSlider(Qt.Orientation.Horizontal); self.vol.setRange(0, 100); self.vol.setValue(80)
        self.vol.setMaximumWidth(110)
        self.vol.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.audio.setVolume(0.8)
        self.speed = QComboBox(); self.speed.addItems(["0.5×", "1.0×", "1.25×", "1.5×", "2.0×"])
        self.speed.setCurrentIndex(1)
        self.speed.currentTextChanged.connect(lambda t: self.player.setPlaybackRate(float(t[:-1])))
        bar = Bar(self.play_btn, self.slider, self.time, QLabel("音量"), self.vol, self.speed,
                  small_btn("全屏", "全屏 (双击画面)", self.fullscreen))
        bar.lay.setStretch(1, 1)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.stack, 1)
        v.addWidget(bar)
        self.player.positionChanged.connect(self._pos)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.errorOccurred.connect(lambda e, s: self.time.setText("播放出错：" + s))
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        QShortcut(QKeySequence("Space"), self, self.toggle)
        QShortcut(QKeySequence("Right"), self, lambda: self.player.setPosition(self.player.position() + 5000))
        QShortcut(QKeySequence("Left"), self, lambda: self.player.setPosition(self.player.position() - 5000))
        QShortcut(QKeySequence("F"), self, self.fullscreen)
        self.video.installEventFilter(self)
        self.title.emit(os.path.basename(path))

    def eventFilter(self, o, ev):
        if ev.type() == QEvent.Type.MouseButtonDblClick:
            self.fullscreen()
            return True
        return False

    def toggle(self):
        if self.player.playbackState() == self.QMP.PlaybackState.PlayingState:
            self.player.pause(); self.play_btn.setText("播放")
        else:
            self.player.play(); self.play_btn.setText("暂停")

    def fullscreen(self):
        w = self.window()
        w.showNormal() if w.isFullScreen() else w.showFullScreen()

    def _pos(self, p):
        if not self.slider.isSliderDown():
            self.slider.setValue(p)
        self.time.setText(f"{fmt_ms(p)} / {fmt_ms(self.player.duration())}")

    def stop(self):
        self.player.stop()


# =============== 窗口 ===============

class ViewerWindow(QMainWindow):
    """每个打开的文件一个窗口（像手机版点开文件一样）。"""
    _open = []

    def __init__(self, widget, path):
        super().__init__()
        self.widget = widget
        self.setWindowTitle(os.path.basename(path) + " — 云匣")
        self.setWindowIcon(util.app_icon())
        if hasattr(widget, "title"):
            widget.title.connect(lambda t: self.setWindowTitle(t + " — 云匣"))
        self.setCentralWidget(widget)
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1200, int(scr.width() * .8)), min(820, int(scr.height() * .85)))
        ViewerWindow._open.append(self)
        QShortcut(QKeySequence("Escape"), self, lambda: self.showNormal() if self.isFullScreen() else None)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)

    def closeEvent(self, ev):
        if hasattr(self.widget, "can_close") and not self.widget.can_close():
            ev.ignore()
            return
        if hasattr(self.widget, "stop"):
            self.widget.stop()
        if self in ViewerWindow._open:
            ViewerWindow._open.remove(self)
        ev.accept()


TEXTLIKE = {"text", "code", "markdown", "html"}


def looks_text(path):
    try:
        chunk = open(path, "rb").read(4096)
    except OSError:
        return False
    if b"\0" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            chunk.decode("gb18030")
            return True
        except UnicodeDecodeError:
            return False


def viewer_for(path, root_mode=False, force=None):
    kind = force or util.kind_of(path)
    if kind == "image":
        return ImageViewer(path)
    if kind == "pdf":
        return PdfViewer(path)
    if kind in ("word", "excel", "ppt"):
        if util.ext_of(path) == "csv":
            return CodeEditor(path, root_mode)
        return OfficeViewer(path)
    if kind == "text" and util.ext_of(path) == "txt" and force != "code":
        return NovelReader(path, open_editor=lambda p: open_file(p, root_mode, force="code"))
    if kind in ("code", "markdown", "html", "text"):
        return CodeEditor(path, root_mode)
    if kind in ("video", "audio"):
        return MediaPlayer(path)
    if kind == "file" and looks_text(path):
        return CodeEditor(path, root_mode)
    return None


def open_file(path, root_mode=False, force=None):
    """能自己打开的就自己打开，返回窗口；打不开的返回 None。"""
    try:
        w = viewer_for(path, root_mode, force)
    except Exception as e:
        QMessageBox.warning(None, "云匣", f"预览失败：{e}")
        return None
    if w is None:
        return None
    win = ViewerWindow(w, path)
    win.show()
    return win
