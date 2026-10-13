# Recurring service CSV → waste-desk manifest

Use a retained CSV to initialize the existing Commercial Waste Route Desk without hand-authoring nested customer/site/container JSON. One row means **one recurring service plan**, never a completed pickup or billable event. The converter does not open or mutate any database.

## Create the manifest

```sh
python revenue/hive/commercial-waste-route-operations/csv_manifest.py recurring-services.csv \
  --business-timezone America/Kentucky/Louisville \
  --out new-waste-manifest.json
```

The output directory must already exist. The named output must not exist: exclusive creation refuses overwrites, including accidentally targeting the input. A successful command prints counts and the chosen timezone. If interrupted during output writing, a partial file may remain; only import output from a successful command and keep the retained CSV.

Without `--out`, the complete manifest is written to standard output. `--preview` instead returns a JSON object with `counts`, `business_timezone`, and `manifest_text`. No partial manifest is produced for invalid input.

Open the console from [WEB_CONSOLE.md](WEB_CONSOLE.md). In **Workspace**, choose a CSV file or paste the same twelve columns, enter the business timezone, and press **Preview CSV**. Preview calls `csv_manifest.preview` through the loopback console and copies `manifest_text` into the manifest editor verbatim. It shows customer, site, container, and plan counts. Invalid input stays a single structural error with its line; nothing is imported, and a rejected preview does not replace an already reviewed manifest or clear its download. A non-UTF-8 or oversize file does not replace the paste box. **Download valid manifest** saves that same text. **Initialize this workspace** is still the explicit command, and an initialized database cannot be replaced. A JSON file can still be loaded directly.

## Required CSV columns

All twelve columns are required. Column order may vary; header case and surrounding whitespace are normalized. Extra columns, blank headers, and duplicate names after normalization are rejected. Save comma-delimited UTF-8 CSV; a UTF-8 BOM and quoted multiline fields are accepted.

| Column | Meaning |
|---|---|
| `customer_id` | Stable customer identity, at most 128 characters. |
| `customer_name` | Repeated rows for an identity must use the same name. |
| `currency` | Explicit three-letter ASCII currency code; converted to uppercase. |
| `site_id` | Globally unique site identity; cannot move between customers in this import. |
| `site_name` | Same identity must retain the same name. |
| `container_id` | Globally unique container identity; cannot move between sites. |
| `container_label` | Human-readable container label. |
| `container_type` | Retained type description, not an inferred category. |
| `plan_id` | Globally unique recurring-plan identity. Every row needs its own ID. |
| `weekday` | `0` through `6`, Monday through Sunday, or a full English weekday name. |
| `service_code` | Explicit service description/code used by the existing desk. |
| `price_minor` | Nonnegative integer in the stated currency's minor units. No decimals, commas, currency symbols, scientific notation, or signs. |

Outer whitespace is stripped from values, consistent with the existing engine's text normalization. Names, descriptions, and codes must be nonempty and at most 240 characters. Prices are parsed as integers and bounded to SQLite's signed 64-bit positive range; zero is a valid price. No floating-point conversion or currency conversion takes place. Two weekday plans for the same container require two distinct plan IDs. The tool does not guess abbreviations such as `T`, turn a monthly fee into a per-stop price, or infer a currency from a symbol.

## Fictional example

The values below are demonstration inputs, not customer data or a price recommendation:

```csv
customer_id,customer_name,currency,site_id,site_name,container_id,container_label,container_type,plan_id,weekday,service_code,price_minor
ACME,Acme Coffee Group,USD,DOWNTOWN,Downtown Cafe,DOWNTOWN-8YD,Rear 8yd,front-load 8yd,P-DOWNTOWN-MON,Monday,RECURRENT_PICKUP,12900
ACME,Acme Coffee Group,USD,DOWNTOWN,Downtown Cafe,DOWNTOWN-8YD,Rear 8yd,front-load 8yd,P-DOWNTOWN-WED,Wednesday,RECURRENT_PICKUP,12900
ACME,Acme Coffee Group,USD,MARKET,Market Cafe,MARKET-4YD,Side 4yd,front-load 4yd,P-MARKET-MON,0,RECURRENT_PICKUP,8900
```

This groups into one customer, two sites, two containers and three plans. The price is still a scheduled minor-unit amount. Generating a route, recording actual service, resolving exceptions and retaining invoice drafts are separate explicit desk operations.

## Conflicts are not silently resolved

Repeated customer/site/container rows are the expected way to describe hierarchy, but their descriptors and parents must agree. A conflicting customer name/currency, a site reassigned to another customer, or a container with a different site/label/type rejects the complete import. Repeated `plan_id` values also reject it—even byte-identical duplicate rows are not silently dropped. This prevents accidental duplicate recurring work from being hidden by a first-row-wins or last-row-wins policy.

Errors identify the physical CSV line where the record ends, and previous-line references where available. Multiline quoted records can span more than one physical line. Correct the retained input and rerun; successful earlier rows are not emitted as a partial replacement. Limits are 1 MiB UTF-8 input and 10,000 plan records. Empty physical lines are ignored by the CSV parser; rows containing missing/blank required fields are errors.

## Reuse by the browser UI

`preview(csv_text, timezone_policy)` is the pure-data adapter the console calls from `POST /api/csv-preview`. It returns display counts and **manifest_text as text**. The Workspace form copies that text verbatim into the manifest editor and can download it. It does not JSON-parse and reserialize the manifest through JavaScript numbers. Initialize remains the only database mutation. An initialized workspace disables this form. No second engine or operator console is added.
