#!/usr/bin/env bash
# Runs ONLY as a child of ci_cpu_meter. All daemon-created cgroups share its parent.
set -euo pipefail
: "${CI_CGROUP:?meter must supply the cgroup}"
: "${CI_RUN_ID:?admission must supply the run}"
: "${BUILD_SHA:?admission must supply the build SHA}"
[[ "$(cat /proc/self/cgroup)" == *"${CI_CGROUP#/sys/fs/cgroup}/host" ]]
[[ "$(cat "$CI_CGROUP/cpu.max")" == '100000 100000' ]]
task_root="/tmp/ci-allocation-$CI_RUN_ID"
mkdir -p "$task_root"
export DOCKER_HOST="unix://$task_root/docker.sock"
export DOCKER_BUILDKIT=1
# A dedicated daemon avoids unaccounted work in the runner's preexisting daemon.
# cgroupfs is explicit: systemd's default slice would move build/runtime tasks out.
dockerd --host="$DOCKER_HOST" --data-root="$task_root/data" \
  --exec-root="$task_root/exec" --pidfile="$task_root/docker.pid" \
  --bridge=none --iptables=false --ip-masq=false \
  --exec-opt=native.cgroupdriver=cgroupfs --cgroup-parent="${CI_CGROUP#/sys/fs/cgroup}" \
  > "$task_root/docker.log" 2>&1 &
daemon_pid=$!
for _ in $(seq 1 100); do
  docker info >/dev/null 2>&1 && break
  kill -0 "$daemon_pid"
  sleep .1
done
docker info >/dev/null
[[ "$(docker info --format '{{.CgroupDriver}}')" == cgroupfs ]]
[[ "$(docker info --format '{{.CgroupVersion}}')" == 2 ]]
# BuildKit RUNs use host networking to reach the local allocation broker.
docker build --network=host --no-cache --build-arg CI_ALLOCATION=1 \
  --build-arg BUILD_SHA="$BUILD_SHA" -t thermal-api:ci .
docker run -d --network=host --name api thermal-api:ci
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:8000/api/health && break; sleep 1; done
curl -sf http://127.0.0.1:8000/api/health | grep -q "\"build_sha\":\"$BUILD_SHA\""
# Origin-lock signing material remains exclusively in process environment/memory.
origin_value="$(openssl rand -hex 16)"
docker run -d --network=host --name locked -e ORIGIN_SHARED_TOKEN="$origin_value" \
  thermal-api:ci uvicorn app.main:app --host 0.0.0.0 --port 8001
for _ in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:8001/api/health && break; sleep 1; done
test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/health)" = 403
test "$(curl -s -o /dev/null -w '%{http_code}' -H "x-origin-token: $(openssl rand -hex 16)" http://127.0.0.1:8001/api/health)" = 403
test "$(curl -s -o /dev/null -w '%{http_code}' -H "x-origin-token: $origin_value" http://127.0.0.1:8001/api/health)" = 200
