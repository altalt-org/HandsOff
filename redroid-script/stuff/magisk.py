import gzip
import os
import shutil
import re
import sqlite3
from stuff.general import General
from tools.helper import bcolors, download_file, host, print_color, run, get_download_dir

class Magisk(General):
    download_loc = get_download_dir()
    dl_link = "https://github.com/ayasa520/Magisk/releases/download/v30.6/app-debug.apk"
    dl_file_name = os.path.join(download_loc, "magisk.apk")
    act_md5 = "77ef9f3538c0767ea45ee5c946f84bc6"
    extract_to = "/tmp/magisk_unpack"
    copy_dir = "./magisk"
    magisk_dir = os.path.join(copy_dir, "system", "etc", "init", "magisk")
    machine = host()
    oringinal_bootanim = """
service bootanim /system/bin/bootanimation
    class core animation
    user graphics
    group graphics audio
    disabled
    oneshot
    ioprio rt 0
    task_profiles MaxPerformance
    
"""
    # Post-boot script to set su_auto_response (stored in SharedPreferences,
    # not in magisk.db, so it can't be pre-baked). Runs once after Magisk app
    # is installed. Core settings (zygisk, denylist, root, shell policy) are
    # already active from the pre-created magisk.db — no reboot needed.
    configure_sh = """#!/system/bin/sh
MAGISK=/sbin/magisk

# su_auto_response: auto-grant new su requests from unknown UIDs (2 = grant).
# The native daemon may read this from the db on some Magisk forks.
$MAGISK --sqlite "REPLACE INTO settings (key,value) VALUES('su_auto_response',2);"

# Write SharedPreferences XML (the canonical location for this setting).
MAGISK_PKG="io.github.huskydg.magisk"
PREFS_DIR="/data/user_de/0/$MAGISK_PKG/shared_prefs"
if [ -d "/data/data/$MAGISK_PKG" ]; then
    mkdir -p "$PREFS_DIR"
    cat > "$PREFS_DIR/${MAGISK_PKG}_preferences.xml" <<'PREFS'
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="su_auto_response">2</string>
</map>
PREFS
    set -- $(ls -ldn "/data/data/$MAGISK_PKG")
    chown -R "$3:$4" "/data/user_de/0/$MAGISK_PKG"
fi

touch /data/adb/.magisk_configured
"""

    bootanim_component = """
on post-fs-data
    start logd
    mkdir /data/adb 700
    mkdir /data/adb/magisk 755
    exec -- /system/bin/sh -c "[ ! -f /data/adb/magisk.db ] && cp /system/etc/init/magisk/magisk.db /data/adb/magisk.db"
    exec -- /system/bin/sh -c "cp /system/etc/init/magisk/* /data/adb/magisk/ 2>/dev/null || true"
    exec u:r:su:s0 root root -- {MAGISKSYSTEMDIR}/magiskpolicy --live --magisk
    exec u:r:magisk:s0 root root -- {MAGISKSYSTEMDIR}/magiskpolicy --live --magisk
    exec u:r:update_engine:s0 root root -- {MAGISKSYSTEMDIR}/magiskpolicy --live --magisk
    exec u:r:su:s0 root root -- {MAGISKSYSTEMDIR}/{magisk_name} --auto-selinux --setup-sbin {MAGISKSYSTEMDIR} {MAGISKTMP}
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --post-fs-data
on nonencrypted
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --service
on property:vold.decrypt=trigger_restart_framework
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --service
on property:sys.boot_completed=1
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --boot-complete
    exec -- /system/bin/sh -c "if [ ! -e /data/data/io.github.huskydg.magisk ] ; then pm install /system/etc/init/magisk/magisk.apk ; fi"
    exec u:r:su:s0 root root -- /system/bin/sh -c "[ ! -f /data/adb/.magisk_configured ] && /system/etc/init/magisk/configure.sh"

on property:init.svc.zygote=restarting
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --zygote-restart

on property:init.svc.zygote=stopped
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --zygote-restart
    """.format(MAGISKSYSTEMDIR="/system/etc/init/magisk", MAGISKTMP="/sbin", magisk_name="magisk")

    def download(self):
        print_color("Downloading latest Magisk now .....", bcolors.GREEN)
        super().download()   

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)
        if not os.path.exists(self.magisk_dir):
            os.makedirs(self.magisk_dir, exist_ok=True)

        if not os.path.exists(os.path.join(self.copy_dir, "sbin")):
            os.makedirs(os.path.join(self.copy_dir, "sbin"), exist_ok=True)

        print_color("Copying magisk libs now ...", bcolors.GREEN)
        
        arch_map = {
            "x86": "x86",
            "x86_64": "x86_64",
            "arm": "armeabi-v7a",
            "arm64": "arm64-v8a"
        }
        lib_dir = os.path.join(self.extract_to, "lib", arch_map[self.machine[0]])
        for parent, dirnames, filenames in os.walk(lib_dir):
            for filename in filenames:
                o_path = os.path.join(lib_dir, filename)  
                filename = re.search('lib(.*)\.so', filename)
                n_path = os.path.join(self.magisk_dir, filename.group(1))
                shutil.copyfile(o_path, n_path)
                run(["chmod", "+x", n_path])
        shutil.copyfile(self.dl_file_name, os.path.join(self.magisk_dir,"magisk.apk") )

        # Pre-create magisk.db so the daemon reads our settings during its
        # first --post-fs-data (before it would create an empty default db).
        # This is what allows Zygisk + DenyList to be active on first boot
        # with zero reboots.  Schema matches Magisk's open_and_init_db().
        db_path = os.path.join(self.magisk_dir, "magisk.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("PRAGMA user_version = 12")
        c.execute("CREATE TABLE IF NOT EXISTS settings "
                  "(key TEXT, value INT, PRIMARY KEY(key))")
        c.execute("CREATE TABLE IF NOT EXISTS policies "
                  "(uid INT, policy INT, until INT, logging INT, "
                  "notification INT, PRIMARY KEY(uid))")
        c.execute("CREATE TABLE IF NOT EXISTS strings "
                  "(key TEXT, value TEXT, PRIMARY KEY(key))")
        c.execute("CREATE TABLE IF NOT EXISTS denylist "
                  "(package_name TEXT, process TEXT, "
                  "PRIMARY KEY(package_name, process))")
        # Zygisk on, DenyList enforced, root for apps+ADB
        for key, value in [("zygisk", 1), ("denylist", 1), ("root_access", 3)]:
            c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",
                      (key, value))
        # Pre-grant shell (uid 2000) permanent root
        c.execute("INSERT OR REPLACE INTO policies VALUES (?,?,?,?,?)",
                  (2000, 2, 0, 1, 1))
        conn.commit()
        conn.close()
        print_color("Pre-created magisk.db with Zygisk + DenyList + shell root",
                    bcolors.GREEN)

        # Write the post-boot configuration script (su_auto_response only)
        configure_path = os.path.join(self.magisk_dir, "configure.sh")
        with open(configure_path, "w") as f:
            f.write(self.configure_sh)
        os.chmod(configure_path, 0o755)

        # Updating Magisk from Magisk manager will modify bootanim.rc,
        # So it is necessary to backup the original bootanim.rc.
        bootanim_path = os.path.join(self.copy_dir, "system", "etc", "init", "bootanim.rc")
        gz_filename = os.path.join(bootanim_path)+".gz"
        with gzip.open(gz_filename,'wb') as f_gz:
            f_gz.write(self.oringinal_bootanim.encode('utf-8'))
        with open(bootanim_path, "w") as initfile:
            initfile.write(self.oringinal_bootanim+self.bootanim_component)

        os.chmod(bootanim_path, 0o644)
