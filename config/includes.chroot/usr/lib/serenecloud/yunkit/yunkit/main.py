# 云匣（电脑版）· 主窗口
# 作者：云安  https://github.com/ZW-SYS/SereneCloud-OS
import os, subprocess, sys

from PyQt6.QtCore import Qt, QSize, QTimer, QUrl, QMimeData
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut, QFont, QFontDatabase
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                             QMessageBox, QProgressBar, QSplitter, QToolButton, QVBoxLayout, QWidget,
                             QFileDialog, QButtonGroup)

from . import dialogs, ops, pane as panemod, sidebar, theme, thumbs, util, vfs, viewers

VERSION = "0.1"


class MainWindow(QMainWindow):
    def __init__(self, start=None):
        super().__init__()
        self.setWindowTitle("云匣")
        self.setWindowIcon(util.app_icon())
        self.root_mode = False
        self.clip = None        # ("copy"|"cut", [Entry])
        self.op = None
        self.search_job = None
        st = theme.settings()
        start = start or vfs.HOME

        # ---- 顶部工具栏 ----
        top = QWidget()
        top.setObjectName("Toolbar")
        th = QHBoxLayout(top)
        th.setContentsMargins(10, 8, 10, 4)
        th.setSpacing(4)
        self.view_btns = QButtonGroup(self)
        for i, (t, tip) in enumerate((("▦", "图标视图 (Ctrl+1)"), ("☰", "列表视图 (Ctrl+2)"), ("≣", "详细信息 (Ctrl+3)"))):
            b = panemod.tool(t, tip, lambda _, i=i: self.set_view(i), True)
            self.view_btns.addButton(b, i)
            th.addWidget(b)
        self.split_btn = panemod.tool("◫", "左右两栏 (F9)", lambda: self.toggle_split(), True)
        th.addWidget(self.split_btn)
        self.hidden_btn = panemod.tool("◌", "显示隐藏文件 (Ctrl+H)", lambda on: self.set_hidden(on), True)
        th.addWidget(self.hidden_btn)
        th.addSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("筛选当前文件夹，按回车搜索所有子文件夹")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(280)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self.deep_search)
        th.addWidget(self.search, 1)
        th.addSpacing(8)
        self.root_btn = QToolButton()
        self.root_btn.setText("Root 模式")
        self.root_btn.setCheckable(True)
        self.root_btn.setToolTip("打开后，没有权限的操作会用管理员身份去做（小心使用）")
        self.root_btn.toggled.connect(self.set_root)
        th.addWidget(self.root_btn)
        self.theme_btn = panemod.tool("◐", "深色 / 浅色", self.toggle_theme)
        th.addWidget(self.theme_btn)
        more = panemod.tool("⋯", "更多", lambda: None)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mm = QMenu(more)
        mm.addAction("新窗口", lambda: MainWindow(self.active.tab().loc).show())
        mm.addAction("在这里打开终端", self.open_terminal)
        mm.addAction("清除缩略图缓存", self.clear_thumbs)
        mm.addSeparator()
        mm.addAction("快捷键", self.show_keys)
        mm.addAction("关于云匣", self.about)
        more.setMenu(mm)
        th.addWidget(more)

        # ---- 两栏 ----
        self.side = sidebar.Sidebar()
        self.side.go.connect(lambda loc: self.active.open_loc(loc))
        self.panes = []
        self.splitter = QSplitter()
        self.splitter.setHandleWidth(8)
        right_start = st.value("right_loc", start)
        if not os.path.isdir(right_start):
            right_start = start
        for loc in (start, right_start):
            p = panemod.Pane(loc, lambda: self.root_mode)
            p.focused.connect(self.set_active)
            p.activated.connect(self.activate)
            p.contextRequested.connect(self.context_menu)
            p.status.connect(lambda pn, s: self.status_lbl.setText(s) if pn is self.active else None)
            p.dropRequested.connect(self.drop)
            p.locationChanged.connect(self._loc_changed)
            self.splitter.addWidget(p)
            self.panes.append(p)
        self.active = self.panes[0]
        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 10, 0)
        cv.setSpacing(0)
        cv.addWidget(top)
        cv.addWidget(self.splitter, 1)
        # 状态栏
        sb = QWidget()
        sh = QHBoxLayout(sb)
        sh.setContentsMargins(14, 4, 14, 6)
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("Muted")
        self.op_lbl = QLabel()
        self.op_lbl.setObjectName("Muted")
        self.op_bar = QProgressBar()
        self.op_bar.setFixedWidth(160)
        self.op_bar.setTextVisible(False)
        self.op_bar.hide()
        self.root_badge = QLabel(" ROOT ")
        self.root_badge.setStyleSheet(f"background: {theme.colors()['danger']}; color: white; border-radius: 6px; padding: 1px 6px;")
        self.root_badge.hide()
        sh.addWidget(self.status_lbl, 1)
        sh.addWidget(self.op_lbl)
        sh.addWidget(self.op_bar)
        sh.addWidget(self.root_badge)
        cv.addWidget(sb)
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.addWidget(self.side)
        h.addWidget(content, 1)
        self.setCentralWidget(central)

        self._shortcuts()
        mode = st.value("view_mode", panemod.VIEW_ICON, int)
        self.view_btns.button(mode).setChecked(True)
        split = st.value("split", True, bool)
        self.split_btn.setChecked(split)
        self.panes[1].setVisible(split)
        self.set_active(self.panes[0])
        self.resize(st.value("size", QSize(1320, 820)))

    # ---------- 基本 ----------
    def _shortcuts(self):
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        table = [
            ("Ctrl+C", self.copy), ("Ctrl+X", self.cut), ("Ctrl+V", self.paste),
            ("Delete", self.trash), ("Shift+Delete", self.delete), ("F2", self.rename),
            ("F5", lambda: self.to_other("copy")), ("F6", lambda: self.to_other("move")),
            ("Ctrl+A", lambda: self.active.tab().select_all()), ("Alt+Return", self.properties),
            ("Ctrl+Shift+N", self.new_folder),
        ]
        for key, fn in table:
            a = QAction(self.splitter)
            a.setShortcut(QKeySequence(key))
            a.setShortcutContext(ctx)
            a.triggered.connect(fn)
            self.splitter.addAction(a)
        glob = [
            ("Ctrl+T", lambda: self.active.new_tab(self.active.tab().loc)),
            ("Ctrl+W", lambda: self.active.close_tab(self.active.tabs.currentIndex())),
            ("Ctrl+L", lambda: self.active.crumbs.start_edit()),
            ("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())),
            ("Ctrl+H", lambda: self.hidden_btn.click()), ("F9", lambda: self.split_btn.click()),
            ("Ctrl+1", lambda: self.view_btns.button(0).click()), ("Ctrl+2", lambda: self.view_btns.button(1).click()),
            ("Ctrl+3", lambda: self.view_btns.button(2).click()), ("Alt+Left", lambda: self.active.tab().go_back()),
            ("Alt+Right", lambda: self.active.tab().go_forward()), ("Alt+Up", lambda: self.active.tab().go_up()),
            ("F5" if False else "Ctrl+R", lambda: self.active.tab().reload()), ("Tab", self.switch_pane),
            ("Ctrl+Tab", lambda: self.active.tabs.setCurrentIndex((self.active.tabs.currentIndex() + 1) % self.active.tabs.count())),
            ("F4", self.open_terminal), ("Ctrl+Q", self.close),
        ]
        for key, fn in glob:
            QShortcut(QKeySequence(key), self, fn)

    def set_active(self, p):
        self.active = p
        for x in self.panes:
            x.set_active(x is p and (not self.panes[1].isHidden()))
        t = p.tab()
        if t:
            t._emit_status()
            self.side.update_disk(t.loc)

    def other(self):
        return self.panes[1] if self.active is self.panes[0] else self.panes[0]

    def switch_pane(self):
        if (not self.panes[1].isHidden()):
            o = self.other()
            self.set_active(o)
            o.tab().current_view().setFocus()

    def toggle_split(self):
        on = self.split_btn.isChecked()
        self.panes[1].setVisible(on)
        theme.settings().setValue("split", on)
        if not on:
            self.set_active(self.panes[0])
        else:
            self.set_active(self.active)

    def set_view(self, i):
        for p in self.panes:
            p.set_view(i)

    def set_hidden(self, on):
        for p in self.panes:
            for t in p.all_tabs():
                t.model.show_hidden = on
                t.model.refilter()
                t._emit_status()

    def _filter(self, text):
        t = self.active.tab()
        if t.search_results is not None and not text:
            t.navigate(t.loc, record=False)
            return
        t.set_filter(text)

    def _loc_changed(self, p, loc):
        if self.search.text() and p is self.active:
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        if p is self.panes[1] and os.path.isdir(loc):
            theme.settings().setValue("right_loc", loc)
        self.side.update_disk(loc)

    def set_root(self, on):
        if on:
            r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
            if r.returncode != 0:
                QMessageBox.warning(self, "云匣", "这个账户不能免密码使用管理员权限，Root 模式开不了。")
                self.root_btn.setChecked(False)
                return
            QMessageBox.information(self, "Root 模式", "已打开 Root 模式。\n现在可以看和改系统文件了，删除前请想清楚 🙂")
        self.root_mode = on
        self.root_badge.setVisible(on)
        self.root_btn.setStyleSheet(f"background: {theme.colors()['danger']}; color: white;" if on else "")
        self.setWindowTitle("云匣（Root 模式）" if on else "云匣")
        for p in self.panes:
            for t in p.all_tabs():
                t.reload()

    def toggle_theme(self):
        st = theme.settings()
        st.setValue("theme", "light" if theme.current_name() == "dark" else "dark")
        theme.apply(QApplication.instance())
        util.kind_pixmap.cache_clear()
        for p in self.panes:
            p.set_active(p is self.active and (not self.panes[1].isHidden()))

    def clear_thumbs(self):
        import shutil
        shutil.rmtree(thumbs.CACHE, ignore_errors=True)
        thumbs.manager().clear()
        for p in self.panes:
            for t in p.all_tabs():
                t.reload()

    def open_terminal(self):
        loc = self.active.tab().loc
        if not os.path.isdir(loc):
            loc = vfs.HOME
        for term in (["konsole", "--workdir", loc], ["x-terminal-emulator"]):
            if util.have(term[0]):
                subprocess.Popen(term, cwd=loc)
                return

    # ---------- 打开 ----------
    def activate(self, p, e):
        tab = p.tab()
        if e.is_dir:
            tab.navigate(e.loc)
            return
        if e.archive:
            self.status_lbl.setText(f"正在从压缩包取出 {e.name}…")
            QApplication.processEvents()
            try:
                path = vfs.extract_member(e.archive, e.inner)
            except Exception as ex:
                QMessageBox.warning(self, "云匣", f"取不出来：{ex}")
                return
            if util.is_browsable_archive(e.name):
                tab.navigate(vfs.make_archive_loc(path, ""))
            else:
                self.open_path(path)
            return
        if e.local and util.is_browsable_archive(e.name) and e.kind != "deb":
            tab.navigate(vfs.make_archive_loc(e.local, ""))
            return
        self.open_path(e.local)

    def open_path(self, path, force=None):
        if viewers.open_file(path, self.root_mode, force) is None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---------- 右键菜单 ----------
    def context_menu(self, p, tab, sel, pos):
        self.set_active(p)
        m = QMenu(self)
        loc = tab.loc
        in_trash = loc == vfs.TRASH
        in_arc = vfs.is_archive_loc(loc)
        two = (not self.panes[1].isHidden())
        if sel:
            e = sel[0]
            if in_trash:
                m.addAction("还原", lambda: self.restore(sel))
                m.addAction("彻底删除", lambda: self.delete(sel))
                m.addSeparator()
                m.addAction("清空回收站", self.empty_trash)
                m.exec(pos)
                return
            if len(sel) == 1:
                m.addAction("打开", lambda: self.activate(p, e))
                if e.is_dir:
                    m.addAction("在新标签打开", lambda: p.new_tab(e.loc))
                    if two:
                        m.addAction("在另一栏打开", lambda: self.other().open_loc(e.loc))
                elif e.local:
                    om = m.addMenu("打开方式")
                    om.addAction("代码编辑器", lambda: self.open_path(e.local, "code"))
                    if e.kind == "text":
                        om.addAction("小说阅读模式", lambda: self.open_path(e.local, "text"))
                    om.addAction("系统默认程序", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(e.local)))
                m.addSeparator()
            if in_arc:
                m.addAction("取出到…", lambda: self.extract_to(sel))
                if two:
                    m.addAction("取出到另一栏  F5", lambda: self.to_other("copy"))
                m.addAction("复制", self.copy)
            else:
                m.addAction("复制\tCtrl+C", self.copy)
                m.addAction("剪切\tCtrl+X", self.cut)
                if two:
                    m.addAction("复制到另一栏\tF5", lambda: self.to_other("copy"))
                    m.addAction("移动到另一栏\tF6", lambda: self.to_other("move"))
                m.addSeparator()
                if len(sel) == 1:
                    m.addAction("重命名\tF2", self.rename)
                else:
                    m.addAction(f"批量重命名（{len(sel)} 个）\tF2", self.rename)
                m.addAction("压缩…", lambda: self.compress(sel))
                if len(sel) == 1 and util.is_browsable_archive(e.name):
                    m.addAction("解压到这里", lambda: self.extract_here(e, False))
                    m.addAction(f"解压到「{os.path.splitext(e.name)[0]}」文件夹", lambda: self.extract_here(e, True))
                m.addAction("复制路径", lambda: QApplication.clipboard().setText("\n".join(x.local for x in sel)))
                m.addSeparator()
                m.addAction("放进回收站\tDelete", self.trash)
                m.addAction("彻底删除\tShift+Delete", self.delete)
            m.addSeparator()
            if len(sel) == 1:
                m.addAction("属性\tAlt+Enter", self.properties)
        else:
            if in_trash:
                m.addAction("清空回收站", self.empty_trash)
            elif not in_arc:
                m.addAction("新建文件夹\tCtrl+Shift+N", self.new_folder)
                m.addAction("新建文本文件", self.new_file)
                pa = m.addAction("粘贴\tCtrl+V", self.paste)
                pa.setEnabled(bool(self.clip) or QApplication.clipboard().mimeData().hasUrls())
                m.addSeparator()
                m.addAction("在这里打开终端\tF4", self.open_terminal)
            else:
                m.addAction("全部解压到…", lambda: self.extract_to(None))
            m.addAction("全选\tCtrl+A", tab.select_all)
            m.addAction("刷新\tCtrl+R", tab.reload)
        m.exec(pos)

    # ---------- 操作 ----------
    def sel(self):
        return self.active.tab().selected()

    def cur_dir(self, p=None):
        loc = (p or self.active).tab().loc
        return loc if not vfs.is_archive_loc(loc) and loc != vfs.TRASH else None

    def run_op(self, op, entries, dest=None):
        if not entries:
            return
        if self.op and self.op.isRunning():
            QMessageBox.information(self, "云匣", "还有一个操作没做完，请稍等。")
            return
        self.op = ops.FileOp(op, entries, dest, self.root_mode)
        self.op_bar.show()
        self.op.progress.connect(self._op_progress)
        self.op.finished_ok.connect(lambda s: self._op_done(s))
        self.op.failed.connect(lambda s: (self._op_done(""), QMessageBox.warning(self, "云匣", s)))
        self.op.start()

    def _op_progress(self, i, n, name):
        self.op_bar.setRange(0, n)
        self.op_bar.setValue(i)
        self.op_lbl.setText(f"{name}  {i}/{n}" if name else "")

    def _op_done(self, msg):
        self.op_bar.hide()
        self.op_lbl.setText(msg)
        QTimer.singleShot(4000, lambda: self.op_lbl.setText(""))
        for p in self.panes:
            p.tab().reload_soon()

    def copy(self):
        s = self.sel()
        if s:
            self.clip = ("copy", s)
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(e.local) for e in s if e.local])
            QApplication.clipboard().setMimeData(md)
            self.op_lbl.setText(f"已复制 {len(s)} 项，到别的文件夹按 Ctrl+V 粘贴")

    def cut(self):
        s = [e for e in self.sel() if e.local]
        if s:
            self.clip = ("cut", s)
            self.op_lbl.setText(f"已剪切 {len(s)} 项")

    def paste(self):
        dest = self.cur_dir()
        if not dest:
            return
        if self.clip:
            mode, entries = self.clip
            self.run_op("move" if mode == "cut" else "copy", entries, dest)
            if mode == "cut":
                self.clip = None
            return
        md = QApplication.clipboard().mimeData()
        if md.hasUrls():
            es = [vfs.local_entry(u.toLocalFile()) for u in md.urls() if u.isLocalFile()]
            self.run_op("copy", [e for e in es if e], dest)

    def to_other(self, op):
        if not (not self.panes[1].isHidden()):
            return
        dest = self.cur_dir(self.other())
        if not dest:
            QMessageBox.information(self, "云匣", "另一栏现在不是普通文件夹，没法放进去。")
            return
        s = self.sel()
        if any(e.archive for e in s):
            op = "copy"
        self.run_op(op, s, dest)

    def drop(self, p, paths, dest, action):
        es = [vfs.local_entry(x) for x in paths]
        es = [e for e in es if e and os.path.dirname(e.local) != dest]
        if not es:
            return
        same_disk = all(os.stat(e.local).st_dev == os.stat(dest).st_dev for e in es)
        op = "move" if (action == Qt.DropAction.MoveAction or same_disk) and \
            not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier) else "copy"
        self.run_op(op, es, dest)

    def trash(self):
        s = [e for e in self.sel() if e.local]
        if self.active.tab().loc == vfs.TRASH:
            return self.delete(s)
        self.run_op("trash", s)

    def delete(self, s=None):
        s = s or [e for e in self.sel() if e.local]
        if not s:
            return
        if QMessageBox.question(self, "彻底删除", f"真的要彻底删除这 {len(s)} 项吗？删了就找不回来了。") \
                == QMessageBox.StandardButton.Yes:
            self.run_op("delete", s)

    def restore(self, s):
        bad = []
        for e in s:
            try:
                vfs.restore_trash(e)
            except Exception as ex:
                bad.append(f"{e.name}：{ex}")
        if bad:
            QMessageBox.warning(self, "云匣", "\n".join(bad))
        self.active.tab().reload()

    def empty_trash(self):
        if QMessageBox.question(self, "清空回收站", "回收站里的东西会全部删掉，确定吗？") == QMessageBox.StandardButton.Yes:
            vfs.empty_trash()
            self.active.tab().reload()

    def rename(self):
        s = [e for e in self.sel() if e.local]
        if not s or self.active.tab().loc == vfs.TRASH:
            return
        if len(s) > 1:
            try:
                n = dialogs.BatchRename(self, s).run()
            except OSError as ex:
                QMessageBox.warning(self, "云匣", f"改名出错：{ex}")
                n = 0
            if n:
                self.op_lbl.setText(f"改好了 {n} 个名字")
            self.active.tab().reload()
            return
        e = s[0]
        name = dialogs.ask_name(self, "重命名", "新名字：", e.name)
        if not name or name == e.name:
            return
        target = os.path.join(os.path.dirname(e.local), name)
        if os.path.exists(target):
            QMessageBox.warning(self, "云匣", "已经有同名的了。")
            return
        try:
            os.rename(e.local, target)
        except PermissionError:
            if not (self.root_mode and subprocess.run(["sudo", "-n", "mv", e.local, target]).returncode == 0):
                QMessageBox.warning(self, "云匣", "没有权限改名（可以打开 Root 模式）。")
                return
        except OSError as ex:
            QMessageBox.warning(self, "云匣", f"改名失败：{ex}")
            return
        self.active.tab()._keep = [target]
        self.active.tab().reload()
        QTimer.singleShot(300, lambda: self.active.tab().select_paths([target]))

    def new_folder(self):
        d = self.cur_dir()
        if not d:
            return
        name = dialogs.ask_name(self, "新建文件夹", "文件夹名字：", "新建文件夹", False)
        if name:
            target = vfs.unique_path(os.path.join(d, name))
            try:
                os.makedirs(target)
            except PermissionError:
                if not (self.root_mode and subprocess.run(["sudo", "-n", "mkdir", "-p", target]).returncode == 0):
                    QMessageBox.warning(self, "云匣", "没有权限（可以打开 Root 模式）。")
                    return
            self.active.tab().reload()
            QTimer.singleShot(300, lambda: self.active.tab().select_paths([target]))

    def new_file(self):
        d = self.cur_dir()
        if not d:
            return
        name = dialogs.ask_name(self, "新建文本文件", "文件名：", "新建文本.txt")
        if name:
            target = vfs.unique_path(os.path.join(d, name))
            try:
                open(target, "x").close()
            except OSError as ex:
                QMessageBox.warning(self, "云匣", f"建不了：{ex}")
                return
            self.active.tab().reload()

    def compress(self, sel):
        d = self.cur_dir()
        got = dialogs.CompressDialog(self, sel).get()
        if not got or not d:
            return
        name, fmt = got
        out = vfs.unique_path(os.path.join(d, name))
        self.op_lbl.setText("正在压缩…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            vfs.compress([e.local for e in sel], out, fmt)
            self.op_lbl.setText(f"压缩好了：{os.path.basename(out)}")
        except Exception as ex:
            QMessageBox.warning(self, "云匣", f"压缩失败：{ex}")
        finally:
            QApplication.restoreOverrideCursor()
        self.active.tab().reload()

    def extract_here(self, e, into_folder):
        d = os.path.dirname(e.local)
        if into_folder:
            stem = e.name
            for suf in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst"):
                if stem.lower().endswith(suf):
                    stem = stem[:-len(suf)]
                    break
            else:
                stem = os.path.splitext(stem)[0]
            d = vfs.unique_path(os.path.join(d, stem))
        self.op_lbl.setText("正在解压…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            vfs.extract_all(e.local, d)
            self.op_lbl.setText("解压好了 ✓")
        except Exception as ex:
            QMessageBox.warning(self, "云匣", f"解压失败：{ex}")
        finally:
            QApplication.restoreOverrideCursor()
        self.active.tab().reload()

    def extract_to(self, sel):
        d = QFileDialog.getExistingDirectory(self, "取出到哪里", vfs.HOME)
        if not d:
            return
        if sel:
            self.run_op("extract", sel, d)
        else:
            a, inner = vfs.split_archive(self.active.tab().loc)
            try:
                vfs.extract_all(a, d)
                self.op_lbl.setText("解压好了 ✓")
            except Exception as ex:
                QMessageBox.warning(self, "云匣", f"解压失败：{ex}")

    def properties(self):
        s = self.sel()
        if len(s) == 1:
            if dialogs.Properties(self, s[0], self.root_mode).apply():
                self.active.tab().reload()

    # ---------- 搜索 ----------
    def deep_search(self):
        text = self.search.text().strip()
        t = self.active.tab()
        root = t.loc if os.path.isdir(t.loc) else None
        if not text or not root:
            return
        if self.search_job and self.search_job.isRunning():
            self.search_job.stop = True
            self.search_job.wait(500)
        t.model.filter = ""
        t.show_search_results([], f"搜索 {text}")
        self.status_lbl.setText(f"正在「{vfs.title_of(root)}」里搜索「{text}」…")
        job = dialogs.SearchJob(root, text, self.hidden_btn.isChecked())
        found = []

        def batch(es):
            found.extend(es)
            t.show_search_results(list(found), f"搜索 {text}")

        job.batch.connect(batch)
        job.done.connect(lambda n: self.status_lbl.setText(f"找到 {n} 个  ·  清空搜索框回到文件夹"))
        self.search_job = job
        job.start()

    # ---------- 其他 ----------
    def show_keys(self):
        QMessageBox.information(self, "快捷键", "\n".join([
            "Tab：切换左右栏        F9：显示/隐藏右栏",
            "Ctrl+T / Ctrl+W：新标签 / 关闭标签",
            "Ctrl+1/2/3：图标 / 列表 / 详细",
            "Ctrl+滚轮：放大缩小图标",
            "F2：重命名（选多个就是批量）",
            "F5 / F6：复制 / 移动到另一栏",
            "Delete：回收站    Shift+Delete：彻底删除",
            "Ctrl+H：隐藏文件    Ctrl+L：输入路径",
            "Ctrl+F：搜索（回车搜索子文件夹）",
            "F4：在这里打开终端    Alt+Enter：属性",
        ]))

    def about(self):
        QMessageBox.about(self, "关于云匣", f"<h3>云匣 电脑版 {VERSION}</h3>"
                          "<p>云安 OS 自带的文件管理器：双栏、多标签、缩略图、压缩包当文件夹、预览和编辑。</p>"
                          "<p>作者：云安<br><a href='https://github.com/ZW-SYS/SereneCloud-OS'>"
                          "github.com/ZW-SYS/SereneCloud-OS</a></p>")

    def closeEvent(self, ev):
        theme.settings().setValue("size", self.size())
        super().closeEvent(ev)


def parse_arg(a):
    if a.startswith("file://"):
        return QUrl(a).toLocalFile()
    return os.path.abspath(os.path.expanduser(a))


def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("YunKit")
    app.setApplicationDisplayName("云匣")
    app.setDesktopFileName("yunkit")
    app.setWindowIcon(util.app_icon())
    f = app.font()
    f.setPointSize(10)
    app.setFont(f)
    theme.apply(app)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    start = None
    files = []
    for a in args:
        p = parse_arg(a)
        if os.path.isdir(p):
            start = start or p
        elif os.path.isfile(p):
            if util.is_browsable_archive(p):
                start = start or vfs.make_archive_loc(p, "")
            else:
                files.append(p)
    if files and not start:
        # 只打开文件（比如双击文本文件）：只开预览窗口
        wins = [viewers.open_file(f) for f in files]
        if not any(wins):
            for f in files:
                QDesktopServices.openUrl(QUrl.fromLocalFile(f))
            return 0
        return app.exec()
    w = MainWindow(start)
    w.show()
    return app.exec()
