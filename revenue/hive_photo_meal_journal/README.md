# MealFrame — private photo meal journal

MealFrame is a local-first browser journal for adults who want a simple record of meals without fabricated nutritional precision. It stores meal photos, editable ingredient lists, plain-language portion notes, reusable recipes, and weekly exports in one local SQLite database.

This is the publication recovery of Hive demand `bm-hive-20260908-019`. **ASTRA-MEALFRAME retains original product/design credit.** ZTK-Q4M7 recovered the stale unpublished lane, rebuilt the same claimed root, tested it, and integrated it after six days with no durable source/branch/PR/checkpoint.

## Offer status

The source demand proposed **$5/month**, with an optional family recipe-library plan later. That is an offer hypothesis, not an observed sale. This repository contains a working first version; no buyer, subscription, payment, or revenue is claimed.

## Run

Python 3.10+; no third-party runtime packages.

```bash
cd revenue/hive_photo_meal_journal
python3 server.py --db mealframe.sqlite3 --demo
```

Open `http://127.0.0.1:8767`. The default host is loopback. `--demo` is idempotent and loads one explicitly self-authored recipe, one fictional meal, and `demo_meal.svg`.

All people who can reach a running instance share its journal. This is a local single-workspace app, **not** a multi-tenant hosted service. Keep the database private to its intended user.

## What the app actually does

- Imports a user-selected JPEG, PNG, WebP, GIF, or SVG meal image up to 5 MiB and stores the exact bytes locally in SQLite with SHA-256 metadata.
- Records a date, title, user-edited ingredients, plain-language portion note, and freeform note.
- Saves reusable recipes.
- Offers ingredient suggestions from **saved recipes and prior meal history only**. Suggestions are labeled with that basis. The application does not inspect photo pixels to infer food.
- Exports a Monday-starting selected week as portable JSON or printable HTML.
- Deletes individual meals, including their photo bytes, with optimistic-version guards.
- Deletes all meal/photo/recipe data only after the exact phrase `DELETE ALL MEALFRAME DATA`.
- Uses exact operation IDs plus canonical payload hashes for retry-safe mutations. Repeating the same operation returns its original result; reusing an operation ID with different data is rejected.
- Uses SQLite `BEGIN IMMEDIATE` plus versions to reject stale concurrent edits instead of silently overwriting them.

## Explicit non-features

MealFrame does **not** infer or prescribe calories, macros, nutrients, diagnoses, treatment, dietary targets, medical outcomes, ingredient certainty, allergies, or food safety. There is no external model/API call, analytics beacon, cloud photo upload, automated message, payment provider, or deployment hook.

A photo hash binds the local bytes; it does not prove what the meal contains. User-entered ingredients and portion notes are journal content, not verified facts.

## Browser/API

The browser calls the same local HTTP API exercised by the test suite.

- `GET /api/state` — current meals/recipes without photo bytes.
- `GET /photo/{meal_id}` — exact local photo bytes.
- `GET /api/suggestions?title=...` — saved recipe/history suggestions only.
- `GET /api/export?week=YYYY-MM-DD&format=json|html` — the week must start Monday.
- `POST /api/meal/create`
- `POST /api/meal/update`
- `POST /api/meal/delete`
- `POST /api/recipe/save`
- `POST /api/delete-all`

Mutation requests require `operation_id`. Meal/recipe updates also require the current version.

The browser currently exposes create/save/suggest/export/delete-all flows. Update/delete-meal operations are in the API/model for integrations; no claim is made that every API operation has a dedicated GUI control in v1.

## Privacy and export semantics

Photo bytes never appear in `/api/state` or the week export. A journal item exposes a local `/photo/{id}` route and content hash. Printable HTML says when a source entry had a photo but does not embed the bytes. Deleting the meal removes its BLOB through SQLite row deletion; delete-all removes every meal/photo and recipe. Minimal idempotency receipts remain so retry semantics do not resurrect deleted content; receipts contain payload hashes/result counts, not photo bytes or meal text.

If you need to move the journal, stop the server and copy its SQLite file. Weekly JSON is a content export, not a complete database backup because it intentionally omits photo bytes.

## Scope boundary

No real meal/customer data are committed. `demo_meal.svg` is self-authored source art and the demo record is fictional. No customer contact, provider action, external upload/send, payment, deployment, paid compute, or owner-device action is part of this source delivery.
