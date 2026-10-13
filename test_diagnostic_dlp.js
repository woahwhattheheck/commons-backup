#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("diagnostic.html", "utf8");
const inlineScripts = Array.from(html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi), (match) => match[1]);
const dlpScript = inlineScripts.find((source) =>
  source.includes("forbiddenNames") && source.includes('form.addEventListener("submit"')
);
assert(dlpScript, "diagnostic DLP inline script was not found");

let submitListener = null;
let capture = null;
const output = { textContent: "" };
const form = {
  elements: [],
  addEventListener(type, listener, options) {
    if (type === "submit") {
      submitListener = listener;
      capture = options;
    }
  },
};
const document = {
  getElementById(id) {
    if (id === "say") return form;
    if (id === "out") return output;
    return null;
  },
};
vm.runInNewContext(dlpScript, { document, JSON, Object, Array, String, URL }, { filename: "diagnostic.html#dlp" });
assert.strictEqual(typeof submitListener, "function", "diagnostic submit listener was not registered");
assert.strictEqual(capture, true, "diagnostic DLP listener must run in capture phase");

function submit(body, fieldName = "body") {
  form.elements = [
    { name: "to", value: "OFFER" },
    { name: fieldName, value: body },
  ];
  const event = {
    prevented: false,
    stopped: false,
    preventDefault() { this.prevented = true; },
    stopImmediatePropagation() { this.stopped = true; },
  };
  output.textContent = "";
  submitListener(event);
  return event;
}

const canonicalForbiddenNames = [
  "authorization", "aws_access_key_id", "password", "passwd", "passphrase",
  "api_key", "access_token", "auth_token", "client_secret", "secret", "token",
  "private_buyer", "private_customer", "buyer_private", "model_bytes",
  "model_weights", "gguf_bytes", "gguf_file", "weights", "base64", "b64",
  "tax_id", "taxpayer_id", "taxpayer_identification", "ein", "tin",
  "email", "email_address", "customer_email", "private_email", "contact_email",
  "buyer_email", "work_email", "contact", "private_contact", "customer_contact",
  "buyer_contact", "phone", "phone_number", "telephone", "mobile", "mobile_phone",
  "customer_phone", "private_phone", "contact_phone", "buyer_phone", "name",
  "full_name", "first_name", "last_name", "legal_name", "customer_name",
  "private_name", "contact_name", "buyer_name", "address", "street_address",
  "address_line_1", "address_line_2", "mailing_address", "postal_address",
  "customer_address", "private_address", "contact_address", "postal_code",
  "zip_code", "postcode", "routing_number", "account_number", "bank_account",
  "bank_account_number", "bank_routing_number", "aba_routing_number", "iban",
  "swift", "swift_code", "bic", "sort_code",
  "aws_secret_access_key",
];

for (const field of canonicalForbiddenNames) {
  for (const payload of [
    JSON.stringify({ [field]: "hidden" }),
    JSON.stringify({ safe: { nested: { [field]: "hidden" } } }),
    `"${field}": "hidden"`,
    `${field}=hidden`,
  ]) {
    const event = submit(payload);
    assert.strictEqual(event.prevented, true, `${field} payload was not prevented: ${payload}`);
    assert.strictEqual(event.stopped, true, `${field} payload did not stop propagation: ${payload}`);
  }
}

for (const payload of [
  "AUTHORIZATION: Bearer owner-secret-token",
  "AWS_ACCESS_KEY_ID: AKIAABCDEFGHIJKLMNOP",
  "AUTH: ghp_1234567890abcdef",
  "PAYLOAD: data:application/octet-stream;base64,QUJDREVGRw==",
  "alice.customer@example.com",
  "555-123-4567",
  "+1 (555) 123-4567",
  "5551234567",
  "123 Main Street",
  "A".repeat(100),
]) {
  const event = submit(payload);
  assert.strictEqual(event.prevented, true, `named sensitive payload was not prevented: ${payload}`);
  assert.strictEqual(event.stopped, true, `named sensitive payload did not stop propagation: ${payload}`);
}

