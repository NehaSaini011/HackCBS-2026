# mock_for_now

Offline fixtures for every Group API response, plus the route table the app uses to
find them. **This folder is the single source of mock data** — mock mode reads it,
and so does the live-mode fallback.

## Why it exists

Person 2's backend is not ready yet, so the app has to work without it. But mock data
must never be mistaken for a real result, so every response served from here is
labelled in the UI.

## How a request is resolved

```
request
  │
  ├─ VITE_USE_MOCKS === "true"  ──────────────► this folder           (MOCK DATA)
  │
  └─ live: fetch the real API
        ├─ 2xx ──────────────────────────────► real data              (LIVE)
        │     └─ and if the response has a MOCK: true header, it is
        │        reported as mock instead
        │
        └─ could not answer ─────────────────► this folder           (MOCK FALLBACK)
              unreachable / timed out / 5xx / 404
```

A **4xx is never replaced by a fixture.** Wrong credentials, a blocked approval and
invalid input are real answers; hiding them behind mock data would hide real bugs.
The rule lives in `shouldFallback()` in `../src/api.ts`.

If the fixture cannot answer either — an unknown incident id, say — the original error
is thrown, so you still see the real reason.

## How it is labelled

Three independent places say where the data came from, so a fixture can never pass as a
result:

| Indicator | Live | Mock | Fallback |
|---|---|---|---|
| Header pill | `LIVE API` | `MOCK DATA` | `MOCK FALLBACK` |
| Sidebar | `Online` | `Mock` | `Mock fallback` |
| Panel footer | `Live · <url>` | `MOCK DATA` | `MOCK FALLBACK` |

A fallback also raises an amber banner naming the endpoint and the reason, e.g.
*"The API could not answer `GET /findings` (unreachable)"*.

## Files

| File | Answers | Shape |
|---|---|---|
| `_manifest.json` | — | route table (method + path → file) |
| `login.json` | `POST /auth/login` | map of email → `{ token, user }` |
| `me.json` | `GET /me` | `User` |
| `findings.json` | `GET /findings` | `Finding[]` |
| `incidents.json` | `GET /incidents/{id}`, approve, reject | map of id → `Incident` |
| `lessons.json` | `GET /lessons` | `Lesson[]` |
| `group_overview.json` | `GET /group/overview` | `CompanyCard[]` |
| `group_risks.json` | `GET /group/risks`, push | `RiskRow[]` |
| `meko.json` | `GET`/`PUT /settings/meko` | `{ mode }` |

Every shape matches `../src/types.ts`, which matches the team contract. If a shape here
drifts from the contract, the screens break only in live mode — so keep them in step.

## Adding or changing an endpoint

1. Add the response body as a JSON file in this folder, in the contract shape.
2. Add a row to `_manifest.json`:
   ```json
   { "method": "GET", "path": "/incidents/{id}/timeline", "file": "timeline.json" }
   ```
   Use `"pick": "id"` when the file is a map keyed by a path parameter.
3. That's it — no code change. `src/mockEngine.ts` reads the manifest.

Restart `npm run dev` after editing.

## Live data is still simulated, not measured

`incidents.json` sets `proof.method` to `"fake"`, and the UI says **"Simulated proof
(test mode) — this is not a real test result"**. Do not change that unless a real fork
prover actually ran. The incidents, latencies and lessons here are scripted examples,
not measurements.

## Marking fixtures from the server side

If Person 2's backend also serves fixture data, it should say so with a response header:

```
MOCK: true
```

The client reads it and reports that response as mock even though it was a real `200`.

**For a cross-origin response the header must also be exposed**, or the browser will
hide it from JavaScript:

```
Access-Control-Expose-Headers: MOCK
```
