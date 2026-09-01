# basyx-setup — Local Wind-Turbine Digital Twin

## What this project is

A local Eclipse BaSyx Go digital-twin stack for a wind turbine, extended from the original
minimal BaSyx starter kit. The architecture and every design decision here follow
`Local Wind-Turbine Digital Twin with Eclipse BaSyx — Research and Implementation Guide.md`
in this directory — treat that file as the spec. Do not redesign the architecture or swap
technologies without updating the guide first.

## Architecture (do not change without reason)

Three separate data planes, kept separate on purpose (see guide §4.4):

- **Semantic/asset data** (AAS shells, submodels, registry, discovery) → PostgreSQL, served by
  `aas-environment` (`eclipsebasyx/aasenvironment-go`) and initialized once by
  `basyx_configuration` (`eclipsebasyx/basyxconfigurationservice-go`).
- **Time-series telemetry** (wind speed, RPM, power, temperatures, angles) → InfluxDB 2.7,
  never PostgreSQL. Ingested via: Python simulator → MQTT (Mosquitto) → Telegraf → InfluxDB.
- **UI/session state** → browser-local / native BaSyx UI (`aas-gui`), reads both other planes.

```
simulator (paho-mqtt, CSV replay) → mosquitto:1883 → telegraf → influxdb:8086 (bucket: wind_turbine)
aas/wind_turbine_aas.json → aas-environment:8082 → postgres_db
aas-gui:3000 reads both aas-environment (REST) and influxdb (Flux, via the TimeSeries submodel's LinkedSegment)
```

## Services (docker-compose.yml)

| Service | Image | Port | Notes |
|---|---|---|---|
| `aas-environment` | `eclipsebasyx/aasenvironment-go:latest` | 8082 | preserved from starter kit |
| `basyx_configuration` | `eclipsebasyx/basyxconfigurationservice-go:latest` | — | one-shot, preserved |
| `db` | `postgres:18` | — | preserved |
| `aas-ui` | `eclipsebasyx/aas-gui:latest` | 3000 | preserved; added `INFLUXDB_TOKEN` |
| `influxdb` | `influxdb:2.7` | 8086 | new — bucket `wind_turbine`, org `basyx` |
| `mosquitto` | `eclipse-mosquitto:2.0.15` | 1883 | new — anonymous access, local only |
| `telegraf` | `telegraf:1.29.1` | — | new — `mqtt_consumer` → `influxdb_v2` output |
| `simulator` | built from `./simulator` | — | new — replays `simulator/data/wind_turbine_mock.csv` over MQTT at 1 Hz |

## Key files

- `aas/wind_turbine_aas.json` — the WindTurbine AAS: Nameplate, TechnicalData, OperationalState,
  and TimeSeries (IDTA `https://admin-shell.io/idta/TimeSeries/1/1`, LinkedSegment pointing at
  InfluxDB) submodels. Loaded automatically via `GENERAL_AAS_PRECONFIG_PATHS`.
- `telegraf/telegraf.conf` — `mqtt_consumer` (topic `WindTurbine/Telemetry`, JSON) →
  `influxdb_v2` output (measurement `wind_turbine_metric`).
- `mosquitto/config/mosquitto.conf` — anonymous, unencrypted, local-only broker.
- `simulator/simulate.py` — CSV-replay MQTT publisher (`paho-mqtt`), 1 Hz.
- `basyx-infra.yml` — `aas-gui` backend endpoints; unchanged from the starter kit (`security: type: none`).

## Auth

Authentication is **disabled** (`ABAC_ENABLED=false`, `security: type: none`). The guide's §8
migration to Keycloak/OIDC/ABAC is documented but intentionally not implemented — do it only if
explicitly asked, and follow guide §8.4 exactly (adds a Keycloak service, `security_env/trustlist.json`,
`security_env/access-rules.json`, and flips `basyx-infra.yml` to `security.type: oauth2`).

## Conventions

- Time-series values NEVER go into the AAS/PostgreSQL — only the `LinkedSegment` config
  (endpoint + Flux query) lives there. Raw readings live only in InfluxDB.
- Static/slow-changing facts (nameplate, technical specs, operational state) are ordinary
  AAS `Property` elements, not telemetry.
- Keep `docker-compose.yml` additions consistent with the reference implementation style
  already used by the Go services (env vars in `SCREAMING_SNAKE_CASE`, named containers,
  `restart: unless-stopped`, healthchecks where the upstream image supports them).
- InfluxDB and Mosquitto data are bind-mounted (`./influxdb/data`, `./mosquitto`) so telemetry
  and broker state survive `docker compose down` (without `-v`), matching PostgreSQL's existing
  persistence behavior.

## Verifying the stack

Reference: guide §5.7, §12 (full validation checklist).

```bash
docker compose up -d
docker compose ps                                   # basyx_configuration should exit 0
curl http://localhost:8082/shells                    # WindTurbine AAS should be listed
curl http://localhost:8086/health                     # {"status":"pass", ...}
docker exec -it mosquitto mosquitto_sub -t "WindTurbine/Telemetry" -v   # messages every ~1s
docker logs telegraf --tail 50                        # no E! errors, "Wrote batch"
```
Then open http://localhost:3000, select the WindTurbine AAS, open the `TimeSeries` submodel's
Visualization tab, pick the `LinkedSegment`, and Fetch Data.

## Known open items (not implemented — flagged in the guide as optional/deferred)

- Authentication (Keycloak/OIDC/ABAC) — guide §8, disabled per explicit instruction.
- 3D visualization — guide §9/§16, explicitly out of scope, no native BaSyx support.
- Real sensor ingestion (OPC UA/Modbus) — guide §4.5, can replace the simulator later without
  touching Telegraf's output or the AAS.
