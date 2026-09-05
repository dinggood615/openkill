#!/bin/sh
. /usr/share/openkill/log.sh
. /lib/functions.sh
. /usr/share/openkill/openkill_ps.sh
. /usr/share/openkill/uci.sh

LOG_FILE="/tmp/openkill.log"
CLASH="/etc/openkill/clash"
# Prevent an overlapping watchdog instance from running expensive discovery
# or streaming checks after a service reload.
WATCHDOG_LOCK="/tmp/openkill-watchdog.lock"
if ! mkdir "$WATCHDOG_LOCK" 2>/dev/null; then
   exit 0
fi
trap 'rmdir "$WATCHDOG_LOCK" 2>/dev/null || true' EXIT INT TERM
CFG_UPDATE_INT=0
SKIP_PROXY_ADDRESS=1
SKIP_PROXY_ADDRESS_INTERVAL=30
UPNP_INT=1
UPNP_INTERVAL=30
FIREWALL_RELOAD=0
MAX_FIREWALL_RELOAD=3
# Expensive address discovery is only needed periodically.  Keeping the
# watchdog loop at one minute preserves recovery speed while avoiding a full
# interface scan on every tick.
LOCALNETWORK_INT=1
LOCALNETWORK_INTERVAL=10
HISTORY_INT=1
HISTORY_INTERVAL=10
FIREWALL_INT=1
FIREWALL_INTERVAL=5
STREAM_INT=1
STREAM_INTERVAL=5
DNS_RELOAD_LAST=0
DNS_RELOAD_COOLDOWN=300
FW4=$(command -v fw4)

# Values are expressed in watchdog cycles.  Keeping the defaults conservative
# avoids a full interface/firewall scan on every heartbeat while still
# allowing advanced users to tune the maintenance cadence in UCI.
valid_cycles() {
   case "${1:-}" in
      ''|*[!0-9]*|0) echo "$2" ;;
      *) echo "$1" ;;
   esac
}
valid_bool() {
   [ "${1:-}" = "1" ] && echo 1 || echo 0
}
WATCHDOG_SLEEP=$(valid_cycles "$(uci_get_config "watchdog_interval" || echo 60)" 60)
LOCALNETWORK_INTERVAL=$(valid_cycles "$(uci_get_config "watchdog_network_cycles" || echo 30)" 30)
HISTORY_INTERVAL=$(valid_cycles "$(uci_get_config "watchdog_history_cycles" || echo 10)" 10)
FIREWALL_INTERVAL=$(valid_cycles "$(uci_get_config "watchdog_firewall_cycles" || echo 5)" 5)
UPNP_INTERVAL=$(valid_cycles "$(uci_get_config "watchdog_upnp_cycles" || echo 60)" 60)
SKIP_PROXY_ADDRESS_INTERVAL=$(valid_cycles "$(uci_get_config "watchdog_proxy_cycles" || echo 60)" 60)
CORE_FAILURES=0

