"""One fresh process, one original TAP worker evaluation, no signer or lab code."""
import json
import os
import resource
import signal
import sys


def main():
    # A child that outlives the conductor still kills its entire process group.
    # The native solver inherits this group's single-CPU affinity. Thus aggregate
    # process-tree CPU cannot exceed its reserved wall lifetime.
    ceiling = float(sys.argv[1])
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    signal.signal(signal.SIGALRM, lambda *_: os.killpg(os.getpgrp(), signal.SIGKILL))
    signal.setitimer(signal.ITIMER_REAL, max(0.001, ceiling - 1))
    resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(ceiling)), max(1, int(ceiling))))
    raw = sys.stdin.buffer.readline(65538)
    if len(raw) > 65537 or not raw.endswith(b"\n"):
        raise ValueError("invalid bounded worker request")
    from sundai_hotspot.tap_oracle_worker import evaluate
    result = evaluate(json.loads(raw))
    usage = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    print(json.dumps({"result": result,
                      "cpu_s": usage.ru_utime + usage.ru_stime + children.ru_utime + children.ru_stime,
                      "process_id": str(os.getpid())}, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
