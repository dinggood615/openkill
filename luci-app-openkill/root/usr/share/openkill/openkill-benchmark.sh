#!/bin/sh
# Read-only OpenKill diagnostics and benchmark helper.
# It never changes UCI, sysctl, nftables, routes, MTU, IRQ affinity,
# RPS/XPS, or flow-offload settings.

set -u
umask 077

LABEL="default"
IPERF_SERVER=""
IPERF_UDP=0
IPERF_UDP_RATE="10M"
IPERF_TIME=5
SHOW_PUBLIC_IP=0
JSON_PATH=""
REPORT_PATH=""

usage() {
    cat <<'EOF'
Usage: openkill-benchmark.sh [options]

Read-only OpenKill/OpenWrt diagnostics. No system configuration is changed.

  --label LABEL              Record before/after/direct/proxy label
  --iperf-server HOST        Run bounded IPv4/IPv6 iperf3 tests against HOST
  --udp                      Add explicitly requested UDP iperf3 tests
  --udp-rate RATE            UDP rate (default: 10M; requires --udp)
  --duration SECONDS         iperf3 duration per case (default: 5)
  --show-public-ip           Show interface addresses in the report
  --json PATH                Write machine-readable output to PATH
  --report PATH              Write the human-readable report to PATH
  -h, --help                 Show this help

No public speed-test server is selected automatically. A direct/proxy label
is recorded as supplied; interception is never guessed from local state.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --label)
            [ "$#" -ge 2 ] || { echo "--label requires a value" >&2; exit 2; }
            LABEL="$2"; shift 2 ;;
        --iperf-server)
            [ "$#" -ge 2 ] || { echo "--iperf-server requires a value" >&2; exit 2; }
            IPERF_SERVER="$2"; shift 2 ;;
        --udp) IPERF_UDP=1; shift ;;
        --udp-rate)
            [ "$#" -ge 2 ] || { echo "--udp-rate requires a value" >&2; exit 2; }
            IPERF_UDP_RATE="$2"; shift 2 ;;
        --duration)
            [ "$#" -ge 2 ] || { echo "--duration requires a value" >&2; exit 2; }
            IPERF_TIME="$2"; shift 2 ;;
        --show-public-ip) SHOW_PUBLIC_IP=1; shift ;;
        --json)
            [ "$#" -ge 2 ] || { echo "--json requires a path" >&2; exit 2; }
            JSON_PATH="$2"; shift 2 ;;
        --report)
            [ "$#" -ge 2 ] || { echo "--report requires a path" >&2; exit 2; }
            REPORT_PATH="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$IPERF_TIME" in
    ''|*[!0-9]*) echo "--duration must be a non-negative integer" >&2; exit 2 ;;
esac

have() { command -v "$1" >/dev/null 2>&1; }
uci_get() { uci -q get "$1" 2>/dev/null || true; }

run_bounded() {
    # Prefer BusyBox timeout. The fallback keeps probes bounded on minimal
    # systems that do not ship that applet.
    seconds="$1"; shift
    if have timeout; then
        timeout "$seconds" "$@"
        return $?
    fi
    "$@" &
    bounded_pid=$!
    elapsed=0
    while kill -0 "$bounded_pid" 2>/dev/null; do
        [ "$elapsed" -ge "$seconds" ] && {
            kill "$bounded_pid" 2>/dev/null || true
            wait "$bounded_pid" 2>/dev/null || true
            return 124
        }
        sleep 1
        elapsed=$((elapsed + 1))
    done
    wait "$bounded_pid"
}

sanitize() {
    # Remove control characters and JSON delimiters from captured text.
    # BusyBox tr does not implement the POSIX [:print:] class reliably and
    # can delete ordinary ASCII characters.  sed handles the class correctly
    # on the OpenWrt ash/BusyBox combinations we support.
    printf '%s' "$1" | tr '\r\n\t' '   ' | sed 's/[^[:print:]]//g' | tr '"' "'" | tr '\\' '/'
}

