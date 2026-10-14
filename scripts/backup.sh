#!/bin/sh
set -eu
umask 077
mkdir -p /backups
while true; do
    backup_file="/backups/dedlainych-$(date -u +%Y%m%dT%H%M%SZ).dump"
    if pg_dump -Fc -f "$backup_file.tmp"; then
        mv "$backup_file.tmp" "$backup_file"
        find /backups -name '*.dump' -type f -mtime +14 -delete
        echo 'Резервная копия создана'
    else
        rm -f "$backup_file.tmp"
        echo 'Ошибка резервного копирования' >&2
        exit 1
    fi
    sleep 86400
done
