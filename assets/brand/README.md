# OrTTS 三色语音积木

使用用户从三个草图中选定的第一个方案。橙红积木保持水平，青绿 L 型块与金黄色块自然拼接。`ortts-master.png` 是透明背景母图，保留选定造型与材质，不再手工重画、扭曲轮廓或添加白色底板。

- `ortts-icon.png`、`ortts-desktop.png`、`ortts-preview.png`：保留 alpha 的 PNG。
- `ortts.ico`：Windows 多尺寸透明图标，16–256px。
- `ortts.icns`：macOS 透明图标资源。
- `ortts-mark.svg`、`ortts-icon.svg`：为现有引用保留的嵌入 PNG 包装，不是真矢量源。

Android 使用透明 PNG 前景与透明背景声明，并留出系统自适应遮罩所需区域；具体遮罩/底色显示由启动器决定。iOS 普通浅色图标提供品牌深青色不透明回退，不加白色边框；另提供透明暗色外观资源。透明 Logo 源文件与普通 iOS 浅色 AppIcon 不是同一种交付，不能以透明母图直接代替所有系统外观。iOS 预览见 `ortts-ios-preview.png`。

CMake 和 Xcode 生成入口共享 `apple/Assets.xcassets`，通过 actool 编译与图标声明集成。目前 PC 入口是命令行程序，桌面安装器可使用 ICO、ICNS 或 PNG。

重新导出只需现有 Pillow，不联网：

```sh
python3 tools/generate_brand_assets.py
```

母图来源为用户选定的第一个草图。资源导出只做格式和尺寸适配，不改变积木的轮廓与拼搭关系。
