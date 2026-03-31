import os
import shutil
from stuff.general import General
from tools.helper import bcolors, get_download_dir, print_color


class DroidrunPortal(General):
    download_loc = get_download_dir()
    dl_link = "https://github.com/droidrun/droidrun-portal/releases/download/v0.6.1/droidrun-portal-v0.6.1.apk"
    dl_file_name = os.path.join(download_loc, "droidrun-portal.apk")
    act_md5 = "f0cfdd82e1747c7465cab83d7f8f7afa"
    extract_to = "/tmp/droidrun_portal_unpack"
    copy_dir = "./droidrun_portal"

    # Store APK in the image and install as a regular user app on first boot
    # using pm install -g (grants all runtime permissions), same pattern as Magisk.
    # Then enable the accessibility service and custom keyboard IME.
    init_rc_content = """
on property:sys.boot_completed=1
    exec -- /system/bin/sh -c "if [ ! -e /data/data/com.droidrun.portal ] ; then pm install -g /system/etc/droidrun/droidrun-portal.apk ; fi"
    exec -- /system/bin/settings put secure enabled_accessibility_services com.droidrun.portal/com.droidrun.portal.service.DroidrunAccessibilityService
    exec -- /system/bin/settings put secure accessibility_enabled 1
    exec -- /system/bin/ime enable com.droidrun.portal/.input.DroidrunKeyboardIME
    exec -- /system/bin/ime set com.droidrun.portal/.input.DroidrunKeyboardIME
"""

    def download(self):
        print_color("Downloading DroidRun Portal now .....", bcolors.GREEN)
        super().download()

    def extract(self):
        # APK doesn't need extraction, skip
        pass

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        # Store APK in /system/etc/droidrun/ for pm install on first boot
        apk_dir = os.path.join(self.copy_dir, "system", "etc", "droidrun")
        os.makedirs(apk_dir, exist_ok=True)
        shutil.copyfile(self.dl_file_name, os.path.join(apk_dir, "droidrun-portal.apk"))

        # Add init.rc to install and configure on boot
        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "droidrun_portal.rc")
        with open(init_rc_path, "w") as f:
            f.write(self.init_rc_content)
        os.chmod(init_rc_path, 0o644)
