#!/bin/bash
. /usr/share/openkill/openkill_ps.sh
. /usr/share/openkill/log.sh
. /usr/share/openkill/openkill_curl.sh
. /usr/share/openkill/uci.sh

set_lock() {
   exec 879>"/tmp/lock/openkill_chn.lock" 2>/dev/null
   flock -x 879 2>/dev/null
}

del_lock() {
   flock -u 879 2>/dev/null
   rm -rf "/tmp/lock/openkill_chn.lock" 2>/dev/null
}

set_lock
inc_job_counter

FW4=$(command -v fw4)
china_ip_route=$(uci_get_config "china_ip_route")
china_ip6_route=$(uci_get_config "china_ip6_route")
CHNR_CUSTOM_URL=$(uci_get_config "chnr_custom_url")
CHNR6_CUSTOM_URL=$(uci_get_config "chnr6_custom_url")
CNDOMAIN_CUSTOM_URL=$(uci_get_config "cndomain_custom_url")
disable_udp_quic=$(uci_get_config "disable_udp_quic")
small_flash_memory=$(uci_get_config "small_flash_memory")
en_mode=$(uci_get_config "en_mode")
restart=0

validate_route_download()
{
   input="$1"
   family="$2"
   normalized="${input}.normalized.$$"
   [ -s "$input" ] || return 1
   if [ "$family" = 4 ]; then
      awk '
         !/^([[:space:]]*#|[[:space:]]*$)/ {
            gsub(/[[:space:]]/, "", $0)
            n = split($0, cidr, "/")
            valid = (n <= 2)
            octets = split(cidr[1], part, ".")
            if (octets != 4) valid = 0
            for (i = 1; i <= 4; i++) {
               if (part[i] !~ /^[0-9]+$/ || part[i] > 255) valid = 0
            }
            if (n == 2 && (cidr[2] !~ /^[0-9]+$/ || cidr[2] > 32)) valid = 0
            if (valid) print
            else bad = 1
            count++
         }
         END { if (bad || count == 0) exit 1 }
      ' "$input" > "$normalized.raw" || { rm -f "$normalized" "$normalized.raw"; return 1; }
   else
      awk '
         !/^([[:space:]]*#|[[:space:]]*$)/ {
            gsub(/[[:space:]]/, "", $0)
            n = split($0, cidr, "/")
            ip = cidr[1]
            valid = (n <= 2 && index(ip, ":") > 0 && ip ~ /^[0-9A-Fa-f:]+$/)
            if (n == 2 && (cidr[2] !~ /^[0-9]+$/ || cidr[2] > 128)) valid = 0
            compressed = ip
            double_colon = gsub(/::/, "X", compressed)
            if (double_colon > 1 || (double_colon == 0 && gsub(/:/, ":", ip) != 7)) valid = 0
            if (double_colon == 0) {
               groups = split(ip, part, ":")
               if (groups != 8) valid = 0
               for (i = 1; i <= groups; i++) if (part[i] !~ /^[0-9A-Fa-f]{1,4}$/) valid = 0
            } else {
               # Keep the compression marker as its own group so addresses
               # such as 2001:db8:: and ::1 are checked correctly by BusyBox
               # awk, whose split handling of trailing empty fields varies.
               compressed = ip
               gsub(/::/, ":X:", compressed)
               groups = split(compressed, part, ":")
               nonempty = 0
               for (i = 1; i <= groups; i++) if (part[i] != "" && part[i] != "X") { if (part[i] !~ /^[0-9A-Fa-f]{1,4}$/) valid = 0; nonempty++ }
               if (nonempty >= 8) valid = 0
            }
            if (valid) print
            else bad = 1
            count++
         }
         END { if (bad || count == 0) exit 1 }
      ' "$input" > "$normalized.raw" || { rm -f "$normalized" "$normalized.raw"; return 1; }
   fi
   sort -u "$normalized.raw" > "$normalized" || { rm -f "$normalized" "$normalized.raw"; return 1; }
   rm -f "$normalized.raw"
   count=$(wc -l < "$normalized" 2>/dev/null || echo 0)
   [ "$count" -gt 0 ] && [ "$count" -le 500000 ] || { rm -f "$normalized"; return 1; }
   mv -f "$normalized" "$input"
}

if [ "$small_flash_memory" != "1" ]; then
   chnr_path="/etc/openkill/china_ip_route.ipset"
   chnr6_path="/etc/openkill/china_ip6_route.ipset"
   mkdir -p /etc/openkill
else
   chnr_path="/tmp/etc/openkill/china_ip_route.ipset"
   chnr6_path="/tmp/etc/openkill/china_ip6_route.ipset"
   mkdir -p /tmp/etc/openkill
fi

LOG_OUT "Start Downloading The Chnroute Cidr List..."
if [ -z "$CHNR_CUSTOM_URL" ]; then
   DOWNLOAD_FILE_CURL "https://ispip.clang.cn/all_cn.txt" "/tmp/china_ip_route.txt" "$chnr_path"
else
   DOWNLOAD_FILE_CURL "$CHNR_CUSTOM_URL" "/tmp/china_ip_route.txt" "$chnr_path"
