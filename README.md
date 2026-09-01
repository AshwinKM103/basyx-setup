# BaSyx Wind-Turbine Digital Twin

A complete local Eclipse BaSyx digital-twin stack for a wind turbine, combining semantic asset metadata with real-time telemetry data. The system separates concerns into three data planes: the AAS (Asset Administration Shell) served from PostgreSQL, time-series telemetry in InfluxDB, and a web UI that reads both.

**Everything runs in Docker.** No dependencies to install—just Docker, `.env`, and `docker compose up`.

---

## Quick Start (3 minutes)

1. **Copy the environment template** (it has working defaults for local development):
   ```bash
   cp .env.example .env
   ```

2. **Start the stack**:
   ```bash
   docker compose up -d
   docker compose ps
   ```
   All services should be running or healthy. `basyx_configuration` is a one-shot job—it runs once at startup and exits with code 0.

3. **Open the UI** and fetch live data:
   - Open http://localhost:3000
   - Select `WindTurbineAAS` → `TimeSeries` submodel → Visualization tab
   - Select the `LinkedSegment` → pick telemetry fields (e.g., `wind_speed`, `power_output`) → **Fetch Data**

That's it. No manual configuration needed for local development.

---

## What's Running

The stack combines three independent data planes:

| Service | Purpose | Port/Transport |
|---------|---------|---|
| **AAS Environment** (`aas-environment`) | REST API serving the Asset Administration Shell, submodels, and registry | HTTP `8082` |
| **AAS Web UI** (`aas-ui`) | Interactive UI for browsing the AAS and visualizing telemetry | HTTP `3000` |
| **PostgreSQL** (`db`) | Storage for all AAS data (shells, submodels, assets) | Internal (Docker network) |
| **InfluxDB** (`influxdb`) | Time-series database for wind-turbine telemetry readings | HTTP `8086` |
| **Mosquitto** (`mosquitto`) | MQTT broker for live telemetry messages | TCP `1883` |
| **Telegraf** (`telegraf`) | Bridge: reads MQTT, writes to InfluxDB | Internal (Docker network) |
| **Simulator** (`simulator`) | Replays mock wind-turbine CSV data to MQTT at 1 Hz | Internal (Docker network) |

**Data flow**: Simulator (Python) → MQTT (Mosquitto) → Telegraf → InfluxDB (bucket: `wind_turbine`)

---

## Environment Configuration (`.env`)

All configuration is externalized to environment variables. The template `.env.example` documents the defaults; `docker-compose.yml` reads `.env` automatically and provides fallbacks for every variable, so the stack starts even without `.env`.

To override any value, edit `.env` and re-run `docker compose up -d`. Containers pick up new values on restart; no rebuild needed.

### Configuration Variables

#### PostgreSQL (Semantic Data)

| Variable | Default | What it controls | Change when | Used by |
|----------|---------|------------------|-------------|---------|
| `POSTGRES_USER` | `admin` | PostgreSQL admin username | Using a different user in production | `db`, `aas-environment`, `basyx_configuration` |
| `POSTGRES_PASSWORD` | `admin123` | PostgreSQL admin password | **Always change before production** | `db`, `aas-environment`, `basyx_configuration` |
| `POSTGRES_DB` | `basyxTestDB` | Initial database name | You want a different db name | `db`, `aas-environment`, `basyx_configuration` |
| `POSTGRES_HOST` | `db` | PostgreSQL host (internal Docker name) | Running PostgreSQL on a separate host | `aas-environment`, `basyx_configuration` |
| `POSTGRES_PORT` | `5432` | PostgreSQL port | PostgreSQL runs on a different port | `aas-environment`, `basyx_configuration` |
| `POSTGRES_MAXOPENCONNECTIONS` | `500` | Max open DB connections from AAS services | Under high concurrent load (tuning, not typical) | `aas-environment`, `basyx_configuration` |
| `POSTGRES_MAXIDLECONNECTIONS` | `500` | Max idle connections held open | Reducing memory under low load | `aas-environment`, `basyx_configuration` |
| `POSTGRES_CONNMAXLIFETIMEMINUTES` | `5` | Max lifetime (minutes) before a connection is closed | Enforcing connection recycling for long-lived deployments | `aas-environment`, `basyx_configuration` |

