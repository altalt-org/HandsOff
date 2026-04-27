import os
import shutil
from tools.helper import bcolors, print_color


class Locale:
    copy_dir = "./locale"

    def __init__(self, locales="en-US,ko-KR"):
        self.locales = locales

    @property
    def init_rc_content(self):
        # Belt-and-suspenders: persist the locale chain into /data so future
        # boots (where /data overrides build.prop defaults) keep the list.
        # `persist.sys.locale` accepts a comma-separated language-tag list —
        # `LocaleList.forLanguageTags()` parses it directly. We write the
        # full list here, not just the first element. There is no
        # `persist.sys.locales` (plural) property in Android; previous
        # versions of this file wrote it but nothing reads it.
        return f"""
on property:sys.boot_completed=1
    exec -- /system/bin/settings put system system_locales {self.locales}
    exec -- /system/bin/setprop persist.sys.locale {self.locales}
"""

    @property
    def build_prop_fragment(self):
        # Init reads build.prop on early boot to compose the system locale list
        # (LocalePicker → Settings UI's Languages screen). Writing both keys
        # here means the full list lands in Configuration before SystemServer
        # initializes the LocaleStore — Korean appears in the language list
        # from boot 0 without a reboot.
        #
        # `ro.product.locale` (singular) is the key SystemServer actually
        # reads to seed the initial LocaleList; the redroid base ships it as
        # `en-US`, which is why Settings showed only English. We override it
        # with the full comma-separated list (LocaleList.forLanguageTags
        # parses that directly). `ro.product.locales` (plural) is also read
        # by some boot paths — keep both so the chain is consistent.
        #
        # The fragment is staged at /tmp/build_prop_extra (via COPY locale /).
        # The unified symlink-fixer Go binary in redroid.py reads this file
        # at build time and appends to /system/build.prop. We use that route
        # because the redroid base image has no runnable shell (no /bin/sh,
        # and /system/bin/sh needs the bionic dynamic linker which fails in
        # a buildkit container) — only static Go binaries work.
        return (
            f"ro.product.locale={self.locales}\n"
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
