<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1009`。

许可：本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

安装、更新、卸载统一使用下面这一条指令；不带参数时会显示菜单：

```sh
# 菜单模式：选择安装、更新或卸载
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh

# 自动化模式：同一入口追加操作参数
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --install   # 安装/修复
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --update    # 更新软件包和内核
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --uninstall  # 卸载并清理

```

更新统一使用 `--update`，会更新 OpenKill 软件包并安装/更新官方稳定 Meta（Mihomo）内核。

安装器会对 GitHub Raw、jsDelivr 和 Fastly 三个源进行快速可达性与响应时间检测，优先使用最快源；下载失败时自动切换到其他源，不需要手动改地址。

2026-1009：更新为真正透明背景的猫咪纸飞机 PNG 图标。
