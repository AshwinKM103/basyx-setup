## 1. Executive Recommendation

The recommended architecture keeps the existing BaSyx Go (`aasenvironment-go` + `basyxconfigurationservice-go`) and PostgreSQL setup untouched as the semantic backbone, and adds three new services next to it: **InfluxDB 2.7** for time-series telemetry, **Telegraf** as the ingestion agent, and a **Python CSV replay/mock generator** that publishes readings once per second. Live telemetry reaches the native BaSyx UI through the **Time Series Data plugin**, which is a first-class, semantic-ID-triggered visualization feature already built into `aas-gui` and specifically designed to read `LinkedSegment` data from InfluxDB. Authentication is added last, migrating `security: type: none` to `security: type: oauth2` against a local Keycloak container, matching the officially maintained "BaSyx Secured Setup" pattern for BaSyx Go. This path requires no new frameworks, uses only already-supported BaSyx mechanisms, and has a maintained, runnable reference implementation to copy from — the `TimeSeriesData` example inside the `eclipse-basyx/basyx-aas-web-ui` repository. 3D visualization is explicitly treated as optional and deferred, because BaSyx has no native 3D support and would require a separate frontend.[^1][^2][^3][^4][^5]

A critical version fact must be stated up front: the images referenced in the query (`aasenvironment-go:latest`, `basyxconfigurationservice-go:latest`) come from the **BaSyx Go component family**, whose current tagged release as of this research is **v1.0.10, published 2026-08-29**. This is a fast-moving, weekly-release Go codebase, distinct from the older BaSyx Java components and from the BaSyx Python SDK, which independently targets **AAS Metamodel v3.1.2 (Part 1) and API v3.0.0 (Part 2)** in its current release line. Because `latest` is a moving tag, this guide explicitly warns wherever Go-server behavior, Python SDK behavior, and Web UI behavior diverge, and recommends pinning exact tags for reproducibility, per official BaSyx guidance.[^6][^7][^8]

## 2. Golden Sources

| Source | Why it matters |
|---|---|
| `eclipse-basyx/basyx-aas-web-ui`, `examples/TimeSeriesData/`  | The single most directly reusable reference implementation: Docker Compose stack with AAS Environment, PostgreSQL, InfluxDB 2.7, Telegraf, Mosquitto MQTT, a Python MQTT publisher, and a preconfigured AAS demonstrating all three telemetry segment types |
| BaSyx Wiki — Time Series Data plugin page [^1][^2] | Defines the exact semantic ID (`https://admin-shell.io/idta/TimeSeries/1/1`), the three segment types, and the Flux query variables the UI understands |
| BaSyx Wiki — Docker Configuration for `aas-gui` [^2] | Authoritative list of environment variables, including `INFLUXDB_TOKEN`, and confirms which configuration knobs are deprecated |
| BaSyx Wiki — Security page for `aas-gui` [^4][^5] | Confirms supported auth types (None, OAuth2/OIDC, Basic, Bearer) and that RBAC/ABAC enforcement happens server-side, not in the UI |
| `eclipse-basyx/basyx-go-components`, `docu/security/` and `examples/BaSyxSecuredExample/` [^9] | Ground-truth ABAC (`access-rules.json`) and OIDC (`trustlist.json`) formats actually consumed by the Go services in this deployment |
| `eclipse-basyx/basyx-go-components` releases  | Confirms current Go release is v1.0.10 (2026-08-29), establishing what "latest" means today |
| `eclipse-basyx/basyx-python-sdk` README and release notes [^6][^7][^10] | Confirms Python SDK's supported AAS metamodel/API versions and installation method |
| BaSyx Wiki — Configuration Service Docker Compose page [^8] | Explains exactly what the `basyxconfigurationservice-go` container does to PostgreSQL and the required startup ordering |
| BaSyx Wiki — Common/Shared Go Features [^11] | Documents the shared PostgreSQL connection settings and confirms ABAC/OIDC are shared building blocks across all Go services |
| PMC — "Asset Administration Shell Tool Comparison" (2025) [^12] | Peer-reviewed confirmation that BaSyx's Time Series plugin is the primary graphical mechanism for time-series submodels compared to other AAS runtimes |

## 3. Existing End-to-End Implementations

| Implementation | AAS | BaSyx | Mock/streaming data | Telegraf | InfluxDB | Visualization | Auth | Code available | AAS files | 3D |
|---|---|---|---|---|---|---|---|---|---|---|
| BaSyx AAS Web UI `TimeSeriesData` example  | Yes, `SensorExampleAAS` with `TimeSeries` submodel | Yes (Go env + configuration service) | Python MQTT publisher generating float and JSON metrics every 1s | Yes, MQTT consumer input plugin | Yes, InfluxDB 2.7 | Native BaSyx UI, Line/Area/Scatter/Histogram/Gauge/Display charts | None (demo credentials only) | Full docker-compose + Python + Telegraf config | Yes, `TimeSeriesDemo.aasx` | No |
| BaSyx Secured Setup example [^4] | Generic bicycle-manufacturer supply-chain AAS | Yes | No | No | No | Native UI with login | Keycloak OIDC + RBAC, fully working | Full docker-compose | Yes (sample AAS) | No |
| BaSyx Dynamic RBAC Management example [^4] | Same supply-chain scenario | Yes | No | No | No | Native UI | Keycloak + Submodel-based dynamic RBAC | Full code/Postman collection | Yes | No |
| PMC AAS tool comparison study (2025) [^12] | Conceptual, multi-tool | Compares BaSyx vs. AASX Server, FA³ST, NOVAAS | Discussed conceptually | Not tested | Discussed as BaSyx's time-series backend | Documents BaSyx's Time Series graphical feature as differentiator | Not focus of paper | No (comparison paper) | No | Not covered |
| BaSyx Go `BaSyxOryHydraExample` / `BaSyxEntraIDExample`  | Generic | Yes | No | No | No | Native UI | ORY Hydra / Microsoft Entra ID OIDC integration patterns | Full code | Yes | No |

