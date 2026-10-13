export const STATES = Object.freeze({
  FULL_PRICE: 'FULL_PRICE',
  AUTHORIZED_DISCOUNT: 'AUTHORIZED_DISCOUNT',
  UNAUTHORIZED_DISCOUNT_REVIEW: 'UNAUTHORIZED_DISCOUNT_REVIEW',
  DISCOUNT_VARIANCE_REVIEW: 'DISCOUNT_VARIANCE_REVIEW',
  PRICE_UPLIFT_OBSERVED: 'PRICE_UPLIFT_OBSERVED',
  HOLD: 'HOLD',
});

function safeInt(value) {
  return typeof value === 'number' && Number.isSafeInteger(value);
}

export function parseMoneyToMinor(text) {
  if (typeof text !== 'string') return null;
  const trimmed = text.trim();
  if (!/^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ''] = trimmed.split('.');
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  return Number.isSafeInteger(cents) ? cents : null;
}

export function formatMinor(minor, currency = 'USD') {
  if (!safeInt(minor)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(minor / 100);
}

export function classifyDiscount({ referenceUnitMinor, billedUnitMinor, quantity, authorityMode = 'none', authorizedUnitReductionMinor = null }) {
  const invalid = [];
  if (!safeInt(referenceUnitMinor) || referenceUnitMinor <= 0) invalid.push('REFERENCE_PRICE_INVALID');
  if (!safeInt(billedUnitMinor) || billedUnitMinor < 0) invalid.push('BILLED_PRICE_INVALID');
  if (!safeInt(quantity) || quantity <= 0 || quantity > 1_000_000) invalid.push('QUANTITY_INVALID');
  if (!['none', 'exact', 'custom'].includes(authorityMode)) invalid.push('AUTHORITY_MODE_INVALID');
  if (authorityMode === 'custom' && (!safeInt(authorizedUnitReductionMinor) || authorizedUnitReductionMinor <= 0)) invalid.push('AUTHORITY_AMOUNT_INVALID');

  if (invalid.length) {
    return {
      state: STATES.HOLD,
      reasons: invalid,
      unitReductionMinor: null,
      discountReferenceMinor: null,
      expectedReferenceMinor: null,
      observedReferenceMinor: null,
    };
  }

  const expected = BigInt(referenceUnitMinor) * BigInt(quantity);
  const observed = BigInt(billedUnitMinor) * BigInt(quantity);
  if (expected > BigInt(Number.MAX_SAFE_INTEGER) || observed > BigInt(Number.MAX_SAFE_INTEGER)) {
    return {
      state: STATES.HOLD,
      reasons: ['TOTAL_EXCEEDS_SAFE_INTEGER'],
      unitReductionMinor: null,
      discountReferenceMinor: null,
      expectedReferenceMinor: null,
      observedReferenceMinor: null,
    };
  }

  const unitReductionMinor = referenceUnitMinor - billedUnitMinor;
  const discount = unitReductionMinor > 0 ? BigInt(unitReductionMinor) * BigInt(quantity) : 0n;
  if (discount > BigInt(Number.MAX_SAFE_INTEGER)) {
    return {
      state: STATES.HOLD,
      reasons: ['DISCOUNT_EXCEEDS_SAFE_INTEGER'],
      unitReductionMinor: null,
      discountReferenceMinor: null,
      expectedReferenceMinor: Number(expected),
      observedReferenceMinor: Number(observed),
    };
  }

  const base = {
    reasons: [],
    unitReductionMinor,
    discountReferenceMinor: Number(discount),
    expectedReferenceMinor: Number(expected),
    observedReferenceMinor: Number(observed),
  };

  if (unitReductionMinor === 0) return { ...base, state: STATES.FULL_PRICE };
  if (unitReductionMinor < 0) return { ...base, state: STATES.PRICE_UPLIFT_OBSERVED, discountReferenceMinor: 0 };
  if (authorityMode === 'none') return { ...base, state: STATES.UNAUTHORIZED_DISCOUNT_REVIEW, reasons: ['NO_ACTIVE_AUTHORITY'] };

  const authority = authorityMode === 'exact' ? unitReductionMinor : authorizedUnitReductionMinor;
  if (authority === unitReductionMinor) return { ...base, state: STATES.AUTHORIZED_DISCOUNT };
  return { ...base, state: STATES.DISCOUNT_VARIANCE_REVIEW, reasons: ['AUTHORIZED_REDUCTION_MISMATCH'] };
}