## Skip Proxies Address
skip_proxies_address()
{
ruby -ryaml -rYAML -I "/usr/share/openkill" -E UTF-8 -e "
begin
   Value = YAML.load_file('$CONFIG_FILE');
rescue Exception => e
   YAML.LOG_ERROR('Load File Failed,【' + e.message + '】');
   exit;
end;

begin
   if not (Value.key?('proxies') or Value.key?('proxy-providers')) then
      exit;
   end

   servers_to_process = Array.new

   # Servers from proxies
   if Value.key?('proxies') and not Value['proxies'].nil?
      Value['proxies'].each do |p|
         servers_to_process.push(p['server']) if p.key?('server')
      end
   end

   # Servers from proxy-providers
   if Value.key?('proxy-providers') and not Value['proxy-providers'].nil?
      Value['proxy-providers'].each do |name, provider|
         if provider.key?('path') and not provider['path'].empty?
            path = provider['path'].start_with?('./') ? '/etc/openkill/' + provider['path'][2..-1] : provider['path']
            if File.exist?(path)
               file_is_age_encrypted = File.read(path, 512).include?('BEGIN AGE ENCRYPTED FILE') rescue false
               begin
                  if provider.key?('age-secret-key') and not provider['age-secret-key'].to_s.empty?
                     begin
                        provider_config = YAML.load_file(path, secret: provider['age-secret-key']) rescue nil
                     rescue Exception => e
                        YAML.LOG_WARN('Set Proxies Address Skip: Failed【' + path + ': ' + e.message+'】')
                        next
                     end
                  else
                     if file_is_age_encrypted
                        YAML.LOG_WARN('Set Proxies Address Skip: Failed【' + path + '】File is AGE encrypted but no secret key provided')
                        next
                     end
                     provider_config = YAML.load_file(path)
                  end

                  if provider_config.is_a?(Hash) and provider_config.key?('proxies') and not provider_config['proxies'].nil?
                     provider_config['proxies'].each do |p|
                        servers_to_process.push(p['server']) if p.key?('server')
                     end
                  end
               rescue StandardError
                  if not provider.key?('age-secret-key') or provider['age-secret-key'].to_s.empty?
                     if file_is_age_encrypted
                        YAML.LOG_WARN('Failed to parse config file with Lua helper【' + path + '】File is AGE encrypted, cannot parse with Lua')
                        next
                     end
                     begin
                        syscall = \"lua /usr/share/openkill/openkill_sub_parser.lua \\\"#{path}\\\"\"
                        sub_servers = IO.popen(syscall).read.split(/\n+/)
                        servers_to_process.concat(sub_servers) if sub_servers
                     rescue Exception => e
                        YAML.LOG_WARN('Failed to parse config file with Lua helper【' + path + ': ' + e.message+'】')
                     end
                  end
               end
            end
         # Inline providers
         elsif provider['type'] == 'inline' and provider.key?('payload') and not provider['payload'].empty?
            provider['payload'].each do |p|
               servers_to_process.push(p['server']) if p.key?('server')
            end
         end
      end
   end

   servers_to_process.compact!
   servers_to_process.uniq!

   domains_to_resolve = Array.new
   ips = Array.new
   reg_domain = /([0-9a-zA-Z-]{1,}\.)+([a-zA-Z]{2,})/
   reg4 = /^((\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5])\.){3}(\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5])$/
   reg6 = /^(?:(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){6}:[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){5}:([0-9A-Fa-f]{1,4}:)?[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){4}:([0-9A-Fa-f]{1,4}:){0,2}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){3}:([0-9A-Fa-f]{1,4}:){0,3}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){2}:([0-9A-Fa-f]{1,4}:){0,4}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){6}((\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b)\.){3}(\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b))|(([0-9A-Fa-f]{1,4}:){0,5}:((\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b)\.){3}(\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b))|(::([0-9A-Fa-f]{1,4}:){0,5}((\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b)\.){3}(\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b))|([0-9A-Fa-f]{1,4}::([0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4})|(::([0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){1,7}:))|\[(?:(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){6}:[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){5}:([0-9A-Fa-f]{1,4}:)?[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){4}:([0-9A-Fa-f]{1,4}:){0,2}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){3}:([0-9A-Fa-f]{1,4}:){0,3}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){2}:([0-9A-Fa-f]{1,4}:){0,4}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){6}((\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b)\.){3}(\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b))|(([0-9A-Fa-f]{1,4}:){0,5}:((\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b)\.){3}(\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b))|(::([0-9A-Fa-f]{1,4}:){0,5}((\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b)\.){3}(\b((25[0-5])|(1\d{2})|(2[0-4]\d)|(\d{1,2}))\b))|([0-9A-Fa-f]{1,4}::([0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4})|(::([0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4})|(([0-9A-Fa-f]{1,4}:){1,7}:))\]$/i

   servers_to_process.each do |server|
      if server.to_s.match(reg4) or server.to_s.match(reg6)
         ips.push(server)
      elsif server.to_s.match(reg_domain)
         domains_to_resolve.push(server)
      end
   end

   ips.uniq!
   domains_to_resolve.uniq!

   if not domains_to_resolve.empty?
      ips_mutex = Mutex.new
      queue = Queue.new
      domains_to_resolve.each{|d| queue << d}

      threads = (1..[10, queue.size].min).map do
         Thread.new do
            while domain = queue.pop(true) rescue nil
               syscall = '/usr/share/openkill/openkill_debug_dns.lua 2>/dev/null \"' + domain + '\" \"true\"'
               result = IO.popen(syscall).read.split(/\n+/)
               if result
                  ips_mutex.synchronize do
                     result.each{|ip| ips.push(ip)}
                  end
               end
            end
         end
      end
      threads.each(&:join)
   end

   ips.compact!
   ips.uniq!

   # Add IPs to ipset/nft
   if not ips.empty? then
      firewall_v = '$FW4'.empty? ? 'ipt' : 'nft'
      set_commands = []
      ips.each do |ip|
         next if ip.nil? or ip.empty?
         if ip.match(reg4) then
            if firewall_v == 'nft' then
               set_commands << 'nft add element inet fw4 localnetwork { \"' + ip + '\" } 2>/dev/null'
            else
               set_commands << 'ipset add localnetwork \"' + ip + '\" 2>/dev/null'
            end
         elsif ip.match(reg6) then
            if firewall_v == 'nft' then
               set_commands << 'nft add element inet fw4 localnetwork6 { \"' + ip + '\" } 2>/dev/null'
            else
               set_commands << 'ipset add localnetwork6 \"' + ip + '\" 2>/dev/null'
            end
         end
      end
      system(set_commands.join('; ')) if not set_commands.empty?
   end
