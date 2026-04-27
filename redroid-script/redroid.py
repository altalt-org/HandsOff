#!/usr/bin/env python3

import argparse
from stuff.gapps import Gapps
from stuff.litegapps import LiteGapps
from stuff.magisk import Magisk
from stuff.mindthegapps import MindTheGapps
from stuff.ndk import Ndk
from stuff.houdini import Houdini
from stuff.houdini_hack import Houdini_Hack
from stuff.widevine import Widevine
from stuff.lawnchair import Lawnchair
from stuff.droidrun_portal import DroidrunPortal
from stuff.gboard import Gboard
from stuff.skip_setup import SkipSetup
from stuff.locale import Locale
import tools.helper as helper
import subprocess


def main():
    dockerfile = ""
    tags = []
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-a', '--android-version',
                        dest='android',
                        help='Specify the Android version to build',
                        default='11.0.0',
                        choices=['14.0.0', '13.0.0', '12.0.0', '12.0.0_64only', '11.0.0', '10.0.0', '9.0.0', '8.1.0'])
    parser.add_argument('-g', '--install-gapps',
                        dest='gapps',
                        help='Install OpenGapps to ReDroid',
                        action='store_true')
    parser.add_argument('-lg', '--install-litegapps',
                        dest='litegapps',
                        help='Install LiteGapps to ReDroid',
                        action='store_true')
    parser.add_argument('-n', '--install-ndk-translation',
                        dest='ndk',
                        help='Install libndk translation files',
                        action='store_true')
    parser.add_argument('-i', '--install-houdini',
                        dest='houdini',
                        help='Install houdini files',
                        action='store_true')
    parser.add_argument('-mtg', '--install-mindthegapps',
                        dest='mindthegapps',
                        help='Install MindTheGapps to ReDroid',
                        action='store_true')
    parser.add_argument('-m', '--install-magisk', dest='magisk',
                        help='Install Magisk ( Bootless )',
                        action='store_true')
    parser.add_argument('-w', '--install-widevine', dest='widevine',
                        help='Integrate Widevine DRM (L3)',
                        action='store_true')
    parser.add_argument('-l', '--install-lawnchair', dest='lawnchair',
                        help='Install Lawnchair launcher as default',
                        action='store_true')
    parser.add_argument('-dp', '--install-droidrun-portal', dest='droidrun_portal',
                        help='Install DroidRun Portal for AI agent control',
                        action='store_true')
    parser.add_argument('-gb', '--install-gboard', dest='gboard',
                        help='Install Gboard as default multilingual IME (hardware-keyboard CJK supported)',
                        action='store_true')
    parser.add_argument('-ss', '--skip-setup', dest='skip_setup',
                        help='Skip Android setup wizard on first boot',
                        action='store_true')
    parser.add_argument('-loc', '--locale', dest='locale',
                        help='Set system locales (comma-separated, e.g. en-US,ko-KR)',
                        default=None)
    parser.add_argument('-p', '--prop', dest='props',
                        help='Set a system property (ro.foo=bar), can be repeated',
                        action='append', default=[])
    parser.add_argument('-c', '--container',
                        dest='container',
                        default='docker',
                        help='Specify container type',
                        choices=['docker', 'podman'])

    args = parser.parse_args()
    # containerd 2.x fix: /etc is an absolute symlink (/etc -> /system/etc) in the
    # Android base image. containerd 2.2+ (Go 1.24 openat2) rejects absolute symlinks
    # in container rootfs.
    # Strategy: compile a CGO_ENABLED=0 Go binary (truly static, no PT_INTERP) that
    # (a) replaces /etc with a relative symlink, and (b) optionally appends a staged
    # /tmp/build_prop_extra fragment to /system/build.prop. Static Go binaries run on
    # any Linux ARM64 kernel regardless of libc — unlike Alpine busybox (musl dynamic)
    # which fails, or Android's /system/bin/sh which needs the bionic linker.
    # We RUN this binary as the LAST Dockerfile step (after all COPYs), so any staged
    # build.prop fragment from e.g. the locale module is in place when it runs.
    # Ref: https://github.com/containerd/containerd/issues/12683
    go_src = (
        'package main\\n'
        'import ("io"; "os")\\n'
        'func main() { '
        'os.Remove("/etc"); '
        'os.Symlink("system/etc", "/etc"); '
        'src, err := os.Open("/tmp/build_prop_extra"); '
        'if err != nil { return }; '
        'defer src.Close(); '
        'dst, err := os.OpenFile("/system/build.prop", os.O_APPEND|os.O_WRONLY, 0644); '
        'if err != nil { return }; '
        'defer dst.Close(); '
        'io.Copy(dst, src) '
        '}'
    )
    dockerfile = dockerfile + \
        "FROM golang:1.23-alpine AS symlink-fixer\n"
    dockerfile = dockerfile + \
        f"RUN printf '{go_src}' > /fix.go && " \
        "CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o /symlink-fix /fix.go\n"
    dockerfile = dockerfile + \
        "FROM redroid/redroid:{}-latest\n".format(
            args.android)
    dockerfile = dockerfile + \
        "COPY --from=symlink-fixer /symlink-fix /tmp/symlink-fix\n"
    tags.append(args.android)
    if args.gapps:
        if args.android in ["11.0.0"]:
            Gapps().install()
            dockerfile = dockerfile + "COPY gapps /\n"
            tags.append("gapps")
        else:
            helper.print_color( "WARNING: OpenGapps only supports 11.0.0", helper.bcolors.YELLOW)
    if args.litegapps:
        LiteGapps(args.android).install()
        dockerfile = dockerfile + "COPY litegapps /\n"
        tags.append("litegapps")
    if args.mindthegapps:
        MindTheGapps(args.android).install()
        dockerfile = dockerfile + "COPY mindthegapps /\n"
        tags.append("mindthegapps")
    if args.ndk:
        if args.android in ["11.0.0", "12.0.0", "12.0.0_64only"]:
            arch = helper.host()[0]
            if arch == "x86" or arch == "x86_64":
                Ndk().install()
                dockerfile = dockerfile+"COPY ndk /\n"
                tags.append("ndk")
        else:
            helper.print_color(
                "WARNING: Libndk seems to work only on redroid:11.0.0 or redroid:12.0.0", helper.bcolors.YELLOW)
    if args.houdini:
        if args.android in ["8.1.0", "9.0.0", "11.0.0", "12.0.0", "13.0.0", "14.0.0"]:
            arch = helper.host()[0]
            if arch == "x86" or arch == "x86_64":
                Houdini(args.android).install()
                if not args.android == "8.1.0":
                    Houdini_Hack(args.android).install()
                dockerfile = dockerfile+"COPY houdini /\n"
                tags.append("houdini") 
        else:
            helper.print_color(
                "WARNING: Houdini seems to work only above redroid:11.0.0", helper.bcolors.YELLOW)
    if args.magisk:
        Magisk().install()
        dockerfile = dockerfile+"COPY magisk /\n"
        tags.append("magisk")
    if args.widevine:
        Widevine(args.android).install()
        dockerfile = dockerfile+"COPY widevine /\n"
        tags.append("widevine")
    if args.lawnchair:
        Lawnchair().install()
        dockerfile = dockerfile+"COPY lawnchair /\n"
        tags.append("lawnchair")
    if args.droidrun_portal:
        DroidrunPortal().install()
        dockerfile = dockerfile+"COPY droidrun_portal /\n"
        tags.append("droidrun_portal")
    if args.gboard:
        Gboard().install()
        dockerfile = dockerfile+"COPY gboard /\n"
        tags.append("gboard")
    if args.skip_setup:
        SkipSetup().install()
        dockerfile = dockerfile+"COPY skip_setup /\n"
    if args.locale:
        loc = Locale(args.locale)
        loc.install()
        dockerfile = dockerfile+"COPY locale /\n"
    # Run symlink-fix + build.prop append AFTER all COPYs so any staged
    # /tmp/build_prop_extra fragment (e.g. from the locale module) is in place.
    dockerfile = dockerfile + 'RUN ["/tmp/symlink-fix"]\n'
    if args.props:
        dockerfile = dockerfile + 'CMD [{}]\n'.format(
            ", ".join('"{}"'.format(p) for p in args.props)
        )
    print("\nDockerfile\n"+dockerfile)
    with open("./Dockerfile", "w") as f:
        f.write(dockerfile)
    new_image_name = "redroid/redroid:"+"_".join(tags)
    subprocess.run([args.container, "build", "-t", new_image_name, "."])
    helper.print_color("Successfully built {}".format(
        new_image_name), helper.bcolors.GREEN)


if __name__ == "__main__":
    main()
