# CBi Astute Device Integration (Real Data Source)

## Update (2026-09-29): data_source field, and a second linked device that turned out unusable

**Sites now carry a `data_source` field (`"simulated"` | `"real"`)**, added via Alembic migration
`75ca82b27a21_add_data_source_to_sites.py`. The 10 seeded households are backfilled as
`"simulated"`; `site-bongani-test` is `"real"`. `get_or_create_site()` takes an optional
`data_source` parameter (defaults to `"simulated"` so the CSV pipeline is unaffected);
`tuya_source.py` passes `data_source="real"` explicitly. `/analytics/sites` now returns this
field, and the frontend uses it to visually separate the two: the site dropdown is grouped into
"Simulated households" / "Real devices" `<optgroup>`s, a "Real device"/"Simulated" badge sits next
to the dashboard title, and the admin overview table has a "Source" column with the same badges.
Any future real device added through `tuya_source.py` is automatically classified as real — no
per-device frontend change needed.

**Checked what else was linked to the Tuya Cloud project, expecting a second CBi plug — found a
Standing Desk controller instead.** `tinytuya.Cloud.getdevices()` listed two devices under the
account: the ASA plug (`bfeebc57c438062c7bcxox`, category `cz`) and a device named
"Bongani Standing Desk" (`bf68a4ca2e41ad7d5135ol`, product `ytr6xsdi1kngw2j1`, category `sjz` — a
desk-lift/motor controller, unrelated to this project, apparently linked to the same Smart Life
account from prior personal use). Checked its actual DPs directly via `getstatus()`/`getdps()`
rather than assuming: it exposes exactly one data point, `child_lock` (Boolean) — no voltage,
current, power, or energy at all. **Confirmed conclusion: only Tuya category-`cz` devices (smart
plugs/sockets) can feed this pipeline** — category alone is a reliable filter before spending time
checking a device's DPs. Not added to `DEVICE_REGISTRY`; not usable for this project regardless of
how it's wired up.

**Household-to-device mapping decision (tentative, revisit once more hardware is bought): one
real device per household**, not multiple devices/channels per household. Simpler than the
`controller_channel`-per-load model the simulated data uses, and closer to how a real household
would realistically be instrumented (one main meter, not per-appliance smart plugs). Each new
real device becomes a new `site_id` entry in `DEVICE_REGISTRY`, following the same
pairing → cloud-link → `tinytuya wizard` DP-verification → registry-entry steps already proven for
the first one — not a new `controller_channel` under the existing `site-bongani-test` entry.

## Current status (2026-09-23) — read this first

**Working: single-device proof of concept, via `tinytuya`, not `tuya-iot-py-sdk`.**
`app/ingestion/tuya_source.py` now polls Tuya's Cloud API using `tinytuya.Cloud`, authenticated
with just the project's Access ID/Secret — **no end-user login at all**. This was discovered
after the Cloud message-queue login (below) stayed blocked: `python -m tinytuya wizard` retrieves
the full device list, the real DP mapping, and the `local_key` using pure Access ID/Secret auth,
and `tinytuya.Cloud(...).getstatus(device_id)` reads live device data the same simple way. Running
`python -m app.ingestion.tuya_source` now produces a real `Reading` row in the database from the
actual physical device (verified live: ~236.6V, 0A/0kW at idle, `switch_1=on`).

The verified real DP mapping for this exact device (from `tinytuya wizard`'s product schema,
replacing all earlier guesses) is in the "DP codes and scale factors" section below — notably,
**`add_ele`'s scale is 3, not 2**, i.e. raw ÷ 1000 for kWh, not ÷ 100 as first assumed.

**Still blocked, and now known to matter only for the multi-household scaling plan, not today's
proof of concept**: the Cloud message-queue login (`TuyaOpenAPI.connect()` via `tuya-iot-py-sdk`)
still returns `{'code': 1106, 'msg': 'permission deny'}` — see the unchanged diagnosis below.
`tinytuya` has **no message-queue/push capability at all** (confirmed by inspecting the installed
package: only low-level local TCP packet-format helpers exist, no Pulsar/pub-sub client) — it only
does REST-style request/response polling. So `tinytuya` solves "get real data from one device
into the database today," but it does **not** solve the quota problem described in "Actual plan"
below for ~10 households × multiple devices; that still depends on either resolving the 1106 error
for `tuya-iot-py-sdk`'s push path, or finding some other way to avoid REST-polling quota limits at
scale. Treat these as two separate problems now, not one.

