include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-openkill
PKG_VERSION:=2026-1120
PKG_MAINTAINER:=dinggood615 <https://github.com/dinggood615/openkill>

PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)

include $(INCLUDE_DIR)/package.mk

# The production package keeps runtime tools in DEPENDS so image builds select
# and build them normally.  The opt-in SDK test mode uses EXTRA_DEPENDS: the
# package contains only scripts/resources and has no build-time dependency on
# those target tools, while the generated package still records them for the
# target package manager.  This keeps the expensive dependency graph out of a
# single-package CI smoke build without changing production metadata.
ifeq ($(OPENKILL_SDK_TEST),1)
  OPENKILL_DEPENDS:=
  OPENKILL_EXTRA_DEPENDS:=dnsmasq-full (>=0),bash (>=0),curl (>=0),ca-bundle (>=0),ip-full (>=0),lua (>=0),ruby (>=0),ruby-yaml (>=0),luci-compat (>=0),kmod-tun (>=0),kmod-inet-diag (>=0),unzip (>=0)
else
  OPENKILL_DEPENDS:=+dnsmasq-full +bash +curl +ca-bundle +ip-full +lua \
	+ruby +ruby-yaml +luci-compat +kmod-tun +kmod-inet-diag +unzip
  OPENKILL_EXTRA_DEPENDS:=
endif

ifneq ($(OPENKILL_SDK_TEST),1)
define Package/$(PKG_NAME)/config
	config PACKAGE_kmod-inet-diag
	default y if PACKAGE_$(PKG_NAME)

	config PACKAGE_luci-compat
	default y if PACKAGE_$(PKG_NAME)

	config PACKAGE_kmod-nft-tproxy
	default y if PACKAGE_firewall4

	config PACKAGE_kmod-ipt-nat
	default y if ! PACKAGE_firewall4

	config PACKAGE_iptables-mod-tproxy
	default y if ! PACKAGE_firewall4

	config PACKAGE_iptables-mod-extra
	default y if ! PACKAGE_firewall4

	config PACKAGE_dnsmasq_full_ipset
	default y if ! PACKAGE_firewall4

	config PACKAGE_dnsmasq_full_nftset
	default y if PACKAGE_firewall4

	config PACKAGE_ipset
	default y if ! PACKAGE_firewall4
endef
endif

define Package/$(PKG_NAME)
	CATEGORY:=LuCI
	SUBMENU:=3. Applications
	TITLE:=LuCI support for OpenKill
	PKGARCH:=all
	DEPENDS:=$(OPENKILL_DEPENDS)
	EXTRA_DEPENDS:=$(OPENKILL_EXTRA_DEPENDS)
	MAINTAINER:=dinggood615
endef

define Package/$(PKG_NAME)/description
    A lightweight LuCI client for the official Mihomo (Meta) core
endef

define Build/Prepare
	$(CP) $(CURDIR)/root $(PKG_BUILD_DIR)
	$(CP) $(CURDIR)/luasrc $(PKG_BUILD_DIR)
	# MetaCubeXD is the bundled dashboard.  Zashboard remains available via
	# the on-demand dashboard downloader but is not shipped in the base IPK.
	rm -rf $(PKG_BUILD_DIR)/root/usr/share/openkill/ui/zashboard
	sh $(CURDIR)/tools/prune-ui-css.sh $(PKG_BUILD_DIR)/root/www/luci-static/resources/openkill/css/oc.css
	$(foreach po,$(wildcard ${CURDIR}/po/zh-cn/*.po), \
		po2lmo $(po) $(PKG_BUILD_DIR)/$(patsubst %.po,%.lmo,$(notdir $(po)));)
	chmod 0755 $(PKG_BUILD_DIR)/root/etc/init.d/openkill
	chmod -R 0755 $(PKG_BUILD_DIR)/root/usr/share/openkill/
	exit 0
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/$(PKG_NAME)/conffiles
/etc/config/openkill
endef

define Package/$(PKG_NAME)/preinst
#!/bin/sh
	if [ -f "/etc/config/openkill" ] && [ ! -f "/tmp/openkill.bak" ]; then
		cp -f "/etc/config/openkill" "/tmp/openkill.bak" >/dev/null 2>&1
		cp -rf "/etc/openkill" "/tmp/openkill" >/dev/null 2>&1
		cp -rf "/usr/share/openkill/ui" "/tmp/openkill_ui" >/dev/null 2>&1
		cp -rf "/www/luci-static/resources/openkill/pac" "/tmp/pac" >/dev/null 2>&1
	fi
	exit 0
endef

define Package/$(PKG_NAME)/postinst
#!/bin/sh
	if [ -z "$${IPKG_INSTROOT}" ]; then
		# Remove the retired bundled copy before normalization so an old
		# selection cannot point at a dashboard that is no longer packaged.
		rm -rf /usr/share/openkill/ui/zashboard >/dev/null 2>&1 || true
		[ -x /usr/share/openkill/openkill_config_normalize.sh ] && /usr/share/openkill/openkill_config_normalize.sh >/dev/null 2>&1 || true
		rm -f /tmp/openkill.change /tmp/openkill/openkill.change /tmp/openkill/capabilities.env >/dev/null 2>&1 || true
		rm -rf /tmp/luci-indexcache /tmp/luci-indexcache.* /tmp/luci-modulecache /var/luci-modulecache >/dev/null 2>&1 || true
	fi
	exit 0
endef

define Package/$(PKG_NAME)/prerm
#!/bin/sh
	[ -x /etc/init.d/openkill ] && /etc/init.d/openkill stop 2>/dev/null || true
	if [ -f "/etc/config/openkill" ] && [ ! -f "/tmp/openkill.bak" ]; then
		cp -f "/etc/config/openkill" "/tmp/openkill.bak" >/dev/null 2>&1
		cp -rf "/etc/openkill" "/tmp/openkill" >/dev/null 2>&1
		cp -rf "/usr/share/openkill/ui" "/tmp/openkill_ui" >/dev/null 2>&1
		cp -rf "/www/luci-static/resources/openkill/pac" "/tmp/pac" >/dev/null 2>&1
	fi
	exit 0
endef

define Package/$(PKG_NAME)/postrm
#!/bin/sh
	rm -rf /tmp/openkill.log >/dev/null 2>&1
	rm -rf /tmp/openkill_start.log >/dev/null 2>&1
	rm -rf /tmp/openkill.change >/dev/null 2>&1
	rm -rf /tmp/openkill_version_history.json /tmp/openkill_version_history_openkill.json >/dev/null 2>&1
    rm -rf /tmp/openkill_cdn_info.json >/dev/null 2>&1
	rm -rf /tmp/etc/openkill >/dev/null 2>&1
	rm -rf /tmp/openkill_announcement >/dev/null 2>&1
	rm -rf /tmp/openkill_version_history_* >/dev/null 2>&1
	rm -rf /tmp/openkill_cdn_info_* >/dev/null 2>&1
	rm -rf /tmp/luci-indexcache /tmp/luci-indexcache.* /var/luci-indexcache /var/luci-indexcache.* >/dev/null 2>&1
	rm -rf /tmp/luci-modulecache /var/luci-modulecache >/dev/null 2>&1
	exit 0
endef

define Package/$(PKG_NAME)/install
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/i18n
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/*.*.lmo $(1)/usr/lib/lua/luci/i18n/
	$(CP) $(PKG_BUILD_DIR)/root/* $(1)/
	$(CP) $(PKG_BUILD_DIR)/luasrc/* $(1)/usr/lib/lua/luci/
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