rescue Exception => e
   YAML.LOG_ERROR('Set Proxies Address Skip: Failed【' + e.message + '】');
end" 2>/dev/null >> $LOG_FILE
}

while :;
do
   CONFIG_FILE="/etc/openkill/$(uci_get_config "config_path" |awk -F '/' '{print $5}' 2>/dev/null)"
   ipv6_enable=$(valid_bool "$(uci_get_config "ipv6_enable" || echo 0)")
   enable_redirect_dns=$(valid_bool "$(uci_get_config "enable_redirect_dns" || echo 0)")
   dns_port=$(valid_cycles "$(uci_get_config "dns_port" || echo 7874)" 7874)
   disable_masq_cache=$(valid_bool "$(uci_get_config "disable_masq_cache" || echo 0)")
   log_size=$(valid_cycles "$(uci_get_config "log_size" || echo 1024)" 1024)
   router_self_proxy=$(valid_bool "$(uci_get_config "router_self_proxy" || echo 1)")
   skip_proxy_address=$(valid_bool "$(uci_get_config "skip_proxy_address" || echo 0)")

   cfg_update=$(valid_bool "$(uci_get_config "auto_update" || echo 0)")
   cfg_update_mode=$(valid_bool "$(uci_get_config "config_auto_update_mode" || echo 0)")
   cfg_update_interval=$(uci_get_config "config_update_interval" || echo 60)
   case "$cfg_update_interval" in ''|*[!0-9]*|0) cfg_update_interval=60 ;; esac
   upnp_lease_file=$(uci -q get upnpd.config.upnp_lease_file)

#wait for core start complete
while ( [ -n "$(unify_ps_pids "/etc/init.d/openkill")" ] )
do
   sleep 1
done >/dev/null 2>&1

#check the clash service status
if ! ubus call service list '{"name":"openkill"}' 2>/dev/null | jsonfilter -e '@.openkill.instances.*.running' | grep -q 'true'; then
   # Do not disable the service or launch a second copy while procd is
   # respawning the core.  This was the source of restart loops on some
   # snapshot firmwares; the next cycle will observe the recovered instance.
   if [ "$(uci_get_config "enable" || echo 0)" = "1" ]; then
      LOG_WATCHDOG "OpenKill service is not ready; waiting for procd recovery."
      sleep "$WATCHDOG_SLEEP"
      continue
   fi
   exit 0
fi

# Health observation only: procd owns restart policy.  The watchdog records a
# persistent failure after three cycles but never starts a duplicate core.
if ! pidof clash >/dev/null 2>&1; then
   CORE_FAILURES=$(expr "$CORE_FAILURES" + 1)
   if [ "$CORE_FAILURES" -ge 3 ]; then
      LOG_WATCHDOG "Mihomo core is not running; procd restart is pending (no duplicate start)."
      CORE_FAILURES=0
   fi
   sleep "$WATCHDOG_SLEEP"
   continue
fi
CORE_FAILURES=0

## Proxy history (maintenance task; the health loop must stay cheap)
if [ "$HISTORY_INT" -eq 1 ] || [ "$(expr "$HISTORY_INT" % "$HISTORY_INTERVAL")" -eq 0 ]; then
   /usr/share/openkill/openkill_history_get.sh
fi
HISTORY_INT=$(expr "$HISTORY_INT" + 1)