json_value() {
    value=$(sanitize "$1")
    value=$(printf '%s' "$value" | sed 's/"/\\"/g')
    printf '"%s"' "$value"
}

timestamp=$(date '+%Y%m%d-%H%M%S' 2>/dev/null || echo unknown)
[ -n "$JSON_PATH" ] || JSON_PATH="/tmp/openkill-benchmark-$timestamp.json"
[ -n "$REPORT_PATH" ] || REPORT_PATH="/tmp/openkill-benchmark-$timestamp.txt"
: > "$REPORT_PATH" 2>/dev/null || REPORT_PATH=""
emit() {
    printf '%s\n' "$1"
    [ -n "$REPORT_PATH" ] && printf '%s\n' "$1" >> "$REPORT_PATH"
}

openwrt_version="N/A"
if [ -r /etc/openwrt_release ]; then
    openwrt_version=$(sed -n "s/^DISTRIB_RELEASE='\([^']*\)'.*/\1/p" /etc/openwrt_release | head -n 1)
    [ -n "$openwrt_version" ] || openwrt_version=$(sed -n 's/^DISTRIB_RELEASE="\([^"]*\)".*/\1/p' /etc/openwrt_release | head -n 1)
fi
[ -n "$openwrt_version" ] || openwrt_version="N/A"
kernel_version=$(uname -r 2>/dev/null || echo N/A)
architecture=$(uname -m 2>/dev/null || echo N/A)
cpu_model=$(awk -F: '/^(model name|Model|machine|Processor)/ {gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null)
[ -n "$cpu_model" ] || cpu_model="N/A"
cpu_cores=$(awk '/^processor[ \t]*:/ {n++} END {print n+0}' /proc/cpuinfo 2>/dev/null)
[ "$cpu_cores" -gt 0 ] 2>/dev/null || cpu_cores=1
cpu_frequency=$(awk -F: '/^(cpu MHz|clock)/ {gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null)
[ -n "$cpu_frequency" ] || cpu_frequency="N/A"

core_path=""
for candidate in /etc/openkill/clash /etc/openkill/core/clash_meta /tmp/etc/openkill/core/clash_meta /usr/bin/mihomo /usr/bin/clash; do
    if [ -x "$candidate" ]; then core_path="$candidate"; break; fi
done
mihomo_version="N/A"
if [ -n "$core_path" ]; then
    mihomo_version=$($core_path -v 2>/dev/null | head -n 1 | tr -cd '[:alnum:]._+-')
    [ -n "$mihomo_version" ] || mihomo_version="N/A"
fi
openkill_version="N/A"
if have opkg; then
    openkill_version=$(opkg status luci-app-openkill 2>/dev/null | sed -n 's/^Version:[[:space:]]*//p' | head -n 1)
fi
if [ -z "$openkill_version" ] && have apk; then
    openkill_version=$(apk list -I luci-app-openkill 2>/dev/null | sed -n 's/^luci-app-openkill-\([^ ]*\).*/\1/p' | head -n 1)
fi
[ -n "$openkill_version" ] || openkill_version="N/A"

ubus_device() {
    if have ubus; then
        ubus call "network.interface.$1" status 2>/dev/null |
            sed -n 's/.*"\(l3_device\|device\)":"\([^"]*\)".*/\2/p' | head -n 1
    fi
}

lan_interface=$(uci_get network.lan.device)
[ -n "$lan_interface" ] || lan_interface=$(uci_get network.lan.ifname)
case "$lan_interface" in @*) lan_interface=$(ubus_device lan) ;; esac
[ -n "$lan_interface" ] || lan_interface=$(ubus_device lan)
[ -n "$lan_interface" ] || lan_interface="N/A"

wan_interface=$(uci_get network.wan.device)
[ -n "$wan_interface" ] || wan_interface=$(uci_get network.wan.ifname)
case "$wan_interface" in @*) wan_interface=$(ubus_device wan) ;; esac
[ -n "$wan_interface" ] || wan_interface=$(ubus_device wan)
if [ -z "$wan_interface" ] && have ip; then
    wan_interface=$(ip -4 route show default 2>/dev/null |
        awk 'NR==1 {for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')
