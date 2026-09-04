<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1003`。

许可：本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

安装器支持安装、更新、卸载和本地软件包安装：

```sh
# 安装或修复 OpenKill（自动识别 opkg/apk 并安装官方稳定 Meta/Mihomo 内核）
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --install

# 更新 OpenKill 软件包并同步更新官方稳定 Meta/Mihomo 内核
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --update

# 卸载 OpenKill 并清理其配置、缓存和运行数据
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --uninstall

# 安装本地 IPK/APK 软件包
sh install-openkill.sh --package-file /tmp/luci-app-openkill_2026-1003_all.ipk
```

更新统一使用 `--update`，会更新 OpenKill 软件包并安装/更新官方稳定 Meta（Mihomo）内核。

2026-1003：默认启用 Mihomo TCP 并发连接与统一延迟测量，改善双栈测速和首连速度；watchdog 网络地址扫描按周期执行，降低后台开销。
