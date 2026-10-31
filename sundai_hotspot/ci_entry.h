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
#include <netinet/in.h>
#include <string.h>
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
    /* Record the violation even if a caller ignores our nonzero exit. */
    {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in address;
        const char message[] = "POST /violation HTTP/1.0\r\nContent-Length: 2\r\n\r\n{}";
        memset(&address, 0, sizeof(address));
        address.sin_family = AF_INET;
        address.sin_port = htons(47631);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (sock >= 0) {
            setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
            if (connect(sock, (struct sockaddr *)&address, sizeof(address)) == 0)
                (void)send(sock, message, sizeof(message) - 1, MSG_NOSIGNAL);
            close(sock);
        }
    }
    fputs("CI HotSpot requires a reserved launch through ci_gate.run_hotspot\n", stderr);
    exit(125);
}
#else
#define ci_hotspot_entry() ((void)0)
#endif
#endif
