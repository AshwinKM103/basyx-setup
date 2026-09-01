# BaSyx Setup — Wind-Turbine Digital Twin

Local Eclipse BaSyx Go stack plus a wind-turbine time-series telemetry pipeline. See
`CLAUDE.md` for the architecture summary.

## Start

1. Open a terminal in this folder.
2. Create your `.env` from the template (working defaults, no edits required for local use):
```
cp .env.example .env
```
3. Start the stack:
```
docker compose up -d
docker compose ps
```
`basyx_configuration` is a one-shot job and should exit with code 0; the rest should be
running/healthy.

## Configuration (`.env`)

All secrets, ports, hostnames, and tuning values are externalized to environment variables.
`docker-compose.yml` reads `.env` automatically (docker compose's default behavior) and every
variable also has a `${VAR:-default}` fallback baked into the compose file, so the stack still
starts even with no `.env` present at all — `.env.example` documents the same defaults for
reference and is the template to copy from.

| Variable | Default | Used by |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `admin` / `admin123` / `basyxTestDB` | `db`, `aas-environment`, `basyx_configuration` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `db` / `5432` | `aas-environment`, `basyx_configuration` |
| `POSTGRES_MAXOPENCONNECTIONS` / `POSTGRES_MAXIDLECONNECTIONS` / `POSTGRES_CONNMAXLIFETIMEMINUTES` | `500` / `500` / `5` | `aas-environment`, `basyx_configuration` |
| `INFLUXDB_TOKEN` | (dev-only default token, see Security notes) | `influxdb`, `telegraf`, `aas-ui` |
| `INFLUXDB_USERNAME` / `INFLUXDB_PASSWORD` | `admin` / `influxpassword` | `influxdb` |
| `INFLUXDB_ORG` / `INFLUXDB_BUCKET` | `basyx` / `wind_turbine` | `influxdb`, `telegraf` |
| `INFLUXDB_HOST` / `INFLUXDB_PORT` | `influxdb` / `8086` | `telegraf` (internal docker network) |
| `INFLUXDB_PUBLIC_ENDPOINT` | `http://localhost:8086` | documentation only — see AAS JSON limitation below |
| `MQTT_BROKER` / `MQTT_PORT` / `MQTT_TOPIC` | `mosquitto` / `1883` / `WindTurbine/Telemetry` | `simulator`, `telegraf` |
| `SIMULATOR_INTERVAL_SECONDS` | `1` | `simulator` |
| `TELEGRAF_INTERVAL` / `TELEGRAF_FLUSH_INTERVAL` | `1s` / `10s` | `telegraf` |
| `TELEGRAF_BATCH_SIZE` / `TELEGRAF_BUFFER_LIMIT` | `1000` / `10000` | `telegraf` |
| `TELEGRAF_MEASUREMENT` | `wind_turbine_metric` | `telegraf` |
| `AAS_ENVIRONMENT_PORT` / `AAS_GUI_PORT` | `8082` / `3000` | `aas-environment`, `aas-ui` |
| `AAS_EXTERNAL_URL` | `http://localhost:8082` | `aas-environment` |

To override any value, edit `.env` and re-run `docker compose up -d` (compose picks up the new
values on container recreation; no rebuild needed except for `simulator`, which bakes nothing
special into its image — env vars are injected at container start).

### Telegraf and environment variables

Telegraf natively expands `${VAR}` references in `telegraf/telegraf.conf` at process start (no
wrapper/envsubst step required) — it reads them from its own process environment, which
`docker-compose.yml` populates for the `telegraf` service via that service's `environment:`
block (itself sourced from `.env`). Every `${VAR}` used in `telegraf.conf` has a matching
`environment:` entry with a `:-default` fallback in `docker-compose.yml`, so `telegraf.conf`
itself never needs manual edits.

### Known limitation: `aas/wind_turbine_aas.json`

The AAS JSON is static data loaded once at `aas-environment` startup — it has no template
engine and cannot reference `.env` variables directly. Three values in the `TimeSeries`
submodel's `LinkedSegment` are literal and must be kept in sync with `.env` **by hand** if you
change the corresponding defaults:

- `Endpoint` property — currently `http://localhost:8086/api/v2/query?org=basyx`. Must match
  `INFLUXDB_PUBLIC_ENDPOINT` + `?org=${INFLUXDB_ORG}`.
- `Query` property — the embedded Flux query hardcodes `bucket: "wind_turbine"`,
  `_measurement == "wind_turbine_metric"`, the `-15m` range, the `2s` aggregation window, and
  the list of 8 telemetry fields. These must match `INFLUXDB_BUCKET`, `TELEGRAF_MEASUREMENT`,
  and the simulator's CSV columns respectively.
- `SamplingInterval` property (`1000`, milliseconds) — must match
  `SIMULATOR_INTERVAL_SECONDS * 1000`.

If you change `INFLUXDB_BUCKET`, `INFLUXDB_ORG`, `TELEGRAF_MEASUREMENT`, or
`SIMULATOR_INTERVAL_SECONDS` from their defaults, edit these three values in
`aas/wind_turbine_aas.json` to match, then restart `aas-environment` (or re-upload the AAS
through the UI). This was intentionally not automated: the JSON is meant to stay a plain,
portable AAS file per the project's `CLAUDE.md` (no structural changes, no templating engine
introduced into the AAS format) — see `HARDCODED_VALUES_AUDIT.md` for the tradeoffs considered
(e.g. dynamic query building in the Time Series UI plugin) and why they were deferred.

