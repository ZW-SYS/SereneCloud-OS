#!/usr/bin/env bash
# 在 QEMU 里启动 ISO，检查能不能进到登录界面，并截图。
# 用法：tests/boot-test.sh path/to.iso out_dir
set -uo pipefail
ISO="$1"; OUT="${2:-test-out}"; mkdir -p "$OUT"
ACCEL="-machine accel=kvm -cpu host"; [ -w /dev/kvm ] || ACCEL="-machine accel=tcg -cpu max"
WORK=$(mktemp -d)
xorriso -osirrox on -indev "$ISO" -extract /live/vmlinuz "$WORK/vmlinuz" -extract /live/initrd.img "$WORK/initrd.img" >/dev/null 2>&1
PASS=0

shot() { # $1=monitor socket $2=name
  echo "screendump $WORK/$2.ppm" | socat - UNIX-CONNECT:"$1" >/dev/null 2>&1 || return
  sleep 2; convert "$WORK/$2.ppm" "$OUT/$2.png" 2>/dev/null || true
}

echo "== 测试 1：直接启动内核，串口日志检查服务 =="
qemu-system-x86_64 $ACCEL -m 4096 -smp 2 -vga virtio -display none \
  -cdrom "$ISO" -kernel "$WORK/vmlinuz" -initrd "$WORK/initrd.img" \
  -append "boot=live components console=ttyS0,115200 systemd.show_status=1 locales=zh_CN.UTF-8 username=yunan hostname=serenecloud" \
  -serial file:"$OUT/serial.log" -monitor unix:"$WORK/mon1",server,nowait &
QPID=$!
for i in $(seq 1 120); do
  sleep 5
  if grep -qaE "Started sddm.service|Started .*Simple Desktop Display Manager" "$OUT/serial.log"; then PASS=1; break; fi
  kill -0 $QPID 2>/dev/null || break
done
sleep 45; shot "$WORK/mon1" "1-login-screen"
kill $QPID 2>/dev/null; wait $QPID 2>/dev/null
grep -aE "FAILED|Failed to start" "$OUT/serial.log" > "$OUT/failed-units.txt" || true

echo "== 测试 2：UEFI 启动整个 ISO（看开机菜单和开机动画）=="
cp /usr/share/OVMF/OVMF_VARS_4M.fd "$WORK/vars.fd" 2>/dev/null || cp /usr/share/OVMF/OVMF_VARS.fd "$WORK/vars.fd"
CODE=/usr/share/OVMF/OVMF_CODE_4M.fd; [ -f "$CODE" ] || CODE=/usr/share/OVMF/OVMF_CODE.fd
qemu-system-x86_64 $ACCEL -m 4096 -smp 2 -vga virtio -display none \
  -drive if=pflash,format=raw,readonly=on,file="$CODE" -drive if=pflash,format=raw,file="$WORK/vars.fd" \
  -cdrom "$ISO" -monitor unix:"$WORK/mon2",server,nowait &
QPID=$!
sleep 8;  shot "$WORK/mon2" "2-uefi-boot-menu"
sleep 14; shot "$WORK/mon2" "3-plymouth-a"
sleep 6;  shot "$WORK/mon2" "4-plymouth-b"
sleep 150; shot "$WORK/mon2" "5-desktop-or-login"
kill $QPID 2>/dev/null; wait $QPID 2>/dev/null

if [ "$PASS" = 1 ]; then echo "✅ 启动测试通过：登录界面服务已启动"; else echo "❌ 启动测试失败：没等到登录界面"; tail -60 "$OUT/serial.log"; exit 1; fi
