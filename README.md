# Student SQL Lab

一個可自行部署的課堂 SQL 練習平台：React + 本機打包 Monaco editor、FastAPI、PostgreSQL 17、Docker Compose、Nginx 和 Caddy。**任何人打開網頁即可練習，不需要學生註冊或登入。** 每個瀏覽器自動獲分配獨立 database；只有老師管理頁需要登入。

**交付狀態：前端 build 和後端自動測試已在製作環境通過；完整 Docker／PostgreSQL 整合測試需要在你的 Docker 環境或 GitHub Actions 執行。** 詳見 [VALIDATION.md](VALIDATION.md)。這不是已上線的網址，也未代你 push GitHub。

## 1. 上載到你現有 GitHub repository

先解壓 `student-sql-lab.zip`。使用你原有 repository 的 URL，保留其 Git 歷史：

```bash
git clone https://github.com/YOUR_USERNAME/student-sql-lab.git
cd student-sql-lab
# 將解壓後 student-sql-lab 資料夾「內的全部檔案」複製到此處，取代同名檔案。
# 包括 .env.example、.gitignore、.github；不要複製成多一層 student-sql-lab/。
git add .
git commit -m "Build complete student SQL lab"
git push
```

macOS Finder 用 Command+Shift+. 顯示隱藏檔。GitHub Desktop 也可 Clone → 複製檔案 → Commit → Push。若 Git 要求登入，使用 GitHub Desktop 或你的 GitHub token/SSH 設定，不是 GitHub 帳戶密碼。

網頁方式：repository → Add file → Upload files → 將解壓後的檔案／資料夾拖入 → Commit changes；請核對隱藏檔確實上載。**不要把 ZIP 本身當成可部署的 source tree；不要上載真正的 `.env`。** 舊教學的 `postgres/init/01-init.sql` 及其他不再使用的初始化檔案要刪除；此版本只保留 `postgres/init/01-security.sql`，school template 改由 backend 建立。

上載後打開 GitHub 的 Actions 頁面，看 `Verify classroom platform`。綠色表示該次提交的容器 build、HTTP 流程與資料庫權限測試成功。

## 2. 本機啟動（macOS / Windows / Linux）

安裝 Docker Desktop（Linux 可用 Docker Engine + Compose plugin）、Git、Python 3。Windows 可在 WSL Ubuntu 執行以下命令。

```bash
git clone https://github.com/YOUR_USERNAME/student-sql-lab.git
cd student-sql-lab
python3 scripts/configure.py
# 用文字編輯器打開 .env：讀取 ADMIN_USERNAME / ADMIN_PASSWORD。
# 初次本機測試保留 DOMAIN=:80、HTTP_PORT=8080、COOKIE_SECURE=false。
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

開啟 **http://localhost:8080**，會直接進入免登入 editor 並自動建立 School DB。右上角「老師登入」進入管理。教師用戶預設名稱 `teacher`，密碼是 `.env` 裏自動產生的 `ADMIN_PASSWORD`。所有服務啟動可能需要數分鐘。

`configure.py` 會由 `.env.example` 產生隨機密碼與 0600 權限 `.env`，不會覆寫已有檔案。你也可 `cp .env.example .env`，但必須自行填入獨立隨機的 `POSTGRES_PASSWORD`（24+ 字元）、`SECRET_KEY`（32+）、`ADMIN_PASSWORD`（12+）；保留 CHANGE_ME 會拒絕啟動。

```bash
# 開機完成後驗證（預設 2 個 DB / 每人、上載上限 5 MiB）
python3 scripts/run_smoke.py
docker compose exec -T backend python - < scripts/check_isolation.py
```

smoke 測試會建立兩個免登入訪客空間，完成後由教師刪除其 DB／帳戶以釋放名額，保留 audit 記錄。它會短暫跑一次超時查詢，宜在上課前測試。非預設上限需相應調整 smoke assertions。

## 3. Ubuntu server + domain + HTTPS

建議起步配置：2 vCPU、4 GiB RAM、至少 20 GiB 可用 SSD；實際班級負載需測量。不要跟其他重要系統共用 PostgreSQL cluster。

先依 [Docker 官方 Ubuntu 安裝文件](https://docs.docker.com/engine/install/ubuntu/) 安裝 Docker Engine、Buildx 及 Compose plugin，並安裝 Git / Python：

```bash
sudo apt update
sudo apt install -y git python3
# Docker 官方 repository 設定完成後：
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker compose version

