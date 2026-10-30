# Android ARM64

使用tools/build.py与显式本地NDK目录；不安装SDK/ADB，也不访问设备。默认现代ARM ISA见profile.json。产物为CPU原生CLI，APK/JNI界面另行接入。

目标运行时需要可写的进程私有TMPDIR和输出目录，以及匹配NDK的libc++_shared.so。不得把shell的/data/local/tmp路径硬编码到App沙箱。不要覆盖系统库或打包个人音色/全套模型到源码仓库。

当前没有执行本仓库新binary的手机验收。已有设备CPU历史数据位于benchmarks/，不代表任意机型或Android前台/后台状态都实时。
