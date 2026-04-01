import os
import shutil
from stuff.general import General
from stuff.gen_lawnchair_prefs import generate_preferences
from tools.helper import bcolors, get_download_dir, print_color


class Lawnchair(General):
    download_loc = get_download_dir()
    dl_link = "https://github.com/LawnchairLauncher/lawnchair/releases/download/v12.1.0-alpha.4/Lawnchair.12.1.0.Alpha.4.apk"
    dl_file_name = os.path.join(download_loc, "lawnchair.apk")
    act_md5 = "751cfefc00df938af1a3e94da9b760e5"
    extract_to = "/tmp/lawnchair_unpack"
    copy_dir = "./lawnchair"

    # Install Lawnchair as a regular app on first boot (same pattern as DroidRun Portal),
    # set it as default launcher, then copy pre-configured preferences.
    init_rc_content = """
on property:sys.boot_completed=1
    exec -- /system/bin/sh -c "if [ ! -e /data/data/app.lawnchair ] ; then pm install -g /system/etc/lawnchair/Lawnchair.apk ; fi"
    exec -- /system/bin/cmd package set-home-activity "app.lawnchair/com.android.launcher3.Launcher"
    exec -- /system/bin/sh -c "mkdir -p /data/data/app.lawnchair/files/datastore && cp /system/etc/lawnchair/preferences.preferences_pb /data/data/app.lawnchair/files/datastore/ && chown -R $(stat -c '%u:%g' /data/data/app.lawnchair) /data/data/app.lawnchair/files"
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

        # Store APK and preferences in /system/etc/lawnchair/
        lawnchair_dir = os.path.join(self.copy_dir, "system", "etc", "lawnchair")
        os.makedirs(lawnchair_dir, exist_ok=True)
        shutil.copyfile(self.dl_file_name, os.path.join(lawnchair_dir, "Lawnchair.apk"))

        # Generate pre-configured preferences (no search bar, no smartspace)
        prefs_path = os.path.join(lawnchair_dir, "preferences.preferences_pb")
        prefs_data = generate_preferences()
        with open(prefs_path, "wb") as f:
            f.write(prefs_data)
        print_color("Generated Lawnchair preferences ({} bytes)".format(len(prefs_data)), bcolors.GREEN)

        # Add init.rc to install, set as default, and apply preferences on boot
        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "lawnchair.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)