**Local network discovery (`tinytuya scan` finding 0 devices) is no longer a live blocker** for
the approach actually being used — `tinytuya.Cloud` talks to Tuya's cloud API, not the device
directly over LAN, so it doesn't need local discovery to work at all. The LAN discovery question
(possibly the device's "Local Network Control" toggle being off) is left unresolved and low
priority, only relevant again if a future local-only fallback is ever wanted.

**Two real bugs fixed along the way, already committed to the code** (not blockers, just worth
knowing they happened): `tuya_source.py` originally read config via raw `os.environ`, bypassing
this project's actual `pydantic-settings`-based config entirely — fixed to go through
`app/config.py` like everything else. Separately, the `.env` file had `TUYA_USERNAME`/
`TUYA_PASSWORD` written with `:` instead of `=` (invalid syntax, silently ignored) and was
missing `TUYA_ACCESS_ID`/`TUYA_ACCESS_SECRET` entirely.


How the project's first real CBi Astute smart adapter gets its data into this system, as an
alternative data source alongside the simulated CSV generator — this is the "real smart-controller
export" path the architecture was deliberately kept agnostic for (see
`ARCHITECTURE_DECISIONS.md`), and the future-work item named in the conference paper.

**Why this route at all**: the CBi Astute is a Tuya white-label device. The stock CBi Home App
only gives on/off control and a consumer dashboard — no exposed API for pulling raw
voltage/current/power readings into our own backend.

## Architecture decision (2026-09-22): centralized via Tuya Cloud API, not local-only

The original plan below (Home Assistant + `localtuya`, local network polling) was built and
tested against a single personally-owned device. It stopped being the right plan the moment the
real project goal was stated clearly: **~10 households, each with one or more devices, all
reporting into one central dashboard.**

`localtuya`/`tinytuya`'s local polling only works because the poller sits on the *same LAN* as the
device — it cannot reach a device sitting in someone else's home over the internet, since the Tuya
local protocol doesn't route. For 10 remote households, that would mean physically deploying and
maintaining a gateway computer (e.g. a Raspberry Pi) *inside each home* — real hardware cost
(~R8,000–15,000 for ten units) and field-maintenance burden that isn't realistic on this project's
Feb–Oct 2026 timeline, for a researcher who can't be on-site at ten homes repeatedly.

**Decision: poll Tuya's Cloud API centrally instead.** Each household does a one-time linking
step (install the Smart Life app, add their device, scan a QR from our Tuya Cloud project to link
it — the exact same "Link Tuya App Account" flow already proven working below, just repeated once
per household) — no extra hardware at any site. The backend then polls Tuya's Cloud API centrally
for every linked device's current status.

This is a conscious, acknowledged departure from the original "avoid any ongoing cloud
dependency" framing — worth being precise about *what* that framing was actually objecting to,
for the write-up: the concern was CBI's closed consumer app/cloud specifically, not cloud
infrastructure in general. Tuya's Cloud API is open, documented, and the same platform this whole
integration already depends on for device linking — a materially different and more defensible
position than being locked into CBI's proprietary ecosystem. The local-only Home Assistant path
below is kept as a record of what was tried and validated for a single device, not deleted, since
it's genuine groundwork (confirms the device, the account linking, and the `local_key`/DP
structure all work) — it's just not the path to the 10-household deployment.

**Still to check before this is real**: Tuya's free-tier Cloud API call quota, once polling 10+
devices on a schedule rather than one. Worth confirming actual limits before assuming ~15-minute
polling across 10 households is sustainable on the free tier.

---

## What's been done so far

### 1. Physical pairing

