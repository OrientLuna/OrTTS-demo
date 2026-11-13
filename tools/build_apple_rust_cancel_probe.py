#!/usr/bin/env python3
"""Build isolated iOS Rust SDK acceptance app. No downloads or OrTavern edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--framework", type=Path, required=True)
    p.add_argument("--target", choices=("device", "simulator"), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--profile", type=Path)
    p.add_argument("--identity", default="-")
    p.add_argument("--bundle-id", default="com.orient.ortts.rustcancelprobe")
    args = p.parse_args()
    out = args.out.resolve()
    if out.exists():
        p.error("Choose a fresh output directory")
    framework = args.framework.resolve(strict=True)
    binary = framework / "OrTTS"
    if args.target == "device" and (not args.profile or args.identity == "-"):
        p.error("Device probe requires a local development profile and signing identity")
    target = "aarch64-apple-ios" if args.target == "device" else "aarch64-apple-ios-sim"
    sdk = "iphoneos" if args.target == "device" else "iphonesimulator"
    triple = "arm64-apple-ios16.3" + ("-simulator" if args.target == "simulator" else "")
    out.mkdir(parents=True)
    env = {**os.environ, "ORTTS_FRAMEWORK_DIR": str(framework.parent), "CARGO_TARGET_DIR": str(out / "rust-target")}
    commands = [["cargo", "build", "--offline", "--release", "--target", target, "--manifest-path",
                 str(ROOT / "tests/apple_rust_cancel_probe/Cargo.toml")]]
    subprocess.run(commands[0], env=env, check=True)
    app = out / "RustCancelProbe.app"
    app.mkdir()
    (app / "Frameworks").mkdir()
    shutil.copytree(framework, app / "Frameworks/OrTTS.framework", symlinks=True)
    sdk_path = subprocess.check_output(["xcrun", "--sdk", sdk, "--show-sdk-path"], text=True).strip()
    command = ["xcrun", "--sdk", sdk, "clang", "-target", triple, "-isysroot", sdk_path,
               "-fobjc-arc", str(ROOT / "tests/apple_rust_cancel_probe/main.m"),
               str(out / "rust-target" / target / "release/libortts_rust_cancel_probe.a"),
               "-F", str(framework.parent), "-framework", "OrTTS", "-framework", "UIKit",
               "-framework", "Foundation", "-framework", "Security", "-liconv", "-lresolv",
               "-Wl,-rpath,@executable_path/Frameworks", "-o", str(app / "RustCancelProbe")]
    commands.append(command)
    subprocess.run(command, check=True)
    info = {"CFBundleExecutable": "RustCancelProbe", "CFBundleIdentifier": args.bundle_id,
            "CFBundleName": "RustCancelProbe", "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1", "CFBundleShortVersionString": "0.1.0", "MinimumOSVersion": "16.3",
            "UIDeviceFamily": [1, 2], "UILaunchScreen": {}, "LSRequiresIPhoneOS": True,
            "UIApplicationSceneManifest": {
                "UIApplicationSupportsMultipleScenes": False,
                "UISceneConfigurations": {"UIWindowSceneSessionRoleApplication": [{
                    "UISceneConfigurationName": "Probe",
                    "UISceneDelegateClassName": "ProbeSceneDelegate"}]}}}
    (app / "Info.plist").write_bytes(plistlib.dumps(info))
    entitlement_args = []
    if args.profile:
        data = subprocess.check_output(["security", "cms", "-D", "-i", str(args.profile)])
        profile = plistlib.loads(data)
        team = profile["Entitlements"]["com.apple.developer.team-identifier"]
        allowed = profile["Entitlements"]["application-identifier"]
        app_id = team + "." + args.bundle_id
        if allowed != app_id and not (allowed.endswith(".*") and app_id.startswith(allowed[:-1])):
            p.error("Profile does not authorize this isolated probe bundle ID")
        shutil.copyfile(args.profile, app / "embedded.mobileprovision")
        ent = {"application-identifier": app_id, "com.apple.developer.team-identifier": team,
               "get-task-allow": profile["Entitlements"].get("get-task-allow", False)}
        ent_path = out / "signing-entitlements.plist"
        ent_path.write_bytes(plistlib.dumps(ent))
        entitlement_args = ["--entitlements", str(ent_path)]
    subprocess.run(["codesign", "--force", "--sign", args.identity, str(app / "Frameworks/OrTTS.framework")], check=True)
    subprocess.run(["codesign", "--force", "--sign", args.identity, *entitlement_args, str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    receipt = {"status": "BUILT_NOT_TARGET_TESTED", "target": args.target, "rust_target": target,
               "bundle_id": args.bundle_id, "commands": commands,
               "source_framework_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
               "app_files_sha256": {str(f.relative_to(app)): hashlib.sha256(f.read_bytes()).hexdigest()
                                    for f in sorted(app.rglob("*")) if f.is_file() and not f.is_symlink()
                                    and f.name != "embedded.mobileprovision"},
               "note": "Local probe only; omit provisioning and local signing material from public SDK bundles"}
    (out / "BUILD_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(app)


if __name__ == "__main__":
    main()