No wind-turbine-specific, code-complete, BaSyx-based reference implementation was found; the closest and most directly reusable code base is the generic `TimeSeriesData` example, which this guide adapts to a wind turbine.

## 4. Recommended Architecture

### 4.1 Minimum Viable Prototype (MVP)

```
                       ┌───────────────────────────┐
                       │   Python CSV/Mock          │
                       │   Simulator (paho-mqtt)    │
                       └─────────────┬─────────────┘
                                     │ MQTT publish (1 Hz)
                                     ▼
                       ┌───────────────────────────┐
                       │   Mosquitto (MQTT broker)  │
                       └─────────────┬─────────────┘
                                     │ mqtt_consumer input
                                     ▼
                       ┌───────────────────────────┐
                       │   Telegraf                 │
                       └─────────────┬─────────────┘
                                     │ influxdb_v2 output
                                     ▼
                       ┌───────────────────────────┐
                       │   InfluxDB 2.7 (bucket:    │
                       │   wind_turbine)             │
                       └─────────────┬─────────────┘
                                     │ Flux query, LinkedSegment
                                     ▼
┌────────────┐   REST   ┌───────────────────────────┐
│ ./aas       │────────▶│  aas-environment-go        │
│ WindTurbine │         │  (registry+repo+discovery) │
│ AAS/JSON    │         └─────────────┬─────────────┘
└────────────┘                       │ PostgreSQL (basyxTestDB)
                                     ▼
                       ┌───────────────────────────┐
                       │   PostgreSQL 18            │
                       └───────────────────────────┘
                                     ▲
                                     │ REST
                       ┌───────────────────────────┐
                       │   aas-gui (native BaSyx UI)│
                       │   Time Series Data plugin  │
                       └───────────────────────────┘
```

### 4.2 Expanded / Industrial-Style Architecture

The expanded version adds authentication (Keycloak/OIDC + ABAC), a reverse proxy, and optional real sensor ingestion (OPC UA/Modbus gateways feeding Telegraf) and a 3D frontend consuming the same AAS/InfluxDB data over REST/Flux, without altering the MVP's data planes.

### 4.3 Component Responsibilities

| Component | Responsibility | Data plane |
|---|---|---|
| AAS (WindTurbine shell) | Identity anchor linking the physical turbine to its submodels via `globalAssetId` | Semantic/asset |
| AAS Environment (`aasenvironment-go`) | Serves AAS Repository, Submodel Repository, Registry, Discovery, Concept Description Repository as one process[^8] | Semantic/asset |
| PostgreSQL | Persistent backing store for AAS/Submodel/Registry/Discovery records managed by the Go environment[^8] | Semantic/asset |
| Configuration service (`basyxconfigurationservice-go`) | One-shot job that initializes/patches the PostgreSQL schema before the environment starts[^8] | Semantic/asset (schema only) |
| InfluxDB | Stores raw time-stamped sensor readings (RPM, wind speed, power output, temperature) as a bucket of measurements | Time-series telemetry |
| Telegraf | Subscribes to MQTT (or another input), transforms/tags data, writes to InfluxDB on an interval[^1] | Time-series telemetry (ingestion) |
| Python simulator | Emulates the eventual CSV feed from real sensors by publishing MQTT messages once per second | Time-series telemetry (source) |
| Native BaSyx UI (`aas-gui`) | Renders AAS tree, submodels, and — via the Time Series Data plugin — Flux-queried InfluxDB charts alongside AAS metadata[^1][^3] | UI/application state (reads both other planes) |
| Identity provider (Keycloak) | Issues OIDC tokens consumed by both the UI and the Go backend services for RBAC/ABAC enforcement[^4][^5] | UI/authentication state |

### 4.4 Three Data Planes and Why They Are Separated

AAS/semantic data (identity, nameplate, technical characteristics, static/operational metadata) belongs in PostgreSQL because it changes rarely, has strong referential/typed structure, and must be queryable by identifier and semantic ID — the exact use case the AAS Repository's relational schema is built for. Time-series telemetry belongs in InfluxDB because it is high-frequency, append-only, time-indexed and benefits from Flux windowing/downsampling that a relational AAS store does not provide; the official Time Series plugin documentation explicitly recommends InfluxDB for this "real-time or large-scale data" case rather than storing it as AAS properties. UI/authentication state (sessions, tokens, infrastructure endpoint configuration) is transient, browser-local or IdP-managed and does not belong in either data store; it lives in the OIDC provider (Keycloak) and the UI's local session storage.[^4][^8][^1]

### 4.5 What Can Be Added Later Without Redesign

Real OPC UA/Modbus sensor gateways can replace the Python MQTT publisher without touching Telegraf's output plugin or the AAS. A reverse proxy and Keycloak can be layered on top of `security: type: none` by editing only `basyx-infra.yml` and adding `ABAC_ENABLED=true` with an `access-rules.json`. A 3D frontend can be added as an independent service reading the same REST/Flux endpoints, since it does not need to modify the AAS Environment or InfluxDB schema.[^9][^4]

## 5. Mock Streaming Telemetry

### 5.1 Approach Comparison

