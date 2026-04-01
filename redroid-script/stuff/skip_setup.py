import os
import shutil
from tools.helper import bcolors, print_color


class SkipSetup:
    copy_dir = "./skip_setup"

    init_rc_content = """
on property:sys.boot_completed=1
    exec -- /system/bin/pm disable-user --user 0 com.google.android.setupwizard
    exec -- /system/bin/settings put global device_provisioned 1
    exec -- /system/bin/settings put secure user_setup_complete 1
"""

    def install(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "skip_setup.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)
        print_color("Skip setup wizard configured", bcolors.GREEN)