#### InfluxDB (Time-Series Telemetry)

| Variable | Default | What it controls | Change when | Used by |
|----------|---------|------------------|-------------|---------|
| `INFLUXDB_USERNAME` | `admin` | InfluxDB admin username | Using a different user in production | `influxdb` |
| `INFLUXDB_PASSWORD` | `influxpassword` | InfluxDB admin password | **Always change before production** | `influxdb` |
| `INFLUXDB_ORG` | `basyx` | InfluxDB organization name | You want a different org name | `influxdb`, `telegraf` |
| `INFLUXDB_BUCKET` | `wind_turbine` | InfluxDB bucket (data storage) | You want a different bucket name for telemetry | `influxdb`, `telegraf` |
| `INFLUXDB_TOKEN` | (see Security notes) | API token for programmatic access to InfluxDB | **Always rotate before production** | `influxdb`, `telegraf`, `aas-ui` |
| `INFLUXDB_HOST` | `influxdb` | InfluxDB hostname (internal Docker name) | InfluxDB runs on a separate host | `telegraf` (internal) |
| `INFLUXDB_PORT` | `8086` | InfluxDB port | InfluxDB runs on a different port | `telegraf` (internal) |
| `INFLUXDB_PUBLIC_ENDPOINT` | `http://localhost:8086` | Public URL for the AAS UI to query InfluxDB | InfluxDB is behind a proxy or on a different host | Documentation reference only; **⚠️ see Known Limitations** |

#### MQTT (Telemetry Transport)

| Variable | Default | What it controls | Change when | Used by |
|----------|---------|------------------|-------------|---------|
| `MQTT_BROKER` | `mosquitto` | MQTT broker hostname (internal Docker name) | Broker runs on a separate host | `simulator`, `telegraf` |
| `MQTT_PORT` | `1883` | MQTT broker port | Broker runs on a different port | `simulator`, `telegraf` |
| `MQTT_TOPIC` | `WindTurbine/Telemetry` | MQTT topic for telemetry messages | Publishing to a different topic name | `simulator`, `telegraf` |

#### Telegraf (Data Bridge)

| Variable | Default | What it controls | Change when | Used by |
|----------|---------|------------------|-------------|---------|
| `TELEGRAF_INTERVAL` | `1s` | Collection interval (read MQTT, sample time-series) | You want coarser or finer granularity | `telegraf` |
| `TELEGRAF_FLUSH_INTERVAL` | `10s` | Batch flush interval (write to InfluxDB) | Reducing latency or write pressure | `telegraf` |
| `TELEGRAF_BATCH_SIZE` | `1000` | Points per InfluxDB write batch | Tuning write throughput under high volume | `telegraf` |
| `TELEGRAF_BUFFER_LIMIT` | `10000` | Max points to buffer in memory before dropping | Handling MQTT spikes without data loss | `telegraf` |
| `TELEGRAF_MEASUREMENT` | `wind_turbine_metric` | InfluxDB measurement name (time-series table) | You want a different measurement name | `telegraf` |

#### AAS (Asset Administration Shell)

| Variable | Default | What it controls | Change when | Used by |
|----------|---------|------------------|-------------|---------|
| `AAS_ENVIRONMENT_PORT` | `8082` | AAS REST API port (HTTP) | Port 8082 is already in use | `aas-environment` |
| `AAS_GUI_PORT` | `3000` | Web UI port (HTTP) | Port 3000 is already in use | `aas-ui` |
| `AAS_EXTERNAL_URL` | `http://localhost:8082` | URL for AAS Environment (used by discovery) | AAS is behind a proxy or reverse-proxy | `aas-environment` |

#### Simulator

| Variable | Default | What it controls | Change when | Used by |
|----------|---------|------------------|-------------|---------|
| `SIMULATOR_INTERVAL_SECONDS` | `1` | Time between MQTT messages from the simulator (seconds) | You want faster or slower mock data replay | `simulator` |

### How Telegraf Reads These Variables