| Approach | Simplicity | Realism | Future-sensor compatibility | Docker fit | Debuggability | Python fit | Timestamp fidelity |
|---|---|---|---|---|---|---|---|
| Python-generated synthetic values published live | High | Medium | High (same MQTT/HTTP path as real sensors) | Native | Easy (readable script) | Native | Uses wall-clock, always fresh |
| CSV replay (read stored file, publish rows on a timer) | High | High (uses real waveform shapes once real CSV arrives) | High | Native | Easy | Native | Can preserve or offset original timestamps |
| Telegraf file input (tail a growing CSV) | Medium | Medium | Medium — works only if the file is continuously appended in the exact schema | Native (Telegraf plugin) | Harder to debug malformed rows | None (no Python needed) | Depends on file writer |
| MQTT broadcast (Python or Telegraf `mqtt_consumer`) | Medium | High | High — this is the same mechanism real IIoT sensors use | Native (Mosquitto container) | Easy with `mosquitto_sub` | Native (`paho-mqtt`) | Preserved if publisher timestamps payloads |
| HTTP push (`inputs.http_listener_v2`) | Medium | Medium | Medium | Native | Easy with `curl` | Native | Preserved if payload includes timestamp |

**Recommendation:** Use a **Python CSV-replay script that publishes over MQTT to Mosquitto**, consumed by Telegraf's `mqtt_consumer` input plugin. This is exactly the mechanism validated in the official BaSyx `TimeSeriesData` example, it naturally generalizes to the eventual real CSV feed (only the data source of the Python script changes, not the ingestion path), it preserves timestamps end-to-end, and it requires no additional infrastructure beyond one lightweight Mosquitto container. A pure Telegraf file input is rejected as the primary approach because it does not naturally simulate a live, incrementally arriving stream and complicates timestamp handling for replayed historical rows; it remains a valid alternative for the `ExternalSegment` (archived CSV attached to the AAS) use case described in Part 6 below.[^1]

### 5.2 Wind-Turbine Telemetry Schema

| Field | Unit | Type | Notes |
|---|---|---|---|
| timestamp | ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | datetime | Primary time index |
| wind_speed | m/s | float | Nacelle anemometer reading |
| rotor_rpm | rpm | float | Rotor rotational speed |
| generator_rpm | rpm | float | Generator shaft speed |
| power_output | kW | float | Instantaneous active power |
| nacelle_temp | °C | float | Nacelle interior temperature |
| gearbox_oil_temp | °C | float | Gearbox lubrication temperature |
| pitch_angle | degrees | float | Blade pitch angle |
| yaw_angle | degrees | float | Nacelle yaw position |
| status | enum (`RUNNING`,`IDLE`,`FAULT`,`MAINTENANCE`) | string | Operational state |