for (const name of canonicalForbiddenNames) {
  const event = submit("hidden", name);
  assert.strictEqual(event.prevented, true, `sensitive form field name was not prevented: ${name}`);
  assert.strictEqual(event.stopped, true, `sensitive form field name did not stop propagation: ${name}`);
}

const reviewerCamelFields = [
  "routingNumber", "accountNumber", "bankAccount", "customerEmail",
  "phoneNumber", "fullName",
];
for (const field of reviewerCamelFields) {
  for (const payload of [
    JSON.stringify({ [field]: "hidden" }),
    JSON.stringify({ public: { nested: { [field]: "hidden" } } }),
    `${field}=hidden`,
  ]) {
    const event = submit(payload);
    assert.strictEqual(event.prevented, true, `camelCase payload was not prevented: ${payload}`);
    assert.strictEqual(event.stopped, true, `camelCase payload did not stop propagation: ${payload}`);
  }
  const fieldEvent = submit("hidden", field);
  assert.strictEqual(fieldEvent.prevented, true, `camelCase form field was not prevented: ${field}`);
  assert.strictEqual(fieldEvent.stopped, true, `camelCase form field did not stop propagation: ${field}`);
}

let overDepthPayload = JSON.stringify({ privateEmail: "alice@example.com" });
for (let layer = 0; layer < 5; layer += 1) overDepthPayload = encodeURIComponent(overDepthPayload);
const encodedReviewerPayloads = [
  "alice%40example.com",
  "%7B%22token%22%3A%22hidden%22%7D",
  "%7B%22privateEmail%22%3A%22alice%40example.com%22%7D",
  "%257B%2522privateEmail%2522%253A%2522alice%2540example.com%2522%257D",
  "customerEmail%3Dalice%2540example.com",
  overDepthPayload,
];
for (const encoded of encodedReviewerPayloads) {
  const event = submit(encoded);
  assert.strictEqual(event.prevented, true, `encoded payload was not prevented: ${encoded}`);
  assert.strictEqual(event.stopped, true, `encoded payload did not stop propagation: ${encoded}`);
}

const fullPostPrefix = [
  "PLAIN: Public, non-confidential GGUF diagnostic purchase intent.",
  "OFFER_ID: gguf-diagnostic-10d-12k",
  "TERMS_SHA256: 1c0756062563415e551587a5f1ab22147366d406135de6c45ccbd3a562985730",
  "PURCHASE_INTENT: YES",
  "GGUF_CONTROL: YES",
  "HARNESS_READY: YES",
  "PUBLIC_CONTACT_URL: https://example.com/contact",
  "START_WINDOW: public",
  "PUBLIC_OBJECTIVE: reproducibility",
].join("\n");
for (const payload of [
  ...reviewerCamelFields.map((field) => `${field}=hidden`),
  ...encodedReviewerPayloads,
]) {
  const event = submit(`${fullPostPrefix}\n${payload}`);
  assert.strictEqual(event.prevented, true, `full-post bypass was not prevented: ${payload}`);
  assert.strictEqual(event.stopped, true, `full-post bypass did not stop propagation: ${payload}`);
}

