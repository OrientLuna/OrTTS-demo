# 下载通道

Android和iOS提供自动、Hugging Face、HF Mirror、ModelScope四种选择。设置在同一应用的模型页面间共享。

自动模式先尝试最近校验成功的通道，再按ModelScope、HF Mirror、Hugging Face尝试可用地址。手动模式只使用选定通道；已有完整文件仍直接复用。

- HF与HF Mirror使用同一仓库、revision和文件路径。
- ModelScope使用目录中显式登记的独立仓库/revision映射，不自动猜测地址。
- 当前多模型目录中8个资产已核对ModelScope同字节镜像；SenseVoice仅登记HF/HF Mirror。OrTTS自研模型目前仍使用已发布的ModelScope地址。
- 各通道必须满足相同大小和SHA256，校验失败的临时文件不安装。取消下载后不继续切换。
- 当前为单文件失败后切换，未提供跨通道断点续传；自动模式不是带宽测速器。

## 开发检查

纯Java路由测试不依赖Android：

```sh
javac -d /tmp/ortts-download-tests \
  android/app/src/main/java/com/orient/ortts/demo/DownloadRoute.java \
  tests/java/com/orient/ortts/demo/DownloadRouteTest.java
java -cp /tmp/ortts-download-tests com.orient.ortts.demo.DownloadRouteTest
```

Apple代码需在Mac/Xcode执行原Apple应用构建；Linux的Android或Java检查不代表iOS编译/真机通过。