fi
if [ -z "$wan_interface" ] && have ip; then
    wan_interface=$(ip -6 route show default 2>/dev/null |
        awk 'NR==1 {for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')
fi
[ -n "$wan_interface" ] || wan_interface="N/A"

wan_ipv4_raw=""
wan_ipv6_raw=""
if [ "$wan_interface" != "N/A" ] && have ip; then
    wan_ipv4_raw=$(ip -4 -o addr show dev "$wan_interface" scope global 2>/dev/null |
        awk 'NR==1 {print $4; exit}')
    wan_ipv6_raw=$(ip -6 -o addr show dev "$wan_interface" scope global 2>/dev/null |
        awk 'NR==1 {print $4; exit}')
fi
if [ "$SHOW_PUBLIC_IP" -eq 1 ]; then
    wan_ipv4=${wan_ipv4_raw:-unavailable}
    wan_ipv6=${wan_ipv6_raw:-unavailable}
else
    [ -n "$wan_ipv4_raw" ] && wan_ipv4="available" || wan_ipv4="unavailable"
    [ -n "$wan_ipv6_raw" ] && wan_ipv6="available" || wan_ipv6="unavailable"
fi

route_summary() {
    family="$1"
    if ! have ip; then printf 'N/A'; return; fi
    if [ "$family" = 6 ]; then
        routes=$(ip -6 route show default 2>/dev/null)
    else
        routes=$(ip -4 route show default 2>/dev/null)
    fi
    # Deliberately omit gateway addresses from the default report.
    printf '%s\n' "$routes" | awk '
        NR==1 {for (i=1; i<=NF; i++) {if ($i=="dev") dev=$(i+1); if ($i=="metric") metric=$(i+1)}}
        END {if (dev!="") {printf "dev=%s", dev; if (metric!="") printf " metric=%s", metric} else printf "absent"}'
}

default_ipv4_route=$(route_summary 4)
default_ipv6_route=$(route_summary 6)
wan_mtu="N/A"
if [ "$wan_interface" != "N/A" ] && have ip; then
    wan_mtu=$(ip link show dev "$wan_interface" 2>/dev/null |
        sed -n 's/.* mtu \([0-9][0-9]*\).*/\1/p' | head -n 1)
fi
[ -n "$wan_mtu" ] || wan_mtu="N/A"

mode=$(uci_get openkill.config.en_mode); [ -n "$mode" ] || mode="N/A"
ipv6_enabled=$(uci_get openkill.config.ipv6_enable); [ -n "$ipv6_enabled" ] || ipv6_enabled="N/A"
tun_stack=$(uci_get openkill.config.stack_type); [ -n "$tun_stack" ] || tun_stack="N/A"
ipv6_stack=$(uci_get openkill.config.stack_type_v6); [ -n "$ipv6_stack" ] || ipv6_stack="N/A"
case "$mode" in
    fake-ip*) dns_mode="fake-ip" ;;
    redir-host*) dns_mode="redir-host" ;;
    *) dns_mode="N/A" ;;
esac
sniffer=$(uci_get openkill.config.enable_meta_sniffer); [ -n "$sniffer" ] || sniffer="N/A"
tcp_concurrent=$(uci_get openkill.config.enable_tcp_concurrent); [ -n "$tcp_concurrent" ] || tcp_concurrent="N/A"
geodata_loader=$(uci_get openkill.config.geodata_loader); [ -n "$geodata_loader" ] || geodata_loader="N/A"

