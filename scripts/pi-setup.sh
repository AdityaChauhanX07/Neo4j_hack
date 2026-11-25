#!/usr/bin/env bash
# Prepare a fresh 64-bit Raspberry Pi OS for the Common Cause bench.
#
#   scripts/pi-setup.sh            set up, then reboot if asked
#   scripts/pi-setup.sh --check    after the reboot, check buses and packages
#
# Safe to run again: the boot settings live in one marked block that is
# rewritten in place, and each install step is skipped when already done.
#
# Options:
#   --i2c3 hw|gpio    How to create /dev/i2c-3 on GPIO 4 (SDA) and 5 (SCL).
#                     hw uses dtoverlay=i2c3,pins_4_5 and is the default on a
#                     Pi 4. gpio uses the bit-banged i2c-gpio overlay and is
#                     the default on other models.
#   --skip-apt        Don't install system packages.
#   --no-relate-cli   Don't install the relate CLI (needed for downlink).
#   --check           Only report the current state.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
BEGIN="# >>> common-cause bench (scripts/pi-setup.sh) >>>"
END="# <<< common-cause bench <<<"
PACKAGES=(i2c-tools python3-venv python3-pip git curl openssh-client)
I2C3_MODE=""
SKIP_APT=0
RELATE_CLI=1
CHECK_ONLY=0
REBOOT=0

# Tests point these at a scratch directory.
BOOT_DIR=${PI_SETUP_BOOT_DIR:-}
MODEL_FILE=${PI_SETUP_MODEL_FILE:-/proc/device-tree/model}
MODULES_FILE=${PI_SETUP_MODULES_FILE:-/etc/modules-load.d/common-cause.conf}

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
die() { printf 'pi-setup: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
	case "$1" in
	--i2c3) I2C3_MODE=${2:-}; shift 2 ;;
	--i2c3=*) I2C3_MODE=${1#*=}; shift ;;
	--skip-apt) SKIP_APT=1; shift ;;
	--no-relate-cli) RELATE_CLI=0; shift ;;
	--check) CHECK_ONLY=1; shift ;;
	-h | --help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
	*) die "unknown option: $1 (see --help)" ;;
	esac
done
case "$I2C3_MODE" in "" | hw | gpio) ;; *) die "--i2c3 takes hw or gpio" ;; esac

[ "$(id -u)" -ne 0 ] || die "run as your normal user, not root; the script calls sudo where it needs to"
[ "$(uname -m)" = aarch64 ] ||
	die "found $(uname -m); use 64-bit Raspberry Pi OS (relate-db publishes aarch64 wheels, not 32-bit ARM)"

MODEL=$(tr -d '\0' <"$MODEL_FILE" 2>/dev/null || true)
case "$MODEL" in
*"Raspberry Pi 4"*) PI4=1 ;;
*) PI4=0 ;;
esac
[ -n "$I2C3_MODE" ] || { [ "$PI4" = 1 ] && I2C3_MODE=hw || I2C3_MODE=gpio; }
if [ "$I2C3_MODE" = hw ]; then
	I2C3_LINE="dtoverlay=i2c3,pins_4_5"
else
	I2C3_LINE="dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=4,i2c_gpio_scl=5"
fi

if [ -z "$BOOT_DIR" ]; then
	if [ -f /boot/firmware/config.txt ]; then BOOT_DIR=/boot/firmware; else BOOT_DIR=/boot; fi
fi
CONFIG="$BOOT_DIR/config.txt"
CMDLINE="$BOOT_DIR/cmdline.txt"

# Write $2 to root-owned file $1 only when it differs. Returns 0 on change.
replace_file() {
	local target=$1 content=$2
	if [ -f "$target" ] && [ "$(cat "$target")" = "$content" ]; then return 1; fi
	if [ -f "$target" ] && [ ! -f "$target.common-cause.bak" ]; then
		sudo cp -p "$target" "$target.common-cause.bak"
		say "Backed up $target to $target.common-cause.bak"
	fi
	sudo mkdir -p "$(dirname "$target")"
	printf '%s\n' "$content" | sudo tee "$target" >/dev/null
	return 0
}

configure_boot() {
	step "Boot settings ($CONFIG)"
	[ -f "$CONFIG" ] || die "no $CONFIG; is this Raspberry Pi OS?"
	local kept block
	kept=$(awk -v b="$BEGIN" -v e="$END" '$0 == b {skip = 1; next} $0 == e {skip = 0; next} !skip' "$CONFIG")
	block=$(printf '%s\n' "$BEGIN" "[all]" "dtparam=i2c_arm=on" "$I2C3_LINE" "enable_uart=1" "$END")
	if replace_file "$CONFIG" "$(printf '%s\n%s' "$kept" "$block")"; then
		REBOOT=1
		say "Updated: I2C-1, I2C-3 ($I2C3_MODE), UART enabled"
	else
		say "Already set: I2C-1, I2C-3 ($I2C3_MODE), UART enabled"
	fi

	step "Serial console ($CMDLINE)"
	[ -f "$CMDLINE" ] || die "no $CMDLINE"
	local line
	line=$(head -n 1 "$CMDLINE" | tr ' ' '\n' | { grep -Ev '^console=(serial0|ttyAMA0|ttyS0),' || true; } | tr '\n' ' ' | sed 's/ *$//')
	if replace_file "$CMDLINE" "$line"; then
		REBOOT=1
		say "Removed the serial login console so UART0 carries the radio heartbeat"
	else
		say "No serial login console on the UART"
	fi

	step "i2c-dev module ($MODULES_FILE)"
	if replace_file "$MODULES_FILE" "i2c-dev"; then say "Loads i2c-dev at boot"; else say "Already loads i2c-dev"; fi
	sudo modprobe i2c-dev 2>/dev/null || true

	if [ "$PI4" = 0 ]; then
		say ""
		say "WARNING: this is not a Pi 4 (model: ${MODEL:-unknown})."
		say "  The UART that /dev/serial0 names may not be on GPIO 14 and 15 here."
		say "  Check hardware/bench-wiring.md and set the UART0 port in hardware/cubesat-pi4.yaml."
	fi
}

