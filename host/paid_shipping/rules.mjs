export const CHANNELS = ['C0BU51F1PL3', 'C0BTB4SUCP9', 'C0BVANHNB26'];
export const COORDINATION_CHANNEL = CHANNELS[0];
export const OWNER_IDS = [293286387, 311286379];
const PR_URL = /https?:\/\/(?:www\.)?github\.com\/([\w.-]+)\/([\w.-]+)\/pull\/(\d+)/giu;
const ISSUE_URL = /https?:\/\/(?:www\.)?github\.com\/([\w.-]+)\/([\w.-]+)\/issues\/(\d+)/giu;
const COMPLETE = /\b(?:done|shipped|merged|released|complete(?:d)?|delivered|finished)\b/iu;
const BOUNTY = /\b(?:bounty|sponsor|paid\s+(?:issue|work|pr)|reward|payout)\b/iu;
const INTERNAL = /\b(?:fork[- ]only|internal(?:[- ]only)?|private\s+(?:pr|repo)|packet|acceptance\s+matrix|donor\s+review|proxy\s+pr)\b/iu;
const PACKET = /\b(?:packet|acceptance\s+matrix|donor\s+review|proxy\s+pr)\b/iu;
const BLOCKED = /\b403\b.*\b(?:upstream|publish|push|pull request|\bpr\b)\b|\b(?:upstream|publish|push|pull request|\bpr\b).*\b403\b/iu;
const REQUIRED = /\b(?:required\s+(?:tests?|checks?|assignment|application|proposal)|sponsor[- ]required|upstream\s+pr\s+(?:opened|updated|merged))\b/iu;
const NOT_COMPLETE = /\b(?:not|never|isn't|wasn't|don't|do\s+not|still\s+not|incomplete|pending)\b.{0,30}\b(?:done|shipped|merged|released|complete(?:d)?|delivered|finished)\b/iu;

export function refsIn(text = '') {
  const refs = new Set();
  for (const match of text.matchAll(PR_URL)) refs.add(`${match[1].toLowerCase()}/${match[2].toLowerCase()}#${match[3]}`);
  for (const match of text.matchAll(ISSUE_URL)) refs.add(`${match[1].toLowerCase()}/${match[2].toLowerCase()}!${match[3]}`);
  return [...refs].sort();
}

export function incidentRefs(destination) {
  let value = destination;
  if (typeof value === 'string') {
    try { value = JSON.parse(value); } catch { /* destination can be plain context */ }
  }
  const flat = typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value || '');
  const refs = refsIn(flat);
  if (typeof value === 'object' && value !== null) {
    const repo = String(value.repo_full_name || value.repository_full_name || value.repository ||
      (value.owner && value.repo ? `${value.owner}/${value.repo}` : value.repo) || '').toLowerCase();
    const number = value.pr_number || value.pull_number || value.issue_number;
    if (/^[\w.-]+\/[\w.-]+$/u.test(repo) && /^\d+$/u.test(String(number || ''))) {
      if (value.issue_number && !value.pr_number && !value.pull_number) {
        return [`${repo}#${number}`, `${repo}!${number}`];
      }
      return [`${repo}#${number}`];
    }
  }
  return [...new Set(refs)].sort();
}

export function targetLabel(destination) {
  const refs = incidentRefs(destination);
  return refs[0] || 'the affected publication';
}

export function candidateThread(messages) {
  return messages.some(m => {
    const t = String(m.text || '');
    return BOUNTY.test(t) || INTERNAL.test(t) || BLOCKED.test(t) || refsIn(t).length > 0;
  });
}

export function classifyThread(messages) {
  const human = messages.filter(m => m.metadata?.event_type !== 'tjlabs_shipping_enforcer' &&
    !String(m.text || '').includes('Ref: `ship-'));
  const texts = human.map(m => String(m.text || ''));
  const joined = texts.join('\n');
  if (!candidateThread(human)) return null;
  const refs = refsIn(joined);
  if (REQUIRED.test(joined) && !COMPLETE.test(joined)) return null;
  if (BLOCKED.test(joined) && (BOUNTY.test(joined) || refs.some(ref => ref.includes('#')))) {
    return { code: 'upstream_403', text: 'Upstream publication returned 403 for this bounty work. Use the shared authenticated publisher road, confirm the provider receipt, and keep the same operation ID for retries. Keep the work on our own payable submission.' };
  }
  if (texts.length && NOT_COMPLETE.test(texts.at(-1))) return null;
  if (!BOUNTY.test(joined) || !texts.some(t => COMPLETE.test(t) && !NOT_COMPLETE.test(t))) return null;
  if (PACKET.test(joined) && !refs.some(ref => ref.includes('#'))) {
    return { code: 'packet_only', text: 'This bounty work is still an internal packet. Carry the completed fix into our eligible upstream PR, run the sponsor-required checks, and link the live submission and payment route here.' };
  }
  if (INTERNAL.test(joined) && refs.some(ref =>
    /^(?:woahwhattheheck|tokenjunkielabs)\//u.test(ref) && ref.includes('#'))) {
    return { code: 'fork_only', text: 'This is a fork/internal PR for bounty work. Open or update our eligible upstream PR, run the sponsor-required checks, and link the live submission and payment route here.' };
  }
  return null;
}

export function incidentNotice(row) {
  const label = targetLabel(row.destination);
  const reason = /^[a-z_]{1,80}$/u.test(row.reason) ? row.reason : 'blocked_incident';
  const email = row.email_status === 'accepted' ? 'The private incident email was accepted for Bryce.' :
    row.email_status === 'delivery_uncertain' ? 'Private incident email delivery is unconfirmed.' :
    'The private incident email has not yet been confirmed delivered.';
  return `Publication blocked for ${label} (incident ${row.id}, operation ${row.op_id}; reason ${reason}). Do not retry by rephrasing or switching accounts. Private details remain in the authenticated publisher /v1/incidents/${row.id} record. ${email} Continue other authorized work.`;
}

const NEXT_ACTION = Object.freeze({
  incident_held: 'Keep the hold. Bryce handles any external incident statement. Do not retry by rephrasing or switching accounts. Private facts remain in the authenticated publisher incident record and its email process; delivery may still be pending. Continue unrelated authorized work.',
  git_publication_inspection_unavailable: 'Repair the configured named Git remote and local publication inspection, then retry the same authorized route. Do not switch accounts or tools to bypass the hook.',
  unpaid_third_party_bounty_work: 'Redirect to our own eligible payable submission or a source-backed paid collaboration. Do not perform unpaid review or repair work for another claimant.',
  paid_work_context_unavailable: 'Restore provider context and retry the same authorized route. Keep the original operation ID.',
  attribution_rewrite_required: 'Remove unauthorized author/tool attribution, then submit the revised routine communication through the same route.'
});

export function operatorNotice(row) {
  const target = row.repository ? `${row.repository}${row.issue_number ? `#${row.issue_number}` : ''}` : 'the current publication';
  if (row.reason_code === 'monitor_transport_check')
    return `Shipping monitor operational transport check for ${target}${row.operation_id ? ` (operation ${row.operation_id})` : ''}. No action needed.`;
  const next = NEXT_ACTION[row.reason_code] || 'Review the internal diagnostic, repair the authorized publication route, and retry with the same operation ID where applicable.';
  return `Publication route blocked for ${target} (${row.reason_code}; tool ${row.tool_name}${row.operation_id ? `; operation ${row.operation_id}` : ''}). ${next}`;
}
