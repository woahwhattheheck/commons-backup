export function compileQualificationPacket(candidate) {
  const blockers = [];
  if (candidate.diagnostic_passed) {
    return { state: "QUALIFIED_FOR_OWNER_SALES_REVIEW", blockers };
  }
  blockers.push("PRIOR_DIAGNOSTIC_PASS_REQUIRED");
  return { state: "HOLD", blockers };
}
