# CUA-S1 cloud inference

This directory is an inference-only Python container. It serves the official
CUA-S1-FORMS checkpoint through `POST /score`; it never controls a browser.
It can run on any Docker-capable Python container host independently of a laptop
or a Codex session. The host must permit an outbound download of two small
files from Hugging Face on first startup and retain enough memory for CPU
PyTorch. The checkpoint files are bound to a fixed repository revision and
SHA-256 values before loading.

## Vercel ONNX function

`api/cua_s1.py` loads `cua-s1-forms.onnx` through `onnxruntime` and uses a
NumPy transcription of the upstream byte collator. This is the lightweight
deployment path in Commons' existing Vercel project. It requires NumPy and
onnxruntime Python dependencies, a `/cua-s1` rewrite to the Python function,
and a remote deployment/readback. The 2.95 MB ONNX artifact is committed with
the source and hash-checked at function cold start, so it does not download
weights at request time. It preserves the official 224-byte context and
96-byte option truncation, with a fixed maximum of 32 candidate options.
The parity test compares its logits and winners against the PyTorch checkpoint
on six cases, including a 32-option form and long UTF-8 inputs that cross the
checkpoint's byte truncation boundaries. The browser operator is
`api/cua_s1_form.mjs`; it launches an isolated Chromium in a Vercel Node
function and calls the scoring route. `GET /cua-s1/form` reports its runtime.

Regenerate the artifact only from the pinned official checkpoint:

```sh
python -m host.cua_s1_cloud.export_onnx --checkpoint /path/to/cua-s1-forms.safetensors
```

The exported file's expected SHA-256 is recorded in `runtime_onnx.py`.

Build from the Commons repository root:

```sh
docker build -f host/cua_s1_cloud/Dockerfile -t commons-cua-s1 .
docker run --rm -p 8080:8080 commons-cua-s1
```

Call the service:

```sh
curl -sS http://localhost:8080/health
curl -sS -X POST http://localhost:8080/score \
  -H 'content-type: application/json' \
  --data '{"context":"ELEMENT Edit Phone","options":["fill 555-0142","skip"]}'
```

The response includes `selected_index`, all choice probabilities, checkpoint
revision, CPU device, and `executed:false`. A browser operator must use its own
fresh observation and verify any action. This endpoint has no action route.

The existing Commons Oracle Always Free definition under
`infra/oracle_always_free/` is not provisioned by this package. Hosting the
container on a real provider and checking its remote `/health` and `/score`
are separate deployment steps; local tests do not establish cloud uptime.

Hugging Face Docker Spaces can host this image using a Space `README.md` with
`sdk: docker` and `app_port: 8080`, but [current Spaces rules](https://huggingface.co/docs/hub/spaces-overview)
require a paid account plan to create a compute Space even on CPU Basic. The
current machine's `hf auth whoami` reports no login, so that deployment route
has not been activated here.
