# 云匣 · 文件栏：一栏里有多个标签，每个标签有 图标 / 列表 / 详细 三种视图
import os, stat

from PyQt6.QtCore import (Qt, QAbstractTableModel, QModelIndex, QSize, QThread, QUrl, QMimeData,
                          pyqtSignal, QTimer, QFileSystemWatcher, QItemSelectionModel, QEvent)
from PyQt6.QtGui import QAction, QKeySequence, QPixmap, QIcon, QFont, QColor, QPainter
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListView, QMenu, QStackedWidget, QStyledItemDelegate, QTabWidget,
                             QToolButton, QTreeView, QVBoxLayout, QWidget, QStyle, QTabBar,
                             QStyleOptionViewItem)

from . import thumbs, util, vfs, theme

COLS = ["名称", "大小", "类型", "修改时间", "权限"]
VIEW_ICON, VIEW_LIST, VIEW_DETAIL = 0, 1, 2


class Loader(QThread):
    loaded = pyqtSignal(int, list, str)

    def __init__(self, token, loc, root):
        super().__init__()
        self.token, self.loc, self.root = token, loc, root

    def run(self):
        try:
            self.loaded.emit(self.token, vfs.list_loc(self.loc, self.root), "")
        except vfs.ListError as e:
            self.loaded.emit(self.token, [], str(e))
        except Exception as e:
            self.loaded.emit(self.token, [], f"出错了：{e}")


class FileModel(QAbstractTableModel):
    dropRequested = pyqtSignal(list, str, object)   # 路径们, 目标文件夹, 动作

    def __init__(self):
        super().__init__()
        self.all = []
        self.rows = []
        self.show_hidden = False
        self.filter = ""
        self.sort_col, self.sort_order = 0, Qt.SortOrder.AscendingOrder
        self.icon_px = 64
        self.loc = ""
        self.row_of = {}
        thumbs.manager().ready.connect(self._thumb_ready)

    # ---- 数据 ----
    def set_entries(self, entries, loc):
        self.beginResetModel()
        self.all = entries
        self.loc = loc
        self._rebuild()
        self.endResetModel()

    def refilter(self):
        self.beginResetModel()
        self._rebuild()
        self.endResetModel()

    def _rebuild(self):
        rows = [e for e in self.all if (self.show_hidden or not e.hidden)]
        if self.filter:
            f = self.filter.lower()
            rows = [e for e in rows if f in e.name.lower()]
        key = {
            0: lambda e: e.name.lower(),
            1: lambda e: e.size,
            2: lambda e: (util.KIND_NAME.get(e.kind, ""), e.name.lower()),
            3: lambda e: e.mtime,
            4: lambda e: e.mode,
        }[self.sort_col]
        rev = self.sort_order == Qt.SortOrder.DescendingOrder
        dirs = sorted([e for e in rows if e.is_dir], key=key, reverse=rev)
        files = sorted([e for e in rows if not e.is_dir], key=key, reverse=rev)
        self.rows = dirs + files
        self.row_of = {e.local: i for i, e in enumerate(self.rows) if e.local}

    def sort(self, col, order=Qt.SortOrder.AscendingOrder):
        self.sort_col, self.sort_order = col, order
        self.refilter()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, s, o, role=Qt.ItemDataRole.DisplayRole):
        if o == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLS[s]
        return None

    def entry(self, index):
        return self.rows[index.row()] if index.isValid() and index.row() < len(self.rows) else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        e = self.entry(index)
        if e is None:
            return None
        c = index.column()
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if c == 0:
                return e.name
            if c == 1:
                return "" if e.is_dir else util.human_size(e.size)
            if c == 2:
                return util.KIND_NAME.get(e.kind, "文件") + ("" if e.is_dir else f" ({util.ext_of(e.name).upper()})" if util.ext_of(e.name) else "")
            if c == 3:
                return util.human_time(e.mtime)
            if c == 4:
                return util.perm_string(e.mode) if e.mode else ""
        if role == Qt.ItemDataRole.DecorationRole and c == 0:
            if e.local and not e.is_dir and e.kind in thumbs.THUMB_KINDS:
                pm = thumbs.manager().pixmap(e.local, e.kind, self.icon_px)
                if pm is not None:
                    return pm
            return util.kind_pixmap(e.kind, self.icon_px, "" if e.is_dir else (util.ext_of(e.name) or "file"))
        if role == Qt.ItemDataRole.ToolTipRole and c == 0:
            tip = e.name
            if self.loc and e.local and os.path.dirname(e.local) != self.loc:
                tip += f"\n在：{os.path.dirname(e.local)}"
            if not e.is_dir:
                tip += f"\n{util.human_size(e.size)}"
            if e.extra.get("orig"):
                tip += f"\n原来的位置：{e.extra['orig']}"
            return tip
        if role == Qt.ItemDataRole.ForegroundRole and e.hidden:
            return QColor(theme.colors()["text2"])
        if role == Qt.ItemDataRole.TextAlignmentRole and c == 1:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def _thumb_ready(self, path):
        r = self.row_of.get(path)
        if r is not None and r < len(self.rows):
            i = self.index(r, 0)
            self.dataChanged.emit(i, i, [Qt.ItemDataRole.DecorationRole])

    # ---- 拖放 ----
    def flags(self, index):
        f = super().flags(index)
        if not index.isValid():
            return f | Qt.ItemFlag.ItemIsDropEnabled
        e = self.entry(index)
        f |= Qt.ItemFlag.ItemIsDragEnabled
        if e and e.is_dir and e.local:
            f |= Qt.ItemFlag.ItemIsDropEnabled
        return f

    def mimeTypes(self):
        return ["text/uri-list"]

    def supportedDropActions(self):
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def mimeData(self, indexes):
        md = QMimeData()
        seen, urls = set(), []
        for i in indexes:
            e = self.entry(i)
            if e and e.local and e.local not in seen:
                seen.add(e.local)
                urls.append(QUrl.fromLocalFile(e.local))
        md.setUrls(urls)
        return md

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasUrls() and not vfs.is_archive_loc(self.loc) and self.loc != vfs.TRASH

    def dropMimeData(self, data, action, row, column, parent):
        dest = self.loc
        e = self.entry(parent)
        if e and e.is_dir and e.local:
            dest = e.local
        paths = [u.toLocalFile() for u in data.urls() if u.isLocalFile()]
        if paths:
            self.dropRequested.emit(paths, dest, action)
        return False


