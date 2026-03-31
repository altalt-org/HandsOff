import os
import shutil
from stuff.general import General
from tools.helper import bcolors, get_download_dir, print_color


class Lawnchair(General):
    download_loc = get_download_dir()
    dl_link = "https://github.com/LawnchairLauncher/lawnchair/releases/download/v12.1.0-alpha.4/Lawnchair.12.1.0.Alpha.4.apk"
    dl_file_name = os.path.join(download_loc, "lawnchair.apk")
    act_md5 = "751cfefc00df938af1a3e94da9b760e5"
    extract_to = "/tmp/lawnchair_unpack"
    copy_dir = "./lawnchair"

    # Android init.rc snippet to set Lawnchair as default launcher on boot
    init_rc_content = """
on property:sys.boot_completed=1
    exec -- /system/bin/cmd package set-home-activity "app.lawnchair/com.android.launcher3.Launcher"
"""

    def download(self):
        print_color("Downloading Lawnchair now .....", bcolors.GREEN)
        super().download()

    def extract(self):
        # APK doesn't need extraction, skip
        pass

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        # Place APK as system priv-app
        priv_app_dir = os.path.join(self.copy_dir, "system", "priv-app", "Lawnchair")
        os.makedirs(priv_app_dir, exist_ok=True)
        shutil.copyfile(self.dl_file_name, os.path.join(priv_app_dir, "Lawnchair.apk"))

        # Add init.rc to set as default launcher on every boot
        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "lawnchair.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)
