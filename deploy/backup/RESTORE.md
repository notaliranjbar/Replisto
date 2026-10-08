# Restoring a backup

Backups are in `./backups` on the server (next to `docker-compose.yml`), named
`replisto-YYYYMMDD-HHMM.dump`. If the server itself is lost, take the newest encrypted copy
(`.dump.enc`) from the operations Telegram chat.

## 1. Decrypt (only for a copy from Telegram)

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -in replisto-20261002-1200.dump.enc -out replisto-20261002-1200.dump
```

It asks for `BACKUP_PASSPHRASE`. Keep that passphrase somewhere safe outside the server
(a password manager): without it the Telegram copies can't be opened.

## 2. Restore into the running database

Stop the services that write to the database, restore, then start everything again:

```bash
docker compose stop api worker
docker compose cp replisto-20261002-1200.dump db:/tmp/restore.dump
docker compose exec db pg_restore -U app -d app --clean --if-exists /tmp/restore.dump
docker compose up -d
```

`--clean` replaces the current data with the backup's. On a brand-new server, start only the
database first (`docker compose up -d db`), restore, then `docker compose up -d`.

The same `ENCRYPTION_KEY` as before must be in `.env`: stored bot tokens and Instagram tokens
are encrypted with it.

## 3. Test it once

A backup that was never restored is a hope, not a backup. After the first deploy, restore the
newest dump into a throwaway database once to be sure it works:

```bash
docker compose exec db createdb -U app restore_test
docker compose exec db pg_restore -U app -d restore_test /backups/<newest>.dump
docker compose exec db psql -U app -d restore_test -c "select count(*) from shops;"
docker compose exec db dropdb -U app restore_test
```

(For this, mount the backups into the db container or copy the file in as in step 2.)
