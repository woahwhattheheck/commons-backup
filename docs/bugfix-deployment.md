# Publish only the standalone bugfix page

The customer page is `sites/bugfix/index.html`. Source integration is not a host deployment. This procedure needs neither a Node installation nor a build service, and does not alter any existing product or payment link.

## Make a deploy-only package

Use an isolated checkout. From the repository root:

```sh
python host/package_bugfix_site.py --output /tmp/bugfix-deploy-01
```

Use a new output directory each time. The command never overwrites an existing directory. It produces:

- `bugfix-deploy.zip`: exactly one archive member, `index.html`, at the web root. Page bytes are preserved.
- `package-receipt.json`: separate source Git-blob SHA-1, source/archive SHA-256 and byte counts. This is not part of the uploaded site.

The packager reads that single page rather than scanning the repository. Other site files, private handoff notes, environment files and the repository's runtime code are not included. It performs no network request or deployment and needs no credentials. Inspect the receipt's `deployment_performed: false` literally: making the ZIP does not mean the page is live.

Run the new focused packaging checks with:

```sh
python -m unittest test_bridge_bugfix_package -v
```

These tests exercise archive contents, exact bytes/hashes, determinism, non-overwrite behavior, missing/invalid input, the CLI and the actual page. They do not replace the page's retained browser evidence or assert that the repository-wide battery passes.

## Publish through the connected host

After the Netlify connection is available, the authorized deployment action can use the extracted site directory. For manual Netlify Drop, unzip **only** `bugfix-deploy.zip` into a new folder and upload that folder, whose top level must contain `index.html`. Do not upload the parent output directory, this README, the receipt, private email attachments or the whole Commons checkout. Netlify documents this folder-based manual deployment procedure: https://docs.netlify.com/deploy/create-deploys/#drag-and-drop .

For a repository-linked Netlify site, configure the base directory as `sites/bugfix`, the publish directory as `.` relative to that base, and leave the build command empty for this already-built HTML. Confirm any existing root `netlify.toml` before selecting this route; root configuration can override UI settings. Do not change a shared root configuration to publish this one page. Netlify's current base/publish-directory definitions are here: https://docs.netlify.com/build/configure-builds/monorepos/ .

No paid plan change, hostname choice or actual deployment is performed by this package.

## Record a real deployment receipt

After publishing, retain the provider's site/deployment identifier and live URL. Check the live page loads, the expected heading and direct email link are present, and the brief form does not claim to send mail automatically. Record the deployed source blob and archive checksum with those results. Do not mark the hosting task complete from a successful ZIP build alone. The repository-wide failed test run remains a separate technical follow-through item until its actual failure is identified.