### Security notes

- `.env` is gitignored — never commit real secrets in it. `.env.example` ships with the
  project's current *local-only development* InfluxDB token and PostgreSQL password purely so
  the stack works out-of-the-box on `localhost`; rotate both before this stack is ever exposed
  beyond your own machine.
- This is a prototype/sandbox setup — authentication is disabled end-to-end (see `CLAUDE.md` §Auth).
  Do not point it at anything but `localhost`.

## Endpoints

- AAS Environment (REST API): http://localhost:8082
- AAS Web UI: http://localhost:3000
- InfluxDB UI: http://localhost:8086 (user/password from `INFLUXDB_USERNAME` / `INFLUXDB_PASSWORD`
  in `.env`, default `admin` / `influxpassword`)
- MQTT broker: `localhost:1883`

## What's running

- **BaSyx Go**: `aas-environment`, `basyx_configuration`, `db` (PostgreSQL), `aas-ui` — semantic/asset
  data (AAS, submodels, registry, discovery).
- **Telemetry pipeline**: `simulator` (Python, replays `simulator/data/wind_turbine_mock.csv`
  over MQTT at 1 Hz) → `mosquitto` (MQTT broker) → `telegraf` (MQTT → InfluxDB) → `influxdb`
  (bucket `wind_turbine`).

## Wind Turbine AAS

`aas/wind_turbine_aas.json` is loaded automatically on `aas-environment` startup
(`GENERAL_AAS_PRECONFIG_PATHS`). It contains:

- `Nameplate` — manufacturer, serial number, rated power.
- `TechnicalData` — rotor diameter, hub height, cut-in/cut-out/rated wind speed.
- `OperationalState` — current status, last-updated timestamp, fault code.
- `TimeSeries` (IDTA `https://admin-shell.io/idta/TimeSeries/1/1`) — a `LinkedSegment`
  pointing at the InfluxDB `wind_turbine` bucket via a Flux query, plus the metadata record
  describing the available telemetry variables.

To view live telemetry: open http://localhost:3000 → select `WindTurbineAAS` → `TimeSeries`
submodel → Visualization tab → select the `LinkedSegment` → pick y-values (e.g. `wind_speed`,
`power_output`) → **Fetch Data**.

## Verify the pipeline

```
docker exec -it mosquitto mosquitto_sub -t "WindTurbine/Telemetry" -v   # a message every ~1s
docker logs telegraf --tail 50                                          # "Wrote batch", no E!
curl http://localhost:8086/health                                       # {"status":"pass", ...}
curl http://localhost:8082/shells                                       # WindTurbineAAS listed
```

## Notes

- The generated setup includes a sample RSA private key at `basyx/rsa-key.pem`.
- Infrastructure connections for the UI are defined in `basyx-infra.yml`.
- Place additional AAS files into the `aas/` folder or upload through the UI.
- InfluxDB data persists in `./influxdb/data`; Mosquitto data/logs persist in `./mosquitto/`.
- Authentication is disabled (`security: type: none`, `ABAC_ENABLED=false`). See the guide's
  §8 for how to add Keycloak/OIDC/ABAC later.