Telegraf expands `${VAR}` references in `telegraf/telegraf.conf` automatically at process start. The references are resolved from the Telegraf container's environment, which `docker-compose.yml` populates from `.env`. Every `${VAR}` in the config file has a `:-default` fallback in the compose file, so edits to `telegraf.conf` are not needed.

---

## Endpoints

Once the stack is running, access services at:

| Service | URL | Credentials / Notes |
|---------|-----|---|
| **AAS REST API** | http://localhost:8082 | No auth required (dev mode) |
| **AAS Web UI** | http://localhost:3000 | No auth required (dev mode) |
| **InfluxDB UI** | http://localhost:8086 | Username: `admin`, Password: from `INFLUXDB_PASSWORD` in `.env` (default `influxpassword`) |
| **MQTT Broker** | `localhost:1883` | Anonymous, no auth |

---

## Wind Turbine AAS

The Wind Turbine Asset Administration Shell is defined in `aas/wind_turbine_aas.json` and is loaded automatically when `aas-environment` starts (via `GENERAL_AAS_PRECONFIG_PATHS`).

The AAS contains four submodels:

- **Nameplate**: Manufacturer, serial number, rated power output
- **TechnicalData**: Rotor diameter, hub height, cut-in/rated/cut-out wind speeds
- **OperationalState**: Current status, last-updated timestamp, fault codes
- **TimeSeries** (IDTA standard): A `LinkedSegment` that points to InfluxDB and a Flux query to fetch live telemetry data

### Viewing Telemetry

1. Open http://localhost:3000
2. Select `WindTurbineAAS` from the AAS list
3. Click the `TimeSeries` submodel
4. Go to the **Visualization** tab
5. Select the `LinkedSegment`
6. Choose y-axis values (e.g., `wind_speed`, `power_output`, `rotor_rpm`)
7. Click **Fetch Data**

You should see a time-series graph of the past 15 minutes of wind-turbine telemetry, updated in real-time as the simulator publishes new data.

---

## Verify the Pipeline

Run these commands to confirm the telemetry pipeline is working end-to-end:

```bash
# 1. Check that MQTT messages are flowing (Simulator → Mosquitto)
docker exec -it mosquitto mosquitto_sub -t "WindTurbine/Telemetry" -v
# Expected: one message per second, e.g.
#   WindTurbine/Telemetry {"wind_speed": 12.5, "power_output": 450, ...}

# 2. Check Telegraf is writing to InfluxDB (Telegraf logs)
docker logs telegraf --tail 50 | grep -E "Wrote|wrote"
# Expected: log lines saying "Wrote batch of NNN points to influxdb" with no E! errors

# 3. Check InfluxDB health
curl http://localhost:8086/health
# Expected: {"status":"pass","checks":{},...}

# 4. Check AAS is loaded and accessible
curl http://localhost:8082/shells
# Expected: JSON array with WindTurbineAAS listed
```

If any of these fail:
- **No MQTT messages**: Check that `simulator` container is running (`docker logs simulator`).
- **Telegraf errors**: Check `docker logs telegraf` for connection issues to MQTT or InfluxDB.
- **InfluxDB unhealthy**: Verify `INFLUXDB_USERNAME` and `INFLUXDB_PASSWORD` are correct in `.env`.
- **AAS not loaded**: Check `docker logs aas-environment` for errors loading the JSON file.

---

## Known Limitations: Hardcoded AAS JSON Values

The AAS is stored as static JSON (`aas/wind_turbine_aas.json`) and has no template engine. Three values in the `TimeSeries` submodel's `LinkedSegment` are hardcoded and must be kept in sync with `.env` **by hand** if you change the defaults:

### What's Hardcoded

1. **`Endpoint`** property
   - Current value: `http://localhost:8086/api/v2/query?org=basyx`
   - Must match: `INFLUXDB_PUBLIC_ENDPOINT` + `?org=${INFLUXDB_ORG}`
   - Why not automated: The AAS is a portable asset file; templating would introduce tooling lock-in.

