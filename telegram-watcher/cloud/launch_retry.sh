#!/bin/bash
# Keep asking Oracle for an Always Free VM until one is available. San Jose is
# often "Out of capacity", so this alternates the two free shapes every few
# minutes and stops as soon as one launches. Prints the public IP at the end.
# Usage: cloud/launch_retry.sh   (uses the "h1b" profile in ~/.oci/config)
set -uo pipefail
export OCI_CLI_PROFILE=h1b PYTHONWARNINGS=ignore SUPPRESS_LABEL_WARNING=True

T=ocid1.tenancy.oc1..aaaaaaaanmcbg4pe6pfzta22e4zeoqwxlizxm343tfwyhkqs2g5e3e4hnwnq
AD="mYCA:US-SANJOSE-1-AD-1"
SUB=ocid1.subnet.oc1.us-sanjose-1.aaaaaaaag3tvnltbz2ix7ygce2bsy5cowkqm7poay64ubfvm37hospwoxvwq
IMG_ARM=ocid1.image.oc1.us-sanjose-1.aaaaaaaa33g6xbfeypx7pviqlgofzmkqaglpmnm65sac225vdqz24l4p4gua
IMG_X86=ocid1.image.oc1.us-sanjose-1.aaaaaaaa5be2zjskuujmjsfyf2liof5uepxwaclycwj463unl6cafvzqhykq
KEY_PUB=$HOME/.ssh/oracle_h1b.pub
WAIT=${WAIT:-180}

existing() {
  oci compute instance list -c "$T" --display-name h1b-watcher \
    --query 'data[?"lifecycle-state"!=`TERMINATED`].id | [0]' --raw-output 2>/dev/null
}

launch() {  # shape image [shape-config]
  local args=(compute instance launch -c "$T" --availability-domain "$AD" --subnet-id "$SUB"
    --assign-public-ip true --display-name h1b-watcher --ssh-authorized-keys-file "$KEY_PUB"
    --shape "$1" --image-id "$2" --wait-for-state RUNNING --query 'data.id' --raw-output)
  [ -n "${3:-}" ] && args+=(--shape-config "$3")
  oci "${args[@]}" 2>&1
}

ID=$(existing)
n=0
while [ -z "$ID" ] || [ "$ID" = "null" ]; do
  n=$((n + 1))
  for try in arm x86; do
    if [ $try = arm ]; then out=$(launch VM.Standard.A1.Flex "$IMG_ARM" '{"ocpus":1,"memoryInGBs":6}')
    else out=$(launch VM.Standard.E2.1.Micro "$IMG_X86"); fi
    if echo "$out" | grep -q '^ocid1.instance'; then ID=$(echo "$out" | grep '^ocid1.instance' | tail -1); break; fi
    reason=$(echo "$out" | grep -o '"message": "[^"]*' | head -1 | cut -c13-90)
    echo "$(date '+%F %T') attempt $n $try: ${reason:-unknown error}" >&2
  done
  [ -n "${ID:-}" ] && break
  sleep "$WAIT"
done

echo "$(date '+%F %T') instance running: $ID" >&2
oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output 2>/dev/null