Suggested sampling frequency: **1 Hz** for the prototype (matching the reference example's `time.sleep(1)` cadence), since this is fast enough to show a live-updating chart without overloading the local sandbox.

### 5.3 Example CSV

```csv
timestamp,wind_speed,rotor_rpm,generator_rpm,power_output,nacelle_temp,gearbox_oil_temp,pitch_angle,yaw_angle,status
2026-08-31T12:00:00Z,7.2,12.4,1487.3,850.2,38.1,62.4,3.2,181.5,RUNNING
2026-08-31T12:00:01Z,7.4,12.6,1491.8,862.7,38.2,62.5,3.1,181.5,RUNNING
2026-08-31T12:00:02Z,7.1,12.3,1483.5,845.1,38.1,62.4,3.3,181.4,RUNNING
```

### 5.4 Python Simulator (MQTT Publisher, CSV-Replay Mode)

```python
import csv
import json
import time
from pathlib import Path
import paho.mqtt.client as mqtt

CSV_PATH = Path("data/wind_turbine_mock.csv")
BROKER = "mosquitto"
PORT = 1883
TOPIC = "WindTurbine/Telemetry"
INTERVAL_SECONDS = 1

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wind-turbine-simulator")
client.connect(BROKER, PORT)
client.loop_start()

def replay_forever(path: Path):
    while True:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                payload = {
                    "wind_speed": float(row["wind_speed"]),
                    "rotor_rpm": float(row["rotor_rpm"]),
                    "generator_rpm": float(row["generator_rpm"]),
                    "power_output": float(row["power_output"]),
                    "nacelle_temp": float(row["nacelle_temp"]),
                    "gearbox_oil_temp": float(row["gearbox_oil_temp"]),
                    "pitch_angle": float(row["pitch_angle"]),
                    "yaw_angle": float(row["yaw_angle"]),
                    "status": row["status"],
                }
                client.publish(TOPIC, json.dumps(payload))
                time.sleep(INTERVAL_SECONDS)

try:
    replay_forever(CSV_PATH)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
```

This follows the same `paho-mqtt` pattern as the official publisher, but replays a CSV instead of generating pure random values, satisfying the requirement to behave identically once a real CSV arrives.

### 5.5 Telegraf Configuration

```toml
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8086"]
  token = "$INFLUXDB_TOKEN"
  organization = "basyx"
  bucket = "wind_turbine"

[[inputs.mqtt_consumer]]
  servers = ["mqtt://mosquitto:1883"]
  topics = ["WindTurbine/Telemetry"]
  data_format = "json"
  name_override = "wind_turbine_metric"
  json_time_key = "timestamp"
  json_time_format = "2006-01-02T15:04:05Z"
```

This mirrors the JSON `mqtt_consumer` block used for `MachineData/Status` in the official example (`telegraf/telegraf.conf`), adapted to the wind-turbine schema and using an environment-variable token rather than a hardcoded one.[^1]

### 5.6 InfluxDB Configuration (Docker Compose Fragment)

```yaml
influxdb:
  image: influxdb:2.7
  container_name: influxdb
  ports:
    - "8086:8086"
  volumes:
    - ./influxdb/data:/var/lib/influxdb2
  environment:
    DOCKER_INFLUXDB_INIT_MODE: setup
    DOCKER_INFLUXDB_INIT_USERNAME: admin
    DOCKER_INFLUXDB_INIT_PASSWORD: influxpassword
    DOCKER_INFLUXDB_INIT_ORG: basyx
    DOCKER_INFLUXDB_INIT_BUCKET: wind_turbine
    DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: "<generate-a-real-token>"
```

This matches the official example's InfluxDB 2.7 setup block, with the bucket renamed for this prototype.[^1]

### 5.7 Data Flow Verification

1. Confirm the Python simulator is publishing: `docker exec -it mosquitto mosquitto_sub -t "WindTurbine/Telemetry" -v`.
2. Confirm Telegraf is writing: check container logs for `Wrote batch` and no `E!` errors.
3. Confirm InfluxDB has data: `influx query 'from(bucket:"wind_turbine") |> range(start:-5m) |> limit(n:5)'` inside the InfluxDB container, or use the InfluxDB UI at `http://localhost:8086`.
4. Confirm end-to-end reach: open the Time Series Data plugin in the BaSyx UI and run the sample Flux query from the plugin documentation, substituting `wind_turbine` and `wind_turbine_metric`.[^1]

## 6. Wind-Turbine AAS

### 6.1 Specification and Compatibility

The current BaSyx Go release (v1.0.10) and its shared Go configuration/security stack target the AAS metamodel used across BaSyx's v3-generation APIs. The BaSyx Python SDK's current release targets **AAS Part 1 Metamodel v3.0.1 (schemata v3.0.8) and Part 2 API v3.0.0**, with its `main` branch tracking v3.1.2. Because the deployed Go environment and the Python SDK are developed and versioned independently, this guide standardizes on the widely compatible **AAS Metamodel v3.0 JSON serialization**, which both the Go server and the currently released Python SDK accept without conversion; using bleeding-edge v3.1 features from the SDK's `main` branch against the pinned Go release is explicitly flagged as a compatibility risk to test before relying on it.[^11][^7][^6]

### 6.2 Model Design

- **Asset**: `WindTurbine-001`, `globalAssetId = "https://example.com/assets/wind-turbine-001"`.
- **AssetAdministrationShell**: `id = "https://example.com/aas/wind-turbine-001"`, references the asset above.
- **Submodel 1 — Nameplate** (identification/nameplate information): manufacturer, serial number, year of construction, rated power. Modeled after the IDTA Digital Nameplate structure.[^13]
- **Submodel 2 — TechnicalData**: rotor diameter, hub height, rated wind speed, cut-in/cut-out wind speed, rated power (static specifications, not live values).
- **Submodel 3 — OperationalState**: current status enum, last-updated timestamp, active fault codes — updated infrequently, stored as ordinary AAS properties.
- **Submodel 4 — TimeSeries** (telemetry): built to the IDTA Time Series Data specification with semantic ID `https://admin-shell.io/idta/TimeSeries/1/1`, containing a `LinkedSegment` pointing at the InfluxDB bucket/measurement, plus metadata records describing available variables (`wind_speed`, `rotor_rpm`, `power_output`, etc.).[^1]
- **Submodel 5 — MaintenanceInfo** (optional): last inspection date, next scheduled maintenance, cumulative operating hours.

### 6.3 What Belongs in the AAS vs. InfluxDB

Static and slowly changing facts — nameplate data, technical specifications, current-state enums, maintenance schedule — belong in AAS submodels because they are structured, typed, semantically identified, and queried by identity rather than by time range. High-frequency numeric telemetry belongs exclusively in InfluxDB; the AAS's `TimeSeries` submodel does not duplicate the readings but instead stores a **reference/configuration pointing at the external database** (the `LinkedSegment`), which is precisely the segment type the plugin was built to resolve at view time.[^1]

### 6.4 Sample AAS JSON (Abbreviated)

```json
{
  "assetAdministrationShells": [
    {
      "modelType": "AssetAdministrationShell",
      "id": "https://example.com/aas/wind-turbine-001",
      "idShort": "WindTurbineAAS",
      "assetInformation": {
        "assetKind": "Instance",
        "globalAssetId": "https://example.com/assets/wind-turbine-001"
      },
      "submodels": [
        { "type": "ModelReference", "keys": [{ "type": "Submodel", "value": "https://example.com/sm/nameplate-001" }] },
        { "type": "ModelReference", "keys": [{ "type": "Submodel", "value": "https://example.com/sm/technicaldata-001" }] },
        { "type": "ModelReference", "keys": [{ "type": "Submodel", "value": "https://example.com/sm/operationalstate-001" }] },
        { "type": "ModelReference", "keys": [{ "type": "Submodel", "value": "https://example.com/sm/timeseries-001" }] }
      ]
    }
  ],
  "submodels": [
    {
      "modelType": "Submodel",
      "id": "https://example.com/sm/technicaldata-001",
      "idShort": "TechnicalData",
      "submodelElements": [
        { "modelType": "Property", "idShort": "RatedPower", "valueType": "xs:double", "value": "2000" },
        { "modelType": "Property", "idShort": "RotorDiameter", "valueType": "xs:double", "value": "90" },
        { "modelType": "Property", "idShort": "HubHeight", "valueType": "xs:double", "value": "80" }
      ]
    }
  ]
}
```

The full `TimeSeries` submodel structure (with `InternalSegment`, `ExternalSegment`, and `LinkedSegment`) should be copied from the working `TimeSeriesDemo.aasx` example and adapted field-by-field, since it is the only verified-working instance of this structure against the current BaSyx UI plugin.[^1]

### 6.5 Python SDK Implementation

```python
from basyx.aas import model
from basyx.aas.adapter.json import write_aas_json_file

asset_id = "https://example.com/assets/wind-turbine-001"
aas = model.AssetAdministrationShell(
    id_="https://example.com/aas/wind-turbine-001",
    id_short="WindTurbineAAS",
    asset_information=model.AssetInformation(
        asset_kind=model.AssetKind.INSTANCE,
        global_asset_id=asset_id,
    ),
)

technical_data = model.Submodel(
    id_="https://example.com/sm/technicaldata-001",
    id_short="TechnicalData",
    submodel_element={
        model.Property(id_short="RatedPower", value_type=model.datatypes.Double, value=2000.0),
        model.Property(id_short="RotorDiameter", value_type=model.datatypes.Double, value=90.0),
        model.Property(id_short="HubHeight", value_type=model.datatypes.Double, value=80.0),
    },
)

object_store = model.DictObjectStore([aas, technical_data])
with open("wind_turbine_aas.json", "w") as f:
    write_aas_json_file(f, object_store)
```

This uses the documented `basyx.aas.model` and `basyx.aas.adapter.json` modules from the official SDK. The SDK can create, serialize, and (via `basyx.aas.adapter.json`/`xml` and validation utilities) validate AAS environments against the schema version it implements, but it does not itself run or replace the Go server — it is a modeling/authoring tool that produces files the Go environment then serves.[^10]

### 6.6 Validation and Import

Validate the exported JSON with the AASX Package Explorer or by attempting a dry-run upload; malformed JSON is rejected by the AAS Environment's upload endpoint with a schema error. Two import paths exist against the existing deployment:

- **File-based preconfiguration** (recommended for this prototype): copy the JSON/AASX into the existing `./aas` directory that is already mounted into the `aasenvironment-go` container; this matches the official example's `GENERAL_AAS_PRECONFIG_PATHS` mechanism, which loads files automatically on container start.[^1]
- **UI upload**: use the native UI's upload feature (`ALLOW_UPLOADING=true`, already enabled) to add the file at runtime without restarting the container.[^2]

File-based preconfiguration is recommended because it is idempotent, versionable, and matches the existing starter-kit convention already used for `./aas`; UI upload remains useful for iterating without a restart. After loading, verify the shell appears in the native UI's AAS list at `http://localhost:3000` and that the submodel tree, including the `TimeSeries` submodel, renders under it.

## 7. PostgreSQL in This Deployment

| Component | Stores | Does not store | Purpose |
|---|---|---|---|
| `aasenvironment-go` (AAS Repository, Submodel Repository, Concept Description Repository, Registry, Discovery — combined) | AAS shells, submodels, submodel elements, concept descriptions, registry descriptors, discovery asset-link mappings, all inside `basyxTestDB`[^8] | Time-series telemetry values; UI session/auth tokens | Persistent structured store for all AAS/semantic data served by the environment |
| `basyxconfigurationservice-go` | Nothing at runtime — it applies the base SQL schema and any patches to the target database once, then exits[^8] | Any AAS content itself | One-time schema initialization/migration job that must run before the environment starts |
| InfluxDB (added in this guide) | Time-stamped telemetry measurements only | AAS metadata, registry data | Time-series storage, separate database entirely |

Registry and discovery data live in the same PostgreSQL database as AAS/submodel content because `aasenvironment-go` bundles all these BaSyx services into one process with `GENERAL_AASREGISTRYINTEGRATION`/`GENERAL_SUBMODELREGISTRYINTEGRATION`/`GENERAL_DISCOVERYINTEGRATION` flags pointing at the same backing store. Telemetry should never be stored in PostgreSQL: it would force every telemetry write through the AAS Repository's typed submodel-element model, defeating the purpose of a purpose-built time-series engine, which is exactly why the official Time Series plugin was built to query InfluxDB directly instead.[^1]

On a container restart without volume removal, all AAS/submodel/registry data persists because PostgreSQL data is written to a named volume; the `basyxTestDB` schema and rows survive. On a full stack restart (`docker compose down -v` or manual volume deletion), everything is lost unless the PostgreSQL data directory and the InfluxDB data directory are both mapped to persistent named volumes — the current starter kit already does this for PostgreSQL, and this guide adds an equivalent bind mount for InfluxDB, matching the official example's `./influxdb/data:/var/lib/influxdb2` pattern. A minimal backup strategy for the prototype is a scheduled `pg_dump` of `basyxTestDB` plus periodic InfluxDB backups via `influx backup`.[^1]

## 8. Authentication and Authorization

### 8.1 Capability Matrix

| Layer | Native support | Notes |
|---|---|---|
| BaSyx Go server components (`aasenvironment-go`, registries, repositories) | Yes — OIDC token verification plus ABAC policy enforcement via shared `internal/common/security` building blocks[^11] | Requires `ABAC_ENABLED=true`, `ABAC_MODELPATH`, and `OIDC_TRUSTLISTPATH` environment variables and matching JSON files[^9] |
| Native BaSyx UI (`aas-gui`) | Yes — supports None, OAuth2/OIDC (Authorization Code or Client Credentials), Basic Auth, and Bearer Token per infrastructure, configured in `basyx-infra.yml`[^4][^5] | UI is agnostic to whether the backend uses RBAC or ABAC; it only manages the OAuth2 token exchange[^5] |
| BaSyx Python SDK | No built-in authentication/authorization layer of its own | It is a modeling/serialization library, not a server; if you write scripts that call the secured Go REST APIs, you must add your own OIDC token acquisition (e.g., `requests-oauthlib`) in that script |

### 8.2 OIDC and ABAC Mechanics

OIDC in this stack works by each Go component validating incoming JWT bearer tokens against a **trustlist** file (`trustlist.json`) that whitelists trusted issuers, audiences, and scopes; the UI performs the Authorization Code Flow against the identity provider and attaches the resulting access token to every REST call. ABAC is enforced independently of OIDC: once a token is verified, an `access-rules.json` file (or a database-backed policy loaded from it) evaluates attributes such as the token's `role` claim against declared rules (`DEFATTRIBUTES`, `DEFOBJECTS`, `DEFACLS`, `DEFFORMULAS`, and `rules`) to allow or deny specific routes. Service-to-service calls (e.g., between the AAS Environment and the Configuration Service) do not require OIDC in this pattern because the Configuration Service does not expose a runtime API — it only runs once at startup and exits.[^8][^4]

### 8.3 Recommended Local Setup

Add a single Keycloak container as the identity provider, following the official "BaSyx Secured Setup" example pattern exactly, because it is the simplest architecture proven compatible with the current Go server family and Docker Compose, and it needs no reverse proxy for a single-host local prototype (the `.localhost` domain trick used in the reference example is optional; direct `localhost:PORT` URLs work equally well for a single-machine setup).[^4]

### 8.4 Migration Steps from `security: type: none`

1. Add a Keycloak service to the compose file, pre-seeded with a `BaSyx` realm and at least one user with a `viewer` or `admin` role, following the official example's realm export approach.[^4]
2. Update `basyx-infra.yml`:

```yaml
infrastructures:
  default: local
  local:
    name: Local BaSyx
    template: mono-all
    components:
      aasEnvironment:
        baseUrl: "http://localhost:8082"
    security:
      type: oauth2
      config:
        flow: auth_code
        issuer: "http://localhost:8080/realms/basyx"
        clientId: "basyx-ui"
```

3. Create `security_env/trustlist.json`:

```json
[
  {
    "issuer": "http://localhost:8080/realms/basyx",
    "audience": "basyx-ui",
    "scopes": ["email", "profile"]
  }
]
```

4. Create `security_env/access-rules.json` (minimal viewer/admin split, adapted from the official example):

```json
{
  "AllAccessPermissionRules": {
    "DEFATTRIBUTES": [
      { "name": "role_attr", "attributes": [{ "CLAIM": "role" }] }
    ],
    "DEFOBJECTS": [
      { "name": "all_api", "objects": [{ "ROUTE": "/shells" }, { "ROUTE": "/shells/*" }, { "ROUTE": "/submodels" }, { "ROUTE": "/submodels/*" }] }
    ],
    "DEFACLS": [
      { "name": "viewer_read", "acl": { "USEATTRIBUTES": "role_attr", "RIGHTS": ["READ"], "ACCESS": "ALLOW" } },
      { "name": "admin_full", "acl": { "USEATTRIBUTES": "role_attr", "RIGHTS": ["ALL"], "ACCESS": "ALLOW" } }
    ],
    "DEFFORMULAS": [
      { "name": "is_admin", "formula": { "$eq": [{ "$attribute": { "CLAIM": "role" } }, { "$strVal": "admin" }] } },
      { "name": "is_viewer", "formula": { "$eq": [{ "$attribute": { "CLAIM": "role" } }, { "$strVal": "viewer" }] } }
    ],
    "rules": [
      { "USEACL": "viewer_read", "USEOBJECTS": ["all_api"], "USEFORMULA": "is_viewer" },
      { "USEACL": "admin_full", "USEOBJECTS": ["all_api"], "USEFORMULA": "is_admin" }
    ]
  }
}
```

5. In the compose file, set on `aas-env`: `ABAC_ENABLED=true`, `ABAC_MODELPATH=/security_env/access-rules.json`, `OIDC_TRUSTLISTPATH=/security_env/trustlist.json`, and mount `./security_env:/security_env:ro`.
6. Restart the stack and confirm the UI redirects to Keycloak's login page before showing any AAS data.

## 9. Native UI and Visualization

The native UI's semantic-ID-driven plugin mechanism automatically activates browsing, editing, upload, and the Time Series Data visualization tab whenever a submodel carries the matching semantic ID — no custom frontend code is required for line/area/scatter/histogram/gauge/display charts. It cannot natively render arbitrary InfluxDB dashboards outside this plugin's model, and it cannot render 3D content at all. For 3D, BaSyx provides no built-in capability; a separate frontend (e.g., a small Three.js or Babylon.js single-page app) would need to fetch the AAS/submodel data over the AAS Environment's REST API and telemetry over InfluxDB's HTTP/Flux API independently, then drive material/animation state (e.g., blade rotation speed) from `rotor_rpm`. No ready-made, license-clear wind-turbine glTF asset with a working AAS+3D integration example was found in this research; free wind-turbine 3D models exist on general asset marketplaces (Sketchfab, Meshy) but none come pre-wired to AAS data, so this remains a genuinely optional, build-from-scratch extension rather than a reproducible reference path.[^3][^14][^15][^16][^2]

## 10. Python-First Implementation Guidance

| Task | Best implemented in |
|---|---|
| AAS authoring/serialization | Python (`basyx-python-sdk`) |
| CSV replay / MQTT publishing | Python (`paho-mqtt`) |
| MQTT-to-InfluxDB ingestion | Telegraf configuration (native, not Python) |
| Time-series storage | InfluxDB configuration (native) |
| AAS serving, registry, discovery | BaSyx Go configuration (native, already deployed) |
| Visualization | Native BaSyx UI configuration (`basyx-infra.yml`, environment variables) — no custom frontend code needed for the MVP |
| Authentication | Keycloak realm configuration + `access-rules.json`/`trustlist.json` (native) |

### 10.1 Recommended Directory Structure

```
basyx-wind-turbine/
├── docker-compose.yml
├── basyx-infra.yml
├── aas/
│   └── wind_turbine_aas.json
├── security_env/
│   ├── access-rules.json
│   └── trustlist.json
├── telegraf/
│   └── telegraf.conf
├── mosquitto/
│   └── config/
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── simulate.py
│   └── data/
│       └── wind_turbine_mock.csv
└── sdk-scripts/
    └── build_aas.py
```

## 11. Step-by-Step Implementation Guide

**Step 1 — Verify current BaSyx deployment/version.** Objective: confirm exact running versions. Command: `docker inspect --format='{{.Config.Image}}' tainer>` and cross-check against release tags at `https://github.com/eclipse-basyx/basyx-go-components/releases`. Expected output: image digest matching a specific v1.0.x tag. Common failure: `latest` silently changed after a `docker compose pull`. Source:.[^8]

**Step 2 — Inspect current services.** Objective: confirm `aasenvironment-go`, `basyxconfigurationservice-go`, `aas-gui`, PostgreSQL are healthy. Command: `docker compose ps`. Expected: configuration service exited 0; others "healthy"/"running". Source:.[^8]

**Step 3 — Add the wind-turbine AAS.** Files changed: `aas/wind_turbine_aas.json` (new). Objective: create the shell and submodels per Section 6. Common failure: missing `globalAssetId` or malformed `modelType`.

**Step 4 — Validate and load/register AAS.** Command: place file in `./aas`, restart `aas-env` (`docker compose restart aas-env`) so `GENERAL_AAS_PRECONFIG_PATHS` re-imports it, or upload via UI. Verify: `curl http://localhost:8082/shells` lists the new shell. Source:.[^1]

**Step 5 — Add InfluxDB.** Files changed: `docker-compose.yml` (add `influxdb` service per Section 5.6). Verify: `curl http://localhost:8086/health` returns `{"status":"pass", ...}`.

**Step 6 — Add Telegraf.** Files changed: `docker-compose.yml`, `telegraf/telegraf.conf` (Section 5.5). Verify: `docker logs telegraf` shows no `E!` errors after startup.

**Step 7 — Create mock wind-turbine CSV data.** Files changed: `simulator/data/wind_turbine_mock.csv` (Section 5.3). Verify: file has header row and valid ISO timestamps.

**Step 8 — Turn CSV into live/replayed sensor data.** Files changed: `simulator/simulate.py`, `simulator/Dockerfile` (Section 5.4). Command: `docker compose up -d simulator`. Verify: `mosquitto_sub -t "WindTurbine/Telemetry" -v` shows JSON messages every second.

**Step 9 — Send data through Telegraf.** No new files; confirm Telegraf's `mqtt_consumer` subscribes to `WindTurbine/Telemetry`. Verify: Telegraf logs show write batches to InfluxDB. Common failure: topic name mismatch between simulator and `telegraf.conf`.

**Step 10 — Verify InfluxDB data.** Command: InfluxDB UI Data Explorer or CLI `influx query`. Expected: rows in bucket `wind_turbine`, measurement `wind_turbine_metric`.

**Step 11 — Connect/reconcile telemetry with the digital-twin model.** Files changed: `aas/wind_turbine_aas.json` `TimeSeries` submodel `LinkedSegment` query/endpoint fields point at the InfluxDB bucket and measurement. Verify against the plugin's documented Flux variables.[^1]

**Step 12 — Visualize through the native UI.** Navigate to `http://localhost:3000` → select AAS → `TimeSeries` submodel → Visualization tab → select `LinkedSegment`, pick y-variables, click Fetch Data. Expected: a live line chart updating on auto-refresh. Source:.[^1]

**Step 13 — Configure authentication.** Files changed: `basyx-infra.yml`, `security_env/access-rules.json`, `security_env/trustlist.json`, `docker-compose.yml` (Keycloak service, ABAC/OIDC env vars per Section 8.4).

**Step 14 — Test authenticated access.** Command: attempt UI access without login (should redirect to Keycloak); log in as `viewer` and confirm read-only access; log in as `admin` and confirm upload/edit works.

**Step 15 — Validate complete end-to-end flow.** Run through the Section 12 checklist below.

**Step 16 — Optional 3D visualization extension.** Build a minimal Three.js page independently fetching AAS REST data and InfluxDB Flux data; not part of the MVP critical path.

## 12. Validation Checklist

- BaSyx stack (`aas-env`, `basyx-configuration`, PostgreSQL, `aas-gui`) starts successfully with `docker compose ps` showing healthy/exited-0 states.[^8]
- PostgreSQL persists AAS/submodel data across container restarts (verified by restarting `aas-env` alone and re-listing `/shells`).
- Wind-turbine AAS exists and is retrievable via `GET /shells`.
- AAS opens in the native UI and its idShort/asset ID display correctly.
- All submodels (Nameplate, TechnicalData, OperationalState, TimeSeries) are visible in the UI tree.
- Mock CSV telemetry file exists with valid schema and timestamps.
- Telemetry behaves like a live stream (MQTT messages arrive once per second, confirmed via `mosquitto_sub`).
- Telegraf receives the MQTT data without plugin errors.
- InfluxDB stores the data, confirmed via Flux query returning non-empty results.
- Telemetry is queryable via the exact Flux query pattern from the Time Series plugin docs.[^1]
- The native UI displays changing telemetry in the Visualization tab, including auto-refresh.
- Authentication works: unauthenticated browser session redirects to Keycloak login.
- Unauthorized access is rejected: a `viewer` token receives 403 on write/delete routes per `access-rules.json`.
- AAS metadata (static) and telemetry (dynamic) have clearly separated storage responsibilities, confirmed by inspecting PostgreSQL (no telemetry rows) and InfluxDB (no AAS structures).
- Full stack restart with named volumes intact (`docker compose down && docker compose up -d`, without `-v`) preserves both AAS content and historical telemetry.

### Intentionally Not Implemented Yet

- Real sensor/PLC ingestion (OPC UA, Modbus, or vendor SCADA integration).
- Cloud deployment or multi-tenant hosting.
- 3D visualization frontend.
- Dynamic/runtime-editable ABAC rules via the Security Submodel mechanism (static file-based rules only).
- TLS/HTTPS termination and a reverse proxy for external network exposure.
- Automated CI/CD or infrastructure-as-code provisioning.

## 13. Troubleshooting Sources

| Failure area | Reference |
|---|---|
| Docker networking / service discovery between containers | Official BaSyx Configuration Service Docker Compose ordering guidance[^8] |
| Telegraf → InfluxDB write failures | Telegraf `outputs.influxdb_v2` plugin documentation and BaSyx `telegraf.conf` reference example[^1] |
| CSV/MQTT ingestion schema mismatches | BaSyx `TimeSeriesData` example README, which documents each segment type's expected structure |
| AAS loading/registration failures | `GENERAL_AAS_PRECONFIG_PATHS` behavior and startup ordering notes in the Configuration Service docs[^8] |
| AAS validation errors | BaSyx Python SDK repository and its schema/adapter modules[^10] |
| BaSyx UI connectivity issues | AAS Web UI Docker Configuration and Security troubleshooting sections[^2][^4] |
| PostgreSQL persistence/volume issues | Configuration Service Docker Compose page's warning on mutable tags and schema patching order[^8] |
| OIDC/authentication failures | BaSyx Secured Setup example and ABAC Policy Repository documentation[^4][^9] |
| ABAC rule-matching failures | `basyx-go-components` `docu/security/ABAC_POLICY_REPOSITORY.md` and access-rules.json schema tests[^9] |
| Telemetry not rendering in UI | Time Series Data plugin's Flux query-variable reference and segment-type troubleshooting[^1] |

---

## References

1. [Time Series Data — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/web_ui/features/plugins/time_series_data.html) - The Time Series Data plugin provides powerful visualization capabilities for time-based data stored ...

2. [Plugins — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/web_ui/features/plugin_mechanism.html) - Visualizes time series data using different chart types (line, bar, area) · Supports data from AAS p...

3. [AAS Web UI — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/web_ui/index.html) - Semantic ID Matching: The AAS Web UI checks if the Submodel or SubmodelElement has a semanticId . If...

4. [Access Control — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/concepts/use_cases/rbac.html) - BaSyx uses JSON-based RBAC rules that define the relationship between roles, actions, and target res...

5. [Authorization — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/v2/aas_repository/features/authorization.html) - Rules are defined using a JSON format as defined below. initial rules can be defined in JSON format....

6. [Eclipse BaSyx Python SDK - GitHub](https://github.com/eclipse-basyx/basyx-python-sdk) - the SDK version number is independent of the supported AAS versions! Version Part 1: Metamodel v3.1....

7. [Eclipse BaSyx 1.2.0 (Python)](https://projects.eclipse.org/projects/dt.basyx/releases/1.2.0-python) - This release implements the following versions of the AAS specification: Part 1 - Metamodel: v3.0.1;...

8. [Docker Compose Integration — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/go/configuration_service/docker-compose.html) - In Docker Compose deployments, run the BaSyx Configuration Service after PostgreSQL is healthy and b...

9. [PostgreSQL-Backed ABAC Policies - GitHub](https://github.com/eclipse-basyx/basyx-go-components/blob/main/docu/security/ABAC_POLICY_REPOSITORY.md) - The BaSyx Go Components include all standardized Server Components. BaSyx services can store ABAC ac...

10. [Eclipse BaSyx Python SDK - GitHub](https://github.com/eclipse-basyx/basyx-python-sdk/blob/main/sdk/README.md) - The Eclipse BaSyx Python project focuses on providing a Python implementation of the Asset Administr...

11. [Common / Shared Features — Eclipse BaSyx™](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/go/common/shared_features.html) - This page summarizes runtime features that are implemented in shared code and reused by multiple BaS...

12. [Asset Administration Shell Tool Comparison: A Case Study ... - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991629/) - Eclipse BaSyx offers a graphical interface for Time Series Submodels through its semantic visualizat...

13. [Digital Nameplate Specification for AAS | PDF - Scribd](https://www.scribd.com/document/961334747/IDTA-02006-3-0-1-Submodel-Digital-Nameplate) - The document IDTA 02006 outlines the specification for a Digital Nameplate for Industrial Equipment,...

14. [Vintage Wind Turbine - GameAsset - Free Download - Sketchfab](https://sketchfab.com/3d-models/vintage-wind-turbine-gameasset-free-download-3e0ca3c6fdf14badbb5750220e6ca7ee) - Vintage Wind Turbine - GameAsset - Free Download 3D Model. I am a freelance 3D generalist from germa...

15. [Free Turbine 3D Models - Download Instantly - Meshy AI](https://www.meshy.ai/tags/turbine) - Download 67+ free Turbine 3D models in STL, GLB, FBX, OBJ formats for 3D Printing, Games, Animation ...

16. [Wind Turbin - Animated | Low-Poly Version - 3D model by VIS-All ...](https://sketchfab.com/3d-models/wind-turbin-animated-low-poly-version-3675841a62b1417eb15b08f03864d72f) - A polygon reduced version of the wind turbine without entrance. 3d modeled, textured and animated by...

