# BaSyx Wind-Turbine Digital Twin

A local Eclipse BaSyx digital twin of a wind turbine, combining semantic asset metadata with live
telemetry. The stack runs entirely in Docker and keeps three data planes separate:

| Plane | Contents | Store |
|---|---|---|
| Semantic / asset | AAS shells, submodels, registry, discovery | PostgreSQL, served by `aas-environment` |
| Time series | Wind speed, RPM, power, temperatures, angles | InfluxDB 2.7 |
| Presentation | Browsing and charting of both planes | BaSyx AAS Web UI |

Telemetry never enters the AAS itself. The `TimeSeries` submodel stores only a link to InfluxDB (an
endpoint plus a Flux query), and the UI runs that query when you open the chart.

```
simulator → mosquitto:1883 → telegraf → influxdb:8086 (bucket: wind_turbine)
aas/wind_turbine_aas.json → aas-environment:8082 → postgres
aas-ui:3000 reads aas-environment over REST and influxdb over Flux
```

---

## Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose version`).
- OpenSSL, for generating the local signing key in step 2 of the quick start.
- Free TCP ports on the host: `3000`, `8082`, `8086`, `1883`. All four are configurable in `.env`.

Nothing else needs to be installed. Python, Go, and the databases all run inside containers.

---

## Quick start

1. Copy the environment template. Its defaults work as-is for local development.
   ```bash
   cp .env.example .env
   ```

2. Generate the RSA key that `aas-environment` expects. The repository does not ship one.
   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out basyx/rsa-key.pem
   ```

3. Start the stack.
   ```bash
   docker compose up -d
   docker compose ps
   ```
   Every service should report `running` or `healthy`, except `basyx_configuration`, which is a
   one-shot database initializer and exits with code 0.

4. Open the UI at http://localhost:3000 and chart live telemetry:
   1. Select `WindTurbineAAS` from the AAS list.
   2. Open the `TimeSeries` submodel.
   3. Switch to the **Visualization** tab.
   4. Select the `LinkedSegment`.
   5. Choose y-axis fields, for example `wind_speed`, `power_output`, `rotor_rpm`.
   6. Click **Fetch Data**.

   The chart shows the last 15 minutes of telemetry and extends as the simulator publishes new
   readings. If the stack has only just started, wait a few seconds for the first Telegraf flush.

---

## What's running

| Service | Container | Role | Exposed on |
|---|---|---|---|
| `aas-environment` | `aas-environment` | REST API for shells, submodels, registry, discovery | `8082` |
| `aas-ui` | `aas-web-ui` | Web UI for browsing the AAS and charting telemetry | `3000` |
| `db` | `postgres_db` | Storage for all AAS data | Docker network only |
| `basyx_configuration` | `basyx_configuration` | One-shot schema initializer, exits after setup | Docker network only |
| `influxdb` | `influxdb` | Time-series store for turbine telemetry | `8086` |
| `mosquitto` | `mosquitto` | MQTT broker carrying telemetry messages | `1883` |
| `telegraf` | `telegraf` | Bridge that subscribes to MQTT and writes to InfluxDB | Docker network only |
| `simulator` | `wind-turbine-simulator` | Replays mock telemetry to MQTT at 1 Hz | Docker network only |

### Endpoints

| Endpoint | URL | Access |
|---|---|---|
| AAS REST API | http://localhost:8082 | No authentication |
| AAS Web UI | http://localhost:3000 | No authentication |
| InfluxDB UI | http://localhost:8086 | `INFLUXDB_USERNAME` / `INFLUXDB_PASSWORD`, by default `admin` / `influxpassword` |
| MQTT broker | `localhost:1883` | Anonymous, unencrypted |

---

## The wind turbine AAS

`aas/wind_turbine_aas.json` defines the shell. `aas-environment` loads it at startup from the
preconfiguration directory (`GENERAL_AAS_PRECONFIG_PATHS`), so no manual upload is needed.

| Submodel | Contents |
|---|---|
| `Nameplate` | Manufacturer, product designation, serial number, year of construction, rated power |
| `TechnicalData` | Rated power, rotor diameter, hub height, cut-in / rated / cut-out wind speeds |
| `OperationalState` | Current status, last-updated timestamp, active fault code |
| `TimeSeries` | IDTA time-series model: record metadata plus a `LinkedSegment` holding the InfluxDB endpoint and Flux query |

The telemetry payload carries nine fields: `wind_speed`, `rotor_rpm`, `generator_rpm`,
`power_output`, `nacelle_temp`, `gearbox_oil_temp`, `pitch_angle`, `yaw_angle`, and `status`.
The first eight are numeric and appear in the chart; `status` is a string enum
(`RUNNING`, `IDLE`, `FAULT`, `MAINTENANCE`) stored as a string field in InfluxDB.

---

## Configuration

All settings live in `.env`. `docker-compose.yml` also carries a `${VAR:-default}` fallback for
every variable, so the stack starts even without an `.env` file. To change a value, edit `.env` and
run `docker compose up -d` again; containers pick up new values on restart and no rebuild is needed.

Telegraf expands `${VAR}` references in `telegraf/telegraf.conf` at startup, reading them from the
container environment that Compose populates. Editing `telegraf.conf` directly is not required.

### PostgreSQL (semantic data)

| Variable | Default | Controls |
|---|---|---|
| `POSTGRES_USER` | `admin` | Database username |
| `POSTGRES_PASSWORD` | `admin123` | Database password. Change before any non-local use |
| `POSTGRES_DB` | `basyxTestDB` | Database name created at first start |
| `POSTGRES_HOST` | `db` | Hostname the AAS services connect to |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_MAXOPENCONNECTIONS` | `500` | Connection-pool ceiling for the AAS services |
| `POSTGRES_MAXIDLECONNECTIONS` | `500` | Idle connections kept open |
| `POSTGRES_CONNMAXLIFETIMEMINUTES` | `5` | Minutes before a pooled connection is recycled |

