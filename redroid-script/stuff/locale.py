import os
import shutil
from tools.helper import bcolors, print_color


# Pre-seed /data/system/users/0/settings_system.xml on first boot so that
# AMS.systemReady() reads system_locales BEFORE building the initial
# Configuration LocaleList. Without this, the `settings put system
# system_locales ...` call (which only works after the settings provider
# is up — i.e. on `sys.boot_completed=1`) lands AFTER systemReady, so
# first-boot Settings → Languages shows English only and only the *second*
# boot picks up the persisted setting.
#
# SettingsProvider auto-detects ABX (binary) vs plain XML on read; the
# legacy plain-XML format below parses fine and is converted to ABX on
# first write-back.
_SEED_SH_TEMPLATE = """#!/system/bin/sh
SETTINGS_XML=/data/system/users/0/settings_system.xml
if [ -f "$SETTINGS_XML" ]; then
    exit 0
fi
mkdir -p /data/system/users/0
chown system:system /data/system /data/system/users /data/system/users/0
chmod 0775 /data/system /data/system/users
chmod 0700 /data/system/users/0
cat > "$SETTINGS_XML" <<'XML'
<?xml version='1.0' encoding='utf-8'?>
<settings version="1">
    <setting id="1" name="system_locales" value="{locales}" package="android" />
</settings>
XML
chown system:system "$SETTINGS_XML"
chmod 0600 "$SETTINGS_XML"
restorecon -R /data/system/users 2>/dev/null
"""


class Locale:
    copy_dir = "./locale"

    def __init__(self, locales="en-US,ko-KR"):
        self.locales = locales

    @property
    def init_rc_content(self):
        # First-boot pre-seed runs as soon as /data is mounted, BEFORE
        # zygote / SystemServer start. That's the only window in which we
        # can plant a system_locales value that AMS.systemReady() will
        # read when it builds the initial Configuration LocaleList.
        #
        # The boot_completed block stays as the belt-and-suspenders
        # idempotent path — it covers pods whose /data was provisioned by
        # an older image (no preseed file) and keeps everything in sync
        # on every boot.
        return f"""
on post-fs-data
    exec -- /system/bin/sh /system/etc/locale/seed.sh

on property:sys.boot_completed=1
    exec -- /system/bin/settings put system system_locales {self.locales}
    exec -- /system/bin/setprop persist.sys.locale {self.locales}
"""

    @property
    def build_prop_fragment(self):
        # `ro.product.locale` (singular) MUST be a single valid BCP47
        # language tag. Earlier revisions wrote the full comma-separated
        # list here, which Locale.forLanguageTag() can't parse — it
        # silently dropped everything after the comma and (worse)
        # mis-tokenized "en-US" down to a bare "en", so the runtime
        # mGlobalConfig ended up as [en] instead of [en_US]. Use only the
        # primary tag here; the supported list goes in
        # `ro.product.locales` (plural), which is the field APK resource
        # matching reads.
        primary = self.locales.split(",")[0]
        return (
            f"ro.product.locale={primary}\n"
            f"ro.product.locales={self.locales}\n"
        )

    def install(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "locale.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)

        # First-boot seed script invoked from `on post-fs-data`.
        seed_dir = os.path.join(self.copy_dir, "system", "etc", "locale")
        os.makedirs(seed_dir, exist_ok=True)
        seed_path = os.path.join(seed_dir, "seed.sh")
        with open(seed_path, "w") as f:
            f.write(_SEED_SH_TEMPLATE.format(locales=self.locales))
        os.chmod(seed_path, 0o755)

        # Stage the build.prop fragment under tmp/ — `COPY locale /` lands it
        # at /tmp/build_prop_extra, where the symlink-fixer Go binary will
        # find it and append to /system/build.prop.
        tmp_dir = os.path.join(self.copy_dir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        fragment_path = os.path.join(tmp_dir, "build_prop_extra")
        with open(fragment_path, "w") as f:
            f.write(self.build_prop_fragment)
        os.chmod(fragment_path, 0o644)

        print_color(f"Locale configured: {self.locales}", bcolors.GREEN)