tun_devices="N/A"
if have ip; then
    tun_devices=$(ip -o link show 2>/dev/null |
        awk -F': ' '$2 ~ /(^|:)utun|(^|:)mihomo|(^|:)tun[0-9]*/ {sub(/@.*/, "", $2); print $2}' |
        tr '\n' ' ' | sed 's/[[:space:]]*$//')
    [ -n "$tun_devices" ] || tun_devices="none"
fi
table_354="absent"
if have ip; then
    if [ -n "$(ip route show table 354 2>/dev/null)" ] ||
       [ -n "$(ip -6 route show table 354 2>/dev/null)" ]; then
        table_354="present"
    fi
fi
rules_162="N/A"
if have ip; then
    rules_162=$(ip rule show 2>/dev/null |
        awk '/0x162|1888|lookup 354/ {print}' | tr '\n' '; ')
    [ -n "$rules_162" ] || rules_162="none"
fi

nft_summary="N/A"
nft_rule_count="N/A"
if have nft; then
    nft_summary=$(nft list table inet fw4 2>/dev/null |
        awk '/^[[:space:]]*(chain|set)[[:space:]]/ && ($0 ~ /openkill|mihomo|china_ip/) {print}
             /0x162|354/ {print}' | head -n 40 | tr '\n' '; ')
    [ -n "$nft_summary" ] || nft_summary="none"
    nft_rule_count=$(nft list table inet fw4 2>/dev/null |
        awk '/^[[:space:]]*chain[[:space:]]/ {chain=$2; sub(/\{/, "", chain)}
             chain ~ /openkill|mihomo/ && /counter/ {count++}
             END {print count+0}')
fi

cpu_snapshot() {
    awk '/^cpu[ \t]/ {print $2, $3, $4, $5, $6, $7, $8, $9, ($2+$3+$4+$5+$6+$7+$8+$9); exit}' /proc/stat 2>/dev/null
}
softirq_snapshot() {
    awk '/^NET_RX[ \t]/ {rx=$2} /^NET_TX[ \t]/ {tx=$2} END {print rx+0, tx+0}' /proc/softirqs 2>/dev/null
}
proc_ticks() {
    pid="$1"
    [ -r "/proc/$pid/stat" ] || { echo 0; return; }
    awk '{print $14+$15}' "/proc/$pid/stat" 2>/dev/null || echo 0
}

mihomo_pid=""
if have pidof; then
    mihomo_pid=$(pidof mihomo 2>/dev/null | awk '{print $1}')
    [ -n "$mihomo_pid" ] || mihomo_pid=$(pidof clash 2>/dev/null | awk '{print $1}')
fi
cpu_before=$(cpu_snapshot); cpu_after=""
softirq_before=$(softirq_snapshot); softirq_after=""
proc_before=0
[ -n "$mihomo_pid" ] && proc_before=$(proc_ticks "$mihomo_pid")
sleep 1
cpu_after=$(cpu_snapshot)
softirq_after=$(softirq_snapshot)
proc_after=0
[ -n "$mihomo_pid" ] && proc_after=$(proc_ticks "$mihomo_pid")

cpu_util=$(awk -v b="$cpu_before" -v a="$cpu_after" 'BEGIN {
    split(b,B," "); split(a,A," "); d=A[9]-B[9]
    if (d>0) printf "%.2f", ((A[9]-A[4])-(B[9]-B[4]))*100/d; else print "N/A"}')
softirq_delta=$(awk -v b="$softirq_before" -v a="$softirq_after" 'BEGIN {
    split(b,B," "); split(a,A," "); d=(A[1]+A[2])-(B[1]+B[2])
    if (d>=0) printf "%s", d; else print "N/A"}')
mihomo_cpu="N/A"
if [ -n "$mihomo_pid" ]; then
    mihomo_cpu=$(awk -v p1="$proc_before" -v p2="$proc_after" -v b="$cpu_before" -v a="$cpu_after" -v n="$cpu_cores" 'BEGIN {
        split(b,B," "); split(a,A," "); d=A[9]-B[9]
        if (d>0) printf "%.2f", (p2-p1)*100*n/d; else print "N/A"}')
fi
loadavg=$(cat /proc/loadavg 2>/dev/null | awk '{print $1 "," $2 "," $3}' || echo N/A)

mem_total=$(awk '/^MemTotal:/ {print $2 " " $3}' /proc/meminfo 2>/dev/null); [ -n "$mem_total" ] || mem_total="N/A"
mem_available=$(awk '/^MemAvailable:/ {print $2 " " $3}' /proc/meminfo 2>/dev/null); [ -n "$mem_available" ] || mem_available="N/A"
mem_cached=$(awk '/^Cached:/ {print $2 " " $3}' /proc/meminfo 2>/dev/null); [ -n "$mem_cached" ] || mem_cached="N/A"
swap_total=$(awk '/^SwapTotal:/ {print $2 " " $3}' /proc/meminfo 2>/dev/null); [ -n "$swap_total" ] || swap_total="N/A"
swap_free=$(awk '/^SwapFree:/ {print $2 " " $3}' /proc/meminfo 2>/dev/null); [ -n "$swap_free" ] || swap_free="N/A"
mihomo_rss="N/A"; mihomo_hwm="N/A"
if [ -n "$mihomo_pid" ] && [ -r "/proc/$mihomo_pid/status" ]; then
    mihomo_rss=$(sed -n 's/^VmRSS:[[:space:]]*//p' "/proc/$mihomo_pid/status" | head -n 1); [ -n "$mihomo_rss" ] || mihomo_rss="N/A"
    mihomo_hwm=$(sed -n 's/^VmHWM:[[:space:]]*//p' "/proc/$mihomo_pid/status" | head -n 1); [ -n "$mihomo_hwm" ] || mihomo_hwm="N/A"
fi

conntrack_count=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo N/A)
conntrack_max=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || echo N/A)
conntrack_util=$(awk -v c="$conntrack_count" -v m="$conntrack_max" 'BEGIN {if (m+0>0) printf "%.2f", c*100/m; else print "N/A"}')

