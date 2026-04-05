import os
import shutil
from tools.helper import bcolors, print_color


class Locale:
    copy_dir = "./locale"

    def __init__(self, locales="en-US,ko-KR"):
        self.locales = locales

    @property
    def init_rc_content(self):
        return f"""
on property:sys.boot_completed=1
    exec -- /system/bin/settings put system system_locales {self.locales}
    exec -- /system/bin/setprop persist.sys.locale {self.locales.split(',')[0]}
    exec -- /system/bin/setprop persist.sys.locales {self.locales}
"""

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
