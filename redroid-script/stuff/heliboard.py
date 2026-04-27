import os
import shutil
from stuff.general import General
from tools.helper import bcolors, get_download_dir, print_color


# HeliBoard's `enabled_subtypes` SharedPref format, derived from
# SettingsSubtype.toPref() and Constants.Separators in HeliBoard 3.9 source:
#   - Each entry:  <languageTag>§<extraValues sorted alphabetically by ",">
#   - Entries joined with ";" (Separators.SETS)
#   - § is U+00A7 (SECTION SIGN, Separators.SET)
# Values mirror HeliBoard's res/xml/method.xml so the pref reload finds the
# canonical resource subtypes — preserving Hangul combining rules, ASCII
# capability, layout selection, etc.
_SEED_ENABLED_SUBTYPES = (
    "en-US§AsciiCapable,EmojiCapable,SupportTouchPositionCorrection,"
    "TrySuppressingImeSwitcher"
    ";"
    "ko§CombiningRules=hangul,EmojiCapable,"
    "KeyboardLayoutSet=MAIN:korean,SupportTouchPositionCorrection"
)

_SEED_PREFS_XML = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n"
    "<map>\n"
    f'    <string name="enabled_subtypes">{_SEED_ENABLED_SUBTYPES}</string>\n'
    "</map>\n"
)


# Ran by init via `exec -- /system/bin/sh /system/etc/heliboard/seed.sh` on
# every boot. Idempotent: only copies the seed prefs when no prefs file
# exists, so user customizations on later boots are not clobbered.
_SEED_SH = """#!/system/bin/sh
PKG=helium314.keyboard
APK=/system/etc/heliboard/heliboard.apk
SEED=/system/etc/heliboard/seed_prefs.xml
PREFS_DIR=/data/user_de/0/$PKG/shared_prefs
PREFS=$PREFS_DIR/${PKG}_preferences.xml

# Install APK on first boot
if [ ! -e /data/data/$PKG ]; then
    pm install -g $APK
fi

# Wait for package data dir (pm install creates it)
i=0
while [ $i -lt 8 ] && [ ! -d /data/user_de/0/$PKG ]; do
    sleep 1
    i=$((i+1))
done

# Seed enabled_subtypes only on a truly fresh install. Once HeliBoard has
# written its own prefs file, we never overwrite — user choices stick.
if [ -d /data/user_de/0/$PKG ] && [ ! -e $PREFS ]; then
    mkdir -p $PREFS_DIR
    cp $SEED $PREFS
    OWN_UID=$(stat -c %u /data/user_de/0/$PKG 2>/dev/null)
    if [ -n "$OWN_UID" ]; then
        chown -R $OWN_UID:$OWN_UID $PREFS_DIR
    fi
    chmod 660 $PREFS
    chmod 771 $PREFS_DIR
    # Fix SELinux labels so HeliBoard can read the file under its own context
    restorecon -R $PREFS_DIR 2>/dev/null
fi
"""


class HeliBoard(General):
    """Bundles HeliBoard as the default multilingual IME.

    HeliBoard is a FOSS soft keyboard (fork of OpenBoard / AOSP LatinIME) that
    ships with ~70 languages including Korean Hangul composition. Set as
    default IME on first boot so human users typing through ws-scrcpy get
    proper multilingual input.

    English (US) + Korean (2-beolsik) are pre-seeded into HeliBoard's
    `enabled_subtypes` pref so the language switcher (long-press space)
    cycles between them out of the box. Locale fallback inside HeliBoard
    serves as a backup if the seed ever fails to land.

    The DroidrunKeyboardIME stays installed and enabled (for the server-side
    transactional swap during agent input_text), but is not the default.
    """

    download_loc = get_download_dir()
    dl_link = (
        "https://github.com/HeliBorg/HeliBoard/releases/download/v3.9/"
        "HeliBoard_3.9-release.apk"
    )
    dl_file_name = os.path.join(download_loc, "heliboard.apk")
    act_md5 = "1f9da7bd7392501888ed2026ed3f3b17"
    extract_to = "/tmp/heliboard_unpack"
    copy_dir = "./heliboard"

    PACKAGE = "helium314.keyboard"
    IME_ID = "helium314.keyboard/.latin.LatinIME"

    init_rc_content = f"""
on property:sys.boot_completed=1
    exec -- /system/bin/sh /system/etc/heliboard/seed.sh
    exec -- /system/bin/ime enable {IME_ID}
    exec -- /system/bin/ime set {IME_ID}
"""

    def download(self):
        print_color("Downloading HeliBoard now .....", bcolors.GREEN)
        super().download()

    def extract(self):
        # APK doesn't need extraction
        pass

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        # APK + seed assets under /system/etc/heliboard/
        asset_dir = os.path.join(self.copy_dir, "system", "etc", "heliboard")
        os.makedirs(asset_dir, exist_ok=True)
        shutil.copyfile(
            self.dl_file_name, os.path.join(asset_dir, "heliboard.apk")
        )

        seed_prefs_path = os.path.join(asset_dir, "seed_prefs.xml")
        with open(seed_prefs_path, "w", encoding="utf-8") as f:
            f.write(_SEED_PREFS_XML)
        os.chmod(seed_prefs_path, 0o644)

        seed_sh_path = os.path.join(asset_dir, "seed.sh")
        with open(seed_sh_path, "w", encoding="utf-8") as f:
            f.write(_SEED_SH)
        os.chmod(seed_sh_path, 0o755)

        # init.rc fragment
        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "heliboard.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)

        print_color(
            "HeliBoard configured as default IME (en-US + ko-KR seeded)",
            bcolors.GREEN,
        )
