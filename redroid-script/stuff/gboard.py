import os
import shutil
import subprocess
import zipfile

from tools.helper import bcolors, get_download_dir, print_color


# Ran by init via `exec -- /system/bin/sh /system/etc/gboard/seed.sh` on
# every boot. Idempotent.
#
# Why we do enable+set in user space (not init.rc): see analogous note for
# heliboard.py — IMMS reconcile during boot races init's `ime set` and
# reverts default_input_method back to the stock keyboard. Polling
# `ime list -s -a` for Gboard's presence gives an authoritative IMMS-ready
# signal; the verify/retry loop on `settings get` defeats any late
# reconcile pass.
_SEED_SH = """#!/system/bin/sh
PKG=com.google.android.inputmethod.latin
IME_ID=com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME
APK=/system/etc/gboard/gboard.apk

# 1) Install APK on first boot
if [ ! -e /data/data/$PKG ]; then
    pm install -g $APK
fi

# 2) Wait for IMMS to index Gboard (authoritative readiness signal)
i=0
while [ $i -lt 60 ]; do
    if ime list -s -a 2>/dev/null | grep -q "^$IME_ID\\$"; then
        break
    fi
    sleep 1
    i=$((i+1))
done

# 3) Enable Gboard (idempotent)
ime enable $IME_ID

# 4) Set as default, verify, retry — defeats late IMMS reconcile passes.
# ~30s budget total.
i=0
while [ $i -lt 15 ]; do
    cur=$(settings get secure default_input_method 2>/dev/null | tr -d '\\r\\n')
    if [ "$cur" = "$IME_ID" ]; then
        break
    fi
    ime set $IME_ID
    sleep 2
    i=$((i+1))
done
"""


class Gboard:
    """Bundles Gboard (Google Keyboard) as the default IME.

    Gboard supports hardware-keyboard composition for Hangul / Kana / Hanzi
    out of the box — HeliBoard does not (the relevant production flag is
    disabled upstream). This means typing Korean from the host through
    ws-scrcpy actually produces 한글 instead of Latin chars when the
    Korean subtype is selected.

    The APK is fetched from APKPure via `apkeep` at build time (apkeep
    must be on PATH when redroid.py runs). ~80MB.

    Korean subtype is *not* pre-seeded — Gboard's pref schema is closed
    and protobuf-encoded inside SharedPreferences strings, brittle across
    versions. With system locales `en-US,ko-KR` already set in the image,
    Gboard surfaces Korean as a suggested addition on first launch; user
    adds it once via Gboard's language picker.

    The DroidrunKeyboardIME stays installed and enabled so the server-side
    transactional swap during agent input_text still works.
    """

    download_loc = get_download_dir()
    PACKAGE = "com.google.android.inputmethod.latin"
    IME_ID = (
        "com.google.android.inputmethod.latin/"
        "com.android.inputmethod.latin.LatinIME"
    )

    # apkeep used to write `<package>.apk`; APKPure has since switched to
    # serving an XAPK (zip-of-base+splits), so apkeep 0.18 now writes
    # `<package>.xapk` instead.  We accept either suffix and unwrap the
    # XAPK to its `base.apk` payload.  `dl_file_name` is the path of the
    # plain APK we ultimately copy into the image.
    dl_file_name = os.path.join(download_loc, f"{PACKAGE}.apk")
    dl_xapk_name = os.path.join(download_loc, f"{PACKAGE}.xapk")
    copy_dir = "./gboard"

    init_rc_content = """
on property:sys.boot_completed=1
    exec -- /system/bin/sh /system/etc/gboard/seed.sh
"""

    def download(self):
        """Fetch latest Gboard APK (or XAPK bundle) via apkeep from APKPure.

        apkeep handles APKPure's URL-signing scheme; pinning a direct URL
        won't work because their links expire.  Cached locally between
        builds; re-downloaded only if missing.

        APKPure now ships split-APK bundles as XAPK (a zip of base.apk +
        config.*.apk + manifest.json), so apkeep writes
        `<package>.xapk`.  If we get an XAPK we unwrap it to `base.apk`
        renamed as `<package>.apk` so the rest of the pipeline keeps
        working with a plain APK.
        """
        if os.path.exists(self.dl_file_name):
            print_color(
                f"Gboard APK already present at {self.dl_file_name}, skipping download",
                bcolors.GREEN,
            )
            return
        print_color("Downloading Gboard via apkeep .....", bcolors.GREEN)
        subprocess.run(
            [
                "apkeep",
                "-a",
                self.PACKAGE,
                "-d",
                "apk-pure",
                self.download_loc,
            ],
            check=True,
        )

        # apkeep may have written either <pkg>.apk or <pkg>.xapk.
        if os.path.exists(self.dl_file_name):
            return
        if os.path.exists(self.dl_xapk_name):
            self._extract_base_apk_from_xapk()
            return

        raise FileNotFoundError(
            f"apkeep did not produce {self.dl_file_name} or "
            f"{self.dl_xapk_name}"
        )

    def _extract_base_apk_from_xapk(self):
        """Unwrap the base APK out of an XAPK bundle.

        XAPK is a zip with at least the main APK, plus zero or more
        `config.*.apk` density / ABI / locale splits, an `icon.png`, and
        a `manifest.json` describing them.  We only want the main APK —
        installing splits via `pm install` would require a multi-session
        install which the on-device first-boot seed.sh keeps simple by
        not supporting; density / ABI / locale splits are not strictly
        needed for Gboard to function.

        APKPure's XAPK convention: the base APK is named `<package>.apk`
        (e.g. `com.google.android.inputmethod.latin.apk`), splits are
        `config.<qualifier>.apk`.  We pick the first APK whose basename
        does NOT start with `config.` as the base.
        """
        print_color(
            f"Unwrapping XAPK at {self.dl_xapk_name} → base APK",
            bcolors.GREEN,
        )
        with zipfile.ZipFile(self.dl_xapk_name, "r") as zf:
            members = zf.namelist()
            base_member = next(
                (
                    n
                    for n in members
                    if n.lower().endswith(".apk")
                    and not os.path.basename(n).lower().startswith("config.")
                ),
                None,
            )
            if base_member is None:
                raise FileNotFoundError(
                    f"XAPK {self.dl_xapk_name} contains no base APK; "
                    f"members: {members}"
                )
            with zf.open(base_member) as src, open(self.dl_file_name, "wb") as dst:
                shutil.copyfileobj(src, dst)
        print_color(
            f"Wrote {self.dl_file_name} from XAPK (base member: {base_member})",
            bcolors.GREEN,
        )

    def extract(self):
        # APK doesn't need extraction
        pass

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        asset_dir = os.path.join(self.copy_dir, "system", "etc", "gboard")
        os.makedirs(asset_dir, exist_ok=True)
        shutil.copyfile(
            self.dl_file_name, os.path.join(asset_dir, "gboard.apk")
        )

        seed_sh_path = os.path.join(asset_dir, "seed.sh")
        with open(seed_sh_path, "w", encoding="utf-8") as f:
            f.write(_SEED_SH)
        os.chmod(seed_sh_path, 0o755)

        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "gboard.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)

        print_color("Gboard configured as default IME", bcolors.GREEN)

    def install(self):
        self.download()
        self.extract()
        self.copy()
