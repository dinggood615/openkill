#!/bin/bash
. /usr/share/openkill/openkill_ps.sh
. /usr/share/openkill/log.sh
. /usr/share/openkill/openkill_curl.sh
. /usr/share/openkill/uci.sh

set_lock() {
   exec 868>"/tmp/lock/openkill_lgbm.lock" 2>/dev/null
   flock -x 868 2>/dev/null
}

del_lock() {
   flock -u 868 2>/dev/null
   rm -rf "/tmp/lock/openkill_lgbm.lock" 2>/dev/null
}

set_lock
inc_job_counter

small_flash_memory=$(uci_get_config "small_flash_memory")
LGBM_CUSTOM_URL=$(uci_get_config "lgbm_custom_url")
restart=0

if [ "$small_flash_memory" != "1" ]; then
   lgbm_path="/etc/openkill/Model.bin"
   mkdir -p /etc/openkill
else
   lgbm_path="/tmp/etc/openkill/Model.bin"
   mkdir -p /tmp/etc/openkill
fi
LOG_OUT "Start Downloading LightGBM Model..."
if [ -z "$LGBM_CUSTOM_URL" ]; then
   DOWNLOAD_URL="https://github.com/vernesong/mihomo/releases/download/LightGBM-Model/Model.bin"
else
   DOWNLOAD_URL=$LGBM_CUSTOM_URL
fi
DOWNLOAD_FILE_CURL "$DOWNLOAD_URL" "/tmp/Model.bin" "$lgbm_path"
DOWNLOAD_RESULT=$?
if [ "$DOWNLOAD_RESULT" -eq 0 ] && [ -s "/tmp/Model.bin" ]; then
   LOG_OUT "LightGBM Model Download Success, Check Updated..."
   cmp -s /tmp/Model.bin "$lgbm_path"
   if [ "$?" -ne "0" ]; then
      LOG_OUT "LightGBM Model Has Been Updated, Starting To Replace The Old Version..."
      rm -rf "/etc/openkill/Model.bin"
      mv /tmp/Model.bin "$lgbm_path" >/dev/null 2>&1
      LOG_OUT "LightGBM Model Update Successful!"
      restart=1
   else
      LOG_OUT "Updated LightGBM Model No Change, Do Nothing..."
   fi
elif [ "$DOWNLOAD_RESULT" -eq 2 ]; then
   LOG_OUT "Updated LightGBM Model No Change, Do Nothing..."
else
   LOG_OUT "LightGBM Model Update Error, Please Try Again Later..."
fi

rm -rf /tmp/Model.bin >/dev/null 2>&1

dec_job_counter_and_restart "$restart"
del_lock