# Validation record

Final variant: **public, no student login**. Anonymous browser sessions isolate workspaces; teacher management requires login.

## Actually completed in this environment

- **51 pytest tests passed**: PostgreSQL AST allow/deny rules, SQL statement splitting, password hashing, teacher session handling, CSRF request header, request-body limit, ownership enforcement, anonymous workspace provisioning with mocked PostgreSQL, cookie reuse, teacher/guest switching, cross-browser access denial, and guest quota exhaustion.
- Python syntax compilation for backend, tests and operational scripts.
- React / Monaco production build with Vite 6.4.3 succeeded. Monaco is bundled locally including its worker.
- `npm audit`: **0 known vulnerabilities** in the installed frontend dependency graph at validation time. This is not a security audit of the application.
- Docker Compose **v5.5.1** official standalone CLI accepted the Compose configuration with `config --no-env-resolution --quiet`, using `.env.example` and disposable validation values. No Docker daemon was available.
- Caddy **2.11.4** official binary successfully adapted and validated the Caddyfile in local HTTP mode.
- YAML inspection verified that PostgreSQL/backend/frontend publish no host ports; only the reverse proxy publishes ports.
- Environment generator tested in a disposable directory: random secrets, file mode 0600, refusal to overwrite an existing `.env`.
- Browser UI check: automatic guest workspace, Monaco loading, School DB selector and results table rendered successfully. **The browser preview used mocked PostgreSQL provisioning/query results**, not a real database.
- Delivery ZIP checked for `.env`, SQLite databases, dependency folders, build folders and Python caches.

## Not completed here

- Full Docker image builds / container boot, Nginx runtime validation, actual PostgreSQL provisioning and SQL execution, real concurrency/timeout/rollback/isolation tests, and production HTTPS certificate issuance.
- A temporary PostgreSQL 17.10 binary was obtained for integration testing, but local initdb failed because the sandbox prohibits the required `shmget` shared-memory operation. Switching mmap options did not remove that platform restriction. No PostgreSQL server was left running.
- No GitHub repository was modified, no commit pushed, no hosted deployment created.

## Re-run the missing checks

On a machine with Docker:

```bash
python3 scripts/configure.py
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
docker compose exec -T frontend nginx -t
docker compose exec -T proxy caddy validate --config /etc/caddy/Caddyfile
python3 scripts/run_smoke.py
docker compose exec -T backend python - < scripts/check_isolation.py
```

The supplied GitHub Actions workflow runs these checks on each push / pull request. It has been written but **has not run on your repository yet**. The HTTP smoke test covers anonymous entry, teacher login, cross-user access denial, dangerous SQL, SQL/CSV import rollback, row/upload/database limits, template clone/reset, query timeout and session revocation. The PostgreSQL isolation script bypasses the HTTP policy deliberately to check the actual low-privilege roles.

Known non-blocking build/test warnings: Monaco's production bundle is large (~2.5 MB uncompressed / ~665 KB gzip); test dependencies emit two deprecation warnings. Public anonymous usage is quota-limited and vulnerable to deliberate allocation exhaustion; see README for the intended classroom scope and operational limits.
