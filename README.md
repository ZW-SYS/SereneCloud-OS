<p align="center"><img src="config/includes.chroot/usr/share/serenecloud/serenecloud-logo.png" width="120"></p>

# SereneCloud OS 云安

基于 **Debian 13 (trixie)** 的电脑版 Linux 系统，桌面是深度定制的 **KDE Plasma**。

- 作者：**云安**
- 适用：普通电脑（x86_64，UEFI 和传统 BIOS 都能启动）以及虚拟机
- 下载：见 [Releases](https://github.com/ZW-SYS/SereneCloud-OS/releases)（最新：v0.1.0 预览版）
- 试用账户：`yunan`，不需要密码

## 特点（规划中，按阶段完成）

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1 | 可启动的 Live + 安装器（Calamares）、开机动画（云朵汇聚成 SereneCloud）、云安主题与壁纸、多用户、管理员免密 sudo + 一键 Root 终端、全套硬件固件 | ✅ v0.1.0 |
| 2 | 更丰富的侧边栏/面板小部件和设置；内置代码运行器（HTML/CSS/JS、Python、C、C++、Java、Node.js、Go、Rust、Shell，全部离线自带）；Wine 运行 Windows 程序；20 个常用软件安装+启动测试 | ⏳ |
| 3 | 彩蛋 | ⏳ |
| 4 | 实验性：运行安卓 APK（Waydroid） | ⏳ |

## 下载后怎么用

1. 如果 Release 里 ISO 被切成了 `.part00`、`.part01`… 几个文件（GitHub 单文件上限 2 GB），先合并：
   - Linux / macOS：`cat SereneCloud-OS-*.iso.part* > SereneCloud-OS.iso`
   - Windows：`copy /b SereneCloud-OS-x.iso.part00 + SereneCloud-OS-x.iso.part01 SereneCloud-OS.iso`
2. 用 `SHA256SUMS` 校验。
3. 用 [Ventoy](https://www.ventoy.net) 或 [balenaEtcher](https://etcher.balena.io) 写入 U 盘，或者直接在 VirtualBox / VMware / QEMU 里打开。
4. 开机进入试用桌面，点桌面上的「安装云安 OS」安装到硬盘。

## 自己构建

ISO 由 GitHub Actions 自动构建（`.github/workflows/build-iso.yml`），每次推送到 `main` 都会构建并在 QEMU 里做启动测试、截图。

本地构建（需要 Debian 13 或 Debian 容器，root 权限）：

```bash
sudo apt install live-build
sudo lb config && sudo lb build
```

修改品牌素材：`python3 branding/tools/gen_branding.py`（需要 Pillow）。

## 目录

- `auto/config` — live-build 主配置
- `config/package-lists/` — 预装软件
- `config/includes.chroot/` — 直接放进系统里的文件（主题、开机动画、配置）
- `config/hooks/` — 构建时运行的脚本
- `tests/boot-test.sh` — QEMU 启动测试
- `branding/tools/` — 生成壁纸、Logo、开机动画帧

## 许可证

GPL-3.0-or-later。云安 OS 基于 Debian 及其自由软件；非自由固件按各自许可证分发。
