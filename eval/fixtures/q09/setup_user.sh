#!/bin/sh
# q09: create the non-root user that runs the answer's install and task commands.
# Run once as root in a fresh dev image, before any answer step.
#
#   sh setup_user.sh            # user "dev", with passwordless sudo (default)
#   GRANT_SUDO=no sh setup_user.sh   # user "dev" without sudo
#
# Whether "dev" gets sudo is a decision recorded in needs.json; use the same
# choice for both groups and write it in the check log.
set -eu

user=${Q09_USER:-dev}
grant=${GRANT_SUDO:-yes}

if [ "$(id -u)" != 0 ]; then
  echo "run as root" >&2
  exit 2
fi

if id "$user" >/dev/null 2>&1; then
  echo "user $user already exists" >&2
  exit 2
fi

useradd --create-home --shell /bin/bash "$user"

case "$grant" in
  yes)
    if ! command -v sudo >/dev/null 2>&1; then
      echo "sudo is not installed in this image; set GRANT_SUDO=no or add sudo to the image" >&2
      exit 3
    fi
    mkdir -p /etc/sudoers.d
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$user" > "/etc/sudoers.d/90-$user"
    chmod 0440 "/etc/sudoers.d/90-$user"
    ;;
  no) ;;
  *) echo "GRANT_SUDO must be yes or no" >&2; exit 2 ;;
esac

mkdir -p /work
chown "$user" /work
echo "user: $(id "$user")"
echo "home: $(getent passwd "$user" | cut -d: -f6)"
echo "sudo: $grant"