### InfluxDB (telemetry)

| Variable | Default | Controls |
|---|---|---|
| `INFLUXDB_USERNAME` | `admin` | Initial admin user |
| `INFLUXDB_PASSWORD` | `influxpassword` | Initial admin password. Change before any non-local use |
| `INFLUXDB_ORG` | `basyx` | Organization name |
| `INFLUXDB_BUCKET` | `wind_turbine` | Bucket that receives telemetry |
| `INFLUXDB_TOKEN` | dev-only default, see [Security notes](#security-notes) | API token used by Telegraf and the UI |
| `INFLUXDB_HOST` | `influxdb` | Hostname Telegraf writes to |
| `INFLUXDB_PORT` | `8086` | Port, published to the host |
| `INFLUXDB_PUBLIC_ENDPOINT` | `http://localhost:8086` | Browser-reachable URL. Not consumed by any container; it documents the value hardcoded in the AAS, see [Known limitations](#known-limitations) |

### MQTT

| Variable | Default | Controls |
|---|---|---|
| `MQTT_BROKER` | `mosquitto` | Broker hostname used by the simulator and Telegraf |
| `MQTT_PORT` | `1883` | Broker port, published to the host |
| `MQTT_TOPIC` | `WindTurbine/Telemetry` | Topic the simulator publishes to and Telegraf subscribes to |

### Telegraf

| Variable | Default | Controls |
|---|---|---|
| `TELEGRAF_INTERVAL` | `1s` | Agent collection interval |
| `TELEGRAF_FLUSH_INTERVAL` | `10s` | How often buffered points are written to InfluxDB |
| `TELEGRAF_BATCH_SIZE` | `1000` | Points per write batch |
| `TELEGRAF_BUFFER_LIMIT` | `10000` | Points buffered in memory before the oldest are dropped |
| `TELEGRAF_MEASUREMENT` | `wind_turbine_metric` | InfluxDB measurement name |

### AAS services

| Variable | Default | Controls |
|---|---|---|
| `AAS_ENVIRONMENT_PORT` | `8082` | REST API port, on both the host and the container |
| `AAS_GUI_PORT` | `3000` | Web UI port on the host |
| `AAS_EXTERNAL_URL` | `http://localhost:8082` | URL the AAS advertises in registry and discovery entries |

### Simulator

| Variable | Default | Controls |
|---|---|---|
| `SIMULATOR_INTERVAL_SECONDS` | `1` | Seconds between published messages |
| `SIMULATOR_LOG_LEVEL` | `DEBUG` | Python log level; `INFO` quiets the per-message output |

---

## Repository layout

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Service definitions for the whole stack |
| `.env.example` | Environment template. Copy to `.env`, which is gitignored |
| `aas/wind_turbine_aas.json` | The wind turbine AAS, loaded at `aas-environment` startup |
| `basyx-infra.yml` | Backend endpoints and security mode for the AAS Web UI |
| `basyx/rsa-key.pem` | JWS signing key. Gitignored; generate it locally, see [Security notes](#security-notes) |
| `simulator/simulate.py` | MQTT publisher that replays the mock telemetry CSV |
| `simulator/data/wind_turbine_mock.csv` | 180 rows of mock telemetry, 10 columns, replayed on a loop |
| `simulator/Dockerfile` | Python 3.12 image for the simulator |
| `telegraf/telegraf.conf` | MQTT consumer input and InfluxDB v2 output |
| `mosquitto/config/mosquitto.conf` | Broker config: listener on 1883, anonymous access, file logging |
| `mosquitto/data/`, `mosquitto/log/` | Broker persistence and logs |
| `influxdb/data/` | InfluxDB data directory |

---

## Verify the pipeline

Run these four checks in order. Each one covers a different hop, so the first failure tells you
where the pipeline broke.

```bash
# 1. Simulator -> Mosquitto: one JSON message per second. Ctrl-C to stop.
docker exec -it mosquitto mosquitto_sub -t "WindTurbine/Telemetry" -v
# Expect: WindTurbine/Telemetry {"timestamp": "...", "wind_speed": 7.1, "power_output": 598.6, ...}

# 2. Telegraf -> InfluxDB: batched writes, no E! lines.
docker logs telegraf --tail 50 | grep -i "wrote"
# Expect: "Wrote batch of N metrics in ..."

# 3. InfluxDB is up.
curl http://localhost:8086/health
# Expect: {"name":"influxdb","message":"ready for queries and writes","status":"pass",...}

# 4. The AAS is loaded.
curl http://localhost:8082/shells
# Expect: a JSON result array containing WindTurbineAAS
```

---

## Troubleshooting

### A service will not start

```bash
docker compose ps
docker compose logs <service>     # e.g. aas-environment, telegraf, simulator
```

If `aas-environment` exits immediately, confirm `basyx/rsa-key.pem` exists. The container mounts it
read-only and fails to start when the path is missing.

### No MQTT messages

Check the simulator. It waits for the broker's health check before connecting, so a broker failure
shows up here first.

```bash
docker logs wind-turbine-simulator
docker logs mosquitto
```

### Messages reach MQTT but no data lands in InfluxDB

```bash
docker logs telegraf --tail 30
```

Look for connection errors to `mosquitto:1883` or `influxdb:8086`, and for JSON parse errors. A
token mismatch between `.env` and the running InfluxDB container is the most common cause: InfluxDB
only applies `INFLUXDB_TOKEN` on first initialization, so changing it later without wiping
`influxdb/data/` leaves the old token in force.

### The Visualization tab shows no data

1. Open the InfluxDB UI at http://localhost:8086 and use Data Explorer to confirm points exist in
   bucket `wind_turbine`, measurement `wind_turbine_metric`, over `range(start: -1h)`.
2. If the bucket is empty, wait one `TELEGRAF_FLUSH_INTERVAL` (10 seconds by default) and retry.
3. If the bucket has data but the chart does not, check that the `Endpoint` and `Query` properties
   in the `TimeSeries` submodel still match your `.env` values. See [Known limitations](#known-limitations).
4. The Flux query looks back 15 minutes. If the stack just started, give it a few cycles.

### Cannot log into the InfluxDB UI

Use `INFLUXDB_USERNAME` and `INFLUXDB_PASSWORD` from `.env`, by default `admin` and
`influxpassword`. Like the token, these are only applied when the InfluxDB data directory is first
created.

---

## Known limitations

### AAS values that need manual syncing

The AAS is a static JSON file with no template engine, so three values in the `TimeSeries`
submodel's `LinkedSegment` duplicate settings from `.env` and must be kept in sync by hand:

| Property | Current value | Must match |
|---|---|---|
| `Endpoint` | `http://localhost:8086/api/v2/query?org=basyx` | `INFLUXDB_PUBLIC_ENDPOINT` + `/api/v2/query?org=` + `INFLUXDB_ORG` |
| `Query` | Flux query over bucket `wind_turbine`, measurement `wind_turbine_metric` | `INFLUXDB_BUCKET` and `TELEGRAF_MEASUREMENT` |
| `SamplingInterval` | `1000` (ms) | `SIMULATOR_INTERVAL_SECONDS` × 1000 |

The `Endpoint` must stay browser-reachable. The Flux query runs client-side in the UI, so it needs
the published `localhost` address rather than the `influxdb` Docker service name.

If you change any of `INFLUXDB_PUBLIC_ENDPOINT`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`,
`TELEGRAF_MEASUREMENT`, or `SIMULATOR_INTERVAL_SECONDS`, edit the matching properties in
`aas/wind_turbine_aas.json` and then reload the AAS, either by restarting `aas-environment` or by
re-uploading the file through the UI.

### Other gaps

- **No authentication.** `ABAC_ENABLED=false` and `basyx-infra.yml` sets `security.type: none`.
  This is deliberate for a local sandbox and is not configurable through `.env`.
- **No real sensor ingestion.** Telemetry comes from a CSV replay. Swapping in a real source is
  described under [Extending the stack](#extending-the-stack).
- **No 3D visualization.** Charting is limited to the time-series plots the AAS Web UI provides.

---

## Security notes

This stack is built for a single local machine. Do not expose it to a public network.

### Local development

- `.env` is gitignored, so local credentials are never committed.
- `.env.example` ships development-only defaults (PostgreSQL `admin123`, InfluxDB
  `influxpassword`, and a fixed InfluxDB token) so the stack runs immediately on `localhost`.
  Treat all three as public.
- `basyx/rsa-key.pem` is gitignored and not distributed. Generate your own before the first run:
  ```bash
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out basyx/rsa-key.pem
  ```
  It is the JWS signing key path for `aas-environment`. With authentication disabled it signs
  nothing, but the file must exist or the container will not start.
- Authentication is disabled end to end, and the MQTT broker accepts anonymous, unencrypted
  connections.

### Before any wider deployment

1. Replace every credential in `.env`: `POSTGRES_PASSWORD`, `INFLUXDB_PASSWORD`, and
   `INFLUXDB_TOKEN`. Generate a new token in the InfluxDB UI, or with `openssl rand -base64 44`
   before first start.
2. Enable authentication. This is not configured here; it requires switching `basyx-infra.yml` to
   an OAuth2 security type, adding an identity provider, and turning on ABAC in `aas-environment`.
3. Terminate TLS at a reverse proxy such as nginx or Caddy, and stop publishing container ports
   directly.
4. Restrict network access to ports 8082, 3000, 8086, and 1883, and set `allow_anonymous false`
   with a password file in `mosquitto/config/mosquitto.conf`.
5. Keep images current: `docker compose pull && docker compose up -d --force-recreate`.

---

## Data persistence

| Data | Location | Survives `docker compose down` |
|---|---|---|
| AAS and metadata | Anonymous Docker volume on the `db` container | Yes, unless you pass `-v` |
| Telemetry | `./influxdb/data/` bind mount | Yes |
| Broker state and logs | `./mosquitto/data/`, `./mosquitto/log/` bind mounts | Yes |

Back up the telemetry directory and dump the database:

```bash
docker exec postgres_db pg_dump -U admin basyxTestDB > backup.sql
tar czf influxdb-backup.tar.gz ./influxdb/data
```

To reset everything and start from empty stores:

```bash
docker compose down -v
sudo rm -rf ./influxdb/data ./mosquitto/data ./mosquitto/log
docker compose up -d
```

`sudo` is needed because InfluxDB and Mosquitto write into the bind mounts as their own container
users. Keep `mosquitto/config/` in place; deleting it removes the broker configuration.

---

## Extending the stack

- **Change the model.** Edit `aas/wind_turbine_aas.json` to add submodels or properties, then
  restart `aas-environment`. You can also upload a shell through the UI or `POST /shells`.
- **Use real sensors.** Replace the `simulator` service with any publisher (an OPC UA or Modbus
  gateway, or a custom MQTT client) that emits the same JSON payload on `MQTT_TOPIC`. Telegraf and
  InfluxDB need no changes.
- **Change the telemetry rate.** Set `SIMULATOR_INTERVAL_SECONDS` in `.env`, run
  `docker compose up -d simulator`, then update `SamplingInterval` in the AAS to match, in
  milliseconds.
- **Tune ingestion throughput.** `TELEGRAF_BATCH_SIZE`, `TELEGRAF_BUFFER_LIMIT`, and
  `TELEGRAF_FLUSH_INTERVAL` govern write behaviour under higher message rates.

---

## License

MIT. This project extends the
[Eclipse BaSyx starter kit](https://github.com/eclipse-basyx/basyx-applications/tree/main/basyx-starter-kit).
See `LICENSE` in the repository root.
