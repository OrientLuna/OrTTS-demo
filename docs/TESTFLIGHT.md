# TestFlight 归档与上传

需要完整 Xcode、XcodeGen、Python/Pillow，以及已构建的设备版 OrTTS.framework 和 eSpeak mobile 目录。模型不嵌入应用；G2P 的 GPL 对应源码与模型许可边界见 [MOBILE_G2P](MOBILE_G2P.md)。

```sh
python3.12 tools/prepare_testflight_project.py \
  --out build/testflight-ortts \
  --engine-install build/demo-unified-ios/install \
  --g2p-install build/g2p-ios/mobile \
  --team YOUR_TEAM_ID --build 3 --version 0.4.0
xcodebuild -project build/testflight-ortts/OrTTS.xcodeproj -scheme OrTTS \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$PWD/build/testflight-ortts/OrTTS.xcarchive" \
  archive CODE_SIGNING_ALLOWED=NO
```

该脚本生成本地项目、应用图标、版本化 plist、固定模型目录以及上传 ExportOptions；不读凭据、不上传。归档内保留 espeak-ng-data 文件夹，嵌入两个框架。准备出的未签名归档需要在分发阶段正常签名。加密声明目前按仅使用系统标准 HTTPS/TLS、无自研非豁免加密设置；引入额外加密功能后须重新核查。

App Store Connect 需有匹配 `com.orient.ortts.prototype` 的应用记录，且登录账号有相应权限。使用已登录 Xcode 的 Organizer 上传；命令行可显式执行：

```sh
xcodebuild -exportArchive \
  -archivePath "$PWD/build/testflight-ortts/OrTTS.xcarchive" \
  -exportOptionsPlist "$PWD/build/testflight-ortts/ExportOptions.plist" \
  -exportPath "$PWD/build/testflight-ortts/export" -allowProvisioningUpdates
```

不要同时操作其他应用正在使用的 Organizer 分发窗口，不要自动点击钥匙串授权窗口或取消已有签名。命令行 `Failed to Use Accounts` 不能证明 Xcode UI 已退出登录，也不能据此要求重登录/新建证书。

## 2026-11-08 状态

0.4.0 build3 已完成实际归档，确认主可执行文件、图标、固定模型目录、G2P 数据路径及两个框架均存在。首次命令行上传返回 `Failed to Use Accounts`，未上传。Organizer 当时由 OrTavern 的现有签名任务占用，等待用户本机钥匙串授权，因此未抢占、取消或重启该流程。App Store Connect 的 OrTTS 应用记录尚未核实；不可将归档成功视为上传成功。

归档保存在本机 `build/testflight-ortts/OrTTS-build3.xcarchive`。只有 Apple 接收并处理成功后，才能称为 TestFlight 上传完成；外部测试邀请还需要后续相应配置/审核。

官方流程：[上传构建](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds)、[应用记录与工作流](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-workflow)。