flow_software=$(uci_get firewall.@defaults[0].flow_offloading); [ -n "$flow_software" ] || flow_software="N/A"
flow_hardware=$(uci_get firewall.@defaults[0].flow_offloading_hw); [ -n "$flow_hardware" ] || flow_hardware="N/A"
packet_steering=$(uci_get network.@globals[0].packet_steering); [ -n "$packet_steering" ] || packet_steering="N/A"
if [ "$packet_steering" = "N/A" ] && [ -x /etc/init.d/packet_steering ]; then
    /etc/init.d/packet_steering enabled >/dev/null 2>&1 && packet_steering="enabled" || packet_steering="disabled"
fi

rps_summary="N/A"
if [ -d /sys/class/net ]; then
    rps_summary=$(for f in /sys/class/net/*/queues/rx-*/rps_cpus; do
        [ -r "$f" ] || continue
        printf '%s=%s; ' "$f" "$(cat "$f" 2>/dev/null)"
    done | head -c 1200)
    [ -n "$rps_summary" ] || rps_summary="none"
fi
xps_summary="N/A"
if [ -d /sys/class/net ]; then
    xps_summary=$(for f in /sys/class/net/*/queues/tx-*/xps_cpus; do
        [ -r "$f" ] || continue
        printf '%s=%s; ' "$f" "$(cat "$f" 2>/dev/null)"
    done | head -c 1200)
    [ -n "$xps_summary" ] || xps_summary="none"
fi
irq_summary="N/A"
if [ -r /proc/interrupts ] && [ "$wan_interface" != "N/A" ]; then
    irq_summary=$(awk -v iface="$wan_interface" 'index($0, iface) {print}' /proc/interrupts |
        head -n 8 | tr '\n' '; ')
    [ -n "$irq_summary" ] || irq_summary="no matching WAN IRQ line"
fi

