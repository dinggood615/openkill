<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1013`。

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

IPK/APK 构建完成后独立发布，互不等待。安装器读取对应格式的最新发布清单，优先查询官方仓库，网络失败时回退镜像；下载 Release 附件或镜像副本后校验 SHA256。页面源码版本可能领先于尚在构建的软件包，安装器显示实际选中的发布版本。
依赖索引和安装共用临时源配置；官方 OpenWrt 源不可用时自动尝试北大、清华镜像，保留固件路径和自定义源，不永久修改系统源。依赖下载失败也会重试兼容镜像，必需依赖缺失会停止安装并显示原因。

2026-1013：独立 IPK/APK 发布、版本清单及包校验；修复依赖镜像未用于实际安装的问题，并包含运行状态页五个外部快捷图标的移除。