git clone https://github.com/YOUR_USERNAME/student-sql-lab.git
cd student-sql-lab
python3 scripts/configure.py
nano .env
```

把網域 A record 指向 server IPv4；有 AAAA record 時也要確保 IPv6 真正可到達。`.env` 設定：

```dotenv
DOMAIN=sql.your-school.example
HTTP_PORT=80
HTTPS_PORT=443
COOKIE_SECURE=true
```

`DOMAIN` 填實際 hostname，沒有 `https://` 或 path。然後：

```bash
docker compose config --quiet
docker compose up -d --build
docker compose logs -f proxy
```

在雲端 firewall / security group 放行 TCP 80、443；SSH 只允許你的管理來源。**不開 5432 或 8000。** Caddy 會申請／更新憑證並把 HTTP 導向 HTTPS，條件是 DNS 正確且外部能到達 80/443。[Caddy 官方 HTTPS 說明](https://caddyserver.com/docs/automatic-https)

打開 `https://sql.your-school.example`。測試時：

```bash
LAB_URL=https://sql.your-school.example python3 scripts/run_smoke.py
```

若已有 Nginx/Caddy 佔用 80/443，使用現有 HTTPS proxy 轉發至此 stack 的 HTTP port，保留 `DOMAIN=:80`、`COOKIE_SECURE=true`，並將 Compose 的 HTTP mapping 改成 `127.0.0.1:8080:80`。不要讓未加密登入頁公開使用。全班經同一 NAT 時，預設登入限制 5 次/分鐘 + burst 10 可能太保守；可按班級需求調整 `frontend/nginx.conf` 的 `login` zone。後端亦有每個 username 10 次/5 分鐘限制。

## 4. 老師與學生使用

1. 任何人打開網址即可使用。平台在背景建立匿名身份、獨立 PostgreSQL role 及 School DB，無需輸入用戶名或密碼。
2. 在 Monaco 寫 SQL → Run SQL。一次執行一個 statement；結果以 table 顯示，錯誤有文字訊息。SQL 修改成功會 commit，失敗 rollback。
3. **Clone School DB** 建立另一個獨立練習 DB；預設每個瀏覽器空間最多 2 個。
4. **Reset DB** 會以 school template 的新 clone 取代該 DB，現有資料會刪除，需要 UI 確認。
5. 右上角 **老師登入** → 以 `.env` 中的教師帳戶進入 **老師管理**。可還原 DB、停用訪客或刪除舊空間以釋放名額。删除是永久操作，需要 UI 確認。訪客不需要密碼，重設密碼按鈕對訪客停用。
6. 教師登出後會返回原來的訪客練習空間。

匿名身份由 HttpOnly cookie 保留 30 日。**同一 browser profile / 同一網站會共用同一個空間；共用電腦請使用不同 profile 或各自無痕視窗。** 清除 cookie、轉裝置、轉網域或 cookie 到期會建立新空間，舊資料不會自動跟隨，也沒有密碼可找回。舊空間由老師清理，避免自動刪除正在使用的資料。學生不會因為其他瀏覽器的 SQL 而互相改動 DB。

這是有限資源的公開入口：預設最多 99 個訪客空間＋1 位老師，達上限後顯示暫時無可用空間，老師須清理或調整 `.env` 上限。建立空間有每 IP 30 次/分鐘 + burst 30 的速率限制，但不能阻止惡意使用者清 cookie 消耗名額；需要時可在上游加課堂網絡／IP 限制。停用 cookie 身份也不能阻止同一真人換瀏覽器重新進入，因為平台刻意不要求身份登入。

教師 session 有效 8 小時，教師可更改密碼。更新 `.env` 的 ADMIN_PASSWORD **不會修改已存在教師帳戶**；用 UI 修改。忘記教師密碼時，在 server 本機用下列命令輸入新密碼：

```bash
docker compose exec backend python -c "from getpass import getpass; from app.state import db,password_hash; p=getpass('New teacher password: '); assert len(p)>=12; s=db(); c=s.__enter__(); c.execute('UPDATE users SET password=? WHERE admin=1',(password_hash(p),)); c.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE admin=1)'); s.__exit__(None,None,None)"
```

管理 audit API：`GET /api/admin/audit`，需教師 cookie，最多顯示最近 100 筆；後端保留最多約 10,000 筆管理／匯入事件，不儲存學生 SQL 或密碼。

## 5. 匯入格式

**SQL**：UTF-8 `.sql`，最多 5 MiB / 100 statements。支援 PostgreSQL CREATE TABLE、INSERT、UPDATE、DELETE、ALTER TABLE 常用操作、CREATE VIEW、btree INDEX、TRUNCATE、DROP TABLE/VIEW/INDEX。整個檔案同一 transaction，任何一行出錯全部 rollback。`;` 在字串／註解中可正常處理。匯入檔不接受獨立 SELECT；請在 editor 執行。

```sql
CREATE TABLE books (id integer PRIMARY KEY, title text, price numeric(8,2));
INSERT INTO books VALUES (1, 'Learning SQL', 99.00);
```

不是任意 PostgreSQL dump restore：psql `\\` 指令、COPY dump、BEGIN/COMMIT、SET、CREATE DATABASE/ROLE、extensions、functions、triggers、procedures、GRANT、任意 server function 不支援。使用自己整理的 schema + INSERT 語句；一般 pg_dump 檔案即使用 `--inserts` 也可能包含 SET / owner 指令，不能原樣上載。MySQL／SQLite dialect 必須先轉 PostgreSQL。

**CSV**：UTF-8（可帶 BOM）、comma-separated、第一行 header。建立一張全新的 table，不覆寫已有 table。最多 50,000 rows、100 columns；欄名須唯一，使用英文字母／底線開頭，後接英數／底線，最長 63 字元。欄位先作 `text`，空白欄位保留空字串；需要時用 ALTER TABLE … USING 轉換型別。CSV 的值用 COPY row encoding 寫入，不拼成 SQL；table/header 用 SQL identifier quoting。引號、逗號及換行按標準 CSV 處理。

```csv
name,score
Alice,88
Bob,75
```

## 6. 隔離及限制

- Browser → Caddy → Nginx → FastAPI → PostgreSQL。只有 proxy 公開 ports；PostgreSQL 位於 internal Docker network，無 host port mapping。
- 帳戶／session／database ownership metadata 放獨立 SQLite volume；學生 SQL 完全不能存取它。密碼使用 PBKDF2-SHA256（600,000 rounds），session token 只存 hash。
- 每個訪客瀏覽器空間一個隨機命名 PostgreSQL LOGIN role，每個練習 DB 真正獨立。非 superuser、無 CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS、無角色繼承，無 server file/program 權限。database 由管理員擁有，學生只擁有自己的 public schema 和練習資料表。
- 所有 DB 撤銷 PUBLIC CONNECT；只授權擁有人。HTTP database ID 會用伺服器驗證的 cookie 身份 user_id 再查 ownership。請求不能帶自訂 host、role、password 或 database name，額外 JSON 欄位被拒絕。
- AST allowlist（不是只靠字首／regex）限制 SQL、函式、型別和 schema，並拒絕 SET／set_config 等超時繞過。多 statement 只可用 SQL import。學生 role 再提供 PostgreSQL 層權限邊界。
- 預設 SQL 10 秒；後端 cancellation timer、statement timeout、lock timeout 3 秒。SELECT 使用 server cursor，最多 500 行／約 1 MiB 顯示結果，會標明截短。RETURNING 不支援，避免 DML 結果在 client 無限制緩衝。
- 原始 HTTP body 在解析前限制 5 MiB；proxy 6 MiB；query JSON sql 最多 100,000 字元。
- 預設每人同時一個操作、role/database 最多 2 connections、全班同時最多 12 查詢、cluster 最多 50 connections、每人 2 DB、全班 200 DB、100 個空間／帳戶（含 teacher / 停用訪客）。Reset 最多短暫多一個 replacement DB。
- PostgreSQL work_mem 4 MiB / temp_file_limit 64 MiB；Compose CPU/RAM limits。這些**不是每位學生的硬磁碟配額**，亦不是抗惡意多租戶的完整隔離。大量 INSERT 可累積資料；需要主機磁碟監控、定期 reset／備份，公開給不受信任使用者前應改用每人獨立 instance/container 配額。單筆巨大值可能先在 PostgreSQL／driver 產生，再受到 result response cap 限制。
- Cookie HttpOnly、SameSite=Strict，HTTPS 模式 Secure。所有 mutation 要 `X-Lab-Request: 1`；不提供跨 origin CORS，因此跨網站不能偽造已登入寫入請求。Monaco worker/assets 本機打包，不需要 CDN。
- Provisioning control plane 持有 cluster admin credential，僅用於固定程式產生的 DB/role 操作；使用者 SQL 始終以學生 role 執行。此設計依賴 backend 主機可信，不應將 cluster 與其他生產資料共用。
- **只運行 1 個 backend worker / replica**，因為操作 mutex 和全班 query semaphore 在 process 內。不要直接把 `--workers 1` 加大；scale-out 需要外部鎖及共享 rate limiter。

所有上限在 `.env.example`；部分有 hard maximum。更改後 `docker compose up -d --force-recreate backend`。現有 PostgreSQL role connection limit 不會自動重設，應由管理員安排 migration；大幅縮小 DB/user 上限也不會自動刪除現有資料。

## 7. 更新、備份、還原與舊版本遷移

```bash
# 先備份（短暫停止 backend，恢復後學生可重新登入）
python3 scripts/backup.py
# 拉取你已 review 的 GitHub 更新
git pull --ff-only
docker compose up -d --build
docker compose ps
```

備份放 `backups/<UTC timestamp>/`，含 PostgreSQL cluster SQL、SQLite snapshot 及 `.env`。包含機密，請加密保存並複製到另一部機器，不要 commit。備份 script 會在 finally 重新啟動 backend；失敗的備份不要當作完整備份。

還原必須成套恢復：PostgreSQL roles + databases、`platform.sqlite`、原來 `.env` 的 `SECRET_KEY` 與 PostgreSQL 密碼。應先在隔離測試 server 還原驗證。停止 backend，以 PostgreSQL superuser 載入 `cluster.sql`；pg_dumpall 中既有 bootstrap role/database 的 CREATE 衝突需由管理員確認（不要忽略其他 SQL 錯誤）。用維護容器把 SQLite snapshot 放回 platform_data 的 `/data/platform.sqlite`、移除旧 WAL/SHM、owner 設為 UID 10001，再啟動 backend。不要混用不同時間的兩份資料。

`SECRET_KEY` 用於推導學生 DB credential，**不可隨意更換**，否則既有學生 DB 無法登入；需同步更改所有 PostgreSQL role passwords 的專門 migration。POSTGRES_PASSWORD 只在首次初始化 PostgreSQL volume 時套用，改 `.env` 不會自動改現有 DB 密碼。

舊教學 Compose 已啟動過：不要讓此版本直接掛載舊 volume。先備份，選一個全新 project 名称（例如 `docker compose -p sql-lab-v2 up -d --build`；之後所有命令都用相同 `-p`）部署，確認成功後再處理舊環境。舊的共用 `sqllab` database／role 不能直接當作本版本學生資料。

停止：`docker compose down`，named volumes 保留。**`docker compose down -v` 會刪除所有學生資料、帳戶、template 及憑證，只可用在確定可丟棄的測試環境。**

## 8. 開發與檔案

```text
backend/app/        FastAPI、auth、SQLite metadata、SQL policy、PostgreSQL provisioning
backend/app/school.sql    School template seed
backend/tests/      policy + auth/API unit tests
frontend/src/       React/Monaco、學生介面、教師管理
postgres/init/      Cluster initialization SQL
proxy/              Caddy reverse proxy / HTTPS
scripts/            env、backup、HTTP smoke、PostgreSQL isolation checks
.github/workflows/  Docker integration CI
```

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend pytest -q backend/tests
cd frontend
npm ci
npm run build
```

前端 build 有 Monaco bundle 大小提示，屬已知非失敗項目。資料庫 template 首次啟動建立後封存；單改 school.sql 不會覆寫現有 template / 學生資料。更新教材請在備份後於維護時段重建 template，或開新 Compose project 測試，不要在上課期間刪除 template。

Troubleshooting：`docker compose logs --tail=100 backend postgres proxy frontend`。空間在重整後消失／登入後立即失去 session 時檢查 COOKIE_SECURE 與 HTTP/HTTPS 是否吻合。若 upload 被擋，查看 413（size）、400（SQL policy/CSV 格式）、409（同一學生另有操作）、429（忙碌／登入速率）。

參考：[PostgreSQL privileges](https://www.postgresql.org/docs/17/ddl-priv.html)、[Psycopg server cursors](https://www.psycopg.org/psycopg3/docs/advanced/cursors.html)、[Docker Ubuntu](https://docs.docker.com/engine/install/ubuntu/)、[Caddy HTTPS](https://caddyserver.com/docs/automatic-https)。