2. **`Query`** property (embedded Flux query)
   - Hardcoded references:
     - Bucket: `"wind_turbine"` → must match `INFLUXDB_BUCKET`
     - Measurement: `"wind_turbine_metric"` → must match `TELEGRAF_MEASUREMENT`
     - Time range: `-15m` (last 15 minutes)
     - Aggregation window: `2s`
     - Field list: 8 telemetry fields (wind_speed, power_output, rotor_rpm, etc.)
   - Why not automated: The query logic lives in the UI plugin, not the AAS. Re-templating would split concerns.

3. **`SamplingInterval`** property
   - Current value: `1000` (milliseconds)
   - Must match: `SIMULATOR_INTERVAL_SECONDS * 1000`
   - Why not automated: The UI plugin uses this to advise on time-series fetch granularity; it's metadata, not configuration.

### What to Do If You Change Defaults

If you change `INFLUXDB_BUCKET`, `INFLUXDB_ORG`, `TELEGRAF_MEASUREMENT`, or `SIMULATOR_INTERVAL_SECONDS` from their defaults:

1. Edit the three values in `aas/wind_turbine_aas.json` to match your new defaults
2. Restart `aas-environment`, or re-upload the AAS through the UI (`aas-ui` → Upload AAS)

The alternative (dynamic query building in the TimeSeries UI plugin) was evaluated and deferred—it adds complexity to the UI without solving the core problem (the JSON format itself cannot embed conditionals).

---

## Security Notes

### For Local Development

- `.env` is **gitignored**. The `.env` file you create locally is never committed.
- `.env.example` ships with default development credentials (PostgreSQL `admin123`, InfluxDB `influxpassword`, a dev-only InfluxDB token) so the stack works immediately on `localhost`.
- **Authentication is disabled end-to-end**: `ABAC_ENABLED=false`, and the AAS UI runs with `security: type: none`. This is intentional for a local sandbox.

### Before Production

**Do not run this stack on a public network or the internet.** If you must:

1. **Rotate all secrets in `.env`**:
   - `POSTGRES_PASSWORD`: Use a strong password (20+ chars, random)
   - `INFLUXDB_PASSWORD`: Use a strong password (20+ chars, random)
   - `INFLUXDB_TOKEN`: Generate a new token in the InfluxDB UI

2. **Enable authentication**:
   - The project README does not document authentication setup (it is deferred). Enabling OIDC/Keycloak is a separate task that requires changes to `basyx-infra.yml` and new configuration files.
   - If you do enable it, review the architecture guide for details.

3. **Use HTTPS**:
   - Put the stack behind a reverse proxy (nginx, Caddy) that terminates TLS.
   - Never expose the services directly to the internet over HTTP.

4. **Restrict network access**:
   - Only allow traffic from trusted IPs to ports 8082, 3000, 8086, 1883.
   - Disable Mosquitto anonymous access (`allow_anonymous false` in `mosquitto/config/mosquitto.conf`).

5. **Run security scans**:
   - Update all Docker images regularly: `docker compose pull && docker compose up -d --force-recreate`
   - Scan for vulnerable dependencies in Python and Go packages.

---

## Data Persistence

- **PostgreSQL data** (AAS/metadata): Stored in the `db` container's default volume. Persists across `docker compose down` (without `-v`).
- **InfluxDB data** (telemetry): Stored in `./influxdb/data/` (bind-mounted volume). Persists across restarts.
- **Mosquitto state** (broker logs, subscriptions): Stored in `./mosquitto/` (bind-mounted volume). Persists across restarts.

To wipe all data and start fresh:
```bash
docker compose down -v
rm -rf ./influxdb/data ./mosquitto
docker compose up -d
```

---

## Files and Directories

| File/Directory | Purpose |
|---|---|
| `.env.example` | Template for environment variables (commit this) |
| `.env` | Your local environment config (gitignored, do not commit) |
| `docker-compose.yml` | Service definitions and container orchestration |
| `aas/wind_turbine_aas.json` | Asset Administration Shell definition (loaded at startup) |
| `basyx-infra.yml` | AAS UI backend configuration (endpoint discovery, auth) |
| `basyx/rsa-key.pem` | RSA private key (unused in dev mode, generated during initial setup) |
| `simulator/simulate.py` | Python script that replays telemetry CSV over MQTT |
| `simulator/data/wind_turbine_mock.csv` | Mock wind-turbine telemetry data (8 columns, 1440 rows, 1-hour recording) |
| `telegraf/telegraf.conf` | Telegraf config: MQTT consumer → InfluxDB writer |
| `mosquitto/config/mosquitto.conf` | Mosquitto MQTT broker config |
| `influxdb/data/` | InfluxDB data directory (persists telemetry across restarts) |
| `mosquitto/` | Mosquitto state directory (persists broker data) |

