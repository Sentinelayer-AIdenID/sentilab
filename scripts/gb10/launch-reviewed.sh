#!/usr/bin/env bash
set -eu
umask 077
cd /home/dell/sentilab/preflight-20261031
test ! -e STOP
test ! -e execution-state.json
nohup python3 /home/dell/sentilab/preflight-20261031/supervise.py run > execution.log 2>&1 < /dev/null &
supervisor_pid=$!
printf '%s\n' "$supervisor_pid" > supervisor.pid
printf 'supervisor_pid=%s\n' "$supervisor_pid"