## Log File Size Manage:
   LOGSIZE=`ls -l /tmp/openkill.log |awk '{print int($5/1024)}'`
   if [ "$LOGSIZE" -gt "$log_size" ]; then
      : > /tmp/openkill.log
      LOG_WATCHDOG "Log Size Limit, Clean Up All Log Records..."
   fi

## 防火墙检查（每两分钟，避免每个心跳都遍历完整规则集）
   if [ "$FIREWALL_INT" -eq 1 ] || [ "$(expr "$FIREWALL_INT" % "$FIREWALL_INTERVAL")" -eq 0 ]; then
   if [ "$FIREWALL_RELOAD" -le "$MAX_FIREWALL_RELOAD" ]; then
      if [ -z "$FW4" ]; then
         nat_last_line=$(iptables -t nat -nL PREROUTING --line-number 2>/dev/null | awk 'END {print $1}')
         man_last_line=$(iptables -t mangle -nL PREROUTING --line-number 2>/dev/null | awk 'END {print $1}')
         nat_op_line=$(iptables -t nat -nL PREROUTING --line-number 2>/dev/null | grep -E "openkill|OpenKill" | grep -Ev "DNS|dns" | awk '{print $1}' | tail -1)
         man_op_line=$(iptables -t mangle -nL PREROUTING --line-number 2>/dev/null | grep -E "openkill|OpenKill" | grep -Ev "DNS|dns" | awk '{print $1}' | tail -1)
      else
         nat_last_line=$(nft -a list chain inet fw4 dstnat 2>/dev/null | grep "# handle" | awk -F '# handle ' '{print $2}' | tail -1)
         man_last_line=$(nft -a list chain inet fw4 mangle_prerouting 2>/dev/null | grep "# handle" | awk -F '# handle ' '{print $2}' | tail -1)
         nat_op_line=$(nft -a list chain inet fw4 dstnat 2>/dev/null | grep -E "openkill|OpenKill" | grep -Ev "DNS|dns" | grep "# handle" | awk -F '# handle ' '{print $2}' | tail -1)
         man_op_line=$(nft -a list chain inet fw4 mangle_prerouting 2>/dev/null | grep -E "openkill|OpenKill" | grep -Ev "DNS|dns" | grep "# handle" | awk -F '# handle ' '{print $2}' | tail -1)
      fi

      if ([ "$nat_last_line" != "$nat_op_line" ] && [ -n "$nat_op_line" ]) || ([ "$man_last_line" != "$man_op_line" ] && [ -n "$man_op_line" ]); then
         ## 转发顺序检查
         LOG_WATCHDOG "Setting Firewall For Rules Order..."
         /etc/init.d/openkill reload "firewall"
         let FIREWALL_RELOAD++
      elif [ -n "$(ip link show utun 2>/dev/null)" ] && [ -z "$(ip route list table 354)" ]; then
         ## 路由表检查
         LOG_WATCHDOG "Setting Firewall For IP Rules Table Recreate..."
         /etc/init.d/openkill reload "firewall"
         let FIREWALL_RELOAD++
      else
         FIREWALL_RELOAD=0
      fi
   fi
   fi
   FIREWALL_INT=$(expr "$FIREWALL_INT" + 1)

