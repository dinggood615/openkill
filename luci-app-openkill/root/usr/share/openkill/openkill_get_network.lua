#!/usr/bin/lua

require "nixio"
require "luci.util"
require "luci.sys"
local ntm = require "luci.model.network".init()
local cidr = require "luci.ip"
local fs = require "luci.openkill"
local type = arg[1]
local rv = {}
local wan, wan6

if not type then os.exit(0) end

if pcall(function() local x = ntm:get_all_wan_networks(); local y = ntm:get_all_wan6_networks(); end) then
	wan = ntm:get_all_wan_networks()
	wan6 = ntm:get_all_wan6_networks()
elseif pcall(function() local x = ntm:get_wan_networks(); local y = ntm:get_wan6_networks(); end) then
	wan = ntm:get_wan_networks()
	wan6 = ntm:get_wan6_networks()
elseif pcall(function() local x = ntm:get_wannet(); local y = ntm:get_wan6net(); end) then
	wan = {}
	wan6 = {}
	wan[1] =  ntm:get_wannet()
	wan6[1] = ntm:get_wan6net()
else
	os.exit(0)
end

if wan then
	rv.wan = {}
	for i = 1, #wan do
		rv.wan[i] = {
			ipaddr  = wan[i]:ipaddr(),
			ip6addr  = wan[i]:ip6addr(),
			gwaddr  = wan[i]:gwaddr(),
			netmask = wan[i]:netmask(),
			dns     = wan[i]:dnsaddrs(),
			expires = wan[i]:expires(),
			uptime  = wan[i]:uptime(),
			proto   = wan[i]:proto(),
			ifname  = wan[i]:ifname()
		}
	end
end

if wan6 then
	rv.wan6 = {}
	for i = 1, #wan6 do
		rv.wan6[i] = {
			ip6addr   = wan6[i]:ip6addr(),
			gw6addr   = wan6[i]:gw6addr(),
			dns       = wan6[i]:dns6addrs(),
			ip6prefix = wan6[i]:ip6prefix(),
			uptime    = wan6[i]:uptime(),
			proto     = wan6[i]:proto(),
			ifname    = wan6[i]:ifname()
		}
	end
end

if type == "dns" then
	if wan then
		for o = 1, #(rv.wan) do
			for i = 1, #(rv.wan[o].dns) do
				if rv.wan[o].dns[i] ~= rv.wan[o].gwaddr and rv.wan[o].dns[i] ~= rv.wan[o].ipaddr then
					print(rv.wan[o].dns[i])
				end
			end
		end
	end
end

if type == "dns6" then
	if wan6 then
		for o = 1, #(rv.wan6) do
			for i = 1, #(rv.wan6[o].dns) do
				if rv.wan6[o].dns[i] ~= rv.wan6[o].gw6addr and rv.wan6[o].ip6addr then
					print(rv.wan6[o].dns[i])
				end
			end
		end
	end
end

if type == "gateway" then
	if wan then
		for o = 1, #(rv.wan) do
			print(rv.wan[o].gwaddr)
		end
	end
end

if type == "gateway6" then
	if wan6 then
		for o = 1, #(rv.wan6) do
			print(rv.wan6[o].gw6addr)
		end
	end
end

if type == "dhcp" then
	if wan then
		for o = 1, #(rv.wan) do
			if rv.wan[o].proto == "dhcp" then
				print(rv.wan[o].ifname)
			end
		end
	end
	if wan6 then
		for o = 1, #(rv.wan6) do
			if rv.wan6[o].proto == "dhcpv6" then
				print(rv.wan6[o].ifname)
			end
		end
	end
end

if type == "pppoe" then
	if wan then
		for o = 1, #(rv.wan) do
			if rv.wan[o].proto == "pppoe" then
				print(rv.wan[o].ifname)
			end
		end
	end
	if wan6 then
		for o = 1, #(rv.wan6) do
			if rv.wan6[o].proto == "pppoe" then
				print(rv.wan6[o].ifname)
			end
		end
	end
end

if type == "wanip" then
	if wan then
		for o = 1, #(rv.wan) do
			if rv.wan[o].proto == "pppoe" then
				print(rv.wan[o].ipaddr)
			end
		end
	end
