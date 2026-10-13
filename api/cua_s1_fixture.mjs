/** A public, inert form for production CUA browser smoke tests. */
const HTML = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>CUA browser fixture</title></head>
<body>
  <h1>Contact</h1>
  <form id="cua-smoke-form">
    <label for="cua-name">Name</label>
    <input id="cua-name" name="name" type="text" autocomplete="off">
  </form>
</body>
</html>`;

export default function handler(request, response) {
  response.setHeader('cache-control', 'no-store');
  response.setHeader('content-type', 'text/html; charset=utf-8');
  response.setHeader('content-security-policy', "default-src 'none'");
  if (request.method !== 'GET') return response.status(405).send('Method not allowed');
  return response.status(200).send(HTML);
}
