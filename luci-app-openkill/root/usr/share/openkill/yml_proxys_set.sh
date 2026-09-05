#!/bin/sh
. /lib/functions.sh
. /usr/share/openkill/ruby.sh
. /usr/share/openkill/log.sh
. /usr/share/openkill/uci.sh

set_lock() {
   exec 886>"/tmp/lock/openkill_proxies_set.lock" 2>/dev/null
   flock -x 886 2>/dev/null
}

del_lock() {
   flock -u 886 2>/dev/null
   rm -rf "/tmp/lock/openkill_proxies_set.lock"
}

SERVER_FILE="/tmp/yaml_servers.yaml"
PROXY_PROVIDER_FILE="/tmp/yaml_provider.yaml"
CONFIG_FILE=$(uci_get_config "config_path")
CONFIG_NAME=$(echo "$CONFIG_FILE" |awk -F '/' '{print $5}' 2>/dev/null)
UPDATE_CONFIG_FILE=$1
UPDATE_CONFIG_NAME=$(echo "$UPDATE_CONFIG_FILE" |awk -F '/' '{print $5}' 2>/dev/null)
UCI_DEL_LIST="uci -q del_list openkill.config.new_servers_group"
UCI_ADD_LIST="uci -q add_list openkill.config.new_servers_group"
UCI_SET="uci -q set openkill.config."
FEATURE_H2C=$(uci -q get openkill.config.feature_h2c 2>/dev/null || echo 0)
FEATURE_SHADOWQUIC=$(uci -q get openkill.config.feature_shadowquic 2>/dev/null || echo 0)
FEATURE_MASQUE=$(uci -q get openkill.config.feature_masque 2>/dev/null || echo 0)
FEATURE_AMNEZIA_WG=$(uci -q get openkill.config.feature_amnezia_wg 2>/dev/null || echo 0)
FEATURE_ANYTLS_METADATA=$(uci -q get openkill.config.feature_anytls_metadata 2>/dev/null || echo 0)
FEATURE_BBR3=$(uci -q get openkill.config.feature_bbr3 2>/dev/null || echo 0)
FEATURE_ZEROTIER=$(uci -q get openkill.config.feature_zerotier 2>/dev/null || echo 0)
servers_name="/tmp/servers_name.list"
proxy_provider_name="/tmp/provider_name.list"
set_lock

if [ ! -z "$UPDATE_CONFIG_FILE" ]; then
   CONFIG_FILE="$UPDATE_CONFIG_FILE"
   CONFIG_NAME="$UPDATE_CONFIG_NAME"
fi