end

if type == "wanip6" then
	if wan6 then
		for o = 1, #(rv.wan6) do
			if rv.wan6[o].proto == "pppoe" or rv.wan6[o].proto == "dhcpv6" then
				print(rv.wan6[o].ip6addr)
			end
		end
	end
end

if type == "lan_cidr" then
	if wan then
		for o = 1, #(rv.wan) do
			if rv.wan[o].proto ~= "pppoe" then
				if rv.wan[o].ipaddr and rv.wan[o].netmask then
					local network = cidr.IPv4(rv.wan[o].ipaddr, rv.wan[o].netmask):network():string()
					local prefix = cidr.IPv4(rv.wan[o].ipaddr, rv.wan[o].netmask):prefix()
					print(network.."/"..prefix)
				end
			end
		end
	end
end

if type == "lan_cidr6" then
	-- Return prefixes belonging to internal network interfaces.  The old
	-- implementation accidentally iterated the WAN model here, which could
	-- put the uplink prefix into localnetwork6 and omit the delegated LAN PD.
	-- Read netifd's authoritative interface dump so multiple internal
	-- prefixes are retained and WAN/WAN6 remain separate.  The historical
	-- predicate was `name ~= "wan" and name ~= "wan6"`; role detection below is
	-- case-insensitive and also checks the active native default-route device.
	local ok, jsonc = pcall(require, "luci.jsonc")
	if ok and jsonc then
		local dump_path = os.getenv("OPENKILL_INTERFACE_DUMP_FILE")
		local dump = nil
		if dump_path and dump_path ~= "" then
			local fd = io.open(dump_path, "r")
			if fd then
				dump = fd:read("*a")
				fd:close()
			end
		end
		dump = dump or luci.sys.exec("ubus call network.interface dump 2>/dev/null")
		local data = jsonc.parse(dump or "")
		if data and data.interface then
			local external_devices = {}
			local route_dump = luci.sys.exec("ip -4 route show default 2>/dev/null; ip -6 route show default 2>/dev/null") or ""
			for device in route_dump:gmatch("%sdev%s+([^%s]+)") do
				external_devices[device] = true
			end
			local prefixes = {}
			local function add_prefix(address, mask)
				mask = tonumber(mask)
				if not address or not mask or mask < 0 or mask > 128 then return end
				local ok_cidr, value = pcall(cidr.IPv6, address, mask)
				if not ok_cidr or not value then return end
				local ok_network, network = pcall(function() return value:network():string() end)
				local ok_prefix, prefix = pcall(function() return value:prefix() end)
				if ok_network and ok_prefix and network and prefix then
					prefixes[network.."/"..prefix] = true
				end
			end
			local function is_external(iface)
				local name = tostring(iface.interface or "")
				local lower_name = string.lower(name)
				if iface.up == false or iface.up == 0 then return true end
				if lower_name == "wan" or lower_name == "wan6" or lower_name == "loopback" or
				   lower_name:match("^wan%d*$") or lower_name:match("^wan6%d*$") then
					return true
				end
				return external_devices[name] or
					external_devices[iface.l3_device or ""] or
					external_devices[iface.device or ""]
			end
			for _, iface in ipairs(data.interface) do
				if not is_external(iface) then
					for _, addr in ipairs(iface["ipv6-address"] or {}) do
						add_prefix(addr.address, addr.mask)
					end
					for _, prefix_info in ipairs(iface["ipv6-prefix"] or {}) do
						add_prefix(prefix_info.address, prefix_info.mask)
					end
					-- netifd commonly exposes a delegated prefix on the WAN6
					-- object and the assigned LAN slice on this separate list.
					-- Internal interfaces must consume the assignment so a PD
					-- does not disappear merely because WAN6 itself is external.
					for _, prefix_info in ipairs(iface["ipv6-prefix-assignment"] or {}) do
						add_prefix(prefix_info.address, prefix_info.mask)
					end
				end
			end
			local sorted = {}
			for prefix in pairs(prefixes) do sorted[#sorted + 1] = prefix end
			table.sort(sorted)
			for _, prefix in ipairs(sorted) do print(prefix) end
		end
	end
end

os.exit(0)
