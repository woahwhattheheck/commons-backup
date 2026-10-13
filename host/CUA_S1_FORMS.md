# CUA-S1-FORMS scoring and browser form execution

## Hosted Commons path

The production deployment has two cloud functions on the existing Commons Vercel project. `POST https://commons-spark-mcp.vercel.app/cua-s1` scores a context and 2–32 options using a hash-pinned ONNX export of the official checkpoint. `POST https://commons-spark-mcp.vercel.app/cua-s1/form` opens a fresh isolated Chromium in the cloud, reads visible form controls, and calls that scorer. Neither route needs this laptop, its Hugging Face cache, a local Chrome profile, or Codex tokens at request time. Commons MCP exposes the scorer as `cua_s1_score`; the form route is the browser operator.

The form route accepts a public exact URL, a title, and up to 29 explicit source entities. The target must resolve to a public IPv4 address; Chromium pins that address and loads only same-host resources. Sites that require assets from other domains may need a different browser carrier. It previews by default:

```json
{"url":"https://example.com/form","form_title":"Contact","entities":[{"label":"Name","value":"Ada"}]}
```

Send that JSON to `/cua-s1/form` with `Content-Type: application/json`. The response includes every scored control and `planned_actions`. Add `"execute":true` only after inspecting the preview; that requires a complete plan and verifies values after each fill. Add `"submit":true` as well to permit one exact `Submit` or `Submit Form` click. A click receipt reports delivery, while site acceptance still needs a site-specific receipt. The cloud browser is a new session, so this route is for pages accessible without the owner's signed-in desktop profile.

The ONNX artifact is pinned in `host/cua_s1_cloud/` and tested against the official PyTorch checkpoint, including 32-option and long UTF-8 cases. The upstream model itself truncates context at 224 bytes and each option at 96 bytes. `GET /cua-s1` reports the artifact hash and these limits; `GET /cua-s1/form` reports the browser runtime. The [hosted runtime README](cua_s1_cloud/README.md) describes export and deployment. Source code and local tests do not establish production availability; use those live GET routes and an actual preview response as the activation check.

`host/cua_s1_forms.py` exposes the published [CUA-S1-FORMS](https://huggingface.co/cua-ai/cua-s1-forms) checkpoint as a local JSON choice scorer and a model-backed adapter for upstream Cua-S1 planning. `host/cua_s1_run.py` composes that planner with `host/cua_s1_browser.py` to observe and act on one exact Chrome tab through direct Chrome DevTools Protocol (CDP). The scorer command below remains read-only.

The upstream [source package](https://github.com/trycua/cua/tree/main/libs/cua-s1) requires Python 3.11–3.13, PyTorch, NumPy, and safetensors. Install `cua-s1` from that package and download the matching `cua-s1-forms.safetensors` and `cua-s1-forms.json` files from the model repository. The upstream loader checks the checkpoint format and tensor signature. The source and published checkpoint carry MIT licenses. This path uses no `llama.cpp` runtime or dependency.

Example input, saved as `request.json`:

```json
{
  "context": "TASK fill the form from the document, then submit\nFORM Northwind Clinic - New Patient Registration\nELEMENT Edit \"Phone number\" value=\"\"\n",
  "options": ["fill Tel: (503) 555-0142", "fill DOB: 03/14/1987", "check", "click", "skip"]
}
```

Run with the local checkpoint and matching JSON sidecar:

```powershell
python host/cua_s1_forms.py --checkpoint C:\path\to\cua-s1-forms.safetensors --input request.json
```

Output contains the selected index, one probability per option, the actual device, and `"executed": false`. The source model truncates context to 224 UTF-8 bytes and each option to 96 bytes; keep the element context concise. The model only chooses from supplied options. Its published evaluation includes three real demo forms and three PDFs, so wider reliability has not been established. [Model card](https://huggingface.co/cua-ai/cua-s1-forms) and [upstream scope and safety guidance](https://github.com/trycua/cua/blob/main/libs/cua-s1/MODEL_CARD.md) govern use.

On this Windows CPU, the published checkpoint chose the phone number option in the example above with probability 0.99998. A second probe using `ELEMENT CheckBox "I agree to terms" checked=false` chose `skip` with probability 1.0, even though `check` was offered. These are observations on two inputs, not a reliability estimate; inspect each proposal before using it.

## Run against a browser form

The browser adapter implements upstream `BaseDriver` with a direct CDP connection and token-based `set_value`/`click`. It attaches to **one already-open Chrome tab by exact URL**; it never starts a Chrome profile, opens a URL, or uses the Chrome extension. Install the optional `playwright` Python package from PyPI for this path. Chrome must already expose a direct CDP endpoint (default `http://127.0.0.1:9222`), and the exact tab URL must match `--url`.

First parse the source document or known account facts into explicit entities. The model only chooses among these values. Save this input as `form.json`:

```json
{"form_title":"Northwind Clinic - New Patient Registration","entities":[{"label":"Tel","value":"(503) 555-0142"},{"label":"DOB","value":"03/14/1987"}]}
```

Preview the observed controls and model choices without changing the page:

```powershell
python -m host.cua_s1_run --url "https://example.com/form" --checkpoint C:\path\to\cua-s1-forms.safetensors --input form.json
```

Once the plan and target are correct, add `--execute` to fill selected fields and check selected boxes. Add `--submit` **only** when the form should be submitted; it permits at most one exact `Submit` or `Submit Form` button click. The browser adapter reads the page after every action and reports observed results. `--min-confidence` sets the minimum probability for an action (default `0.5`). A stale tab, ambiguous control, missing token, unavailable CDP connection, or unconfirmed action returns a typed failure rather than a success claim.

```powershell
python -m host.cua_s1_run --url "https://example.com/form" --checkpoint C:\path\to\cua-s1-forms.safetensors --input form.json --execute
```

This runner uses the upstream [planner and driver contract](https://github.com/trycua/cua/tree/main/libs/cua-s1/python/src/cua_s1). The portable Cua Driver manifest still lacks `set_value`; the browser adapter supplies that capability through the connected Chrome runtime. The model's [published evaluation](https://huggingface.co/cua-ai/cua-s1-forms) is narrow, so inspect proposals and readbacks for the actual form before treating them as a reliable workflow.

## Call from a Commons peer

The existing shared equipment catalog exposes `cua_s1_form` with the same plan and execute behavior. Discover the tool through `GET /v1/tools` on the local gateway or the established Commons equipment carrier, then call it with an exact open tab URL, a form title, and source entities. The tool finds the official checkpoint in the host's local Hugging Face cache unless `checkpoint` is supplied. `execute` and `submit` default to `false`.

```json
{"name":"cua_s1_form","arguments":{"url":"https://example.com/form","form_title":"Northwind Clinic - New Patient Registration","entities":[{"label":"Tel","value":"(503) 555-0142"}],"execute":false}}
```

See [shared equipment](../integrations/shared_equipment/README.md) for the gateway call envelope and remote peer road. The runtime must have direct CDP access to the requested Chrome tab. A successful click report means the browser action was delivered; a real site's acceptance or stored form submission needs that site's own receipt or readback.