let overDepthQuery = "privateEmail=hidden";
for (let layer = 0; layer < 5; layer += 1) overDepthQuery = encodeURIComponent(overDepthQuery);
const sensitivePublicContactUrls = [
  "https://example.com/contact?private+email%3Dhidden",
  "https://example.com/contact?privateEmail%3Dhidden",
  "https://example.com/contact?priv%FFateEmail=hidden",
  "https://example.com/contact?tok%FFen=hidden",
  "https://example.com/contact?pass%FFword=hidden",
  "https://example.com/contact?accountNum%FFber=hidden",
  "https://example.com/contact?topic=%FF",
  "https://example.com/contact?topic=%C3%28",
  "https://example.com/contact?payload=private%252Bemail%253Dhidden",
  "https://example.com/contact?payload=%257B%2522privateEmail%2522%253A%2522hidden%2522%257D",
  "https://example.com/contact?next=https%3A%2F%2Fpublic.example%2Fcontact%3FprivateEmail%253Dhidden",
  "https://example.com/contact#private_email=hidden",
  "https://example.com/contact#private%5Femail%3Dhidden",
  "https://example.com/contact#privateEmail=hidden",
  "https://example.com/contact#accountNumber=hidden",
  "https://example.com/contact#safe=1&privateEmail=hidden",
  `https://example.com/contact?payload=${overDepthQuery}`,
  "https://alice@example.com",
  "https://alice@127.0.0.1",
  "https://alice%40example.com",
  "https://alice%40127.0.0.1",
  "https://alice:secret@example.com",
  "https://alice:secret@127.0.0.1",
  "https://alice%3Asecret%40example.com",
  "https://alice%3Asecret%40127.0.0.1",
  "https://alice%2F@127.0.0.1/contact",
  "https://alice%3F@127.0.0.1/contact",
  "https://alice%23@127.0.0.1/contact",
  "https://alice%0A@example.com/contact",
  "https://alice%252F@127.0.0.1/contact",
  "https://@example.com",
  "https://:@example.com",
  "https://%40example.com",
];
for (const url of sensitivePublicContactUrls) {
  const fullPost = fullPostPrefix.replace(
    "PUBLIC_CONTACT_URL: https://example.com/contact",
    `PUBLIC_CONTACT_URL: ${url}`,
  );
  const event = submit(fullPost);
  assert.strictEqual(event.prevented, true, `sensitive public URL was not prevented: ${url}`);
  assert.strictEqual(event.stopped, true, `sensitive public URL did not stop propagation: ${url}`);
}

const nestedPrivateJson = JSON.stringify({ privateEmail: "hidden" });
const onceNestedPrivateJson = encodeURIComponent(nestedPrivateJson);
const twiceNestedPrivateJson = encodeURIComponent(onceNestedPrivateJson);
const sensitiveBareComponents = [
  "?privateEmail[0]=hidden",
  "?user.privateEmail=hidden",
  "?user[privateEmail]=hidden",
  "?PrIvAtEeMaIl=hidden",
  "?privateEmail=hidden",
  "?privateEmail%3Dhidden",
  "?private_email=hidden",
  "?customerEmail=hidden",
  "#privateEmail=hidden",
  "#privateEmail%3Dhidden",
  "#customerEmail=hidden",
  "?payload=privateEmail=hidden",
  "?payload=privateEmail%3Dhidden",
  "#payload=privateEmail%3Dhidden",
  "payload=privateEmail%3Dhidden",
  `?payload=${nestedPrivateJson}`,
  `?payload=${onceNestedPrivateJson}`,
  `?payload=${twiceNestedPrivateJson}`,
  `payload=${onceNestedPrivateJson}`,
  "%C0%AF",
  "%ED%A0%80",
  "%F4%90%80%80",
];
for (const payload of sensitiveBareComponents) {
  for (const candidate of [payload, `${fullPostPrefix}\n${payload}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, true, `bare/nested payload was not prevented: ${payload}`);
    assert.strictEqual(event.stopped, true, `bare/nested payload did not stop propagation: ${payload}`);
  }
}

const safeBareComponents = [
  "?topic=reproducibility",
  "?topic[0]=reproducibility",
  "?user.progress=steady",
  "?domain=docs.example.com",
  "?ToPiC[0]=reproducibility",
  "?UsEr.PrOgReSs=steady",
  "?progress=100%",
  "?progress=100%25",
  "?topic=C%2B%2B",
  "?note=%2",
  "?note=%GG",
  "#section-2",
  "#topic=C%2B%2B",
  "#progress=100%25",
  "payload=topic%3Dreproducibility",
  "payload=progress%3D100%2525",
];
for (const payload of safeBareComponents) {
  for (const candidate of [payload, `${fullPostPrefix}\nPUBLIC_OBJECTIVE: ${payload}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, false, `safe bare/nested payload was prevented: ${payload}`);
    assert.strictEqual(event.stopped, false, `safe bare/nested payload stopped propagation: ${payload}`);
  }
}

