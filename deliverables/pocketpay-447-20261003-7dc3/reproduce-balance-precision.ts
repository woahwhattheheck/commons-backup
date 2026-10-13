import { parseMultiAssetBalance } from './src';

const issuer = 'GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF';
const cases = [
  {
    name: 'native maximum minus reserve and one stroop',
    row: { asset_type: 'native', balance: '922337203685.4775807', selling_liabilities: '0.0000001' },
    expected: { availableBalance: '922337203684.4775806', reservedBalance: '1.0000001', state: 'available', formattedDisplay: '922337203684.48 XLM' },
  },
  {
    name: 'issued single remaining stroop near maximum',
    row: { asset_type: 'credit_alphanum4', asset_code: 'USDC', asset_issuer: issuer, balance: '922337203685.4775807', selling_liabilities: '922337203685.4775806' },
    expected: { availableBalance: '0.0000001', reservedBalance: '922337203685.4775806', state: 'available', formattedDisplay: '0.00 USDC' },
  },
  {
    name: 'issued rounding after one-stroop liability',
    row: { asset_type: 'credit_alphanum4', asset_code: 'USDC', asset_issuer: issuer, balance: '922337203685.0050000', selling_liabilities: '0.0000001' },
    expected: { availableBalance: '922337203685.0049999', reservedBalance: '0.0000001', state: 'available', formattedDisplay: '922337203685.00 USDC' },
  },
];

const results = cases.map(({ name, row, expected }) => {
  const model = parseMultiAssetBalance(issuer, { subentry_count: 0, balances: [row] });
  const item = model.native ?? model.issuedAssets[0];
  if (!item) throw new Error(`No parsed item: ${name}`);
  const actual = { availableBalance: item.availableBalance, reservedBalance: item.reservedBalance, state: item.state, formattedDisplay: item.formattedDisplay };
  return { name, input: row, expected, actual, passed: JSON.stringify(actual) === JSON.stringify(expected) };
});
console.log(JSON.stringify({ results, passed: results.filter(result => result.passed).length, total: results.length }, null, 2));
if (results.some(result => !result.passed)) process.exitCode = 1;
