/* ytk.app launcher stub.
 *
 * macOS TCC attributes permissions (Full Disk Access, etc.) to the process
 * executable — a bare python daemon shows up as "python3.13" with no icon,
 * and the grant dies whenever uv replaces the interpreter. This stub is the
 * stable, branded identity: launchd runs it, it spawns `ytk ui` as a child
 * and stays alive as the responsible process, so the child inherits the
 * bundle's TCC attribution. It must NOT exec-replace itself (attribution
 * would fall back to python); it spawns, forwards signals, and mirrors the
 * child's exit status.
 *
 * Built once by build_app.sh; ytk code updates never require a rebuild,
 * which is the entire point — the FDA grant keys on this binary.
 */

#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(void) {
    const char *home = getenv("HOME");
    if (!home) {
        fprintf(stderr, "ytk-hub: HOME unset\n");
        return 1;
    }
    char ytk[1024];
    snprintf(ytk, sizeof ytk, "%s/.local/bin/ytk", home);

    char *args[] = {ytk, "ui", NULL};
    signal(SIGTERM, forward);
    signal(SIGINT, forward);

    if (posix_spawn(&child, ytk, NULL, NULL, args, environ) != 0) {
        perror("ytk-hub: spawn");
        return 1;
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
        /* interrupted by a forwarded signal; keep waiting for the child */
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 0;
}