for (const field of [
  "privateEmail[0]", "user.privateEmail", "user[privateEmail]", "PrIvAtEeMaIl",
]) {
  const event = submit("hidden", field);
  assert.strictEqual(event.prevented, true, `sensitive path/mixed-case field was not prevented: ${field}`);
  assert.strictEqual(event.stopped, true, `sensitive path/mixed-case field did not stop propagation: ${field}`);
}
for (const field of [
  "topic[0]", "user.progress", "docs.example.com",
  "ToPiC[0]", "UsEr.PrOgReSs", "DoCs.ExAmPlE.CoM",
]) {
  const event = submit("reproducibility", field);
  assert.strictEqual(event.prevented, false, `safe path/dotted field was prevented: ${field}`);
  assert.strictEqual(event.stopped, false, `safe path/dotted field stopped propagation: ${field}`);
}

function nestedJsonArray(depth, value) {
  return "[".repeat(depth) + JSON.stringify(value) + "]".repeat(depth);
}
const belowSafeJson = nestedJsonArray(32, "topic=reproducibility");
const belowSensitiveJson = nestedJsonArray(32, "privateEmail=hidden");
for (const candidate of [belowSensitiveJson, `${fullPostPrefix}\nPUBLIC_OBJECTIVE: ${belowSensitiveJson}`]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, true, "below-bound nested sensitive JSON was not prevented");
  assert.strictEqual(event.stopped, true, "below-bound nested sensitive JSON did not stop propagation");
}
for (const candidate of [
  belowSafeJson,
  fullPostPrefix.replace("PUBLIC_OBJECTIVE: reproducibility", `PUBLIC_OBJECTIVE: ${belowSafeJson}`),
]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, false, "below-bound nested safe JSON was prevented");
  assert.strictEqual(event.stopped, false, "below-bound nested safe JSON stopped propagation");
}
const overDepthJson = nestedJsonArray(65, "topic=reproducibility");
for (const candidate of [overDepthJson, `${fullPostPrefix}\nPUBLIC_OBJECTIVE: ${overDepthJson}`]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, true, "over-depth JSON failed open");
  assert.strictEqual(event.stopped, true, "over-depth JSON did not stop propagation");
}
const safeBoundaryJson = JSON.stringify(Array(4095).fill(null));
const hostileOverNodeJson = JSON.stringify(Array(4097).fill(null));
const safeBoundaryJsonAssignment = `payload=${safeBoundaryJson}`;
const hostileOverNodeJsonAssignment = `payload=${hostileOverNodeJson}`;
for (const candidate of [safeBoundaryJsonAssignment, `${fullPostPrefix}\n${safeBoundaryJsonAssignment}`]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, false, "4096-node assignment JSON was prevented");
  assert.strictEqual(event.stopped, false, "4096-node assignment JSON stopped propagation");
}
for (const candidate of [hostileOverNodeJsonAssignment, `${fullPostPrefix}\n${hostileOverNodeJsonAssignment}`]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, true, "4098-node assignment JSON failed open");
  assert.strictEqual(event.stopped, true, "4098-node assignment JSON did not stop propagation");
}
for (const candidate of [
  "payload=[null,null",
  `${fullPostPrefix}\npayload=[null,null`,
  'payload={"topic":"reproducibility",}',
  `${fullPostPrefix}\npayload={"topic":"reproducibility",}`,
]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, true, "malformed assignment JSON failed open");
  assert.strictEqual(event.stopped, true, "malformed assignment JSON did not stop propagation");
}
for (const candidate of [
  "payload=alpha,beta",
  `${fullPostPrefix}\npayload=alpha,beta`,
  'payload={"topics":["reproducibility","diagnostics"]}',
  `${fullPostPrefix}\npayload={"topics":["reproducibility","diagnostics"]}`,
]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, false, "safe comma assignment was prevented");
  assert.strictEqual(event.stopped, false, "safe comma assignment stopped propagation");
}
for (const candidate of [
  'payload={"topic":"reproducibility","privateEmail":"hidden"}',
  `${fullPostPrefix}\npayload={"topic":"reproducibility","privateEmail":"hidden"}`,
]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, true, "comma-containing sensitive assignment JSON failed open");
  assert.strictEqual(event.stopped, true, "comma-containing sensitive assignment JSON did not stop propagation");
}
for (const field of ["privateEmail", "token"]) {
  const assignment = `payload=${JSON.stringify(JSON.stringify({ [field]: "hidden" }))}`;
  for (const candidate of [assignment, `${fullPostPrefix}\n${assignment}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, true, `quoted ${field} JSON assignment failed open`);
    assert.strictEqual(event.stopped, true, `quoted ${field} JSON assignment did not stop propagation`);
  }
}
for (const assignment of [
  `payload=${JSON.stringify("alpha,beta")}`,
  `payload=${JSON.stringify(JSON.stringify({ topics: ["reproducibility", "diagnostics"] }))}`,
]) {
  for (const candidate of [assignment, `${fullPostPrefix}\n${assignment}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, false, "safe quoted comma/JSON assignment was prevented");
    assert.strictEqual(event.stopped, false, "safe quoted comma/JSON assignment stopped propagation");
  }
}
for (const assignment of [
  `payload=${JSON.stringify("[null,null")}`,
  `payload=${JSON.stringify('{"topic":"reproducibility",}')}`,
  'payload="[null,null',
]) {
  for (const candidate of [assignment, `${fullPostPrefix}\n${assignment}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, true, "malformed quoted JSON assignment failed open");
    assert.strictEqual(event.stopped, true, "malformed quoted JSON assignment did not stop propagation");
  }
}
const quotedOverDepthJsonAssignment = `payload=${JSON.stringify(overDepthJson)}`;
const quotedOverNodeJsonAssignment = `payload=${JSON.stringify(hostileOverNodeJson)}`;
for (const assignment of [quotedOverDepthJsonAssignment, quotedOverNodeJsonAssignment]) {
  for (const candidate of [assignment, `${fullPostPrefix}\n${assignment}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, true, "overbudget quoted JSON assignment failed open");
    assert.strictEqual(event.stopped, true, "overbudget quoted JSON assignment did not stop propagation");
  }
}

