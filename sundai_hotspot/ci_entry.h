/* CI-only entry gate, compiled into HotSpot so copies retain the check.
 * The Python wrapper supplies a one-use socket AFTER a durable reservation.
 * No environment flag alone authorizes a solver entry. This guards accidental
 * CI bypasses; it is not a sandbox against an actor rewriting solver source.
 */
#ifndef SENTILAB_CI_ENTRY_H
#define SENTILAB_CI_ENTRY_H
#ifdef CI_ALLOCATION
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <limits.h>
static void ci_hotspot_entry(void)
{
    const char *value = getenv("CI_HOTSPOT_ENTRY_FD");
    char *end = NULL, permit = 0;
    long descriptor;
    struct timeval timeout = {5, 0};
    if (!value || !*value) goto refused;
    errno = 0;
    descriptor = strtol(value, &end, 10);
    if (errno || *end || descriptor < 3 || descriptor > INT_MAX) goto refused;
    unsetenv("CI_HOTSPOT_ENTRY_FD");
    if (setsockopt((int)descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0)
        goto refused;
    if (recv((int)descriptor, &permit, 1, 0) != 1 || permit != 'G') goto refused;
    close((int)descriptor);
    return;
refused:
    fputs("CI HotSpot requires a reserved launch through ci_gate.run_hotspot\n", stderr);
    exit(125);
}
#else
#define ci_hotspot_entry() ((void)0)
#endif
#endif