Device plugged in and paired to Wi-Fi (2.4GHz only — the device doesn't support 5GHz). LED
states, per the ASC/ASA datasheet's Pair LED table:

| State | Meaning |
|---|---|
| Solid red, no blue | Powered on, not yet paired / no Wi-Fi |
| Red flashing (blue solid) | Pairing mode active — entered by holding the power button 5 seconds |
| **Solid red + solid blue** | **Connected, output off — this is the confirmed state after pairing** |

### 2. Cloud linking — first attempt failed, second attempt worked

**Attempted first**: create a Tuya IoT Developer account and Cloud Project, then link the device
via **Link Tuya App Account → scan QR with the CBi Home App**. This repeatedly failed with
"QR code has expired" even when scanning within a few seconds of refreshing it — the symptom of a
**data-center mismatch** between the CBi Home App's account and the project's selected data
center, not an actual timing issue. Tuya has no Africa-specific data center; per Tuya's own
[country-to-data-center table](https://github.com/tuya/tuya-home-assistant/blob/main/docs/regions_dataCenters.md),
South Africa is officially mapped to **Central Europe Data Center**, though some community
reports suggest newer OEM app registrations land on **Western Europe** instead — this
inconsistency is exactly what caused the repeated failures. Note the Devices page has its **own**
data-center selector in the top-right corner, separate from the project's home region — that's
what needs to match the app account, and it's changeable without recreating the project.

**What actually worked**: rather than keep fighting the CBi Home App's data-center linking,
the device was registered directly under a generic **Smart Life** app account instead. Cloud
linking (Automatic Link) then succeeded immediately, with the device showing up **Online** in
the Tuya Developer Platform's device list under the App Account's Manage Devices screen.

### 3. Device details retrieved

Via **Cloud → API Explorer → Query Device Details**, using the linked device's ID:

| Field | Value |
|---|---|
| `id` (Device ID) | `bfeebc57c438062c7bcxox` |
| `product_id` | `zugqh18dk3g6lwbr` |
| `category` | `cz` (Tuya's standard smart-socket/plug category — confirms `localtuya` is the right integration path) |
| `model` | `ASA ver 1` |
| `local_key` | **Not stored here — see "Secrets handling" below** |

**Important gotcha**: the `ip` field in this response (`41.193.162.36` at time of writing) is the
device's **public WAN IP as last seen by Tuya's cloud**, not its LAN address — recognizable as a
South African ISP public range, not a `192.168.x.x`/`10.x.x.x` private address. The real local IP
still needs to be found separately.

### 4. Finding the device's real LAN IP

Tuya devices consistently listen on TCP port `6668` for the local protocol `localtuya` speaks, so
scanning for that port is a more reliable way to find it than trying to match hostnames/MAC
addresses in a router's device list. The purpose-built tool for this is `tinytuya`:

```powershell
pip install tinytuya
python -m tinytuya scan
```

This broadcasts on the local network and lists every Tuya device that responds, including its IP,
device ID and product info — cross-check the device ID against `bfeebc57c438062c7bcxox` (from step
3) to confirm which result is the right one. It's also a good sanity check that the `local_key`
retrieved earlier is genuinely correct, since `tinytuya` can optionally do a live poll of the
device once you give it the key.

**Fallback if that doesn't find it** (e.g. router client isolation blocking broadcast discovery):
log into the router's admin page → connected devices / DHCP client list, and look for a device
name matching the product (`ASA`) or cross-reference by MAC address if the device's packaging/label
has one printed.

### Secrets handling

`local_key` is a device access credential, scoped to the local network but still a credential —
**it does not go in this file, or any committed doc**. Store it the same way as every other secret
in this project: in `backend/.env` (gitignored), following the pattern already established for
`DATABASE_URL`. Suggested variable names once the ingestion adapter (below) is built:

```
CBI_ASTUTE_DEVICE_ID=bfeebc57c438062c7bcxox
CBI_ASTUTE_LOCAL_KEY=<redacted - from Query Device Details, not committed>
CBI_ASTUTE_LOCAL_IP=<the device's actual LAN IP, not the WAN IP above>
```

---

## Superseded: local-only path for a single device (kept for reference, not the deployment plan)

Everything from here down was the plan before the 10-household architecture decision above. Not
deleted because it's genuine validated groundwork for one device — just not what gets built out
further, since it doesn't scale to households you can't physically visit.

1. **Run Home Assistant.** Docker is the simplest path on this machine — Docker Desktop is
   already installed and running (it's used for the day-job TemplateAPI project too), so this is
   just one more container, not a new toolchain.

   ```powershell
   docker run -d `
     --name homeassistant `
     --restart=unless-stopped `
     -e TZ=Africa/Johannesburg `
     -v ${PWD}/homeassistant-config:/config `
     -p 8123:8123 `
     ghcr.io/home-assistant/home-assistant:stable
   ```

   Pulls the image on first run (~1GB), then starts it in the background.
   `-v ${PWD}/homeassistant-config:/config` persists Home Assistant's settings/database in a
   local folder rather than losing them if the container is recreated.

   **Windows-specific note**: most Home Assistant guides use `--network=host` instead of
   `-p 8123:8123`, for LAN auto-discovery via broadcast. `--network=host` does not work
   correctly on Docker Desktop for Windows (only on native Linux hosts) — not a blocker here,
   since the plan is to give `localtuya` the device's IP and `local_key` directly (via
   `tinytuya scan`, above) rather than relying on broadcast auto-discovery.

   After ~1-2 minutes on first boot, open `http://localhost:8123` for the onboarding wizard
   (create a local admin account, set location to Cape Town for correct sunrise/sunset and
   timezone-dependent automations, though neither matters much for this project's purposes).

2. **Install HACS** (Home Assistant Community Store) via Settings → Add-ons → Add-on Store —
   `localtuya` is community-distributed, not a built-in HA integration.
3. **Install `localtuya`** via HACS, restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → localtuya.** First-time setup accepts the
   Tuya Cloud *project's* Access ID/Client ID + Access Secret (from the project's
   Overview/Authorization tab — not the device's `local_key`) to enable device auto-discovery.
5. **Add the device**: Device ID, `local_key`, and the real LAN IP.
6. **Map data points (DPs) to entities.** Not yet confirmed live, but the Tuya smart-plug
   convention for a `cz`-category device with energy monitoring is typically:

   | DP | Meaning |
   |---|---|
   | 1 | Switch on/off |
   | 17 | Cumulative energy (`add_ele`) |
   | 18 | Current |
   | 19 | Power |
   | 20 | Voltage |

   `localtuya`'s config flow can usually detect and list live DPs during setup rather than this
   needing to be guessed blind — treat the table above as a starting hypothesis to confirm, not a
   certainty.
7. **Build a `HomeAssistantReadingSource` ingestion adapter** (`backend/app/ingestion/`,
   alongside the existing simulated-CSV path) that either:
   - polls Home Assistant's REST API (`GET /api/states/<entity_id>`, authenticated with a
     Long-Lived Access Token) on an interval, matching this project's existing
     poll-and-ingest pattern, or
   - is triggered by a Home Assistant automation (`rest_command`) that POSTs to our own API on
     every state change.

   Poll-based is the better fit given the existing architecture — it reuses the same
   "fetch a structured reading, validate, ingest" shape as the simulated-CSV path, with no
   change needed to the validation, analytics or presentation layers. Map the polled values into
   the existing `RawReading` shape: `device_id`, `timestamp`, `voltage_v`, `current_a`,
   `power_kw`, `energy_kwh_interval`, `switching_state`, `quality_flag`.

---

## What's actually built today: polling via `tinytuya.Cloud` (`backend/app/ingestion/tuya_source.py`)

Reuses the *exact same* validation/ingestion functions the simulated CSV path already uses
(`classify_reading`, `get_or_create_site`, `get_or_create_channel`) — a real Tuya reading goes
through identical quality-flagging to a simulated one. Run it directly:

```powershell
python -m app.ingestion.tuya_source            # poll once
python -m app.ingestion.tuya_source --loop 900  # poll every 900s, indefinitely
```

Authenticates with just `TUYA_ACCESS_ID`/`TUYA_ACCESS_SECRET` from `.env` — no username/password,
no login call, no `1106` to fight. This is deliberately a much smaller adapter than the earlier
`tuya-iot-py-sdk`-based version: no `TuyaDeviceListener`, no persistent message-queue connection,
just a function that calls `cloud.getstatus(device_id)` and maps the result into a `Reading`.

### DP codes and scale factors — VERIFIED, not guessed

Retrieved via `python -m tinytuya wizard -key <id> -secret <secret> -region eu`, which returns
this exact product's real Device Function schema (`add_ele`'s scale was wrongly assumed to be 2
in early drafts of this doc — it's actually 3):

| DP | code | type | scale/unit | conversion |
|---|---|---|---|---|
| 1 | `switch_1` | Boolean | — | direct |
| 17 | `add_ele` | Integer | scale=3 | raw ÷ 1000 → kWh |
| 18 | `cur_current` | Integer | unit=mA, scale=0 | raw ÷ 1000 → A |
| 19 | `cur_power` | Integer | unit=W, scale=1 | raw ÷ 10 → W (÷ 1000 again for kW) |
| 20 | `cur_voltage` | Integer | unit=V, scale=1 | raw ÷ 10 → V |

Live-verified real reading from the physical device: `switch_1=on, cur_voltage≈236.6V,
cur_current=0A, cur_power=0kW, add_ele=0.001 kWh` — plausible idle-load South African mains
values, and confirmed landing correctly in the local database as a `Reading` row with
`quality_flag=valid`.

**Deliberately not solved by this path — the multi-household quota problem**: Cloud → Usage on
the Tuya platform shows the free tier gives **30,000 API calls/month** but **140,000 message
subscriptions/month**. `tinytuya.Cloud.getstatus()` is a plain REST call, so it counts against the
30,000 figure like any polling approach — at a 15-minute interval, 10 devices (one per household)
already costs 28,800 calls/month, no margin, and over budget the moment any household has a second
device. This is fine for today's one-device proof of concept polled occasionally, but was never
going to scale to 10 households on its own.

**The originally-intended fix for that — Tuya's Cloud Message Queue (Pulsar, via
`tuya-iot-py-sdk`'s `TuyaOpenMQ`/`TuyaDeviceManager`), which pushes a message on every device
status change instead of being polled — remains blocked** on `TuyaOpenAPI.connect()` returning
`{'code': 1106, 'msg': 'permission deny'}`. Ruled out so far: wrong Access ID/Secret (fixed a real
`.env` bug), wrong password (error changed from "wrong password" to "permission deny" once auth
params were corrected — a different failure class), missing Cloud Service subscription (**IoT
Core, Authorization Token Management, Smart Home Basic Service, Data Dashboard Service are all
confirmed "In service"**). Confirmed by reading the actual installed SDK source
(`tuya_iot/openapi.py`) that this login is unavoidable for `TuyaOpenMQ` — there's no
client-credentials-only mode in that SDK. Not yet tried: an actual Tuya support ticket, or a
one-time third-party-login consent/authorization step on the Smart Life account itself (unverified
hypothesis). **`tinytuya` cannot substitute here** — confirmed via `dir(tinytuya)` inspection that
it has no message-queue/Pulsar client at all, only low-level local TCP packet helpers.

**Also still open, deliberately not solved yet**:
- `DEVICE_REGISTRY` (device_id → site_id/controller_channel) is a hardcoded dict for the one test
  device right now — a real per-household onboarding flow needs to replace it before a second
  household exists, not a code edit per new site. Current plan is one real device per household
  (see the 2026-09-29 update above), so each new entry is a new `site_id`, not a new channel on an
  existing one.
- **Where this actually runs in production isn't decided.** A one-shot poll works fine run
  manually; a real deployment needs either a scheduled job (cron/Render Cron Job hitting
  `--loop`-less mode periodically) or a long-running Background Worker service — Render's
  free-tier *web* services spin down on inactivity and can't run `--loop` continuously, so a
  Background Worker (a distinct, always-on service type) is the likely answer once this needs to
  run unattended, but it hasn't been set up or costed yet.
- The 10-household quota/push question above is the real remaining architectural gap before this
  scales past one device.