nic_offload="N/A"
if have ethtool && [ "$wan_interface" != "N/A" ]; then
    nic_offload=$(ethtool -k "$wan_interface" 2>/dev/null |
        awk '/^(gro|gso|tso|rx-checksumming|tx-checksumming):/ {print}' | tr '\n' '; ')
    [ -n "$nic_offload" ] || nic_offload="unavailable"
fi

tracepath4="not-installed"; tracepath6="not-installed"
have tracepath && tracepath4="available"
have tracepath6 && tracepath6="available"

probe_dns() {
    domain="$1"; query_type="$2"; nslookup_args=""
    [ "$query_type" = "aaaa" ] && nslookup_args="-type=AAAA"
    if ! have nslookup; then printf 'unavailable'; return; fi
    started=$(date +%s 2>/dev/null || echo 0)
    # BusyBox nslookup accepts the optional type flag used here.
    run_bounded 5 nslookup $nslookup_args "$domain" >/dev/null 2>&1
    status=$?
    ended=$(date +%s 2>/dev/null || echo "$started")
    elapsed=$((ended-started))
    [ "$status" -eq 0 ] && printf 'pass,%ss' "$elapsed" || printf 'fail,%ss' "$elapsed"
}

probe_https() {
    family="$1"; url="$2"
    if have curl; then
        curl_flag="-4"; [ "$family" = 6 ] && curl_flag="-6"
        curl "$curl_flag" -fsS --connect-timeout 5 --max-time 8 -o /dev/null "$url" >/dev/null 2>&1 && printf 'pass' || printf 'fail'
    elif have wget && [ "$family" = 4 ]; then
        wget -T 8 -O /dev/null "$url" >/dev/null 2>&1 && printf 'pass' || printf 'fail'
    else
        printf 'unavailable'
    fi
}