if [ -z "$CONFIG_FILE" ]; then
  for file_name in /etc/openkill/config/*
   do
      if [ -f "$file_name" ]; then
         CONFIG_FILE=$file_name
         CONFIG_NAME=$(echo "$CONFIG_FILE" |awk -F '/' '{print $5}' 2>/dev/null)
         break
      fi
   done
fi

if [ -z "$CONFIG_NAME" ]; then
   CONFIG_FILE="/etc/openkill/config/config.yaml"
   CONFIG_NAME="config.yaml"
fi

#写入代理集到配置文件
yml_proxy_provider_set()
{
   local section="$1"
   local enabled config type name path provider_filter provider_url provider_interval health_check health_check_url health_check_interval other_parameters
   config_get_bool "enabled" "$section" "enabled" "1"
   config_get "config" "$section" "config" ""
   config_get "type" "$section" "type" ""
   config_get "name" "$section" "name" ""
   config_get "path" "$section" "path" ""
   config_get "provider_filter" "$section" "provider_filter" ""
   config_get "provider_url" "$section" "provider_url" ""
   config_get "provider_interval" "$section" "provider_interval" ""
   config_get "health_check" "$section" "health_check" ""
   config_get "health_check_url" "$section" "health_check_url" ""
   config_get "health_check_interval" "$section" "health_check_interval" ""
   config_get "other_parameters" "$section" "other_parameters" ""

   if [ "$enabled" = "0" ]; then
      return
   fi

   if [ -z "$type" ]; then
      return
   fi

   if [ -z "$name" ]; then
      return
   fi

   if [ "$path" != "./proxy_provider/$name.yaml" ] && [ "$type" = "http" ]; then
      path="./proxy_provider/$name.yaml"
   elif [ -z "$path" ]; then
      return
   fi

   if [ -z "$health_check" ]; then
      return
   fi

   if [ ! -z "$config" ] && [ "$config" != "$CONFIG_NAME" ] && [ "$config" != "all" ]; then
      return
   fi

   #避免重复代理集
   if [ "$config" = "$CONFIG_NAME" ] || [ "$config" = "all" ]; then
      if [ -n "$(grep -w "path: $path" "$PROXY_PROVIDER_FILE" 2>/dev/null)" ]; then
         return
      elif [ "$(grep -w "^$name$" "$proxy_provider_name" |wc -l 2>/dev/null)" -ge 2 ] && [ -z "$(grep -w "path: $path" "$PROXY_PROVIDER_FILE" 2>/dev/null)" ]; then
      	 convert_name=$(echo "$name" |sed 's/\//\\\//g' 2>/dev/null)
         sed -i "1,/^${convert_name}$/{//d}" "$proxy_provider_name" 2>/dev/null
         return
      fi
   fi

   LOG_OUT "Start Writing【$CONFIG_NAME - $type - $name】Proxy-provider To Config File..."
   echo "$name" >> /tmp/Proxy_Provider

cat >> "$PROXY_PROVIDER_FILE" <<-EOF
  $name:
    type: $type
    path: "$path"
EOF
   if [ -n "$provider_filter" ]; then
cat >> "$PROXY_PROVIDER_FILE" <<-EOF
    filter: "$provider_filter"
EOF
   fi
   if [ -n "$provider_url" ]; then
cat >> "$PROXY_PROVIDER_FILE" <<-EOF
    url: "$provider_url"
    interval: $provider_interval
EOF
   fi
cat >> "$PROXY_PROVIDER_FILE" <<-EOF
    health-check:
      enable: $health_check
      url: "$health_check_url"
      interval: $health_check_interval
EOF

#other_parameters
   if [ -n "$other_parameters" ]; then
      echo -e "$other_parameters" >> "$PROXY_PROVIDER_FILE"
   fi
}

set_alpn()
{
   if [ -z "$1" ]; then
      return
   fi
cat >> "$SERVER_FILE" <<-EOF
      - '$1'
EOF
}

set_http_path()
{
   if [ -z "$1" ]; then
      return
   fi
cat >> "$SERVER_FILE" <<-EOF
        - '$1'
EOF
}

set_h2_host()
{
   if [ -z "$1" ]; then
      return
   fi
cat >> "$SERVER_FILE" <<-EOF
        - '$1'
EOF
}

set_ws_headers()
{
   if [ -z "$1" ]; then
      return
   fi
cat >> "$SERVER_FILE" <<-EOF
        $1
EOF
}

set_zerotier_orbit()
{
   local value="$1"
   local world seed
   [ -n "$value" ] || return
   case "$value" in
      *:*) ;;
      *) return ;;
   esac
   world="${value%%:*}"
   seed="${value#*:}"
   world=$(printf '%s' "$world" | sed 's/[^A-Za-z0-9_.-]//g')
   seed=$(printf '%s' "$seed" | sed 's/[^A-Za-z0-9_.-]//g')
   printf '%s\n' "$world" | grep -Eq '^[0-9A-Fa-f]{16}$' || return
   printf '%s\n' "$seed" | grep -Eq '^[0-9]{10}$' || return
cat >> "$SERVER_FILE" <<-EOF
      - world: "$world"
        seed: "$seed"
EOF
}

emit_amnezia_option()
{
   local key="$1"
   local value="$2"
   [ -n "$value" ] || return
   case "$key" in
      jc|jmin|jmax|s1|s2|s3|s4|h1|h2|h3|h4|i1|i2|i3|i4|i5|j1|j2|j3|itime) ;;
      *) return ;;
   esac
cat >> "$SERVER_FILE" <<-EOF
      $key: $value
EOF
}

#写入服务器节点到配置文件
yml_servers_set()
{

   local section="$1"
   config_get_bool "enabled" "$section" "enabled" "1"
   config_get "config" "$section" "config" ""
   config_get "type" "$section" "type" ""
   config_get "name" "$section" "name" ""
   config_get "server" "$section" "server" ""
   config_get "port" "$section" "port" ""

   if [ "$enabled" = "0" ]; then
      return
   fi

   if [ -z "$type" ]; then
      return
   fi

   if [ -z "$name" ]; then
      return
   fi

   if [ -z "$server" ] && [ "$type" != "direct" ] && [ "$type" != "dns" ] && [ "$type" != "zerotier" ]; then
      return
   fi

   if [ -z "$port" ] && [ "$type" != "direct" ] && [ "$type" != "dns" ] && [ "$type" != "zerotier" ]; then
      return
   fi

    if [ "$type" = "ss" ] || [ "$type" = "trojan" ] || [ "$type" = "ssr" ] || [ "$type" = "shadowquic" ]; then
        config_get "password" "$section" "password" ""
        if [ -z "$password" ]; then
            return
        fi
    fi

    # ShadowQUIC requires both credentials.  Keep malformed imported nodes
    # out of the generated YAML instead of letting them fail the whole core
    # preflight later.
    if [ "$type" = "shadowquic" ]; then
        config_get "shadowquic_username" "$section" "shadowquic_username" ""
        if [ -z "$shadowquic_username" ]; then
            return
        fi
    fi

   if [ ! -z "$config" ] && [ "$config" != "$CONFIG_NAME" ] && [ "$config" != "all" ]; then
      return
   fi

   #避免重复节点
   if [ "$config" = "$CONFIG_NAME" ] || [ "$config" = "all" ]; then
      if [ "$(grep -w "^$name$" "$servers_name" |wc -l 2>/dev/null)" -ge 2 ] && [ -n "$(grep -w "name: \"$name\"" "$SERVER_FILE" 2>/dev/null)" ]; then
         return
      fi
   fi

   if [ "$config" = "$CONFIG_NAME" ] || [ "$config" = "all" ]; then
      if [ -n "$(grep -w "name: \"$name\"" "$SERVER_FILE" 2>/dev/null)" ]; then
         return
      elif [ "$(grep -w "^$name$" "$servers_name" |wc -l 2>/dev/null)" -ge 2 ] && [ -z "$(grep -w "name: \"$name\"" "$SERVER_FILE" 2>/dev/null)" ]; then
      	 convert_name=$(echo "$name" |sed 's/\//\\\//g' 2>/dev/null)
         sed -i "1,/^${convert_name}$/{//d}" "$servers_name" 2>/dev/null
         return
      fi
   fi
   LOG_OUT "Start Writing【$CONFIG_NAME - $type - $name】Proxy To Config File..."

   config_get "dialer_proxy" "$section" "dialer_proxy" ""
   config_get "udp" "$section" "udp" ""
   config_get "skip_cert_verify" "$section" "skip_cert_verify" ""
   config_get "tls" "$section" "tls" ""
   config_get "sni" "$section" "sni" ""
   config_get "alpn" "$section" "alpn" ""
   config_get "fingerprint" "$section" "fingerprint" ""
   config_get "client_fingerprint" "$section" "client_fingerprint" ""
   config_get "ip_version" "$section" "ip_version" ""
   config_get "tfo" "$section" "tfo" ""
   config_get "multiplex" "$section" "multiplex" ""
   config_get "multiplex_protocol" "$section" "multiplex_protocol" ""
   config_get "multiplex_max_connections" "$section" "multiplex_max_connections" ""
   config_get "multiplex_min_streams" "$section" "multiplex_min_streams" ""
   config_get "multiplex_max_streams" "$section" "multiplex_max_streams" ""
   config_get "multiplex_padding" "$section" "multiplex_padding" ""
   config_get "multiplex_statistic" "$section" "multiplex_statistic" ""
   config_get "multiplex_only_tcp" "$section" "multiplex_only_tcp" ""
   config_get "interface_name" "$section" "interface_name" ""
   config_get "routing_mark" "$section" "routing_mark" ""
   config_get "other_parameters" "$section" "other_parameters" ""

   if [ "$client_fingerprint" = "none" ]; then
        client_fingerprint=""
   fi

   if [ "$multiplex" = "false" ]; then
        multiplex=""
   fi

#ss
if [ "$type" = "ss" ]; then
   config_get "cipher" "$section" "cipher" ""
   config_get "obfs" "$section" "obfs" ""
   config_get "host" "$section" "host" ""
   config_get "mux" "$section" "mux" ""
   config_get "custom" "$section" "custom" ""
   config_get "path" "$section" "path" ""
   config_get "obfs_password" "$section" "obfs_password" ""
   config_get "obfs_version_hint" "$section" "obfs_version_hint" ""
   config_get "obfs_restls_script" "$section" "obfs_restls_script" ""
   config_get "udp_over_tcp" "$section" "udp_over_tcp" ""

   if [ "$obfs" != "none" ] && [ -n "$obfs" ]; then
      if [ "$obfs" = "websocket" ]; then
            obfss="plugin: v2ray-plugin"
      elif [ "$obfs" = "shadow-tls" ]; then
            obfss="plugin: shadow-tls"
      elif [ "$obfs" = "restls" ]; then
            obfss="plugin: restls"
      else
            obfss="plugin: obfs"
      fi
   else
      obfss=""
   fi

   if [ ! -z "$path" ]; then
      path="path: \"$path\""
   fi

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    cipher: $cipher
    password: "$password"
EOF
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ ! -z "$udp_over_tcp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp-over-tcp: $udp_over_tcp
EOF
    fi
    if [ ! -z "$obfss" ]; then
cat >> "$SERVER_FILE" <<-EOF
    $obfss
    plugin-opts:
EOF
        if [ "$obfs" != "shadow-tls" ] && [ "$obfs" != "restls" ]; then
cat >> "$SERVER_FILE" <<-EOF
      mode: $obfs
EOF
        fi
        if [ ! -z "$host" ]; then
cat >> "$SERVER_FILE" <<-EOF
      host: "$host"
EOF
        fi
        if [  "$obfss" = "plugin: shadow-tls" ]; then
            if [ ! -z "$obfs_password" ]; then
cat >> "$SERVER_FILE" <<-EOF
      password: "$obfs_password"
EOF
            fi
            if [ ! -z "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
      fingerprint: "$fingerprint"
EOF
            fi
        fi
        if [  "$obfss" = "plugin: restls" ]; then
            if [ ! -z "$obfs_password" ]; then
cat >> "$SERVER_FILE" <<-EOF
      password: "$obfs_password"
EOF
            fi
            if [ ! -z "$obfs_version_hint" ]; then
cat >> "$SERVER_FILE" <<-EOF
      version-hint: "$obfs_version_hint"
EOF
            fi
            if [ ! -z "$obfs_restls_script" ]; then
cat >> "$SERVER_FILE" <<-EOF
      restls-script: "$obfs_restls_script"
EOF
            fi
        fi
        if [  "$obfss" = "plugin: v2ray-plugin" ]; then
            if [ ! -z "$tls" ]; then
cat >> "$SERVER_FILE" <<-EOF
      tls: $tls
EOF
            fi
            if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
      skip-cert-verify: $skip_cert_verify
EOF
            fi
            if [ ! -z "$path" ]; then
cat >> "$SERVER_FILE" <<-EOF
      $path
EOF
            fi
            if [ ! -z "$mux" ]; then
cat >> "$SERVER_FILE" <<-EOF
      mux: $mux
EOF
            fi
            if [ ! -z "$custom" ]; then
cat >> "$SERVER_FILE" <<-EOF
      headers:
        custom: $custom
EOF
            fi
            if [ ! -z "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
      fingerprint: "$fingerprint"
EOF
            fi
        fi
    fi
fi

#ssr
if [ "$type" = "ssr" ]; then
   config_get "cipher_ssr" "$section" "cipher_ssr" ""
   config_get "obfs_ssr" "$section" "obfs_ssr" ""
   config_get "protocol" "$section" "protocol" ""
   config_get "obfs_param" "$section" "obfs_param" ""
   config_get "protocol_param" "$section" "protocol_param" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    cipher: $cipher_ssr
    password: "$password"
    obfs: "$obfs_ssr"
    protocol: "$protocol"
EOF
    if [ ! -z "$obfs_param" ]; then
cat >> "$SERVER_FILE" <<-EOF
    obfs-param: $obfs_param
EOF
    fi
    if [ ! -z "$protocol_param" ]; then
cat >> "$SERVER_FILE" <<-EOF
    protocol-param: $protocol_param
EOF
    fi
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
   fi
fi

#vmess
if [ "$type" = "vmess" ]; then
   config_get "uuid" "$section" "uuid" ""
   config_get "alterId" "$section" "alterId" ""
   config_get "securitys" "$section" "securitys" ""
   config_get "xudp" "$section" "xudp" ""
   config_get "packet_encoding" "$section" "packet_encoding" ""
   config_get "global_padding" "$section" "global_padding" ""
   config_get "authenticated_length" "$section" "authenticated_length" ""
   config_get "servername" "$section" "servername" ""
   config_get "obfs_vmess" "$section" "obfs_vmess" ""
   config_get "custom" "$section" "custom" ""
   config_get "path" "$section" "path" ""
   config_get "ws_opts_path" "$section" "ws_opts_path" ""
   config_get "ws_opts_headers" "$section" "ws_opts_headers" ""
   config_get "max_early_data" "$section" "max_early_data" ""
   config_get "early_data_header_name" "$section" "early_data_header_name" ""
   config_get "http_path" "$section" "http_path" ""
   config_get "keep_alive" "$section" "keep_alive" ""
   config_get "h2_path" "$section" "h2_path" ""
   config_get "h2_host" "$section" "h2_host" ""
   config_get "h2c_enable" "$section" "h2c_enable" ""
   config_get "grpc_service_name" "$section" "grpc_service_name" ""

   if [ "$obfs_vmess" = "websocket" ]; then
      obfs_vmess="network: ws"
   fi
   if [ "$obfs_vmess" = "http" ]; then
      obfs_vmess="network: http"
   fi
   if [ "$obfs_vmess" = "h2" ]; then
      obfs_vmess="network: h2"
   fi
   if [ "$obfs_vmess" = "grpc" ]; then
      obfs_vmess="network: grpc"
   fi

   if [ "$FEATURE_H2C" = "1" ] && [ "$h2c_enable" = "1" ] && [ "$obfs_vmess" = "network: h2" ]; then
      tls="false"
   fi

   if [ ! -z "$custom" ]; then
      custom="Host: \"$custom\""
   fi

   if [ ! -z "$path" ] && [ "$obfs_vmess" = "network: ws" ]; then
      path="ws-path: \"$path\""
   fi

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    uuid: $uuid
    alterId: $alterId
    cipher: $securitys
EOF
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ ! -z "$xudp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    xudp: $xudp
EOF
    fi
    if [ ! -z "$packet_encoding" ]; then
cat >> "$SERVER_FILE" <<-EOF
    packet-encoding: "$packet_encoding"
EOF
    fi
    if [ ! -z "$global_padding" ]; then
cat >> "$SERVER_FILE" <<-EOF
    global-padding: $global_padding
EOF
    fi
    if [ ! -z "$authenticated_length" ]; then
cat >> "$SERVER_FILE" <<-EOF
    authenticated-length: $authenticated_length
EOF
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ ! -z "$tls" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tls: $tls
EOF
    fi
    if [ ! -z "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fingerprint: "$fingerprint"
EOF
    fi
    if [ ! -z "$client_fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    client-fingerprint: "$client_fingerprint"
EOF
    fi
    if [ ! -z "$servername" ] && [ "$tls" = "true" ]; then
cat >> "$SERVER_FILE" <<-EOF
    servername: "$servername"
EOF
    fi
    if [ "$obfs_vmess" != "none" ]; then
cat >> "$SERVER_FILE" <<-EOF
    $obfs_vmess
EOF
        if [ "$obfs_vmess" = "network: ws" ]; then
            if [ ! -z "$path" ]; then
cat >> "$SERVER_FILE" <<-EOF
    $path
EOF
            fi
            if [ ! -z "$custom" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ws-headers:
      $custom
EOF
            fi
            if [ -n "$ws_opts_path" ] || [ -n "$ws_opts_headers" ] || [ -n "$max_early_data" ] || [ -n "$early_data_header_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ws-opts:
EOF
                if [ -n "$ws_opts_path" ]; then
cat >> "$SERVER_FILE" <<-EOF
      path: "$ws_opts_path"
EOF
                fi
                if [ -n "$ws_opts_headers" ]; then
cat >> "$SERVER_FILE" <<-EOF
      headers:
EOF
                    config_list_foreach "$section" "ws_opts_headers" set_ws_headers
                fi
                if [ -n "$max_early_data" ]; then
cat >> "$SERVER_FILE" <<-EOF
      max-early-data: $max_early_data
EOF
                fi
                if [ -n "$early_data_header_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
      early-data-header-name: "$early_data_header_name"
EOF
                fi
            fi
        fi
        if [ "$obfs_vmess" = "network: http" ]; then
            if [ ! -z "$http_path" ]; then
cat >> "$SERVER_FILE" <<-EOF
    http-opts:
      method: "GET"
      path:
EOF
                config_list_foreach "$section" "http_path" set_http_path
            fi
            if [ "$keep_alive" = "true" ]; then
cat >> "$SERVER_FILE" <<-EOF
      headers:
        Connection:
          - keep-alive
EOF
            fi
        fi
        #h2
        if [ "$obfs_vmess" = "network: h2" ]; then
            if [ ! -z "$h2_host" ]; then
cat >> "$SERVER_FILE" <<-EOF
    h2-opts:
      host:
EOF
                config_list_foreach "$section" "h2_host" set_h2_host
            fi
            if [ ! -z "$h2_path" ]; then
cat >> "$SERVER_FILE" <<-EOF
      path: $h2_path
EOF
            fi
        fi
        if [ ! -z "$grpc_service_name" ] && [ "$obfs_vmess" = "network: grpc" ]; then
cat >> "$SERVER_FILE" <<-EOF
    grpc-opts:
      grpc-service-name: "$grpc_service_name"
EOF
        fi
    fi
fi

#anytls
if [ "$type" = "anytls" ]; then
   config_get "password" "$section" "password" ""
   config_get "idle_session_check_interval" "$section" "idle_session_check_interval" ""
   config_get "idle_session_timeout" "$section" "idle_session_timeout" ""
   config_get "min_idle_session" "$section" "min_idle_session" ""
   config_get "anytls_advanced" "$section" "anytls_advanced" ""
   config_get "anytls_client_metadata" "$section" "anytls_client_metadata" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$password" ]; then
cat >> "$SERVER_FILE" <<-EOF
    password: "$password"
EOF
    fi
    if [ -n "$client_fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    client-fingerprint: "$client_fingerprint"
EOF
    fi
    if [ -n "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ -n "$idle_session_check_interval" ]; then
cat >> "$SERVER_FILE" <<-EOF
    idle-session-check-interval: $idle_session_check_interval
EOF
    fi
    if [ -n "$idle_session_timeout" ]; then
cat >> "$SERVER_FILE" <<-EOF
    idle-session-timeout: $idle_session_timeout
EOF
    fi
    if [ -n "$min_idle_session" ]; then
cat >> "$SERVER_FILE" <<-EOF
    min-idle-session: $min_idle_session
EOF
    fi
    if [ "$FEATURE_ANYTLS_METADATA" = "1" ] && [ "$anytls_advanced" = "1" ] && [ -n "$anytls_client_metadata" ]; then
cat >> "$SERVER_FILE" <<-EOF
    client-metadata: "$anytls_client_metadata"
EOF
    fi
    if [ -n "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ ! -z "$alpn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
        config_list_foreach "$section" "alpn" set_alpn
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
fi

#Mieru
if [ "$type" = "mieru" ]; then
   config_get "port_range" "$section" "port_range" ""
   config_get "username" "$section" "username" ""
   config_get "transport" "$section" "transport" "TCP"
   config_get "multiplexing" "$section" "multiplexing" "MULTIPLEXING_LOW"

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$port_range" ]; then
cat >> "$SERVER_FILE" <<-EOF
    port-range: "$port_range"
EOF
    fi
    if [ -n "$username" ]; then
cat >> "$SERVER_FILE" <<-EOF
    username: "$username"
EOF
    fi
    if [ -n "$transport" ]; then
cat >> "$SERVER_FILE" <<-EOF
    transport: "$transport"
EOF
    fi
    if [ -n "$multiplexing" ]; then
cat >> "$SERVER_FILE" <<-EOF
    multiplexing: "$multiplexing"
EOF
    fi
fi

#Tuic
if [ "$type" = "tuic" ]; then
   config_get "tc_ip" "$section" "tc_ip" ""
   config_get "tc_token" "$section" "tc_token" ""
   config_get "tc_uuid" "$section" "tc_uuid" ""
   config_get "tc_password" "$section" "tc_password" ""
   config_get "udp_relay_mode" "$section" "udp_relay_mode" ""
   config_get "congestion_controller" "$section" "congestion_controller" ""
   config_get "tc_alpn" "$section" "tc_alpn" ""
   config_get "disable_sni" "$section" "disable_sni" ""
   config_get "reduce_rtt" "$section" "reduce_rtt" ""
   config_get "fast_open" "$section" "fast_open" ""
   config_get "heartbeat_interval" "$section" "heartbeat_interval" ""
   config_get "request_timeout" "$section" "request_timeout" ""
   config_get "max_udp_relay_packet_size" "$section" "max_udp_relay_packet_size" ""
   config_get "max_open_streams" "$section" "max_open_streams" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$tc_ip" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ip: "$tc_ip"
EOF
    fi
    if [ -n "$tc_token" ]; then
cat >> "$SERVER_FILE" <<-EOF
    token: "$tc_token"
EOF
    fi
    if [ -n "$tc_uuid" ]; then
cat >> "$SERVER_FILE" <<-EOF
    uuid: "$tc_uuid"
EOF
    fi
    if [ -n "$tc_password" ]; then
cat >> "$SERVER_FILE" <<-EOF
    password: "$tc_password"
EOF
    fi
    if [ -n "$udp_relay_mode" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp-relay-mode: "$udp_relay_mode"
EOF
    fi
    if [ -n "$congestion_controller" ]; then
cat >> "$SERVER_FILE" <<-EOF
    congestion-controller: "$congestion_controller"
EOF
    fi
    if [ -n "$tc_alpn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
        config_list_foreach "$section" "tc_alpn" set_alpn
    fi
    if [ -n "$disable_sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    disable-sni: $disable_sni
EOF
    fi
    if [ -n "$reduce_rtt" ]; then
cat >> "$SERVER_FILE" <<-EOF
    reduce-rtt: $reduce_rtt
EOF
    fi
    if [ -n "$fast_open" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fast-open: $fast_open
EOF
    fi
    if [ -n "$heartbeat_interval" ]; then
cat >> "$SERVER_FILE" <<-EOF
    heartbeat-interval: $heartbeat_interval
EOF
    fi
    if [ -n "$request_timeout" ]; then
cat >> "$SERVER_FILE" <<-EOF
    request-timeout: $request_timeout
EOF
    fi
    if [ -n "$max_udp_relay_packet_size" ]; then
cat >> "$SERVER_FILE" <<-EOF
    max-udp-relay-packet-size: $max_udp_relay_packet_size
EOF
    fi
    if [ -n "$max_open_streams" ]; then
cat >> "$SERVER_FILE" <<-EOF
    max-open-streams: $max_open_streams
EOF
    fi
    if [ -n "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
fi

#WireGuard
if [ "$type" = "wireguard" ]; then
   config_get "wg_ip" "$section" "wg_ip" ""
   config_get "wg_ipv6" "$section" "wg_ipv6" ""
   config_get "private_key" "$section" "private_key" ""
   config_get "public_key" "$section" "public_key" ""
   config_get "preshared_key" "$section" "preshared_key" ""
   config_get "wg_dns" "$section" "wg_dns" ""
   config_get "wg_mtu" "$section" "wg_mtu" ""
   config_get "amnezia_wg_enable" "$section" "amnezia_wg_enable" ""
   config_get "amnezia_jc" "$section" "amnezia_jc" ""
   config_get "amnezia_jmin" "$section" "amnezia_jmin" ""
   config_get "amnezia_jmax" "$section" "amnezia_jmax" ""
   config_get "amnezia_s1" "$section" "amnezia_s1" ""
   config_get "amnezia_s2" "$section" "amnezia_s2" ""
   config_get "amnezia_s3" "$section" "amnezia_s3" ""
   config_get "amnezia_s4" "$section" "amnezia_s4" ""
   config_get "amnezia_h1" "$section" "amnezia_h1" ""
   config_get "amnezia_h2" "$section" "amnezia_h2" ""
   config_get "amnezia_h3" "$section" "amnezia_h3" ""
   config_get "amnezia_h4" "$section" "amnezia_h4" ""
   config_get "amnezia_i1" "$section" "amnezia_i1" ""
   config_get "amnezia_i2" "$section" "amnezia_i2" ""
   config_get "amnezia_i3" "$section" "amnezia_i3" ""
   config_get "amnezia_i4" "$section" "amnezia_i4" ""
   config_get "amnezia_i5" "$section" "amnezia_i5" ""
   config_get "amnezia_j1" "$section" "amnezia_j1" ""
   config_get "amnezia_j2" "$section" "amnezia_j2" ""
   config_get "amnezia_j3" "$section" "amnezia_j3" ""
   config_get "amnezia_itime" "$section" "amnezia_itime" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$wg_ip" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ip: "$wg_ip"
EOF
    fi
    if [ -n "$wg_ipv6" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ipv6: "$wg_ipv6"
EOF
    fi
    if [ -n "$private_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    private-key: "$private_key"
EOF
    fi
    if [ -n "$public_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    public-key: "$public_key"
EOF
    fi
    if [ -n "$preshared_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    preshared-key: "$preshared_key"
EOF
    fi
    if [ -n "$wg_dns" ]; then
cat >> "$SERVER_FILE" <<-EOF
    dns:
EOF
        config_list_foreach "$section" "wg_dns" set_alpn
    fi
    if [ -n "$wg_mtu" ]; then
cat >> "$SERVER_FILE" <<-EOF
    mtu: "$wg_mtu"
EOF
    fi
    amnezia_has_options=0
    if [ -n "$amnezia_jc" ] || [ -n "$amnezia_jmin" ] || [ -n "$amnezia_jmax" ] || \
       [ -n "$amnezia_s1" ] || [ -n "$amnezia_s2" ] || [ -n "$amnezia_s3" ] || [ -n "$amnezia_s4" ] || \
       [ -n "$amnezia_h1" ] || [ -n "$amnezia_h2" ] || [ -n "$amnezia_h3" ] || [ -n "$amnezia_h4" ] || \
       [ -n "$amnezia_i1" ] || [ -n "$amnezia_i2" ] || [ -n "$amnezia_i3" ] || [ -n "$amnezia_i4" ] || [ -n "$amnezia_i5" ] || \
       [ -n "$amnezia_j1" ] || [ -n "$amnezia_j2" ] || [ -n "$amnezia_j3" ] || [ -n "$amnezia_itime" ]; then
        amnezia_has_options=1
    fi
    if [ "$FEATURE_AMNEZIA_WG" = "1" ] && [ "$amnezia_wg_enable" = "1" ] && [ "$amnezia_has_options" = "1" ]; then
cat >> "$SERVER_FILE" <<-EOF
    amnezia-wg-option:
EOF
        emit_amnezia_option jc "$amnezia_jc"
        emit_amnezia_option jmin "$amnezia_jmin"
        emit_amnezia_option jmax "$amnezia_jmax"
        emit_amnezia_option s1 "$amnezia_s1"
        emit_amnezia_option s2 "$amnezia_s2"
        emit_amnezia_option s3 "$amnezia_s3"
        emit_amnezia_option s4 "$amnezia_s4"
        emit_amnezia_option h1 "$amnezia_h1"
        emit_amnezia_option h2 "$amnezia_h2"
        emit_amnezia_option h3 "$amnezia_h3"
        emit_amnezia_option h4 "$amnezia_h4"
        emit_amnezia_option i1 "$amnezia_i1"
        emit_amnezia_option i2 "$amnezia_i2"
        emit_amnezia_option i3 "$amnezia_i3"
        emit_amnezia_option i4 "$amnezia_i4"
        emit_amnezia_option i5 "$amnezia_i5"
        emit_amnezia_option j1 "$amnezia_j1"
        emit_amnezia_option j2 "$amnezia_j2"
        emit_amnezia_option j3 "$amnezia_j3"
        emit_amnezia_option itime "$amnezia_itime"
    fi
    if [ -n "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
fi

#hysteria
if [ "$type" = "hysteria" ]; then
   config_get "hysteria_protocol" "$section" "hysteria_protocol" ""
   config_get "hysteria_up" "$section" "hysteria_up" ""
   config_get "hysteria_down" "$section" "hysteria_down" ""
   config_get "hysteria_alpn" "$section" "hysteria_alpn" ""
   config_get "hysteria_obfs" "$section" "hysteria_obfs" ""
   config_get "hysteria_auth" "$section" "hysteria_auth" ""
   config_get "hysteria_auth_str" "$section" "hysteria_auth_str" ""
   config_get "hysteria_ca" "$section" "hysteria_ca" ""
   config_get "hysteria_ca_str" "$section" "hysteria_ca_str" ""
   config_get "recv_window_conn" "$section" "recv_window_conn" ""
   config_get "recv_window" "$section" "recv_window" ""
   config_get "disable_mtu_discovery" "$section" "disable_mtu_discovery" ""
   config_get "fast_open" "$section" "fast_open" ""
   config_get "ports" "$section" "ports" ""
   config_get "hop_interval" "$section" "hop_interval" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    protocol: $hysteria_protocol
EOF
    if [ -n "$hysteria_up" ]; then
cat >> "$SERVER_FILE" <<-EOF
    up: "$hysteria_up"
EOF
    fi
    if [ -n "$hysteria_down" ]; then
cat >> "$SERVER_FILE" <<-EOF
    down: "$hysteria_down"
EOF
    fi
    if [ -n "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ -n "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ -n "$hysteria_alpn" ]; then
        if [ -z "$(echo $hysteria_alpn |grep ' ')" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn: 
      - "$hysteria_alpn"
EOF
        else
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
        config_list_foreach "$section" "hysteria_alpn" set_alpn
        fi
    fi
    if [ -n "$hysteria_obfs" ]; then
cat >> "$SERVER_FILE" <<-EOF
    obfs: "$hysteria_obfs"
EOF
    fi
    if [ -n "$hysteria_auth" ]; then
cat >> "$SERVER_FILE" <<-EOF
    auth: "$hysteria_auth"
EOF
    fi
    if [ -n "$hysteria_auth_str" ]; then
cat >> "$SERVER_FILE" <<-EOF
    auth-str: "$hysteria_auth_str"
EOF
    fi
    if [ -n "$hysteria_ca" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ca: "$hysteria_ca"
EOF
    fi
    if [ -n "$hysteria_ca_str" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ca-str: "$hysteria_ca_str"
EOF
    fi
    if [ -n "$recv_window_conn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    recv-window-conn: "$recv_window_conn"
EOF
    fi
    if [ -n "$recv_window" ]; then
cat >> "$SERVER_FILE" <<-EOF
    recv-window: "$recv_window"
EOF
    fi
    if [ -n "$disable_mtu_discovery" ]; then
cat >> "$SERVER_FILE" <<-EOF
    disable-mtu-discovery: $disable_mtu_discovery
EOF
    fi
    if [ -n "$fast_open" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fast-open: $fast_open
EOF
    fi
    if [ -n "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fingerprint: "$fingerprint"
EOF
    fi
    if [ -n "$ports" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ports: $ports
EOF
    fi
    if [ -n "$hop_interval" ]; then
cat >> "$SERVER_FILE" <<-EOF
    hop-interval: $hop_interval
EOF
    fi
fi

#hysteria2
if [ "$type" = "hysteria2" ]; then
   config_get "password" "$section" "password" ""
   config_get "hysteria_up" "$section" "hysteria_up" ""
   config_get "hysteria_down" "$section" "hysteria_down" ""
   config_get "hysteria_alpn" "$section" "hysteria_alpn" ""
   config_get "hysteria_obfs" "$section" "hysteria_obfs" ""
   config_get "hysteria_obfs_password" "$section" "hysteria_obfs_password" ""
   config_get "hysteria_ca" "$section" "hysteria_ca" ""
   config_get "hysteria_ca_str" "$section" "hysteria_ca_str" ""
   config_get "initial_stream_receive_window" "$section" "initial_stream_receive_window" ""
   config_get "max_stream_receive_window" "$section" "max_stream_receive_window" ""
   config_get "initial_connection_receive_window" "$section" "initial_connection_receive_window" ""
   config_get "max_connection_receive_window" "$section" "max_connection_receive_window" ""
   config_get "ports" "$section" "ports" ""
   config_get "hysteria2_protocol" "$section" "hysteria2_protocol" ""
   config_get "hop_interval" "$section" "hop_interval" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    password: "$password"
EOF
    if [ -n "$hysteria_up" ]; then
cat >> "$SERVER_FILE" <<-EOF
    up: "$hysteria_up"
EOF
    fi
    if [ -n "$hysteria_down" ]; then
cat >> "$SERVER_FILE" <<-EOF
    down: "$hysteria_down"
EOF
    fi
    if [ -n "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ -n "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ -n "$hysteria_alpn" ]; then
        if [ -z "$(echo $hysteria_alpn |grep ' ')" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn: 
      - "$hysteria_alpn"
EOF
        else
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
            config_list_foreach "$section" "hysteria_alpn" set_alpn
        fi
    fi
    if [ -n "$hysteria_obfs" ]; then
cat >> "$SERVER_FILE" <<-EOF
    obfs: "$hysteria_obfs"
EOF
    fi
    if [ -n "$hysteria_obfs_password" ]; then
cat >> "$SERVER_FILE" <<-EOF
    obfs-password: "$hysteria_obfs_password"
EOF
    fi
    if [ -n "$hysteria_ca" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ca: "$hysteria_ca"
EOF
    fi
    if [ -n "$hysteria_ca_str" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ca-str: "$hysteria_ca_str"
EOF
    fi
    if [ -n "$initial_stream_receive_window" ]; then
cat >> "$SERVER_FILE" <<-EOF
    initial-stream-receive-window: "$initial_stream_receive_window"
EOF
    fi
    if [ -n "$max_stream_receive_window" ]; then
cat >> "$SERVER_FILE" <<-EOF
    max-stream-receive-window: "$max_stream_receive_window"
EOF
    fi
    if [ -n "$initial_connection_receive_window" ]; then
cat >> "$SERVER_FILE" <<-EOF
    initial-connection-receive-window: "$initial_connection_receive_window"
EOF
    fi
    if [ -n "$max_connection_receive_window" ]; then
cat >> "$SERVER_FILE" <<-EOF
    max-connection-receive-window: "$max_connection_receive_window"
EOF
    fi
    if [ -n "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fingerprint: "$fingerprint"
EOF
    fi
    if [ -n "$ports" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ports: $ports
EOF
    fi
    if [ -n "$hysteria2_protocol" ]; then
cat >> "$SERVER_FILE" <<-EOF
    protocol: $hysteria2_protocol
EOF
    fi
    if [ -n "$hop_interval" ]; then
cat >> "$SERVER_FILE" <<-EOF
    hop-interval: $hop_interval
EOF
    fi
fi

#shadowquic
if [ "$type" = "shadowquic" ]; then
   [ "$FEATURE_SHADOWQUIC" = "1" ] || return
   config_get "password" "$section" "password" ""
   config_get "shadowquic_username" "$section" "shadowquic_username" ""
   config_get "shadowquic_advanced" "$section" "shadowquic_advanced" ""
   config_get "shadowquic_quic_versions" "$section" "shadowquic_quic_versions" ""
   config_get "shadowquic_udp_over_stream" "$section" "shadowquic_udp_over_stream" ""
   config_get "shadowquic_zero_rtt" "$section" "shadowquic_zero_rtt" ""
   config_get "shadowquic_keep_alive_interval" "$section" "shadowquic_keep_alive_interval" ""
   config_get "shadowquic_congestion_controller" "$section" "shadowquic_congestion_controller" ""
   config_get "shadowquic_up" "$section" "shadowquic_up" ""
   config_get "shadowquic_down" "$section" "shadowquic_down" ""
   config_get "shadowquic_cwnd" "$section" "shadowquic_cwnd" ""
   config_get "shadowquic_bbr_profile" "$section" "shadowquic_bbr_profile" ""
   config_get "shadowquic_max_datagram_frame_size" "$section" "shadowquic_max_datagram_frame_size" ""
   config_get "shadowquic_max_open_streams" "$section" "shadowquic_max_open_streams" ""
   config_get "shadowquic_recv_window_conn" "$section" "shadowquic_recv_window_conn" ""
   config_get "shadowquic_recv_window" "$section" "shadowquic_recv_window" ""
   config_get "shadowquic_disable_mtu_discovery" "$section" "shadowquic_disable_mtu_discovery" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: shadowquic
    server: "$server"
    port: $port
    username: "$shadowquic_username"
    password: "$password"
EOF
    if [ -n "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ -n "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ -n "$alpn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
        config_list_foreach "$section" "alpn" set_alpn
    fi
    if [ -n "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ -n "$client_fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    client-fingerprint: "$client_fingerprint"
EOF
    fi
    # Advanced ShadowQUIC fields require both the global capability switch
    # and the per-node advanced switch.  Required credentials and common TLS
    # fields above remain available for every enabled ShadowQUIC node.
    if [ "$FEATURE_SHADOWQUIC" = "1" ] && [ "$shadowquic_advanced" = "1" ]; then
      if [ "$FEATURE_H2C" = "1" ] && [ -n "$shadowquic_quic_versions" ]; then
cat >> "$SERVER_FILE" <<-EOF
    quic-versions:
EOF
        config_list_foreach "$section" "shadowquic_quic_versions" set_alpn
      fi
    if [ -n "$shadowquic_udp_over_stream" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp-over-stream: $shadowquic_udp_over_stream
EOF
    fi
    if [ -n "$shadowquic_zero_rtt" ]; then
cat >> "$SERVER_FILE" <<-EOF
    zero-rtt: $shadowquic_zero_rtt
EOF
    fi
    if [ -n "$shadowquic_keep_alive_interval" ]; then
cat >> "$SERVER_FILE" <<-EOF
    keep-alive-interval: $shadowquic_keep_alive_interval
EOF
    fi
    if [ -n "$shadowquic_congestion_controller" ]; then
cat >> "$SERVER_FILE" <<-EOF
    congestion-controller: $shadowquic_congestion_controller
EOF
    fi
    if [ -n "$shadowquic_up" ]; then
cat >> "$SERVER_FILE" <<-EOF
    up: "$shadowquic_up"
EOF
    fi
    if [ -n "$shadowquic_down" ]; then
cat >> "$SERVER_FILE" <<-EOF
    down: "$shadowquic_down"
EOF
    fi
    if [ -n "$shadowquic_cwnd" ]; then
cat >> "$SERVER_FILE" <<-EOF
    cwnd: $shadowquic_cwnd
EOF
    fi
    if [ -n "$shadowquic_bbr_profile" ] && [ "$shadowquic_congestion_controller" = "bbr" ]; then
cat >> "$SERVER_FILE" <<-EOF
    bbr-profile: "$shadowquic_bbr_profile"
EOF
    fi
    if [ -n "$shadowquic_max_datagram_frame_size" ]; then
cat >> "$SERVER_FILE" <<-EOF
    max-datagram-frame-size: $shadowquic_max_datagram_frame_size
EOF
    fi
    if [ -n "$shadowquic_max_open_streams" ]; then
cat >> "$SERVER_FILE" <<-EOF
    max-open-streams: $shadowquic_max_open_streams
EOF
    fi
    if [ -n "$shadowquic_recv_window_conn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    recv-window-conn: $shadowquic_recv_window_conn
EOF
    fi
    if [ -n "$shadowquic_recv_window" ]; then
cat >> "$SERVER_FILE" <<-EOF
    recv-window: $shadowquic_recv_window
EOF
    fi
    if [ -n "$shadowquic_disable_mtu_discovery" ]; then
cat >> "$SERVER_FILE" <<-EOF
    disable-mtu-discovery: $shadowquic_disable_mtu_discovery
EOF
    fi
    fi
fi

#vless
if [ "$type" = "vless" ]; then
   config_get "uuid" "$section" "uuid" ""
   config_get "xudp" "$section" "xudp" ""
   config_get "packet_addr" "$section" "packet_addr" ""
   config_get "packet_encoding" "$section" "packet_encoding" ""
   config_get "servername" "$section" "servername" ""
   config_get "obfs_vless" "$section" "obfs_vless" ""
   config_get "ws_opts_path" "$section" "ws_opts_path" ""
   config_get "ws_opts_headers" "$section" "ws_opts_headers" ""
   config_get "grpc_service_name" "$section" "grpc_service_name" ""
   config_get "reality_public_key" "$section" "reality_public_key" ""
   config_get "reality_short_id" "$section" "reality_short_id" ""
   config_get "vless_flow" "$section" "vless_flow" ""
   config_get "xhttp_opts_path" "$section" "xhttp_opts_path" ""
   config_get "xhttp_opts_host" "$section" "xhttp_opts_host" ""
   config_get "vless_encryption" "$section" "vless_encryption" ""

   if [ "$obfs_vless" = "ws" ]; then
      obfs_vless="network: ws"
   fi
   if [ "$obfs_vless" = "grpc" ]; then
      obfs_vless="network: grpc"
   fi
   if [ "$obfs_vless" = "tcp" ]; then
      obfs_vless="network: tcp"
   fi
   if [ "$obfs_vless" = "xhttp" ]; then
      obfs_vless="network: xhttp"
   fi

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    uuid: $uuid
EOF
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ ! -z "$xudp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    xudp: $xudp
EOF
    fi
    if [ ! -z "$packet_addr" ]; then
cat >> "$SERVER_FILE" <<-EOF
    packet-addr: $packet_addr
EOF
    fi
    if [ ! -z "$packet_encoding" ]; then
cat >> "$SERVER_FILE" <<-EOF
    packet-encoding: "$packet_encoding"
EOF
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ ! -z "$tls" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tls: $tls
EOF
    fi
    if [ ! -z "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fingerprint: "$fingerprint"
EOF
    fi
    if [ ! -z "$client_fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    client-fingerprint: "$client_fingerprint"
EOF
    fi
    if [ ! -z "$servername" ]; then
cat >> "$SERVER_FILE" <<-EOF
    servername: "$servername"
EOF
    fi
    if [ -n "$obfs_vless" ]; then
cat >> "$SERVER_FILE" <<-EOF
    $obfs_vless
EOF
        if [ "$obfs_vless" = "network: ws" ]; then
            if [ -n "$ws_opts_path" ] || [ -n "$ws_opts_headers" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ws-opts:
EOF
                if [ -n "$ws_opts_path" ]; then
cat >> "$SERVER_FILE" <<-EOF
      path: "$ws_opts_path"
EOF
                fi
                if [ -n "$ws_opts_headers" ]; then
cat >> "$SERVER_FILE" <<-EOF
      headers:
EOF
                  config_list_foreach "$section" "ws_opts_headers" set_ws_headers
                fi
            fi
        fi
        if [ ! -z "$grpc_service_name" ] && [ "$obfs_vless" = "network: grpc" ]; then
cat >> "$SERVER_FILE" <<-EOF
    grpc-opts:
      grpc-service-name: "$grpc_service_name"
EOF
            if [ -n "$reality_public_key" ] || [ -n "$reality_short_id" ]; then
cat >> "$SERVER_FILE" <<-EOF
    reality-opts:
EOF
            fi
            if [ -n "$reality_public_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
      public-key: "$reality_public_key"
EOF
            fi
            if [ -n "$reality_short_id" ]; then
cat >> "$SERVER_FILE" <<-EOF
      short-id: "$reality_short_id"
EOF
            fi
        fi
        if [ "$obfs_vless" = "network: tcp" ]; then
            if [ ! -z "$vless_flow" ]; then
cat >> "$SERVER_FILE" <<-EOF
    flow: "$vless_flow"
EOF
            fi
            if [ -n "$vless_encryption" ]; then
cat >> "$SERVER_FILE" <<-EOF
      encryption: "$vless_encryption"
EOF
            fi
            if [ -n "$reality_public_key" ] || [ -n "$reality_short_id" ]; then
cat >> "$SERVER_FILE" <<-EOF
    reality-opts:
EOF
            fi
            if [ -n "$reality_public_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
      public-key: "$reality_public_key"
EOF
            fi
            if [ -n "$reality_short_id" ]; then
cat >> "$SERVER_FILE" <<-EOF
      short-id: "$reality_short_id"
EOF
            fi
        fi
        if [ "$obfs_vless" = "network: xhttp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    xhttp-opts:
EOF
            if [ -n "$xhttp_opts_path" ]; then
cat >> "$SERVER_FILE" <<-EOF
      path: "$xhttp_opts_path"
EOF
            fi
            if [ -n "$xhttp_opts_host" ]; then
cat >> "$SERVER_FILE" <<-EOF
      host: "$xhttp_opts_host"
EOF
            fi
        fi
    fi
fi

#dns
if [ "$type" = "dns" ]; then
cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
EOF
fi

#direct
if [ "$type" = "direct" ]; then
cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
EOF
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
fi

#ssh
if [ "$type" = "ssh" ]; then
   config_get "auth_name" "$section" "auth_name" ""
   config_get "auth_pass" "$section" "auth_pass" ""
   config_get "private_key" "$section" "private_key" ""
   config_get "private_key_passphrase" "$section" "private_key_passphrase" ""
   config_get "host_key" "$section" "host_key" ""
   config_get "host_key_algorithms" "$section" "host_key_algorithms" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ ! -z "$auth_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
    username: "$auth_name"
EOF
    fi
    if [ ! -z "$auth_pass" ]; then
cat >> "$SERVER_FILE" <<-EOF
    password: "$auth_pass"
EOF
    fi
    if [ ! -z "$private_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    private-key: "$private_key"
EOF
    fi
    if [ ! -z "$private_key_passphrase" ]; then
cat >> "$SERVER_FILE" <<-EOF
    private-key-passphrase: "$private_key_passphrase"
EOF
    fi
    if [ ! -z "$host_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    host-key:
EOF
        config_list_foreach "$section" "host_key" set_alpn
    fi
    if [ ! -z "$host_key_algorithms" ]; then
cat >> "$SERVER_FILE" <<-EOF
    host-key-algorithms:
EOF
        config_list_foreach "$section" "host_key_algorithms" set_alpn
    fi
fi

#socks5
if [ "$type" = "socks5" ]; then
   config_get "auth_name" "$section" "auth_name" ""
   config_get "auth_pass" "$section" "auth_pass" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ ! -z "$auth_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
    username: "$auth_name"
EOF
    fi
    if [ ! -z "$auth_pass" ]; then
cat >> "$SERVER_FILE" <<-EOF
    password: "$auth_pass"
EOF
    fi
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ ! -z "$tls" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tls: $tls
EOF
    fi
    if [ ! -z "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    fingerprint: "$fingerprint"
EOF
    fi
fi

#http
if [ "$type" = "http" ]; then
   config_get "auth_name" "$section" "auth_name" ""
   config_get "auth_pass" "$section" "auth_pass" ""
   config_get "http_headers" "$section" "http_headers" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ ! -z "$auth_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
    username: "$auth_name"
EOF
    fi
    if [ ! -z "$auth_pass" ]; then
cat >> "$SERVER_FILE" <<-EOF
    password: "$auth_pass"
EOF
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ ! -z "$tls" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tls: $tls
EOF
    fi
    if [ ! -z "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ -n "$http_headers" ]; then
cat >> "$SERVER_FILE" <<-EOF
    headers:
EOF
      config_list_foreach "$section" "http_headers" set_ws_headers
    fi
fi

#trojan
if [ "$type" = "trojan" ]; then
   config_get "grpc_service_name" "$section" "grpc_service_name" ""
   config_get "obfs_trojan" "$section" "obfs_trojan" ""
   config_get "trojan_ws_path" "$section" "trojan_ws_path" ""
   config_get "trojan_ws_headers" "$section" "trojan_ws_headers" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    password: "$password"
EOF
    if [ ! -z "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ ! -z "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ ! -z "$alpn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
        config_list_foreach "$section" "alpn" set_alpn
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
    if [ ! -z "$fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
  fingerprint: "$fingerprint"
EOF
    fi
    if [ ! -z "$client_fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
  client-fingerprint: "$client_fingerprint"
EOF
    fi
    if [ ! -z "$grpc_service_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
    network: grpc
    grpc-opts:
      grpc-service-name: "$grpc_service_name"
EOF
    fi
    if [ "$obfs_trojan" = "ws" ]; then
        if [ -n "$trojan_ws_path" ] || [ -n "$trojan_ws_headers" ]; then
cat >> "$SERVER_FILE" <<-EOF
    network: ws
    ws-opts:
EOF
        fi
        if [ -n "$trojan_ws_path" ]; then
cat >> "$SERVER_FILE" <<-EOF
      path: "$trojan_ws_path"
EOF
        fi
        if [ -n "$trojan_ws_headers" ]; then
cat >> "$SERVER_FILE" <<-EOF
      headers:
EOF
         config_list_foreach "$section" "trojan_ws_headers" set_ws_headers
        fi
    fi
fi

#snell
if [ "$type" = "snell" ]; then
   config_get "psk" "$section" "psk" ""
   config_get "snell_version" "$section" "snell_version" ""
   config_get "obfs_snell" "$section" "obfs_snell" ""
   config_get "host" "$section" "host" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
    psk: $psk
EOF
    if [ -n "$snell_version" ]; then
cat >> "$SERVER_FILE" <<-EOF
    version: "$snell_version"
EOF
    fi
    if [ "$obfs_snell" != "none" ] && [ ! -z "$host" ]; then
cat >> "$SERVER_FILE" <<-EOF
    obfs-opts:
      mode: $obfs_snell
      host: "$host"
EOF
    fi
fi

#Sudoku
if [ "$type" = "sudoku" ]; then
   config_get "sudoku_key" "$section" "sudoku_key" ""
   config_get "aead_method" "$section" "aead_method" "none"
   config_get "padding_min" "$section" "padding_min" ""
   config_get "padding_max" "$section" "padding_max" ""
   config_get "table_type" "$section" "table_type" "prefer_ascii"
   config_get "http_mask" "$section" "http_mask" "true"

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$sudoku_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    key: "$sudoku_key"
EOF
    fi
    if [ -n "$aead_method" ]; then
cat >> "$SERVER_FILE" <<-EOF
    aead-method: $aead_method
EOF
    fi
    if [ -n "$padding_min" ]; then
cat >> "$SERVER_FILE" <<-EOF
    padding-min: $padding_min
EOF
    fi
    if [ -n "$padding_max" ]; then
cat >> "$SERVER_FILE" <<-EOF
    padding-max: $padding_max
EOF
    fi
    if [ -n "$table_type" ]; then
cat >> "$SERVER_FILE" <<-EOF
    table-type: $table_type
EOF
    fi
    if [ -n "$http_mask" ]; then
cat >> "$SERVER_FILE" <<-EOF
    http-mask: $http_mask
EOF
    fi
fi

#MASQUE
if [ "$type" = "masque" ]; then
   config_get "masque_private_key" "$section" "masque_private_key" ""
   config_get "masque_public_key" "$section" "masque_public_key" ""
   config_get "masque_ip" "$section" "masque_ip" ""
   config_get "masque_ipv6" "$section" "masque_ipv6" ""
   config_get "masque_mtu" "$section" "masque_mtu" ""
   config_get "masque_remote_dns_resolve" "$section" "masque_remote_dns_resolve" ""
   config_get "masque_dns" "$section" "masque_dns" ""
   config_get "masque_advanced" "$section" "masque_advanced" ""
   config_get "masque_ip_stack_mode" "$section" "masque_ip_stack_mode" ""
   config_get "masque_ip_stack_congestion_controller" "$section" "masque_ip_stack_congestion_controller" ""
   config_get "masque_congestion_controller" "$section" "masque_congestion_controller" ""
   config_get "masque_network" "$section" "masque_network" ""
   config_get "masque_handshake_timeout" "$section" "masque_handshake_timeout" ""
   config_get "masque_bbr_profile" "$section" "masque_bbr_profile" ""
   case "$masque_network" in
      ""|quic|h2|h3-l4proxy) ;;
      *) masque_network="" ;;
   esac
   masque_udp="$udp"
   if [ "$masque_network" = "h3-l4proxy" ]; then
      # Mihomo's h3-l4proxy transport currently does not support UDP.
      masque_udp="false"
   fi

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$masque_private_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    private-key: "$masque_private_key"
EOF
    fi
    if [ -n "$masque_public_key" ]; then
cat >> "$SERVER_FILE" <<-EOF
    public-key: "$masque_public_key"
EOF
    fi
    if [ -n "$masque_ip" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ip: "$masque_ip"
EOF
    fi
    if [ -n "$masque_ipv6" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ipv6: "$masque_ipv6"
EOF
    fi
    if [ -n "$masque_mtu" ]; then
cat >> "$SERVER_FILE" <<-EOF
    mtu: $masque_mtu
EOF
    fi
    if [ -n "$masque_remote_dns_resolve" ]; then
cat >> "$SERVER_FILE" <<-EOF
    remote-dns-resolve: $masque_remote_dns_resolve
EOF
    fi
    masque_emit_ip_stack=0
    if [ -n "$masque_ip_stack_mode" ]; then
        masque_emit_ip_stack=1
    elif [ -n "$masque_ip_stack_congestion_controller" ] && { [ "$masque_ip_stack_congestion_controller" != "bbr3" ] || [ "$FEATURE_BBR3" = "1" ]; }; then
        masque_emit_ip_stack=1
    fi
    if [ "$FEATURE_MASQUE" = "1" ] && [ "$masque_advanced" = "1" ]; then
        if [ "$masque_emit_ip_stack" = "1" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ip-stack:
EOF
            if [ -n "$masque_ip_stack_mode" ]; then
cat >> "$SERVER_FILE" <<-EOF
      mode: $masque_ip_stack_mode
EOF
            fi
            if [ -n "$masque_ip_stack_congestion_controller" ]; then
                if [ "$masque_ip_stack_congestion_controller" != "bbr3" ] || [ "$FEATURE_BBR3" = "1" ]; then
cat >> "$SERVER_FILE" <<-EOF
      congestion-controller: $masque_ip_stack_congestion_controller
EOF
                fi
            fi
        fi
        if [ -n "$masque_network" ] && [ "$masque_network" != "quic" ]; then
cat >> "$SERVER_FILE" <<-EOF
    network: $masque_network
EOF
        fi
        if [ -n "$masque_congestion_controller" ]; then
cat >> "$SERVER_FILE" <<-EOF
    congestion-controller: $masque_congestion_controller
EOF
        fi
        if [ -n "$masque_bbr_profile" ] && [ "$masque_congestion_controller" = "bbr" ]; then
cat >> "$SERVER_FILE" <<-EOF
    bbr-profile: "$masque_bbr_profile"
EOF
        fi
        if [ -n "$masque_handshake_timeout" ]; then
cat >> "$SERVER_FILE" <<-EOF
    handshake-timeout: $masque_handshake_timeout
EOF
        fi
    fi
    if [ ! -z "$masque_udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $masque_udp
EOF
   fi
   if [ ! -z "$masque_dns" ]; then
cat >> "$SERVER_FILE" <<-EOF
    dns:
EOF
        config_list_foreach "$section" "masque_dns" set_alpn
    fi
fi

#ZeroTier (Mihomo built-in overlay node)
if [ "$type" = "zerotier" ]; then
   [ "$FEATURE_ZEROTIER" = "1" ] || return
   config_get "zerotier_network" "$section" "zerotier_network" ""
   config_get "zerotier_advanced" "$section" "zerotier_advanced" ""
   config_get "zerotier_state_dir" "$section" "zerotier_state_dir" ""
   config_get "zerotier_planet" "$section" "zerotier_planet" ""
   config_get "zerotier_mtu" "$section" "zerotier_mtu" ""
   config_get "zerotier_physical_mtu" "$section" "zerotier_physical_mtu" ""
   config_get "zerotier_ip_stack_mode" "$section" "zerotier_ip_stack_mode" ""
   config_get "zerotier_ip_stack_congestion_controller" "$section" "zerotier_ip_stack_congestion_controller" ""
   config_get "zerotier_primary_port" "$section" "zerotier_primary_port" ""
   config_get "zerotier_secondary_port" "$section" "zerotier_secondary_port" ""
   config_get "zerotier_tcp_fallback_mode" "$section" "zerotier_tcp_fallback_mode" ""
   config_get "zerotier_tcp_fallback_relay" "$section" "zerotier_tcp_fallback_relay" ""
   config_get "zerotier_remote_trace_target" "$section" "zerotier_remote_trace_target" ""
   config_get "zerotier_remote_trace_level" "$section" "zerotier_remote_trace_level" ""
   config_get "zerotier_low_bandwidth" "$section" "zerotier_low_bandwidth" ""
   config_get "zerotier_encrypted_hello" "$section" "zerotier_encrypted_hello" ""
   config_get "zerotier_orbit" "$section" "zerotier_orbit" ""
   config_get "zerotier_remote_dns_resolve" "$section" "zerotier_remote_dns_resolve" ""
   config_get "zerotier_dns" "$section" "zerotier_dns" ""

   # Mihomo requires a 16-character hexadecimal network id.  A malformed
   # section is ignored so one optional node cannot invalidate all proxies.
   if ! printf '%s\n' "$zerotier_network" | grep -Eq '^[0-9a-fA-F]{16}$'; then
      return
   fi

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: zerotier
    network: "$zerotier_network"
EOF
   if [ -n "$zerotier_state_dir" ]; then
cat >> "$SERVER_FILE" <<-EOF
    state-dir: "$zerotier_state_dir"
EOF
   fi
   if [ -n "$zerotier_planet" ]; then
cat >> "$SERVER_FILE" <<-EOF
    planet: "$zerotier_planet"
EOF
   fi
   if [ -n "$zerotier_mtu" ]; then
cat >> "$SERVER_FILE" <<-EOF
    mtu: $zerotier_mtu
EOF
   fi
   if [ -n "$zerotier_physical_mtu" ]; then
cat >> "$SERVER_FILE" <<-EOF
    physical-mtu: $zerotier_physical_mtu
EOF
   fi

   zerotier_emit_ip_stack=0
   if [ -n "$zerotier_ip_stack_mode" ]; then
      zerotier_emit_ip_stack=1
   elif [ -n "$zerotier_ip_stack_congestion_controller" ] && { [ "$zerotier_ip_stack_congestion_controller" != "bbr3" ] || [ "$FEATURE_BBR3" = "1" ]; }; then
      zerotier_emit_ip_stack=1
   fi
   if [ "$zerotier_emit_ip_stack" = "1" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ip-stack:
EOF
      if [ -n "$zerotier_ip_stack_mode" ]; then
cat >> "$SERVER_FILE" <<-EOF
      mode: $zerotier_ip_stack_mode
EOF
      fi
      if [ -n "$zerotier_ip_stack_congestion_controller" ] && { [ "$zerotier_ip_stack_congestion_controller" != "bbr3" ] || [ "$FEATURE_BBR3" = "1" ]; }; then
cat >> "$SERVER_FILE" <<-EOF
      congestion-controller: $zerotier_ip_stack_congestion_controller
EOF
      fi
   fi
   if [ "$zerotier_advanced" = "1" ]; then
      if [ -n "$zerotier_primary_port" ]; then
cat >> "$SERVER_FILE" <<-EOF
    primary-port: $zerotier_primary_port
EOF
      fi
      if [ -n "$zerotier_secondary_port" ]; then
cat >> "$SERVER_FILE" <<-EOF
    secondary-port: $zerotier_secondary_port
EOF
      fi
      if [ -n "$zerotier_tcp_fallback_mode" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tcp-fallback-mode: $zerotier_tcp_fallback_mode
EOF
      fi
      if [ -n "$zerotier_tcp_fallback_relay" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tcp-fallback-relay: "$zerotier_tcp_fallback_relay"
EOF
      fi
      if [ -n "$zerotier_remote_trace_target" ]; then
cat >> "$SERVER_FILE" <<-EOF
    remote-trace-target: "$zerotier_remote_trace_target"
EOF
      fi
      if [ -n "$zerotier_remote_trace_level" ]; then
cat >> "$SERVER_FILE" <<-EOF
    remote-trace-level: $zerotier_remote_trace_level
EOF
      fi
      if [ -n "$zerotier_low_bandwidth" ]; then
cat >> "$SERVER_FILE" <<-EOF
    low-bandwidth: $zerotier_low_bandwidth
EOF
      fi
      if [ -n "$zerotier_encrypted_hello" ]; then
cat >> "$SERVER_FILE" <<-EOF
    encrypted-hello: $zerotier_encrypted_hello
EOF
      fi
      if [ -n "$zerotier_orbit" ]; then
cat >> "$SERVER_FILE" <<-EOF
    orbit:
EOF
         config_list_foreach "$section" "zerotier_orbit" set_zerotier_orbit
      fi
   fi
   if [ -n "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
   fi
   if [ -n "$zerotier_remote_dns_resolve" ]; then
cat >> "$SERVER_FILE" <<-EOF
    remote-dns-resolve: $zerotier_remote_dns_resolve
EOF
   fi
   if [ -n "$zerotier_dns" ]; then
cat >> "$SERVER_FILE" <<-EOF
    dns:
EOF
      config_list_foreach "$section" "zerotier_dns" set_alpn
   fi
fi

#TrustTunnel
if [ "$type" = "trusttunnel" ]; then
   config_get "trusttunnel_username" "$section" "trusttunnel_username" ""
   config_get "trusttunnel_password" "$section" "trusttunnel_password" ""
   config_get "trusttunnel_health_check" "$section" "trusttunnel_health_check" ""
   config_get "trusttunnel_quic" "$section" "trusttunnel_quic" ""
   config_get "trusttunnel_congestion_controller" "$section" "trusttunnel_congestion_controller" ""

cat >> "$SERVER_FILE" <<-EOF
  - name: "$name"
    type: $type
    server: "$server"
    port: $port
EOF
    if [ -n "$trusttunnel_username" ]; then
cat >> "$SERVER_FILE" <<-EOF
    username: "$trusttunnel_username"
EOF
    fi
    if [ -n "$trusttunnel_password" ]; then
cat >> "$SERVER_FILE" <<-EOF
    password: "$trusttunnel_password"
EOF
    fi
    if [ -n "$trusttunnel_health_check" ]; then
cat >> "$SERVER_FILE" <<-EOF
    health-check: $trusttunnel_health_check
EOF
    fi
    if [ -n "$trusttunnel_quic" ]; then
cat >> "$SERVER_FILE" <<-EOF
    quic: $trusttunnel_quic
EOF
    fi
    if [ -n "$trusttunnel_congestion_controller" ]; then
cat >> "$SERVER_FILE" <<-EOF
    congestion-controller: "$trusttunnel_congestion_controller"
EOF
    fi
    if [ -n "$client_fingerprint" ]; then
cat >> "$SERVER_FILE" <<-EOF
    client-fingerprint: "$client_fingerprint"
EOF
    fi
    if [ -n "$udp" ]; then
cat >> "$SERVER_FILE" <<-EOF
    udp: $udp
EOF
    fi
    if [ -n "$sni" ]; then
cat >> "$SERVER_FILE" <<-EOF
    sni: "$sni"
EOF
    fi
    if [ ! -z "$alpn" ]; then
cat >> "$SERVER_FILE" <<-EOF
    alpn:
EOF
        config_list_foreach "$section" "alpn" set_alpn
    fi
    if [ ! -z "$skip_cert_verify" ]; then
cat >> "$SERVER_FILE" <<-EOF
    skip-cert-verify: $skip_cert_verify
EOF
    fi
fi

#ip_version
if [ ! -z "$ip_version" ]; then
cat >> "$SERVER_FILE" <<-EOF
    ip-version: "$ip_version"
EOF
fi

#TFO
if [ ! -z "$tfo" ]; then
cat >> "$SERVER_FILE" <<-EOF
    tfo: $tfo
EOF
fi

#Multiplex
if [ ! -z "$multiplex" ]; then
cat >> "$SERVER_FILE" <<-EOF
    smux:
      enabled: $multiplex
EOF
    if [ -n "$multiplex_protocol" ]; then
cat >> "$SERVER_FILE" <<-EOF
      protocol: $multiplex_protocol
EOF
    fi
    if [ -n "$multiplex_max_connections" ]; then
cat >> "$SERVER_FILE" <<-EOF
      max-connections: $multiplex_max_connections
EOF
    fi
    if [ -n "$multiplex_min_streams" ]; then
cat >> "$SERVER_FILE" <<-EOF
      min-streams: $multiplex_min_streams
EOF
    fi
    if [ -n "$multiplex_max_streams" ]; then
cat >> "$SERVER_FILE" <<-EOF
      max-streams: $multiplex_max_streams
EOF
    fi
    if [ -n "$multiplex_padding" ]; then
cat >> "$SERVER_FILE" <<-EOF
      padding: $multiplex_padding
EOF
    fi
    if [ -n "$multiplex_statistic" ]; then
cat >> "$SERVER_FILE" <<-EOF
      statistic: $multiplex_statistic
EOF
    fi
    if [ -n "$multiplex_only_tcp" ]; then
cat >> "$SERVER_FILE" <<-EOF
      only-tcp: $multiplex_only_tcp
EOF
    fi
fi

#interface-name
if [ -n "$interface_name" ]; then
cat >> "$SERVER_FILE" <<-EOF
    interface-name: "$interface_name"
EOF
fi

#routing_mark
if [ -n "$routing_mark" ]; then
cat >> "$SERVER_FILE" <<-EOF
    routing-mark: "$routing_mark"
EOF
fi

#other_parameters
if [ -n "$other_parameters" ]; then
    echo -e "$other_parameters" >> "$SERVER_FILE"
fi

#dialer_proxy
if [ -n "$dialer_proxy" ]; then
cat >> "$SERVER_FILE" <<-EOF
    dialer-proxy: "$dialer_proxy"
EOF
fi
}

yml_servers_name_get()
{
	 local section="$1"
   local name
   config_get "name" "$section" "name" ""
   [ ! -z "$name" ] && {
      echo "$name" >>"$servers_name"
   }
}

yml_proxy_provider_name_get()
{
	 local section="$1"
   local name
   config_get "name" "$section" "name" ""
   [ ! -z "$name" ] && {
      echo "$name" >>"$proxy_provider_name"
   }
}

#创建配置文件
config_load "openkill"
config_foreach yml_servers_name_get "servers"
config_foreach yml_proxy_provider_name_get "proxy-provider"

#proxy-provider
LOG_OUT "Start Writing【$CONFIG_NAME】Proxy-providers Setting..."
echo "proxy-providers:" >$PROXY_PROVIDER_FILE
rm -rf /tmp/Proxy_Provider
config_foreach yml_proxy_provider_set "proxy-provider"
sed -i "s/^ \{0,\}/      - /" /tmp/Proxy_Provider 2>/dev/null #添加参数
if [ "$(grep "-" /tmp/Proxy_Provider 2>/dev/null |wc -l)" -eq 0 ]; then
   rm -rf $PROXY_PROVIDER_FILE
   rm -rf /tmp/Proxy_Provider
fi
rm -rf $proxy_provider_name

#proxy
LOG_OUT "Start Writing【$CONFIG_NAME】Proxies Setting..."
echo "proxies:" >$SERVER_FILE
config_foreach yml_servers_set "servers"
egrep '^ {0,}-' $SERVER_FILE |grep name: |awk -F 'name: ' '{print $2}' |sed 's/,.*//' 2>/dev/null >/tmp/Proxy_Server 2>&1
if [ -s "/tmp/Proxy_Server" ]; then
   sed -i "s/^ \{0,\}/      - /" /tmp/Proxy_Server 2>/dev/null #添加参数