install_packages() {
	step "System packages"
	local missing=()
	for package in "${PACKAGES[@]}"; do
		dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
	done
	if [ ${#missing[@]} -eq 0 ]; then
		say "Already installed: ${PACKAGES[*]}"
	else
		sudo apt-get update
		sudo apt-get install -y "${missing[@]}"
	fi
}

join_groups() {
	step "Device groups"
	local group
	for group in i2c dialout; do
		getent group "$group" >/dev/null || { say "No $group group yet; skipping"; continue; }
		if id -nG "$USER" | tr ' ' '\n' | grep -qx "$group"; then
			say "$USER is in $group"
		else
			sudo usermod -aG "$group" "$USER"
			REBOOT=1
			say "Added $USER to $group (takes effect after the reboot)"
		fi
	done
}

install_python() {
	step "Python environment ($REPO/.venv)"
	[ -x "$REPO/.venv/bin/python" ] || python3 -m venv "$REPO/.venv"
	"$REPO/.venv/bin/python" -m pip install --quiet --upgrade pip
	local log
	if ! log=$("$REPO/.venv/bin/python" -m pip install --quiet -e "${REPO}[board]" 2>&1); then
		printf '%s\n' "$log" >&2
		die "pip could not install commoncause[board]"
	fi
	say "Installed commoncause with the board extras"
}

RELATE="$HOME/.local/bin/relate"
# Every relate CLI release for Linux arm64 needs glibc 2.39 or newer. Raspberry
# Pi OS based on Debian 13 (trixie) has it; the Debian 12 (bookworm) release
# has 2.36, where only the Python package works.
GLIBC=$(ldd --version 2>/dev/null | head -n 1 | awk '{print $NF}')
glibc_ok() { [ "$(printf '%s\n' 2.39 "${GLIBC:-0}" | sort -V | head -n 1)" = 2.39 ]; }
relate_version() { "$RELATE" --version 2>/dev/null | head -n 1; }

install_relate_cli() {
	step "relate CLI"
	if ! glibc_ok; then
		say "SKIPPED: this OS has glibc ${GLIBC:-unknown}; the relate CLI needs 2.39 (Raspberry Pi OS trixie)."
		say "  Capture and diagnosis still work. To downlink, stop commoncause run, copy board/store"
		say "  to a laptop and run commoncause downlink there, or reflash with the trixie image."
		return
	fi
	if [ -x "$RELATE" ] && relate_version >/dev/null && [ -n "$(relate_version)" ]; then
		say "Already installed: $(relate_version)"
		return
	fi
	local installer
	installer=$(mktemp)
	# The installer verifies the release signature and checksum before it
	# writes $HOME/.local/bin/relate.
	curl -sSfL https://relatedb.ai/install.sh -o "$installer"
	sh "$installer"
	rm -f "$installer"
}

check() {
	step "Check"
	local failures=0 device
	for device in /dev/i2c-1 /dev/i2c-3 /dev/serial0; do
		if [ -e "$device" ]; then
			say "ok    $device $( [ -L "$device" ] && printf -- '-> %s' "$(readlink -f "$device")")"
		else
			say "MISSING $device"
			failures=$((failures + 1))
		fi
	done
	if "$REPO/.venv/bin/python" -c 'import relate, serial, smbus2; print("ok    relate-db", relate.__version__, "with smbus2 and pyserial")' 2>/dev/null; then
		:
	else
		say "MISSING relate-db, smbus2 or pyserial in $REPO/.venv"
		failures=$((failures + 1))
	fi
	if [ -x "$REPO/.venv/bin/commoncause" ]; then say "ok    commoncause command"; else
		say "MISSING commoncause command"; failures=$((failures + 1)); fi
	if [ "$RELATE_CLI" = 1 ]; then
		if [ -n "$(relate_version)" ]; then
			say "ok    $(relate_version) at $RELATE"
		elif ! glibc_ok; then
			say "WARN  no relate CLI: glibc ${GLIBC:-unknown} is older than 2.39, so downlink runs on a laptop"
		else
			say "MISSING relate CLI at $RELATE"; failures=$((failures + 1))
		fi
	fi
	command -v i2cdetect >/dev/null && say "ok    i2cdetect" || { say "MISSING i2cdetect"; failures=$((failures + 1)); }
	return "$failures"
}

if [ "$CHECK_ONLY" = 1 ]; then
	say "Common Cause Pi check: ${MODEL:-unknown model}"
	if check; then say ""; say "Ready for hardware/bring-up-checklist.md"; exit 0; fi
	exit 1
fi

say "Common Cause Pi setup: ${MODEL:-unknown model}, I2C-3 via $I2C3_MODE"
configure_boot
[ "$SKIP_APT" = 1 ] || install_packages
join_groups
install_python
[ "$RELATE_CLI" = 0 ] || install_relate_cli

if [ "$REBOOT" = 1 ]; then
	say ""
	say "Done. Reboot to apply the boot and group changes, then run:"
	say "  sudo reboot"
	say "  scripts/pi-setup.sh --check"
	exit 0
fi
check || exit 1
say ""
say "Ready for hardware/bring-up-checklist.md"