for (const assignment of [
  'x["token"]="hidden"',
  "x['token']='hidden'",
  String.raw`root["to\u006ben"]="hidden"`,
  'root["topic]=reproducibility',
  String.raw`root["to\ken"]="hidden"`,
  "paßword=hidden",
  "paſſword=hidden",
  "ſecret=hidden",
  'x="{\\"token\\":\\"hidden\\"}"',
  'payload={"paſſword":"hidden"}',
  'payload={"paßword":"hidden"}',
  'payload={"ſecret":"hidden"}',
  "PUBLIC_CONTACT_URL: https://example.com/contact?payload=%7B%22pa%5Cu017f%5Cu017fword%22%3A%22hidden%22%7D",
  "PUBLIC_CONTACT_URL: https://alice%3Ahidden%0A%40example.com",
  "PUBLIC_CONTACT_URL: https://exa%7Fmple.com/contact",
  "PUBLIC_CONTACT_URL: https://exa%C2%85mple.com/contact",
  "PUBLIC_CONTACT_URL: https://alice%3Ahidden%C2%A0%40example.com",
  `x=[${Array(4096).fill("null").join(",")}]`,
  'privateEmail=""customerEmail=hidden',
  'publicObjective=""customerEmail=hidden',
  "privateEmail=''customerEmail=hidden",
  "publicObjective=''customerEmail=hidden",
]) {
  for (const candidate of [assignment, `${fullPostPrefix}\n${assignment}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, true, `adversarial assignment failed open: ${assignment.slice(0, 96)}`);
    assert.strictEqual(event.stopped, true, `adversarial assignment did not stop propagation: ${assignment.slice(0, 96)}`);
  }
}

for (const assignment of [
  'x="reproducibility"',
  'x["topic"]="reproducibility"',
  String.raw`root["to\u0070ic"]="reproducibility"`,
  "paßage=public",
  "ſtatus=ready",
  "topic=straße",
  'privateEmail=""',
  "privateEmail=''",
]) {
  for (const candidate of [assignment, `${fullPostPrefix}\n${assignment}`]) {
    const event = submit(candidate);
    assert.strictEqual(event.prevented, false, `safe short binding was prevented: ${assignment}`);
    assert.strictEqual(event.stopped, false, `safe short binding stopped propagation: ${assignment}`);
  }
}
const hostileDepthJson = nestedJsonArray(2200, "topic=reproducibility");
for (const candidate of [hostileDepthJson, `${fullPostPrefix}\nPUBLIC_OBJECTIVE: ${hostileDepthJson}`]) {
  const hostileDepthEvent = submit(candidate);
  assert.strictEqual(hostileDepthEvent.prevented, true, "hostile-depth JSON failed open");
  assert.strictEqual(hostileDepthEvent.stopped, true, "hostile-depth JSON did not stop propagation");
}
const quotedHostileDepthJsonAssignment = `payload=${JSON.stringify(hostileDepthJson)}`;
for (const candidate of [
  quotedHostileDepthJsonAssignment,
  `${fullPostPrefix}\n${quotedHostileDepthJsonAssignment}`,
]) {
  const event = submit(candidate);
  assert.strictEqual(event.prevented, true, "quoted hostile-depth JSON failed open");
  assert.strictEqual(event.stopped, true, "quoted hostile-depth JSON did not stop propagation");
}

let encodedPercentBoundary = "%";
for (let layer = 1; layer <= 5; layer += 1) {
  encodedPercentBoundary = encodeURIComponent(encodedPercentBoundary);
  const event = submit(`PUBLIC_OBJECTIVE: ${encodedPercentBoundary}`);
  assert.strictEqual(
    event.prevented,
    layer > 4,
    `encoded percent boundary mismatch at layer ${layer}: ${encodedPercentBoundary}`,
  );
}

const safePublicContactUrls = [
  "https://example.com/contact?next=%2Fpublic",
  "https://example.com/contact?topic=C%2B%2B",
  "https://example.com/contact?progress=100%",
  "https://example.com/contact?progress=100%25",
  "https://example.com/contact?note=%2",
  "https://example.com/contact?note=%GG",
  "https://example.com/contact?next=https%3A%2F%2Fpublic.example%2Fdocs%3Ftopic%3Dreproducibility",
  "https://example.com/contact#section-2",
  "https://example.com/contact#topic=C%2B%2B",
  "https://example.com/contact#progress=100%25",
];
for (const url of safePublicContactUrls) {
  const fullPost = fullPostPrefix.replace(
    "PUBLIC_CONTACT_URL: https://example.com/contact",
    `PUBLIC_CONTACT_URL: ${url}`,
  );
  const event = submit(fullPost);
  assert.strictEqual(event.prevented, false, `safe public URL was unexpectedly prevented: ${url}`);
  assert.strictEqual(event.stopped, false, `safe public URL unexpectedly stopped propagation: ${url}`);
}

for (const safe of [
  JSON.stringify({ public_objective: "reproducibility" }),
  JSON.stringify({ api_key: "", nested: { token: "" } }),
  "PUBLIC_CONTACT_URL: https://example.com/contact",
  "PUBLIC_CONTACT_URL: https://example.com/contact?next=%2Fpublic",
  "PUBLIC_OBJECTIVE: reproducibility",
  "PUBLIC_OBJECTIVE: improve by 100% reproducibly",
  "PUBLIC_OBJECTIVE: improve by 100%25 reproducibly",
  "PUBLIC_OBJECTIVE: literal %2 and %GG",
]) {
  const event = submit(safe);
  assert.strictEqual(event.prevented, false, `safe payload was unexpectedly prevented: ${safe}`);
  assert.strictEqual(event.stopped, false, `safe payload unexpectedly stopped propagation: ${safe}`);
}

console.log(`diagnostic inline DLP PASS: ${canonicalForbiddenNames.length} canonical names plus camelCase/encoded/full-post adversarial payloads`);