class IconDelegate(QStyledItemDelegate):
    """图标视图：图标在上，名字最多两行（太长中间省略），选中/悬停是圆角高亮。"""

    def paint(self, p, option, index):
        from PyQt6.QtGui import QTextLayout, QTextOption as TO
        from PyQt6.QtCore import QRectF, QPointF
        c = theme.colors()
        r = option.rect.adjusted(3, 3, -3, -3)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = option.state & QStyle.StateFlag.State_Selected
        hover = option.state & QStyle.StateFlag.State_MouseOver
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["sel"] if selected else c["hover"]))
            p.drawRoundedRect(QRectF(r), 10, 10)
        pm = index.data(Qt.ItemDataRole.DecorationRole)
        isz = self.parent().iconSize().width()
        if isinstance(pm, QPixmap) and not pm.isNull():
            if pm.width() != isz:
                pm = pm.scaled(isz, isz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = r.x() + (r.width() - pm.width()) // 2
            y = r.y() + 6 + (isz - pm.height()) // 2
            p.drawPixmap(x, y, pm)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        p.setPen(fg if isinstance(fg, QColor) else QColor(c["text"]))
        p.setFont(option.font)
        fm = option.fontMetrics
        tw = r.width() - 8
        top = r.y() + isz + 12
        lay = QTextLayout(text, option.font)
        opt = TO()
        opt.setWrapMode(TO.WrapMode.WrapAtWordBoundaryOrAnywhere)
        opt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.setTextOption(opt)
        lay.beginLayout()
        lines = []
        while len(lines) < 2:
            ln = lay.createLine()
            if not ln.isValid():
                break
            ln.setLineWidth(tw)
            lines.append(ln)
        lay.endLayout()
        for i, ln in enumerate(lines):
            y = top + i * fm.height()
            if i == 1 and ln.textStart() + ln.textLength() < len(text):
                rest = fm.elidedText(text[ln.textStart():], Qt.TextElideMode.ElideMiddle, tw)
                p.drawText(QRectF(r.x() + 4, y, tw, fm.height()), Qt.AlignmentFlag.AlignHCenter, rest)
            else:
                ln.draw(p, QPointF(r.x() + 4, y))
        p.restore()

    def sizeHint(self, option, index):
        isz = self.parent().iconSize().width()
        return QSize(isz + 40, isz + 58)


class FileTab(QWidget):
    locationChanged = pyqtSignal(str)
    activated = pyqtSignal(object)             # Entry
    contextRequested = pyqtSignal(object, list, object)
    status = pyqtSignal(str)
    focused = pyqtSignal()

    def __init__(self, loc, view_mode=VIEW_ICON, root_getter=lambda: False):
        super().__init__()
        self.loc = ""
        self.back, self.fwd = [], []
        self.root_getter = root_getter
        self.token = 0
        self.loader = None
        self.model = FileModel()
        self.search_results = None

        self.icon_view = QListView()
        self.icon_view.setViewMode(QListView.ViewMode.IconMode)
        self.icon_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.icon_view.setMovement(QListView.Movement.Static)
        self.icon_view.setUniformItemSizes(True)
        self.icon_view.setWordWrap(True)
        self.icon_view.setSpacing(6)
        self.icon_view.setItemDelegate(IconDelegate(self.icon_view))
        self.list_view = QListView()
        self.list_view.setViewMode(QListView.ViewMode.ListMode)
        self.list_view.setFlow(QListView.Flow.TopToBottom)
        self.list_view.setUniformItemSizes(True)
        self.detail_view = QTreeView()
        self.detail_view.setRootIsDecorated(False)
        self.detail_view.setSortingEnabled(True)
        self.detail_view.setUniformRowHeights(True)
        self.detail_view.setAlternatingRowColors(False)
        self.detail_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.views = [self.icon_view, self.list_view, self.detail_view]
        self.stack = QStackedWidget()
        for v in self.views:
            v.setModel(self.model)
            v.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            v.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            v.customContextMenuRequested.connect(lambda pos, v=v: self._ctx(v, pos))
            v.doubleClicked.connect(self._activate)
            v.activated.connect(self._activate) if False else None
            v.setDragEnabled(True)
            v.setAcceptDrops(True)
            v.setDropIndicatorShown(True)
            v.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            v.setDefaultDropAction(Qt.DropAction.CopyAction)
            v.installEventFilter(self)
            v.viewport().installEventFilter(self)
            v.setFrameShape(QFrame.Shape.NoFrame)
            v.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.stack.addWidget(v)
        for v in self.views:
            v.selectionModel().selectionChanged.connect(self._sel_changed)
        hdr = self.detail_view.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(False)
        for i, w in ((1, 80), (2, 120), (3, 120), (4, 84)):
            self.detail_view.setColumnWidth(i, w)
        self.empty = QLabel("")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        self.watcher = QFileSystemWatcher()
        self.watcher.directoryChanged.connect(lambda _: self.reload_soon())
        self.reload_timer = QTimer(singleShot=True, interval=300)
        self.reload_timer.timeout.connect(self.reload)
        self.view_mode = VIEW_ICON
        self.set_view(view_mode)
        self.navigate(loc, record=False)

    # ---- 视图 ----
    def current_view(self):
        return self.views[self.view_mode]

    def set_view(self, mode, zoom=None):
        self.view_mode = mode
        sel = self.selected_paths()
        if mode == VIEW_ICON:
            px = zoom or theme.settings().value("icon_size", 96, int)
            self.model.icon_px = px
            self.icon_view.setIconSize(QSize(px, px))
            self.icon_view.setGridSize(QSize(px + 46, px + 64))
        elif mode == VIEW_LIST:
            self.model.icon_px = 28
            self.list_view.setIconSize(QSize(28, 28))
            self.list_view.setGridSize(QSize(0, 0))
        else:
            self.model.icon_px = 24
            self.detail_view.setIconSize(QSize(24, 24))
        self.model.layoutChanged.emit()
        if self.stack.currentWidget() is not self.empty:
            self.stack.setCurrentIndex(mode)
        self.select_paths(sel)

    def zoom(self, delta):
        if self.view_mode != VIEW_ICON:
            return
        px = max(48, min(256, self.model.icon_px + delta))
        theme.settings().setValue("icon_size", px)
        self.set_view(VIEW_ICON, px)

    # ---- 导航 ----
    def navigate(self, loc, record=True):
        if record and self.loc and loc != self.loc:
            self.back.append(self.loc)
            self.fwd.clear()
        self.search_results = None
        old = self.loc
        self.loc = loc
        self.model.filter = ""
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        if not vfs.is_archive_loc(loc) and loc != vfs.TRASH and os.path.isdir(loc):
            self.watcher.addPath(loc)
        elif loc == vfs.TRASH and os.path.isdir(os.path.join(vfs.TRASH_DIR, "files")):
            self.watcher.addPath(os.path.join(vfs.TRASH_DIR, "files"))
        self._load(select_name=os.path.basename(old.rstrip("/")) if old and vfs.parent_of(old) == loc else None)
        self.locationChanged.emit(loc)

    def _load(self, select_name=None, keep=None):
        self.token += 1
        if vfs.is_archive_loc(self.loc) and not keep:
            self.empty.setText("正在打开压缩包…")
            self.stack.setCurrentWidget(self.empty)
        self._select_after = select_name
        self._keep = keep
        ld = Loader(self.token, self.loc, self.root_getter())
        ld.loaded.connect(self._loaded)
        ld.finished.connect(ld.deleteLater)
        self.loader = ld
        ld.start()

    def _loaded(self, token, entries, err):
        if token != self.token:
            return
        self.model.set_entries(entries, self.loc)
        if err:
            self.empty.setText("⚠️  " + err)
            self.stack.setCurrentWidget(self.empty)
        elif not self.model.rows:
            self.empty.setText("回收站是空的" if self.loc == vfs.TRASH else "这里什么都没有")
            self.stack.setCurrentWidget(self.empty)
        else:
            self.stack.setCurrentIndex(self.view_mode)
        if self._keep:
            self.select_paths(self._keep)
        elif self._select_after:
            for i, e in enumerate(self.model.rows):
                if e.name == self._select_after:
                    idx = self.model.index(i, 0)
                    self.current_view().setCurrentIndex(idx)
                    self.current_view().scrollTo(idx)
                    break
        self._emit_status()

    def reload_soon(self):
        self.reload_timer.start()

    def reload(self):
        if self.search_results is not None:
            return
        self._load(keep=self.selected_paths())

    def go_back(self):
        if self.back:
            self.fwd.append(self.loc)
            self.navigate(self.back.pop(), record=False)

    def go_forward(self):
        if self.fwd:
            self.back.append(self.loc)
            self.navigate(self.fwd.pop(), record=False)

    def go_up(self):
        p = vfs.parent_of(self.loc)
        if p != self.loc:
            self.navigate(p)

    def show_search_results(self, entries, title):
        self.search_results = title
        self.model.set_entries(entries, self.loc)
        self.stack.setCurrentIndex(self.view_mode) if entries else (
            self.empty.setText("没有找到"), self.stack.setCurrentWidget(self.empty))
        self._emit_status()

    def set_filter(self, text):
        self.model.filter = text
        self.model.refilter()
        self._emit_status()

    # ---- 选择 ----
    def selected(self):
        v = self.current_view()
        rows = sorted({i.row() for i in v.selectionModel().selectedIndexes()})
        return [self.model.rows[r] for r in rows if r < len(self.model.rows)]

    def selected_paths(self):
        return [e.loc for e in self.selected()]

    def select_paths(self, locs):
        if not locs:
            return
        v = self.current_view()
        sm = v.selectionModel()
        sm.clearSelection()
        s = set(locs)
        first = None
        for i, e in enumerate(self.model.rows):
            if e.loc in s:
                idx = self.model.index(i, 0)
                sm.select(idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                first = first or idx
        if first:
            v.scrollTo(first)

    def select_all(self):
        self.current_view().selectAll()

    def _sel_changed(self, *a):
        self._emit_status()

    def _emit_status(self):
        rows = self.model.rows
        sel = self.selected()
        nd = sum(1 for e in rows if e.is_dir)
        txt = f"{nd} 个文件夹，{len(rows) - nd} 个文件"
        if sel:
            size = sum(e.size for e in sel if not e.is_dir)
            txt = f"选中 {len(sel)} 项" + (f"，{util.human_size(size)}" if size else "") + "  ·  " + txt
        self.status.emit(txt)

    # ---- 事件 ----
    def _activate(self, index):
        e = self.model.entry(index)
        if e:
            self.activated.emit(e)

    def _ctx(self, view, pos):
        idx = view.indexAt(pos)
        if idx.isValid() and not view.selectionModel().isSelected(idx):
            view.selectionModel().select(idx, QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                         QItemSelectionModel.SelectionFlag.Rows)
        if not idx.isValid():
            view.clearSelection()
        self.contextRequested.emit(self, self.selected(), view.viewport().mapToGlobal(pos))

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
            self.focused.emit()
        if t == QEvent.Type.Wheel and ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(16 if ev.angleDelta().y() > 0 else -16)
            return True
        if t == QEvent.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                for e in self.selected()[:1]:
                    self.activated.emit(e)
                return True
            if k == Qt.Key.Key_Backspace:
                self.go_up()
                return True
            if ev.modifiers() & Qt.KeyboardModifier.MetaModifier:
                return False
        if t == QEvent.Type.MouseButtonPress:
            if ev.button() == Qt.MouseButton.BackButton:
                self.go_back(); return True
            if ev.button() == Qt.MouseButton.ForwardButton:
                self.go_forward(); return True
        return super().eventFilter(obj, ev)


class Crumbs(QWidget):
    """路径栏：平时显示成一节一节的按钮，点空白处变成可输入。"""
    go = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("PathBar")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(4, 2, 4, 2)
        self.lay.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.hide()
        self.edit.returnPressed.connect(self._typed)
        self.edit.installEventFilter(self)
        self.btns = QWidget()
        self.bl = QHBoxLayout(self.btns)
        self.bl.setContentsMargins(0, 0, 0, 0)
        self.bl.setSpacing(0)
        self.lay.addWidget(self.btns, 1)
        self.lay.addWidget(self.edit, 1)
        self.loc = ""

    def set_loc(self, loc):
        self.loc = loc
        while self.bl.count():
            w = self.bl.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        parts = vfs.display_parts(loc)
        if len(parts) > 5:
            parts = [parts[0], ("…", parts[-5][1])] + parts[-4:]
        for i, (name, target) in enumerate(parts):
            if i:
                sep = QLabel("›")
                sep.setObjectName("Muted")
                self.bl.addWidget(sep)
            b = QToolButton()
            b.setObjectName("Crumb")
            b.setText(name)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == len(parts) - 1:
                f = b.font(); f.setBold(True); b.setFont(f)
            b.clicked.connect(lambda _, t=target: self.go.emit(t))
            self.bl.addWidget(b)
        self.bl.addStretch(1)

    def mousePressEvent(self, ev):
        self.start_edit()

    def start_edit(self):
        self.btns.hide()
        self.edit.setText(self.loc)
        self.edit.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def _typed(self):
        t = os.path.expanduser(self.edit.text().strip())
        self.end_edit()
        if t:
            self.go.emit(t)

    def end_edit(self):
        self.edit.hide()
        self.btns.show()

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == QEvent.Type.FocusOut:
            self.end_edit()
        if obj is self.edit and ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
            self.end_edit()
            return True
        return False


def tool(text, tip, cb, checkable=False):
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(cb)
    f = b.font(); f.setPointSize(12); b.setFont(f)
    b.setFixedSize(32, 32)
    return b


class Pane(QFrame):
    """一栏：顶上是后退/前进/上一级 + 路径，下面是标签页。"""
    focused = pyqtSignal(object)
    activated = pyqtSignal(object, object)          # pane, entry
    contextRequested = pyqtSignal(object, object, list, object)
    status = pyqtSignal(object, str)
    dropRequested = pyqtSignal(object, list, str, object)
    locationChanged = pyqtSignal(object, str)

    def __init__(self, start, root_getter):
        super().__init__()
        self.setObjectName("Pane")
        self.root_getter = root_getter
        self.view_mode = theme.settings().value("view_mode", VIEW_ICON, int)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 6)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(2)
        self.b_back = tool("‹", "后退 (Alt+←)", lambda: self.tab().go_back())
        self.b_fwd = tool("›", "前进 (Alt+→)", lambda: self.tab().go_forward())
        self.b_up = tool("⌃", "上一级 (Backspace)", lambda: self.tab().go_up())
        self.crumbs = Crumbs()
        self.crumbs.go.connect(lambda loc: self.open_loc(loc))
        for w in (self.b_back, self.b_fwd, self.b_up):
            top.addWidget(w)
        top.addWidget(self.crumbs, 1)
        v.addLayout(top)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setMovable(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        plus = QToolButton()
        plus.setText("+")
        plus.setToolTip("新标签 (Ctrl+T)")
        plus.clicked.connect(lambda: self.new_tab(self.tab().loc if self.tab() else start))
        self.tabs.setCornerWidget(plus, Qt.Corner.TopRightCorner)
        v.addWidget(self.tabs, 1)
        self.new_tab(start)

    def tab(self):
        return self.tabs.currentWidget()

    def all_tabs(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def new_tab(self, loc):
        t = FileTab(loc, self.view_mode, self.root_getter)
        t.locationChanged.connect(lambda l, t=t: self._loc_changed(t, l))
        t.activated.connect(lambda e: self.activated.emit(self, e))
        t.contextRequested.connect(lambda tab, sel, pos: self.contextRequested.emit(self, tab, sel, pos))
        t.status.connect(lambda s, t=t: self.status.emit(self, s) if t is self.tab() else None)
        t.focused.connect(lambda: self.focused.emit(self))
        t.model.dropRequested.connect(lambda paths, dest, act: self.dropRequested.emit(self, paths, dest, act))
        i = self.tabs.addTab(t, vfs.title_of(loc))
        x = QToolButton()
        x.setText("×")
        x.setToolTip("关闭标签 (Ctrl+W)")
        x.setFixedSize(18, 18)
        x.setStyleSheet("QToolButton { padding: 0; border-radius: 9px; font-size: 12pt; }")
        x.clicked.connect(lambda _, t=t: self.close_tab(self.tabs.indexOf(t)))
        self.tabs.tabBar().setTabButton(i, QTabBar.ButtonPosition.RightSide, x)
        self._update_close()
        self.tabs.setCurrentIndex(i)
        self._loc_changed(t, t.loc)
        return t

    def close_tab(self, i):
        if self.tabs.count() <= 1:
            return
        w = self.tabs.widget(i)
        self.tabs.removeTab(i)
        w.deleteLater()
        self._update_close()

    def _update_close(self):
        bar = self.tabs.tabBar()
        for i in range(self.tabs.count()):
            b = bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if b:
                b.setVisible(self.tabs.count() > 1)

    def _tab_changed(self, i):
        t = self.tab()
        if t:
            self.crumbs.set_loc(t.loc)
            t._emit_status()
            self.focused.emit(self)

    def _loc_changed(self, t, loc):
        i = self.tabs.indexOf(t)
        if i >= 0:
            title = vfs.title_of(loc)
            self.tabs.setTabText(i, title if len(title) < 18 else title[:16] + "…")
            self.tabs.setTabToolTip(i, loc)
        if t is self.tab():
            self.crumbs.set_loc(loc)
            self.b_back.setEnabled(bool(t.back))
            self.b_fwd.setEnabled(bool(t.fwd))
        self.locationChanged.emit(self, loc)

    def open_loc(self, loc):
        if not vfs.is_archive_loc(loc) and loc != vfs.TRASH:
            loc = os.path.abspath(loc)
        self.tab().navigate(loc)

    def set_active(self, on):
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_view(self, mode):
        self.view_mode = mode
        theme.settings().setValue("view_mode", mode)
        for t in self.all_tabs():
            t.set_view(mode)
