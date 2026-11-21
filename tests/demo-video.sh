#!/usr/bin/env bash
# 自动录制演示视频：U 盘开机菜单 → 开机动画 → 桌面 → 打开常用软件。
# 在 QEMU 虚拟机里运行，用键盘自动操作，每秒截 4 张图，最后合成 MP4。
# 用法：tests/demo-video.sh path/to.iso out_dir
set -uo pipefail
ISO="$1"; OUT="${2:-demo-out}"; mkdir -p "$OUT"
ACCEL="-machine accel=kvm -cpu host"; [ -w /dev/kvm ] || ACCEL="-machine accel=tcg -cpu max"
WORK=$(mktemp -d); FR="$WORK/frames"; mkdir -p "$FR"
cp /usr/share/OVMF/OVMF_VARS_4M.fd "$WORK/vars.fd" 2>/dev/null || cp /usr/share/OVMF/OVMF_VARS.fd "$WORK/vars.fd"
CODE=/usr/share/OVMF/OVMF_CODE_4M.fd; [ -f "$CODE" ] || CODE=/usr/share/OVMF/OVMF_CODE.fd

qemu-system-x86_64 $ACCEL -m 6144 -smp 4 -vga virtio -display none \
  -drive if=pflash,format=raw,readonly=on,file="$CODE" -drive if=pflash,format=raw,file="$WORK/vars.fd" \
  -cdrom "$ISO" -nic user,model=virtio-net-pci \
  -chardev socket,id=m1,path="$WORK/cap.sock",server=on,wait=off -mon chardev=m1,mode=readline \
  -chardev socket,id=m2,path="$WORK/key.sock",server=on,wait=off -mon chardev=m2,mode=readline &
QPID=$!
sleep 1

# 截图线程：一直开着一个监视器连接，每 0.25 秒截一张
( i=0; while kill -0 $QPID 2>/dev/null; do
    printf 'screendump %s/f%05d.ppm\n' "$FR" "$i"; i=$((i+1)); sleep 0.25
  done ) | socat - UNIX-CONNECT:"$WORK/cap.sock" >/dev/null 2>&1 &
CAP=$!

# 键盘线程用的连接
coproc KEYS { socat - UNIX-CONNECT:"$WORK/key.sock"; }
key() { echo "sendkey $1" >&"${KEYS[1]}"; sleep 0.15; }
type_text() { # 一个字一个字地打
  local s="$1" c k
  for ((n=0; n<${#s}; n++)); do
    c="${s:n:1}"
    case "$c" in
      [a-z0-9]) k="$c" ;;
      [A-Z]) k="shift-${c,,}" ;;
      ' ') k=spc ;; '-') k=minus ;; '_') k=shift-minus ;; '.') k=dot ;; '/') k=slash ;;
      ':') k=shift-semicolon ;; '=') k=equal ;; '|') k=shift-backslash ;; "'") k=apostrophe ;;
      '(') k=shift-9 ;; ')') k=shift-0 ;; '"') k=shift-apostrophe ;; ',') k=comma ;;
      *) continue ;;
    esac
    echo "sendkey $k" >&"${KEYS[1]}"; sleep 0.09
  done
}
run() { # 用 KRunner（Alt+F2）运行一条命令
  key alt-f2; sleep 1.5; type_text "$1"; sleep 1.5; key ret
}

echo "等待开机（开机菜单 5 秒后自动启动）..."
sleep 75

echo "1) Firefox 打开项目主页"
run "firefox-esr"; sleep 18
key ctrl-l; sleep 1; type_text "github.com/ZW-SYS/SereneCloud-OS"; key ret; sleep 16
key meta_l-pgdn; sleep 3   # 最小化（不关，避免弹出“关闭多个标签页”的确认框）

echo "2) 文件管理器 Dolphin"
run "dolphin"; sleep 8
key ctrl-q; sleep 3

echo "3) 设置 → 关于本系统"
run "systemsettings kcm_about-distro"; sleep 12
key ctrl-q; sleep 3

echo "4) Root 终端"
run "serenecloud-root-terminal"; sleep 6
type_text "whoami"; key ret; sleep 1.5
type_text "cat /etc/os-release | head -4"; key ret; sleep 1.5
type_text "uname -r"; key ret; sleep 1.5
type_text "free -h"; key ret; sleep 5
type_text "exit"; key ret; sleep 3

echo "5) 文本编辑器 Kate"
run "kate"; sleep 8
type_text "print('Hello, SereneCloud OS!')"; sleep 4
key meta_l-pgdn; sleep 3

echo "6) 安装器"
run "calamares-install-debian"; sleep 25

kill $CAP 2>/dev/null; kill $QPID 2>/dev/null; wait $QPID 2>/dev/null
kill "$KEYS_PID" 2>/dev/null || true

N=$(ls "$FR" | wc -l); echo "共 $N 帧"
# 合成视频：统一成 1280x800，4 帧/秒的截图转成 30 帧/秒的视频
ffmpeg -y -loglevel error -framerate 4 -pattern_type glob -i "$FR/f*.ppm" \
  -vf "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p" \
  -c:v libx264 -preset medium -crf 23 -movflags +faststart "$OUT/SereneCloud-OS-demo.mp4"
# 缩略总览图（方便检查）：均匀取 16 帧
mkdir -p "$WORK/sheet"
ls "$FR"/f*.ppm | awk -v n="$N" 'NR % int(n/16 + 1) == 1' | head -16 | while read -r f; do
  convert "$f" -resize 480x300 "$WORK/sheet/$(basename "$f" .ppm).png"
done
montage "$WORK/sheet"/*.png -tile 4x -geometry +4+4 -background '#1b2b44' "$OUT/demo-overview.jpg" 2>/dev/null || true
ls -lh "$OUT"
[ -s "$OUT/SereneCloud-OS-demo.mp4" ] || { echo "❌ 视频没有生成"; exit 1; }
