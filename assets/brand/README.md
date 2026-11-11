# OrTTS 三色语音积木

由用户提供的参考插画中橙红、青绿、金黄积木衍生。使用圆润、无缝搭接的平面几何，减少外围留白，保留星芒与声波符号；没有复制人物或照片材质。`ortts-mark.svg` 是可编辑的标志源，`ortts-icon.svg` 增加暖白背景，平台图标从同一源生成。

- `ortts-icon.png`：1024px、不透明应用图标和展示预览。
- `ortts-desktop.png`：桌面圆角背景版本，四角透明。
- `ortts.ico`：Windows 多尺寸图标（16–256px）。
- `ortts.icns`：macOS 图标资源。
- `ortts-mark.svg`：无画布底色的矢量标志；三块颜色直接衔接，不使用浅色描边或内部空隙。

Android 使用缩入安全区的自适应矢量前景、暖白背景和传统 mipmap 回退。iOS 的 CMake Demo 与 Xcode 生成入口共享 `apple/Assets.xcassets`；CMake 构建通过 actool 编译并合并图标声明。实际签名安装包包含 Assets.car 与 CFBundleIcons，不能只改图标文件而遗漏声明。

目前 macOS PC 入口是 CLI，Windows/Linux 也没有新增图形客户端。桌面格式已提供，实际应用/安装器需在各自打包环节指定 ICO、ICNS 或 PNG。

重新生成（Python 3、Pillow、CairoSVG 和本机 Cairo；不联网）：

```sh
# macOS Homebrew 的 Cairo 可显式设置搜索路径
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python3 tools/generate_brand_assets.py
```

生成资源已提交；普通应用构建不需要重新安装这些绘图依赖。图标资产随本仓库提供，模型与第三方组件许可证独立处理。
