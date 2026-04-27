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
        # The primary mechanism — ro.product.locales in build.prop — is
        # injected via dockerfile_extras() below.
        return f"""
on property:sys.boot_completed=1
    exec -- /system/bin/settings put system system_locales {self.locales}
    exec -- /system/bin/setprop persist.sys.locale {self.locales.split(',')[0]}
    exec -- /system/bin/setprop persist.sys.locales {self.locales}
"""

    def dockerfile_extras(self):
        """Dockerfile snippet to append ro.product.locales to /system/build.prop.

        Init reads build.prop on early boot to compose the system locale list
        (LocalePicker → Settings UI's Languages screen). Writing this here
        means Korean appears in the language list from boot 0 — without a
        reboot. Without it, locale.rc's setprop fires too late: SystemServer
        has already cached its locale list before sys.boot_completed=1.
        """
        return (
            f"RUN echo 'ro.product.locales={self.locales}' >> /system/build.prop\n"
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
        print_color(f"Locale configured: {self.locales}", bcolors.GREEN)