## Localnetwork 刷新 (periodic; phase-2 CPU/network overhead reduction)
if [ "$LOCALNETWORK_INT" -eq 1 ] || [ "$(expr "$LOCALNETWORK_INT" % "$LOCALNETWORK_INTERVAL")" -eq 0 ]; then
   wan_ip4s=$(/usr/share/openkill/openkill_get_network.lua "wanip" 2>/dev/null)
   wan_ip6s=$(ifconfig | grep 'inet6 addr' | awk '{print $3}' 2>/dev/null)
   lan_ip4s=$(/usr/share/openkill/openkill_get_network.lua "lan_cidr" 2>/dev/null)
   lan_ip6s=$(/usr/share/openkill/openkill_get_network.lua "lan_cidr6" 2>/dev/null)
   if [ -n "$FW4" ]; then
      if [ -n "$wan_ip4s" ]; then
         for wan_ip4 in $wan_ip4s; do
            nft add element inet fw4 localnetwork { "$wan_ip4" } 2>/dev/null
         done
      fi
      if [ -n "$lan_ip4s" ]; then
         for lan_ip4 in $lan_ip4s; do
            nft add element inet fw4 localnetwork { "$lan_ip4" } 2>/dev/null
         done
      fi

      if [ "$ipv6_enable" -eq 1 ]; then
         if [ -n "$wan_ip6s" ]; then
            for wan_ip6 in $wan_ip6s; do
               nft add element inet fw4 localnetwork6 { "$wan_ip6" } 2>/dev/null
            done
         fi
         if [ -n "$lan_ip6s" ]; then
            for lan_ip6 in $lan_ip6s; do
               nft add element inet fw4 localnetwork6 { "$lan_ip6" } 2>/dev/null
            done
         fi
      fi
   else
      if [ -n "$wan_ip4s" ]; then
         for wan_ip4 in $wan_ip4s; do
            ipset add localnetwork "$wan_ip4" 2>/dev/null
         done
      fi
      if [ -n "$lan_ip4s" ]; then
         for lan_ip4 in $lan_ip4s; do
            ipset add localnetwork "$lan_ip4" 2>/dev/null
         done
      fi
      if [ "$ipv6_enable" -eq 1 ]; then
         if [ -n "$wan_ip6s" ]; then
            for wan_ip6 in $wan_ip6s; do
               ipset add localnetwork6 "$wan_ip6" 2>/dev/null
            done
         fi
         if [ -n "$lan_ip6s" ]; then
            for lan_ip6 in $lan_ip6s; do
               ipset add localnetwork6 "$lan_ip6" 2>/dev/null
            done
         fi
      fi
   fi
fi
LOCALNETWORK_INT=$(expr "$LOCALNETWORK_INT" + 1)

## UPNP
   if [ "$UPNP_INT" -eq 1 ] || [ "$(expr "$UPNP_INT" % "$UPNP_INTERVAL")" -eq 0 ]; then
      if [ -f "$upnp_lease_file" ]; then
         #del
         if [ -n "$FW4" ]; then
            nft list chain inet fw4 openkill_upnp 2>/dev/null |grep "return" |while read -r i
            do
               upnp_ip=$(echo "$i" |awk -F 'ip saddr ' '{print $2}' |awk  '{print $1}')
               upnp_dp=$(echo "$i" |awk -F 'sport ' '{print $2}' |awk  '{print $1}')
               upnp_type=$(echo "$i" |awk -F 'sport ' '{print $1}' |awk  '{print $4}' |tr '[a-z]' '[A-Z]')
               if [ -n "$upnp_ip" ] && [ -n "$upnp_dp" ] && [ -n "$upnp_type" ]; then
                  if [ -z "$(cat "$upnp_lease_file" |grep "$upnp_ip" |grep "$upnp_dp" |grep "$upnp_type")" ]; then
                     handle=$(nft -a list chain inet fw4 openkill_upnp |grep "$i" |awk -F '# handle ' '{print$2}')
                     nft delete rule inet fw4 openkill_upnp handle ${handle}
                  fi
               fi
            done >/dev/null 2>&1
         else
            iptables -t mangle -nL openkill_upnp 2>/dev/null |grep "RETURN" |while read -r i
            do
               upnp_ip=$(echo "$i" |awk '{print $4}')
               upnp_dp=$(echo "$i" |awk -F 'spt:' '{print $2}')
               upnp_type=$(echo "$i" |awk '{print $2}' |tr '[a-z]' '[A-Z]')
               if [ -n "$upnp_ip" ] && [ -n "$upnp_dp" ] && [ -n "$upnp_type" ]; then
                  if [ -z "$(cat "$upnp_lease_file" |grep "$upnp_ip" |grep "$upnp_dp" |grep "$upnp_type")" ]; then
                     iptables -t mangle -D openkill_upnp -p "$upnp_type" -s "$upnp_ip" --sport "$upnp_dp" -j RETURN 2>/dev/null
                  fi
               fi
            done >/dev/null 2>&1
         fi
         #add
         if [ -s "$upnp_lease_file" ] && { { [ -z "$FW4" ] && [ -n "$(iptables --line-numbers -t mangle -xnvL openkill_upnp 2>/dev/null)" ]; } || { [ -n "$FW4" ] && [ -n "$(nft list chain inet fw4 openkill_upnp 2>/dev/null)" ]; }; }; then
            cat "$upnp_lease_file" |while read -r line
            do
               if [ -n "$line" ]; then
                  upnp_ip=$(echo "$line" |awk -F ':' '{print $3}')
                  upnp_dp=$(echo "$line" |awk -F ':' '{print $4}')
                  upnp_type=$(echo "$line" |awk -F ':' '{print $1}' |tr '[A-Z]' '[a-z]')
                  if [ -n "$upnp_ip" ] && [ -n "$upnp_dp" ] && [ -n "$upnp_type" ]; then
                     if [ -n "$FW4" ]; then
                        if [ -z "$(nft list chain inet fw4 openkill_upnp |grep "$upnp_ip" |grep "$upnp_dp" |grep "$upnp_type")" ]; then
                           nft add rule inet fw4 openkill_upnp ip saddr { "$upnp_ip" } "$upnp_type" sport "$upnp_dp" counter return 2>/dev/null
                        fi
                     else
                        if [ -z "$(iptables -t mangle -nL openkill_upnp |grep "$upnp_ip" |grep "$upnp_dp" |grep "$upnp_type")" ]; then
                           iptables -t mangle -A openkill_upnp -p "$upnp_type" -s "$upnp_ip" --sport "$upnp_dp" -j RETURN 2>/dev/null
                        fi
                     fi
                  fi
               fi
            done >/dev/null 2>&1
         fi
      fi
      let UPNP_INT++
   else
      let UPNP_INT++
   fi