fi
DOWNLOAD_RESULT=$?
if [ "$DOWNLOAD_RESULT" -eq 0 ]; then
   LOG_OUT "Chnroute Cidr List Download Success, Check Updated..."
   if ! validate_route_download /tmp/china_ip_route.txt 4; then
      LOG_OUT "Chnroute Cidr List Validation Failed, Keeping The Last Valid Version."
      rm -f /tmp/china_ip_route.txt
      DOWNLOAD_RESULT=1
   fi
fi
if [ "$DOWNLOAD_RESULT" -eq 0 ]; then
   #预处理
   if [ -n "$FW4" ]; then
      echo "define china_ip_route = {" >/tmp/china_ip_route.list
      awk '!/^$/&&!/^#/{printf("    %s,'" "'\n",$0)}' /tmp/china_ip_route.txt >>/tmp/china_ip_route.list
      echo "}" >>/tmp/china_ip_route.list
      echo "add set inet fw4 china_ip_route { type ipv4_addr; flags interval; auto-merge; }" >>/tmp/china_ip_route.list
      echo 'add element inet fw4 china_ip_route $china_ip_route' >>/tmp/china_ip_route.list
   else
      echo "create china_ip_route hash:net family inet hashsize 1024 maxelem 1000000" >/tmp/china_ip_route.list
      awk '!/^$/&&!/^#/{printf("add china_ip_route %s'" "'\n",$0)}' /tmp/china_ip_route.txt >>/tmp/china_ip_route.list
   fi
   cmp -s /tmp/china_ip_route.list "$chnr_path"
   if [ "$?" -ne 0 ]; then
      LOG_OUT "Chnroute Cidr List Has Been Updated, Starting To Replace The Old Version..."
      mv /tmp/china_ip_route.list "$chnr_path" >/dev/null 2>&1
      if [ "$china_ip_route" -ne 0 ] || [ "$disable_udp_quic" -eq 1 ]; then
         restart=1
      fi
      LOG_OUT "Chnroute Cidr List Update Successful!"
   else
      LOG_OUT "Updated Chnroute Cidr List No Change, Do Nothing..."
   fi
elif [ "$DOWNLOAD_RESULT" -eq 2 ]; then
   LOG_OUT "Updated Chnroute Cidr List No Change, Do Nothing..."
else
   LOG_OUT "Chnroute Cidr List Update Error, Please Try Again Later..."
fi

#ipv6
LOG_OUT "Start Downloading The Chnroute6 Cidr List..."
if [ -z "$CHNR6_CUSTOM_URL" ]; then
   DOWNLOAD_FILE_CURL "https://ispip.clang.cn/all_cn_ipv6.txt" "/tmp/china_ip6_route.txt" "$chnr6_path"
else
   DOWNLOAD_FILE_CURL "$CHNR6_CUSTOM_URL" "/tmp/china_ip6_route.txt" "$chnr6_path"
fi
DOWNLOAD_RESULT=$?
if [ "$DOWNLOAD_RESULT" -eq 0 ]; then
   LOG_OUT "Chnroute6 Cidr List Download Success, Check Updated..."
   if ! validate_route_download /tmp/china_ip6_route.txt 6; then
      LOG_OUT "Chnroute6 Cidr List Validation Failed, Keeping The Last Valid Version."
      rm -f /tmp/china_ip6_route.txt
      DOWNLOAD_RESULT=1
   fi
fi
if [ "$DOWNLOAD_RESULT" -eq 0 ]; then
   #预处理
   if [ -n "$FW4" ]; then
      echo "define china_ip6_route = {" >/tmp/china_ip6_route.list
      awk '!/^$/&&!/^#/{printf("    %s,'" "'\n",$0)}' /tmp/china_ip6_route.txt >>/tmp/china_ip6_route.list
      echo "}" >>/tmp/china_ip6_route.list
      echo "add set inet fw4 china_ip6_route { type ipv6_addr; flags interval; auto-merge; }" >>/tmp/china_ip6_route.list
      echo 'add element inet fw4 china_ip6_route $china_ip6_route' >>/tmp/china_ip6_route.list
   else
      echo "create china_ip6_route hash:net family inet6 hashsize 1024 maxelem 1000000" >/tmp/china_ip6_route.list
      awk '!/^$/&&!/^#/{printf("add china_ip6_route %s'" "'\n",$0)}' /tmp/china_ip6_route.txt >>/tmp/china_ip6_route.list
   fi
   cmp -s /tmp/china_ip6_route.list "$chnr6_path"
   if [ "$?" -ne 0 ]; then
      LOG_OUT "Chnroute6 Cidr List Has Been Updated, Starting To Replace The Old Version..."
      mv /tmp/china_ip6_route.list "$chnr6_path" >/dev/null 2>&1
      if [ "$china_ip6_route" -ne 0 ] || [ "$disable_udp_quic" -eq 1 ]; then
         restart=1
      fi
      LOG_OUT "Chnroute6 Cidr List Update Successful!"
   else
      LOG_OUT "Updated Chnroute6 Cidr List No Change, Do Nothing..."
   fi
elif [ "$DOWNLOAD_RESULT" -eq 2 ]; then
   LOG_OUT "Updated Chnroute6 Cidr List No Change, Do Nothing..."
else
   LOG_OUT "Chnroute6 Cidr List Update Error, Please Try Again Later..."
fi

rm -rf /tmp/china_ip*_route* >/dev/null 2>&1

dec_job_counter_and_restart "$restart"
del_lock