---

## Common Questions

**Q: Can I use real sensor data instead of the simulator?**

A: Yes. Replace the simulator container with your own data source (OPC UA, Modbus, direct HTTP polling, or a custom MQTT publisher). Telegraf's MQTT consumer and InfluxDB output remain unchanged. You only need to ensure messages arrive on the `MQTT_TOPIC` in the same JSON format.

**Q: How do I change the telemetry refresh rate in the UI?**

A: Edit `SIMULATOR_INTERVAL_SECONDS` in `.env` (default `1` = one message per second). Restart the simulator: `docker compose up -d simulator`. Also update `SamplingInterval` in `aas/wind_turbine_aas.json` (value in milliseconds) to match, then restart `aas-environment`.

**Q: Can I add more submodels to the AAS?**

A: Yes. Add new submodels to `aas/wind_turbine_aas.json` or upload a new AAS file through the UI. The `aas-environment` REST API (`POST /shells`) can also be used to programmatically create submodels.

**Q: How do I back up the data?**

A: Backup `./influxdb/data/` (telemetry) and the PostgreSQL database using `docker exec db pg_dump`:
```bash
docker exec db pg_dump -U admin basyxTestDB > backup.sql
tar czf influxdb-backup.tar.gz ./influxdb/data
```

**Q: Why is the UI showing "No data" even though the simulator is running?**

A: Check (1) that the `TimeSeries` submodel's `Endpoint` and `Query` match your current `.env` values (especially `INFLUXDB_ORG`, `INFLUXDB_BUCKET`, `TELEGRAF_MEASUREMENT`); (2) that Telegraf logs show "Wrote batch"; (3) that the time range in the Flux query is not too narrow (default is `-15m`—if the simulator just started, wait 2-3 cycles and try again).

---

## Troubleshooting

### Service won't start or is crashing

```bash
# Check service status and logs
docker compose ps
docker logs <service_name>
```

### MQTT messages not reaching InfluxDB

```bash
# Verify MQTT topic and format
docker exec -it mosquitto mosquitto_sub -t "WindTurbine/Telemetry" -v | head -5

# Check Telegraf can parse the JSON
docker logs telegraf | tail -30
```

### InfluxDB queries fail (no data in Visualization tab)

1. Open InfluxDB UI (http://localhost:8086 → Data Explorer)
2. Select bucket `wind_turbine`, measurement `wind_turbine_metric`
3. Check if any points exist: `|> range(start: -1h)`
4. If no points, wait 10 seconds and try again (Telegraf batches writes every `TELEGRAF_FLUSH_INTERVAL`)
5. If still empty, check `docker logs telegraf` for write errors

### Can't log into InfluxDB UI

Check that `INFLUXDB_USERNAME` and `INFLUXDB_PASSWORD` in `.env` are set correctly. Default is `admin` / `influxpassword`.

---

## Next Steps

- **Customize the Wind Turbine model**: Edit `aas/wind_turbine_aas.json` to add/remove submodels or properties
- **Connect real sensors**: Replace the simulator with your own MQTT publisher or OPC UA gateway
- **Add authentication**: See the architecture guide for Keycloak/OIDC/ABAC setup (deferred from this baseline)
- **Scale telemetry ingestion**: Tune `TELEGRAF_BATCH_SIZE`, `TELEGRAF_BUFFER_LIMIT`, and InfluxDB retention policies for high-volume scenarios

---

## License

This project extends the [Eclipse BaSyx starter kit](https://github.com/eclipse-basyx/basyx-applications/tree/main/basyx-starter-kit). See LICENSE in the repository root.
