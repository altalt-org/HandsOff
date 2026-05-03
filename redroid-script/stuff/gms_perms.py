import os
import shutil
from tools.helper import bcolors, print_color


# Pre-grants the SMS-family runtime permissions to com.google.android.gms
# at first boot.
#
# Why this exists:  MindTheGapps' GMS APK declares RECEIVE_SMS, READ_SMS,
# and SEND_SMS as hard-restricted permissions.  On a real Play-certified
# Pixel image these are granted at install time via the OEM whitelist at
# /etc/permissions/privapp-permissions-google.xml; MindTheGapps does not
# ship that whitelist.  So at runtime an inspect of `dumpsys package
# com.google.android.gms` shows:
#
#     android.permission.RECEIVE_SMS: granted=false, flags=[
#         USER_SENSITIVE_WHEN_GRANTED|RESTRICTION_INSTALLER_EXEMPT|
#         RESTRICTION_UPGRADE_EXEMPT]
#
# The `INSTALLER_EXEMPT|UPGRADE_EXEMPT` flags mean the package is allowed
# to receive these grants — they just are not pre-granted.  When an app
# (e.g. KakaoTalk) starts the SMS Retriever User Consent flow, GMS opens
# the OS permission dialog asking the human to enable SMS — which is
# fine on a real phone but breaks the agent-driven UX we want here.
#
# `pm grant` from a normal shell context works because of the
# INSTALLER_EXEMPT flag (verified empirically — exits 0 and flips
# `granted=true` in the dumpsys output).  We run it once on first boot
# and drop a marker file so the script is a no-op afterwards.


_GRANT_SH = """#!/system/bin/sh
# Pre-grant SMS permissions to Google Play services so the SMS-Retriever
# User Consent flow does not pop a permission dialog at the human.
MARKER=/data/local/.gms_perms_granted
[ -f "$MARKER" ] && exit 0

PKG=com.google.android.gms
for perm in \\
    android.permission.RECEIVE_SMS \\
    android.permission.READ_SMS \\
    android.permission.SEND_SMS \\
    android.permission.READ_PHONE_STATE \\
    android.permission.READ_PHONE_NUMBERS; do
    pm grant "$PKG" "$perm" 2>/dev/null || true
done

mkdir -p /data/local
touch "$MARKER"
"""


# Init.rc trigger.  Has to fire AFTER PackageManagerService is up (i.e.
# after `sys.boot_completed=1`) — earlier triggers race PMS package
# scanning and `pm grant` returns "Unknown package".
_INIT_RC = """
on property:sys.boot_completed=1
    exec -- /system/bin/sh /system/etc/gms-perms/grant.sh
"""


class GmsPerms:
    copy_dir = "./gms_perms"

    def install(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        init_dir = os.path.join(self.copy_dir, "system", "etc", "init")
        os.makedirs(init_dir, exist_ok=True)
        init_rc_path = os.path.join(init_dir, "gms_perms.rc")
        with open(init_rc_path, "w") as f:
            f.write(_INIT_RC)
        os.chmod(init_rc_path, 0o644)

        script_dir = os.path.join(self.copy_dir, "system", "etc", "gms-perms")
        os.makedirs(script_dir, exist_ok=True)
        script_path = os.path.join(script_dir, "grant.sh")
        with open(script_path, "w") as f:
            f.write(_GRANT_SH)
        os.chmod(script_path, 0o755)

        print_color("GMS SMS-permission pre-grant installed", bcolors.GREEN)