else
   rm -rf $SERVER_FILE
   rm -rf /tmp/Proxy_Server
fi
rm -rf $servers_name


LOG_OUT "Proxies, Proxy-providers, Groups Edited Successful, Updating Config File【$CONFIG_NAME】..."
config_hash=$(ruby -ryaml -rYAML -I "/usr/share/openkill" -E UTF-8 -e "
begin
  Value = YAML.load_file('$CONFIG_FILE')
  {
    'proxies' => '$SERVER_FILE',
    'proxy-providers' => '$PROXY_PROVIDER_FILE',
    'proxy-groups' => '/tmp/yaml_groups.yaml'
  }.each do |key, src_file|
    begin
      if File.exist?(src_file)
        src = YAML.load_file(src_file)
        Value[key] = src[key]
      else
        Value.delete(key)
      end
    rescue Exception => e
      YAML.LOG_ERROR('Merge [' + key + '] Failed: ' + e.message)
    end
  end
  YAML.dump(Value, '$CONFIG_FILE')
  puts 'OK'
rescue Exception => e
  YAML.LOG_ERROR('Update Config File Failed: ' + e.message)
end
" 2>/dev/null)

if [ "$config_hash" != "OK" ]; then
    cat "$SERVER_FILE" "$PROXY_PROVIDER_FILE" "/tmp/yaml_groups.yaml" > "$CONFIG_FILE" 2>/dev/null
fi

rm -rf $SERVER_FILE 2>/dev/null
rm -rf $PROXY_PROVIDER_FILE 2>/dev/null
rm -rf /tmp/yaml_groups.yaml 2>/dev/null
rm -rf /tmp/Proxy_Server 2>/dev/null
rm -rf /tmp/Proxy_Provider 2>/dev/null

LOG_OUT "Config File【$CONFIG_NAME】Write Successful!"
del_lock
