import { readFile } from 'node:fs/promises';
import { RFQLedger } from '../src/quote-ledger.mjs';

const fixture = JSON.parse(await readFile(new URL('./synthetic-rfq.json', import.meta.url), 'utf8'));
const ledger = new RFQLedger(fixture.round);
for (const vendor of fixture.vendors) ledger.registerVendor(vendor);
for (const quote of fixture.quotes) ledger.recordQuote(quote);
console.log(JSON.stringify(ledger.comparison({ at: fixture.compareAt }), null, 2));