dns_cn=$(probe_dns www.baidu.com a)
dns_overseas=$(probe_dns example.com a)
dns_ipv6=$(probe_dns example.com aaaa)
https4_cn=$(probe_https 4 https://www.baidu.com)
https4_overseas=$(probe_https 4 https://example.com)
https6_overseas=$(probe_https 6 https://example.com)

iperf_results=""
iperf_json=""
iperf_add_result() {
    family="$1"; streams="$2"; protocol="$3"; status="$4"; summary="$5"
    result=$(printf '{"family":%s,"streams":%s,"protocol":%s,"status":%s,"summary":%s}' \
        "$(json_value "$family")" "$(json_value "$streams")" "$(json_value "$protocol")" "$(json_value "$status")" "$(json_value "$summary")")
    if [ -n "$iperf_json" ]; then iperf_json="$iperf_json,$result"; else iperf_json="$result"; fi
    iperf_results="$iperf_results; ${family}/${protocol}/${streams}streams=${status} ${summary}"
}

if [ -n "$IPERF_SERVER" ] && have iperf3; then
    for family in 4 6; do
        for streams in 1 4; do
            iperf_output=$(run_bounded $((IPERF_TIME + 10)) iperf3 -$family -c "$IPERF_SERVER" -P "$streams" -t "$IPERF_TIME" 2>&1)
            iperf_status=$?
            iperf_summary=$(printf '%s\n' "$iperf_output" | awk '/receiver|sender/ {if (line != "") line=line" | "; line=line$0} END {print line}')
            [ -n "$iperf_summary" ] || iperf_summary="no summary"
            [ "$iperf_status" -eq 0 ] && iperf_state="pass" || iperf_state="fail"
            iperf_add_result "$family" "$streams" tcp "$iperf_state" "$(sanitize "$iperf_summary")"
        done
    done
    if [ "$IPERF_UDP" -eq 1 ]; then
        for family in 4 6; do
            for streams in 1 4; do
                iperf_output=$(run_bounded $((IPERF_TIME + 10)) iperf3 -$family -c "$IPERF_SERVER" -u -b "$IPERF_UDP_RATE" -P "$streams" -t "$IPERF_TIME" 2>&1)
                iperf_status=$?
                iperf_summary=$(printf '%s\n' "$iperf_output" | awk '/receiver|sender/ {if (line != "") line=line" | "; line=line$0} END {print line}')
                [ -n "$iperf_summary" ] || iperf_summary="no summary"
                [ "$iperf_status" -eq 0 ] && iperf_state="pass" || iperf_state="fail"
                iperf_add_result "$family" "$streams" udp "$iperf_state" "$(sanitize "$iperf_summary")"
            done
        done
    fi
elif [ -n "$IPERF_SERVER" ]; then
    iperf_results="; iperf3 unavailable"
fi

emit "OpenKill benchmark label: $(sanitize "$LABEL")"
emit "Report: $REPORT_PATH"
emit "JSON: $JSON_PATH"
emit "Device: OpenWrt=$(sanitize "$openwrt_version") kernel=$(sanitize "$kernel_version") arch=$(sanitize "$architecture")"
emit "CPU: model=$(sanitize "$cpu_model") cores=$cpu_cores frequency=$(sanitize "$cpu_frequency")"
emit "Versions: OpenKill=$(sanitize "$openkill_version") Mihomo=$(sanitize "$mihomo_version")"
emit "Network: LAN=$(sanitize "$lan_interface") WAN=$(sanitize "$wan_interface") IPv4=$wan_ipv4 IPv6=$wan_ipv6 MTU=$wan_mtu"
emit "Routes: IPv4=$(sanitize "$default_ipv4_route") IPv6=$(sanitize "$default_ipv6_route")"
emit "OpenKill: mode=$(sanitize "$mode") ipv6=$ipv6_enabled tun-stack=$(sanitize "$tun_stack") ipv6-stack=$(sanitize "$ipv6_stack") dns=$(sanitize "$dns_mode") sniffer=$sniffer tcp-concurrent=$tcp_concurrent geodata=$(sanitize "$geodata_loader")"
emit "TUN: devices=$(sanitize "$tun_devices") table354=$table_354 rules=$(sanitize "$rules_162")"
emit "nftables: rule-count=$nft_rule_count matches=$(sanitize "$nft_summary")"
emit "CPU sample: utilization=${cpu_util}% softirq-delta=$softirq_delta mihomo=${mihomo_cpu}% load=$(sanitize "$loadavg")"
emit "Memory: total=$(sanitize "$mem_total") available=$(sanitize "$mem_available") cached=$(sanitize "$mem_cached") swap-total=$(sanitize "$swap_total") swap-free=$(sanitize "$swap_free") mihomo-rss=$(sanitize "$mihomo_rss") mihomo-hwm=$(sanitize "$mihomo_hwm")"
emit "Conntrack: count=$conntrack_count max=$conntrack_max utilization=${conntrack_util}%"
emit "Offload: software=$(sanitize "$flow_software") hardware=$(sanitize "$flow_hardware") packet-steering=$(sanitize "$packet_steering")"
emit "RPS/XPS: rps=$(sanitize "$rps_summary") xps=$(sanitize "$xps_summary")"
emit "IRQ: $(sanitize "$irq_summary")"
emit "NIC offload: $(sanitize "$nic_offload")"
emit "PMTU tools: IPv4=$tracepath4 IPv6=$tracepath6 (no public target is contacted)"
emit "Connectivity ($LABEL; path is not inferred): DNS-cn=$dns_cn DNS-overseas=$dns_overseas DNS-AAAA=$dns_ipv6 HTTPS4-cn=$https4_cn HTTPS4-overseas=$https4_overseas HTTPS6-overseas=$https6_overseas"
[ -n "$IPERF_SERVER" ] && emit "iperf3 (explicit server only):$(sanitize "$iperf_results")"

iperf_json_array="[$iperf_json]"
iperf_server_supplied=false
[ -n "$IPERF_SERVER" ] && iperf_server_supplied=true
iperf_udp_requested=false
[ "$IPERF_UDP" -eq 1 ] && iperf_udp_requested=true
cat > "$JSON_PATH" <<EOF
{
  "label": $(json_value "$LABEL"),
  "timestamp": $(json_value "$timestamp"),
  "device": {"openwrt": $(json_value "$openwrt_version"), "kernel": $(json_value "$kernel_version"), "architecture": $(json_value "$architecture"), "cpu_model": $(json_value "$cpu_model"), "cpu_cores": $(json_value "$cpu_cores"), "cpu_frequency": $(json_value "$cpu_frequency"), "openkill_version": $(json_value "$openkill_version"), "mihomo_version": $(json_value "$mihomo_version")},
  "network": {"lan_interface": $(json_value "$lan_interface"), "wan_interface": $(json_value "$wan_interface"), "wan_ipv4": $(json_value "$wan_ipv4"), "wan_ipv6": $(json_value "$wan_ipv6"), "default_ipv4_route": $(json_value "$default_ipv4_route"), "default_ipv6_route": $(json_value "$default_ipv6_route"), "mtu": $(json_value "$wan_mtu")},
  "openkill": {"mode": $(json_value "$mode"), "ipv6_enabled": $(json_value "$ipv6_enabled"), "tun_stack": $(json_value "$tun_stack"), "ipv6_stack": $(json_value "$ipv6_stack"), "dns_mode": $(json_value "$dns_mode"), "sniffer": $(json_value "$sniffer"), "tcp_concurrent": $(json_value "$tcp_concurrent"), "geodata_loader": $(json_value "$geodata_loader")},
  "tun": {"devices": $(json_value "$tun_devices"), "table_354": $(json_value "$table_354"), "rules_162": $(json_value "$rules_162")},
  "nftables": {"rule_count": $(json_value "$nft_rule_count"), "matches": $(json_value "$nft_summary")},
  "cpu": {"utilization_percent": $(json_value "$cpu_util"), "softirq_delta": $(json_value "$softirq_delta"), "mihomo_percent": $(json_value "$mihomo_cpu"), "loadavg": $(json_value "$loadavg")},
  "memory": {"mem_total": $(json_value "$mem_total"), "mem_available": $(json_value "$mem_available"), "cached": $(json_value "$mem_cached"), "swap_total": $(json_value "$swap_total"), "swap_free": $(json_value "$swap_free"), "mihomo_rss": $(json_value "$mihomo_rss"), "mihomo_hwm": $(json_value "$mihomo_hwm")},
  "conntrack": {"count": $(json_value "$conntrack_count"), "max": $(json_value "$conntrack_max"), "utilization_percent": $(json_value "$conntrack_util")},
  "offload": {"software": $(json_value "$flow_software"), "hardware": $(json_value "$flow_hardware"), "packet_steering": $(json_value "$packet_steering"), "rps": $(json_value "$rps_summary"), "xps": $(json_value "$xps_summary"), "irq": $(json_value "$irq_summary"), "nic": $(json_value "$nic_offload")},
  "pmtu": {"ipv4_tool": $(json_value "$tracepath4"), "ipv6_tool": $(json_value "$tracepath6")},
  "connectivity": {"dns_cn": $(json_value "$dns_cn"), "dns_overseas": $(json_value "$dns_overseas"), "dns_aaaa": $(json_value "$dns_ipv6"), "https_ipv4_cn": $(json_value "$https4_cn"), "https_ipv4_overseas": $(json_value "$https4_overseas"), "https_ipv6_overseas": $(json_value "$https6_overseas")},
  "iperf_context": {"server_supplied": $iperf_server_supplied, "duration_seconds": $(json_value "$IPERF_TIME"), "udp_requested": $iperf_udp_requested, "udp_rate": $(json_value "$IPERF_UDP_RATE")},
  "iperf": $iperf_json_array
}
EOF

exit 0