## Skip Proxies Address
   if [ "$skip_proxy_address" -eq 1 ]; then
      if [ "$SKIP_PROXY_ADDRESS" -eq 1 ] || [ "$(expr "$SKIP_PROXY_ADDRESS" % "$SKIP_PROXY_ADDRESS_INTERVAL")" -eq 0 ]; then
         if mkdir /tmp/openkill-proxy-address.lock 2>/dev/null; then
            skip_proxies_address
            rmdir /tmp/openkill-proxy-address.lock 2>/dev/null || true
         fi
         let SKIP_PROXY_ADDRESS++
      else
         let SKIP_PROXY_ADDRESS++
      fi
   fi

## DNS转发劫持
   if [ "$enable_redirect_dns" = "1" ]; then
      if [ -z "$(uci -q get dhcp.@dnsmasq[0].server |grep "$dns_port")" ] || [ ! -z "$(uci -q get dhcp.@dnsmasq[0].server |awk -F ' ' '{print $2}')" ]; then
         dns_now=$(date +%s 2>/dev/null || echo 0)
         if [ "$DNS_RELOAD_LAST" -eq 0 ] || [ "$dns_now" -ge $((DNS_RELOAD_LAST + DNS_RELOAD_COOLDOWN)) ]; then
            LOG_WATCHDOG "Force Reset DNS Hijack..."
            uci -q del dhcp.@dnsmasq[-1].server
            uci -q add_list dhcp.@dnsmasq[0].server=127.0.0.1#"$dns_port"
            uci -q delete dhcp.@dnsmasq[0].resolvfile
            uci -q set dhcp.@dnsmasq[0].noresolv=1
            [ "$disable_masq_cache" -eq 1 ] && {
              uci -q set dhcp.@dnsmasq[0].cachesize=0
            }
            uci -q commit dhcp
            /etc/init.d/dnsmasq restart >/dev/null 2>&1
            DNS_RELOAD_LAST="$dns_now"
         fi
      fi
   fi

## 配置文件循环更新
   if [ "$cfg_update" -eq 1 ] && [ "$cfg_update_mode" -eq 1 ]; then
      if [ "$CFG_UPDATE_INT" -ne 0 ]; then
         [ "$(expr "$CFG_UPDATE_INT" % "$cfg_update_interval")" -eq 0 ] && /usr/share/openkill/openkill.sh
      fi
      CFG_UPDATE_INT=$(expr "$CFG_UPDATE_INT" + 1)
   fi

##STREAMING_UNLOCK_CHECK (isolated from the health loop)
   if [ "$STREAM_INT" -eq 1 ] || [ "$(expr "$STREAM_INT" % "$STREAM_INTERVAL")" -eq 0 ]; then
      /usr/share/openkill/openkill_watchdog_stream.sh &
   fi
   STREAM_INT=$(expr "$STREAM_INT" + 1)

    sleep "$WATCHDOG_SLEEP"
done 2>/dev/null
