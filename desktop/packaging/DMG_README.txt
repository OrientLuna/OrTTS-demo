OrTTS 本地语音合成 Demo — macOS Apple Silicon

安装：将 OrTTS.app 拖到 Applications（应用程序），然后推出此磁盘映像。
首次打开后，选择与本地模型一致的版本，再选择完整模型目录进行校验。
默认版本：0.6B Q4（精简）/ P3。安装包不包含模型，不自动下载。

模型目录应包含 DOWNLOAD_MANIFEST.json 或 download-manifest.json、native、voices，
以及 P3 推理所需的 P3 目录。Q8 模型须选择 Q8，不能当作 Q4 导入。
请勿在运行时移动或修改模型文件。

程序数据和合成音频默认写入：
~/Library/Application Support/OrTTS Desktop/

停止推理或退出时，离线计算可能需等待当前计算返回，程序会安全释放模型。

这是本机测试版：Apple Silicon / arm64，最低声明 macOS 13.3。
应用只有 ad-hoc 本地签名，没有 Developer ID 签名或 Apple 公证。
DMG 本身不解决 Gatekeeper 信任问题。仅应运行你确认来源可信的副本；
公开分发版本应由发布者完成 Developer ID 签名与公证。
不要全局关闭 Gatekeeper。

运行时与随包依赖许可：OrTTS.app/Contents/Resources/licenses/
模型权重另有独立许可，请保留模型目录内的 LICENSE/NOTICE/licenses 文件。
