# SPDX-License-Identifier: Apache-2.0
"""Select whole accepted T12 streams without relying on surviving lag labels."""


def bounded_history_streams(historical, limit):
    """Prefer unshifted paired streams, then retain deduplicated equivalents.

    T12 deduplicates by the actual complete (stream, alignment), retaining the
    first label. When clamping makes shifts -1 and 0 identical, only the -1
    name remains. Selection must preserve that causal stream. Values and their
    correlations are used exactly as emitted by T12; no model is estimated.
    """
    paired=[row for row in historical if row[2]=='paired']
    preferred=[row for row in paired if row[0].endswith('_shift_0_paired')]
    ordered=preferred+[row for row in paired if row not in preferred]
    seen=set();out=[]
    for row in ordered:
        key=(tuple(tuple(x) for x in row[1]),row[2])
        if key in seen:continue
        seen.add(key);out.append(row)
        if len(out)>=max(0,limit):break
    return out if limit>0 else []
