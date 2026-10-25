# Qidi Q2: change the boot logo and flash the kernel

This guide covers two ways to change the logo the Q2 shows when it powers on:

- **Option A: logo swap only.** Keeps the existing kernel and swaps the two BMP images inside `boot.img`. This is the quick route and what was tested on the printer. No compiling needed.
- **Option B: full kernel rebuild.** Builds a new kernel and boot image from source with your own logo, using the build files from n3oney's repo.

Credits: the build files in `n3oney-qidi-q2-klipper/nix/q2-kernel/` come from
[n3oney/qidi-q2-klipper](https://github.com/n3oney/qidi-q2-klipper/tree/main/nix/q2-kernel)
(`nix/q2-kernel`). Kernel sources are GPL-2.0.

> **Warning.** Writing to the `boot` partition is the one step that can stop the printer from booting. Always back up the partitions first (step 1), and keep the backups until you've confirmed the printer boots.

## Download the files

All files for this guide are in the GitHub repository [theboleslaw/q2-kernel](https://github.com/theboleslaw/q2-kernel). You need `git` to download them.

### 1. Install git

On Debian 11 (bullseye), which the printer runs, install git with:

```bash
sudo apt update && sudo apt install -y git
```

Check that it installed:

```bash
git --version
```

### 2. Download the repository

```bash
git clone --recurse-submodules https://github.com/theboleslaw/q2-kernel.git
cd q2-kernel
```

The `--recurse-submodules` option also downloads n3oney's repository into `n3oney-qidi-q2-klipper/`. If you cloned without it, run `git submodule update --init` inside the folder.

This creates a `q2-kernel` folder with:

- `README.md`: this guide
- `logo/`: the ready-made logo, `klipper-black-480x272.bmp`
- `scripts/`: `replace-boot-logo.py`, used for Option A
- `n3oney-qidi-q2-klipper/`: n3oney's repository as a git submodule. The build files are in `nix/q2-kernel/`, used for Option B.

To update to the latest version later, run `git pull` inside the `q2-kernel` folder.

### 3. Copy the files to the printer (only if you run the commands on the printer)

Some commands in this guide, such as the backup and the logo replacement, run on the printer. Copy the folder to the printer from your computer with `scp`. Replace `mks` and `192.168.2.210` with your printer's user and address:

```bash
scp -r q2-kernel mks@192.168.2.210:~/
```

Then on the printer, run the commands from inside `~/q2-kernel`.

### 4. Download the kernel source (Option B only)

Option B also needs the kernel source. This is large, so clone it only when you need to build. The Rockchip kernel repository is [rockchip-linux/kernel](https://github.com/rockchip-linux/kernel). Use the branch that matches the printer's kernel (6.12). Check the n3oney flake for the exact branch name before cloning:

```bash
git clone --depth 1 --branch <branch> https://github.com/rockchip-linux/kernel.git
```

## What is where

The eMMC on the Q2 (`mmcblk1` on the printer) has these partitions:

| Partition | Label | Size | Contents |
|---|---|---|---|
| mmcblk1p1 | `uboot` | 2 MB | U-Boot |
| mmcblk1p2 | `trust` | 2 MB | ARM trusted firmware |
| mmcblk1p3 | `misc` | 1 MB | misc |
| mmcblk1p4 | `recovery` | 20 MB | recovery image |
| mmcblk1p5 | `boot` | 9 MB | `boot.img`: kernel + `resource.img` (logos) |
| mmcblk1p6 | `rootfs` | rest | Linux root filesystem |

Boot order: U-Boot shows `logo.bmp` (the first logo), then the kernel shows `logo_kernel.bmp` (the second logo), then the system starts. Both logos are 480×272, 24-bit, uncompressed BMPs stored in the Rockchip `resource.img` inside `boot.img`. Writing the logo to the `boot` partition is the only flash needed for a logo change. The rest of the system is unchanged.

The printer's partitions are addressed by label (`/dev/disk/by-partlabel/boot`), so the same commands work even if the device numbering changes.

## Step 1: back up the boot partitions (do this first)

Run on the printer (or on any machine with the printer's storage available), as root:

```bash
mkdir -p ~/q2-boot-backup
sudo dd if=/dev/disk/by-partlabel/uboot    of=~/q2-boot-backup/uboot.img    bs=1M status=none
sudo dd if=/dev/disk/by-partlabel/boot     of=~/q2-boot-backup/boot.img     bs=1M status=none
sudo dd if=/dev/disk/by-partlabel/recovery of=~/q2-boot-backup/recovery.img bs=1M status=none
sha256sum ~/q2-boot-backup/*.img
```

Keep these files off the printer too, if you can.

## Option A: swap the logo in the existing boot.img

### A1. Make the logo BMP

The source PNG is white on a transparent background. Converting it directly to BMP turns the transparent pixels into a gray square, so composite it onto black first:

```bash
ffmpeg -y -f lavfi -i color=black:s=480x272 -i klipper-light.png \
  -filter_complex "[1:v]scale=200:200,format=rgba[logo];[0:v][logo]overlay=(W-w)/2:(H-h)/2:format=auto,format=bgr24" \
  -frames:v 1 logo.bmp
file logo.bmp   # must say: 480 x 272 x 24
```

The result is a black background with the logo centered in white. The ready-made file is `logo/klipper-black-480x272.bmp`. Change the `scale=200:200` value to make the logo larger or smaller.

### A2. Replace the logos

The script swaps the two logos for your BMP. The new BMP must be exactly the same size as the original (391734 bytes), and the script checks this:

```bash
cp ~/q2-boot-backup/boot.img boot-orig.img
python3 scripts/replace-boot-logo.py boot-orig.img logo/klipper-black-480x272.bmp boot-new.img
```

### A3. Flash and verify

```bash
sudo dd if=boot-new.img of=/dev/disk/by-partlabel/boot bs=1M conv=fsync status=none
sudo dd if=/dev/disk/by-partlabel/boot of=/tmp/boot-check.img bs=1M count=9 status=none
cmp /tmp/boot-check.img boot-new.img && echo "flash verified"
sudo reboot
```

### Rollback

If the printer doesn't boot or shows the wrong logo:

```bash
sudo dd if=~/q2-boot-backup/boot.img of=/dev/disk/by-partlabel/boot bs=1M conv=fsync status=none
sudo reboot
```

## Option B: build a new kernel and boot image

This rebuilds `Image.lz4`, modules, the device tree, and `boot.img` with your logo included. It's needed for kernel changes. For a logo change alone, Option A is enough.

### B1. Get the sources

- **Build machine:** Linux with Nix (flakes enabled) and about 20 GB of free disk space. Cross-compilation for aarch64 is handled by Nix.
- **Kernel source:** the Rockchip kernel (6.12 branch) from [rockchip-linux/kernel](https://github.com/rockchip-linux/kernel).
- **U-Boot source:** the Rockchip U-Boot tree, used for the `resource_tool` build input.
- **Wi-Fi driver source:** the RTL8189FS driver used by the Q2.

The n3oney flake wires these together. Check that repo's `flake.nix` for the exact inputs and versions before building.

### B2. Put your logo in the source

Replace `logo.bmp` in the build directory with your 480×272 BMP:

```bash
cp logo/klipper-black-480x272.bmp n3oney-qidi-q2-klipper/nix/q2-kernel/logo.bmp
```

The `default.nix` installs this file as both `logo.bmp` and `logo_kernel.bmp`.

### B3. Build

```bash
nix build .#q2-kernel   # attribute name depends on the n3oney flake; check flake.nix
```

Output:
- `result/boot/boot.img`: the boot image to flash. It already includes the new logos.
- `result/boot/Image.lz4`, `result/boot/*.dtb`, and `result/rootfs/` (modules): only needed if you flash the kernel and modules separately.

`verify-boot.py` runs during the build and checks that `boot.img` fits in the 9 MB partition. If the check fails, the image is too large. Fix the cause before flashing.

### B4. Flash

Use the same steps as A3 with the new file:

```bash
sudo dd if=result/boot/boot.img of=/dev/disk/by-partlabel/boot bs=1M conv=fsync status=none
sudo dd if=/dev/disk/by-partlabel/boot of=/tmp/boot-check.img bs=1M count=9 status=none
cmp /tmp/boot-check.img result/boot/boot.img && echo "flash verified"
sudo reboot
```

If you also changed the kernel modules, copy the new `rootfs/lib/modules/<version>` directory into `/lib/modules/` on the printer's root filesystem and run `depmod`. This step modifies the running system, so do it carefully.

## CPU governor (no reflash needed)

The CPU governor decides how the clock speed changes with load. It's set at runtime through sysfs, so you don't need to rebuild or flash anything. It runs on the printer, so `sudo` is needed.

Governors available on the Q2 (listed in `scaling_available_governors`): `interactive`, `ondemand`, `userspace`, `performance`.

- **`ondemand`:** the stock setting. Speeds up under load and slows down at idle.
- **`performance`:** always at the maximum speed (1104 MHz on this build). Lowest latency, highest heat and power use.
- **`interactive`:** ramps up quickly on sudden load and holds the higher speed briefly. Aimed at responsive UIs such as the touchscreen.

### Check the current governor

```bash
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors
```

### Change it until the next reboot

```bash
echo interactive | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor
```

Replace `interactive` with `ondemand` or `performance` to try another setting.

### Make it apply at every boot

Create a small systemd service. Run this on the printer:

```bash
sudo tee /etc/systemd/system/cpu-governor.service >/dev/null <<'UNIT'
[Unit]
Description=Set CPU frequency governor to interactive
After=sysinit.target
Before=klipper.service moonraker.service q2-mode.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'echo interactive | tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor >/dev/null'

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now cpu-governor.service
```

To use a different governor, change `interactive` in both the description and the `echo` line.

### Go back to the default

```bash
sudo systemctl disable --now cpu-governor.service
sudo rm /etc/systemd/system/cpu-governor.service
sudo systemctl daemon-reload
```

The governor returns to `ondemand` at the next reboot. To switch right away, run `echo ondemand | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor`.

### Notes

- Changing the governor doesn't change the speed or voltage limits. Those come from the device-tree table described in the overclock/undervolt notes.
- `performance` and `interactive` run the CPU at higher speeds more often, which means more heat. Watch the printer's temperature under load.
- Check that the printer prints normally after changing the governor. A crash during a print can ruin it.

## Swap

The Q2 has about 485 MB of RAM. Swap gives the system extra room when memory runs short, such as during a large Moonraker or Klipper task or while the UI is busy. Swap on eMMC is slower than RAM and adds wear to the flash, so keep it modest.

The kernel config already enables swap and zram (`CONFIG_SWAP=y`, `CONFIG_ZRAM=y`, `CONFIG_ZRAM_DEF_COMP_LZ4=y`), so no reflash is needed.

### Current state on the printer

The printer has two swap devices, used in priority order:

- **zram (256 MB, priority 100):** compressed swap in RAM, set up by the `zram-swap.service` below. It's used first.
- **`/swapfile` (512 MB, priority 10):** the swap file, listed in `/etc/fstab`. It's used only after zram is full.

Swappiness is 10, which means the system uses swap only when it really needs to.

### Check swap

```bash
free -m
cat /proc/swaps
cat /proc/sys/vm/swappiness
```

`swapon` and `mkswap` are in `/sbin` or `/usr/sbin` on this system, so use the full path if you get "command not found", for example `/sbin/swapon --show`.

### Add a swap file (if none exists)

```bash
sudo fallocate -l 512M /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon -p 10 /swapfile
echo '/swapfile none swap sw,pri=10 0 0' | sudo tee -a /etc/fstab
```

Swap files only work on a filesystem that supports them. The printer's root filesystem is ext4, which works.

### Resize the swap file

To change the size of an existing swap file, for example from 1 GB to 512 MB, turn it off, recreate it, and turn it back on. The printer's `/etc/fstab` entry doesn't need to change, since it refers to the file path, not the size.

```bash
sudo swapoff /swapfile
sudo rm -f /swapfile
sudo fallocate -l 512M /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon -p 10 /swapfile
cat /proc/swaps
```

Check that the swap is in use only briefly. `swapoff` moves any swapped data back into RAM, so run it when `free -m` shows enough free memory, and not during a print.

### Add compressed RAM swap (zram)

zram creates swap in RAM, compressed with LZ4. It's faster than the swap file and doesn't wear the eMMC. Use a size well below your free RAM, for example 256 MB:

```bash
echo lz4 | sudo tee /sys/block/zram0/comp_algorithm
echo 256M | sudo tee /sys/block/zram0/disksize
sudo mkswap /dev/zram0
sudo swapon -p 100 /dev/zram0
```

The `-p 100` priority makes zram the first swap used, before `/swapfile`.

To make it apply at every boot, create a systemd service:

```bash
sudo tee /etc/systemd/system/zram-swap.service >/dev/null <<'UNIT'
[Unit]
Description=zram compressed swap
After=sysinit.target
Before=klipper.service moonraker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'echo lz4 > /sys/block/zram0/comp_algorithm; echo 256M > /sys/block/zram0/disksize; mkswap /dev/zram0; swapon -p 100 /dev/zram0'
ExecStop=/bin/sh -c 'swapoff /dev/zram0; echo 1 > /sys/block/zram0/reset'

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now zram-swap.service
```

### Change swappiness

Swappiness controls how eagerly the kernel moves memory to swap, from 0 (avoid it) to 100 (use it readily). The current value is 10, which is sensible for a printer host.

```bash
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
```

### Turn swap off or undo changes

```bash
sudo swapoff /dev/zram0
sudo systemctl disable --now zram-swap.service
sudo rm /etc/systemd/system/zram-swap.service
sudo systemctl daemon-reload
```

To remove the swap file, run `sudo swapoff /swapfile`, then delete the line from `/etc/fstab` and `sudo rm /swapfile`.

### Notes

- Swap doesn't speed up the system. It only prevents out-of-memory crashes, which can kill Klipper or Moonraker in the middle of a print.
- Watch `free -m` during long prints. If swap use keeps growing, look for a memory-heavy process before adding more swap.
- Keep zram smaller than your free RAM. Compressed data takes memory too.

## Notes and limits

- **Animation and percentage are not included here.** The boot logo is a static image. A loading percentage has to be drawn by the HelixScreen splash, which runs after the logo. That is a separate change.
- **Test before relying on it.** After any change, confirm the printer boots, that Klipper and Moonraker start, and that the touchscreen works. Compare boot time with `systemd-analyze` on the printer.
- **Logo timing:** the logo appears for only a short time before the system starts.

## Files in this folder

- `README.md`: this guide.
- `logo/klipper-black-480x272.bmp`: the ready-made logo (black background, white logo).
- `scripts/replace-boot-logo.py`: swaps the two logos inside an existing `boot.img` (Option A).
- `n3oney-qidi-q2-klipper/`: git submodule of [n3oney/qidi-q2-klipper](https://github.com/n3oney/qidi-q2-klipper). The build files (`default.nix`, `q2.config`, `qemu.config`, `output.dts`, `verify-boot.py`, the Rockchip patch, and the original `logo.bmp`) are in `nix/q2-kernel/`.
