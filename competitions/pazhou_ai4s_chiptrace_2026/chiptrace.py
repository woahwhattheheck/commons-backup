#!/usr/bin/env python3
"""ChipTrace: deterministic organ-on-chip experiment quality and drift intelligence.

Research quality-control only. This tool does not make clinical, diagnostic,
treatment, efficacy, or patient-specific claims.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple
VERSION = '1.0.0'
REQUIRED_COLUMNS = ('run_id', 'replicate_id', 'time_s', 'channel', 'value', 'unit', 'source', 'modality')
STATES = ('SUPPORTED', 'REVIEW', 'INSUFFICIENT_EVIDENCE')

class ContractError(ValueError):
    pass

@dataclass(frozen=True)
class Observation:
    run_id: str
    replicate_id: str
    time_s: float
    channel: str
    value: float
    unit: str
    source: str
    modality: str

@dataclass(frozen=True)
class ChannelBaseline:
    channel: str
    unit: str
    modality: str
    n: int
    center: float
    scale: float
    scale_method: str
    cadence_s: float
    replicate_count: int

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())

def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def median(values: Sequence[float]) -> float:
    if not values:
        raise ContractError('median requires at least one value')
    return float(statistics.median(values))

def robust_scale(values: Sequence[float]) -> Tuple[float, str]:
    c = median(values)
    mad = median([abs(x - c) for x in values])
    sigma = 1.4826 * mad
    if sigma > 1e-12:
        return (sigma, 'MAD')
    if len(values) >= 2:
        std = statistics.pstdev(values)
        if std > 1e-12:
            return (float(std), 'PSTD_FALLBACK')
    return (max(abs(c) * 1e-06, 1e-09), 'DEGENERATE_FLOOR')

def theil_sen_slope(points: Sequence[Tuple[float, float]]) -> float:
    """Deterministic robust slope; cap pair count by regular subsampling for large series."""
    if len(points) < 2:
        return 0.0
    ordered = sorted(points)
    if len(ordered) > 80:
        step = max(1, len(ordered) // 80)
        ordered = ordered[::step][:80]
    slopes: List[float] = []
    for i, (x1, y1) in enumerate(ordered[:-1]):
        for x2, y2 in ordered[i + 1:]:
            if x2 != x1:
                slopes.append((y2 - y1) / (x2 - x1))
    return median(slopes) if slopes else 0.0

def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = (statistics.fmean(xs), statistics.fmean(ys))
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    vx = sum((x * x for x in dx))
    vy = sum((y * y for y in dy))
    if vx <= 1e-18 or vy <= 1e-18:
        return None
    return sum((a * b for a, b in zip(dx, dy))) / math.sqrt(vx * vy)

def _positive_cadence(obs: Sequence[Observation]) -> float:
    deltas: List[float] = []
    by_rep: Dict[str, List[float]] = defaultdict(list)
    for o in obs:
        by_rep[o.replicate_id].append(o.time_s)
    for times in by_rep.values():
        s = sorted(set(times))
        deltas.extend((b - a for a, b in zip(s, s[1:]) if b > a))
    return median(deltas) if deltas else 0.0

def load_csv(path: Path) -> List[Observation]:
    raw = path.read_bytes()
    if b'\x00' in raw:
        raise ContractError(f'{path}: binary/NUL content rejected')
    text = raw.decode('utf-8')
    reader = csv.DictReader(text.splitlines())
    headers = tuple(reader.fieldnames or ())
    if headers != REQUIRED_COLUMNS:
        raise ContractError(f'{path}: exact header required {REQUIRED_COLUMNS}; got {headers}. Unknown columns are rejected to prevent accidental clinical/identity data ingestion.')
    out: List[Observation] = []
    seen = set()
    for line_no, row in enumerate(reader, start=2):
        try:
            t = float(row['time_s'])
            v = float(row['value'])
        except (TypeError, ValueError) as exc:
            raise ContractError(f'{path}:{line_no}: time_s/value must be finite numbers') from exc
        if not math.isfinite(t) or not math.isfinite(v):
            raise ContractError(f'{path}:{line_no}: non-finite number rejected')
        if t < 0:
            raise ContractError(f'{path}:{line_no}: negative time rejected')
        fields = {k: (row[k] or '').strip() for k in REQUIRED_COLUMNS if k not in ('time_s', 'value')}
        for k in ('run_id', 'replicate_id', 'channel', 'unit', 'source', 'modality'):
            if not fields[k]:
                raise ContractError(f'{path}:{line_no}: {k} must be non-empty')
        key = (fields['run_id'], fields['replicate_id'], t, fields['channel'])
        if key in seen:
            raise ContractError(f'{path}:{line_no}: duplicate observation key {key}')
        seen.add(key)
        out.append(Observation(run_id=fields['run_id'], replicate_id=fields['replicate_id'], time_s=t, channel=fields['channel'], value=v, unit=fields['unit'], source=fields['source'], modality=fields['modality']))
    if not out:
        raise ContractError(f'{path}: no observations')
    return out

def build_baselines(obs: Sequence[Observation]) -> Dict[str, ChannelBaseline]:
    groups: Dict[str, List[Observation]] = defaultdict(list)
    for o in obs:
        groups[o.channel].append(o)
    result: Dict[str, ChannelBaseline] = {}
    for channel, rows in sorted(groups.items()):
        units = {r.unit for r in rows}
        modalities = {r.modality for r in rows}
        if len(units) != 1 or len(modalities) != 1:
            raise ContractError(f'baseline channel {channel!r} mixes unit/modality')
        vals = [r.value for r in rows]
        scale, method = robust_scale(vals)
        result[channel] = ChannelBaseline(channel=channel, unit=next(iter(units)), modality=next(iter(modalities)), n=len(rows), center=median(vals), scale=scale, scale_method=method, cadence_s=_positive_cadence(rows), replicate_count=len({r.replicate_id for r in rows}))
    return result

def aligned_correlations(obs: Sequence[Observation]) -> Dict[str, float]:
    aligned: Dict[Tuple[str, float], Dict[str, float]] = defaultdict(dict)
    for o in obs:
        aligned[o.replicate_id, o.time_s][o.channel] = o.value
    channels = sorted({o.channel for o in obs})
    out: Dict[str, float] = {}
    for i, a in enumerate(channels):
        for b in channels[i + 1:]:
            xs: List[float] = []
            ys: List[float] = []
            for values in aligned.values():
                if a in values and b in values:
                    xs.append(values[a])
                    ys.append(values[b])
            r = pearson(xs, ys)
            if r is not None:
                out[f'{a}|{b}'] = r
    return out

def _missing_fraction(rows: Sequence[Observation], cadence: float) -> float:
    if cadence <= 0:
        return 0.0
    missing = 0
    observed = len(rows)
    by_rep: Dict[str, List[float]] = defaultdict(list)
    for o in rows:
        by_rep[o.replicate_id].append(o.time_s)
    for times in by_rep.values():
        s = sorted(set(times))
        for a, b in zip(s, s[1:]):
            steps = int(round((b - a) / cadence))
            if steps > 1 and abs(b - a - steps * cadence) <= cadence * 0.25:
                missing += steps - 1
    total = observed + missing
    return missing / total if total else 0.0

def correlation_deltas(baseline_obs: Sequence[Observation], run_obs: Sequence[Observation]) -> Tuple[Dict[str, dict], Dict[str, float]]:
    base = aligned_correlations(baseline_obs)
    run = aligned_correlations(run_obs)
    details: Dict[str, dict] = {}
    channel_max: Dict[str, float] = defaultdict(float)
    for pair in sorted(set(base) & set(run)):
        delta = abs(run[pair] - base[pair])
        details[pair] = {'baseline_r': round(base[pair], 8), 'run_r': round(run[pair], 8), 'absolute_delta': round(delta, 8)}
        a, b = pair.split('|', 1)
        channel_max[a] = max(channel_max[a], delta)
        channel_max[b] = max(channel_max[b], delta)
    return (details, dict(channel_max))

def assess_channel(channel: str, rows: Sequence[Observation], baseline: ChannelBaseline, corr_delta: float, min_points: int, min_baseline_points: int) -> dict:
    units = {r.unit for r in rows}
    modalities = {r.modality for r in rows}
    if units != {baseline.unit}:
        raise ContractError(f'run channel {channel!r} unit mismatch: {units} vs {baseline.unit!r}')
    if modalities != {baseline.modality}:
        raise ContractError(f'run channel {channel!r} modality mismatch')
    vals = [r.value for r in rows]
    z = [abs(v - baseline.center) / baseline.scale for v in vals]
    outlier_fraction = sum((v >= 3.0 for v in z)) / len(z)
    run_center = median(vals)
    level_z = abs(run_center - baseline.center) / baseline.scale
    ordered = sorted(rows, key=lambda r: (r.replicate_id, r.time_s))
    by_rep: Dict[str, List[Observation]] = defaultdict(list)
    for r in ordered:
        by_rep[r.replicate_id].append(r)
    change_z = 0.0
    trend_z = 0.0
    replicate_centers = []
    for rep_rows in by_rep.values():
        rep_rows = sorted(rep_rows, key=lambda r: r.time_s)
        replicate_centers.append(median([r.value for r in rep_rows]))
        if len(rep_rows) >= 4:
            mid = len(rep_rows) // 2
            first = median([r.value for r in rep_rows[:mid]])
            second = median([r.value for r in rep_rows[mid:]])
            change_z = max(change_z, abs(second - first) / baseline.scale)
        slope = theil_sen_slope([(r.time_s, r.value) for r in rep_rows])
        cadence = baseline.cadence_s or _positive_cadence(rep_rows) or 1.0
        trend_z = max(trend_z, abs(slope) * cadence / baseline.scale)
    replicate_divergence_z = 0.0
    if len(replicate_centers) >= 2:
        replicate_divergence_z = (max(replicate_centers) - min(replicate_centers)) / baseline.scale
    missing_fraction = _missing_fraction(rows, baseline.cadence_s)
    components = {'level': clamp01(level_z / 6.0), 'change_point': clamp01(change_z / 5.0), 'trend': clamp01(trend_z / 4.0), 'outliers': clamp01(outlier_fraction / 0.25), 'missingness': clamp01(missing_fraction / 0.1), 'replicate_divergence': clamp01(replicate_divergence_z / 5.0), 'cross_sensor_shift': clamp01(corr_delta / 0.75)}
    weights = {'level': 0.2, 'change_point': 0.18, 'trend': 0.12, 'outliers': 0.16, 'missingness': 0.12, 'replicate_divergence': 0.14, 'cross_sensor_shift': 0.08}
    quality_risk = 100.0 * sum((components[k] * weights[k] for k in weights))
    insufficient = len(rows) < min_points or baseline.n < min_baseline_points
    severe = level_z >= 4.0 or change_z >= 3.0 or outlier_fraction >= 0.12 or (missing_fraction >= 0.05) or (replicate_divergence_z >= 3.0) or (corr_delta >= 0.45)
    state = 'INSUFFICIENT_EVIDENCE' if insufficient else 'REVIEW' if quality_risk >= 25.0 or severe else 'SUPPORTED'
    uncertainty = clamp01(1.0 / math.sqrt(max(1, len(rows))) + 1.0 / math.sqrt(max(1, baseline.n)) + 0.5 * missing_fraction + (0.12 if baseline.scale_method == 'DEGENERATE_FLOOR' else 0.0))
    reasons = []
    for label, value, threshold in (('level shift', level_z, 4.0), ('within-run change', change_z, 3.0), ('replicate divergence', replicate_divergence_z, 3.0)):
        if value >= threshold:
            reasons.append(f'{label} exceeds review threshold')
    if outlier_fraction >= 0.12:
        reasons.append('elevated robust-outlier fraction')
    if missing_fraction >= 0.05:
        reasons.append('cadence-derived missingness exceeds review threshold')
    if corr_delta >= 0.45:
        reasons.append('cross-sensor correlation structure shifted')
    if insufficient:
        reasons.append('insufficient observations for supported-state decision')
    if not reasons:
        reasons.append('no configured quality-review threshold exceeded')
    return {'channel': channel, 'state': state, 'quality_risk_score': round(quality_risk, 3), 'uncertainty': round(uncertainty, 6), 'reasons': reasons, 'run_n': len(rows), 'baseline_n': baseline.n, 'unit': baseline.unit, 'modality': baseline.modality, 'baseline_center': round(baseline.center, 10), 'baseline_scale': round(baseline.scale, 10), 'baseline_scale_method': baseline.scale_method, 'metrics': {'run_center': round(run_center, 10), 'level_z': round(level_z, 6), 'max_change_z': round(change_z, 6), 'max_trend_z_per_baseline_step': round(trend_z, 6), 'outlier_fraction': round(outlier_fraction, 8), 'missing_fraction': round(missing_fraction, 8), 'replicate_divergence_z': round(replicate_divergence_z, 6), 'max_cross_sensor_correlation_delta': round(corr_delta, 8)}, 'score_components': {k: round(v, 8) for k, v in components.items()}}

def analyze(baseline_path: Path, run_path: Path, *, min_points: int=6, min_baseline_points: int=12) -> dict:
    if min_points < 2 or min_baseline_points < 2:
        raise ContractError('minimum point counts must be >=2')
    baseline_obs = load_csv(baseline_path)
    run_obs = load_csv(run_path)
    baselines = build_baselines(baseline_obs)
    run_groups: Dict[str, List[Observation]] = defaultdict(list)
    for o in run_obs:
        run_groups[o.channel].append(o)
    missing_channels = sorted(set(run_groups) - set(baselines))
    if missing_channels:
        raise ContractError(f'run contains channels absent from baseline: {missing_channels}')
    corr_details, per_channel_corr = correlation_deltas(baseline_obs, run_obs)
    assessments = [assess_channel(ch, run_groups[ch], baselines[ch], per_channel_corr.get(ch, 0.0), min_points, min_baseline_points) for ch in sorted(run_groups)]
    state_order = {'SUPPORTED': 0, 'REVIEW': 1, 'INSUFFICIENT_EVIDENCE': 2}
    overall = max((a['state'] for a in assessments), key=state_order.get)
    payload = {'schema': 'chiptrace.report.v1', 'tool': {'name': 'ChipTrace', 'version': VERSION}, 'scope': {'intended_use': 'organ-on-chip research experiment quality control and drift review', 'not_for': ['clinical diagnosis', 'treatment recommendation', 'patient-specific decision making', 'drug efficacy or safety claim'], 'state_semantics': {'SUPPORTED': 'No configured QC review threshold was exceeded; this is not a biological-efficacy claim.', 'REVIEW': 'One or more QC signals warrant researcher review.', 'INSUFFICIENT_EVIDENCE': 'Observation counts are too small for a supported QC state.'}}, 'inputs': {'baseline_file': baseline_path.name, 'baseline_sha256': file_sha256(baseline_path), 'run_file': run_path.name, 'run_sha256': file_sha256(run_path), 'baseline_rows': len(baseline_obs), 'run_rows': len(run_obs)}, 'config': {'min_points': min_points, 'min_baseline_points': min_baseline_points}, 'overall_state': overall, 'max_quality_risk_score': round(max((a['quality_risk_score'] for a in assessments)), 3), 'channel_assessments': assessments, 'cross_sensor_correlations': corr_details, 'baseline_model': {k: asdict(v) for k, v in sorted(baselines.items())}}
    payload['receipt_sha256'] = _sha256_bytes(canonical_bytes(payload))
    return payload

def verify_report(report: Mapping[str, object]) -> bool:
    candidate = dict(report)
    receipt = candidate.pop('receipt_sha256', None)
    return isinstance(receipt, str) and receipt == _sha256_bytes(canonical_bytes(candidate))

def render_html(report: Mapping[str, object]) -> str:
    rows = []
    for a in report['channel_assessments']:
        rows.append(f"<tr><td>{html.escape(str(a['channel']))}</td><td><strong>{html.escape(str(a['state']))}</strong></td><td>{a['quality_risk_score']}</td><td>{a['uncertainty']}</td><td>{html.escape('; '.join(a['reasons']))}</td></tr>")
    receipt = html.escape(str(report['receipt_sha256']))
    raw = html.escape(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return f"""<!doctype html>\n<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<title>ChipTrace judge report</title>\n<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.45}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:.55rem;text-align:left;vertical-align:top}}code,pre{{background:#f3f3f3;padding:.15rem .3rem}}pre{{overflow:auto;padding:1rem}}.note{{border-left:4px solid #666;padding:.7rem 1rem;background:#fafafa}}</style>\n<h1>ChipTrace experiment-quality report</h1>\n<p class="note"><strong>Research QC only.</strong> SUPPORTED means configured quality-review thresholds were not exceeded. It does not establish biological efficacy, clinical safety, diagnosis, or treatment suitability.</p>\n<p><strong>Overall state:</strong> {html.escape(str(report['overall_state']))}<br>\n<strong>Max quality-risk score:</strong> {report['max_quality_risk_score']} / 100<br>\n<strong>Replay receipt:</strong> <code>{receipt}</code></p>\n<h2>Channel evidence</h2><table><thead><tr><th>Channel</th><th>State</th><th>Risk</th><th>Uncertainty</th><th>Why</th></tr></thead><tbody>{''.join(rows)}</tbody></table>\n<h2>Machine-readable evidence</h2><pre>{raw}</pre></html>"""

def write_csv(path: Path, rows: Iterable[Observation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(REQUIRED_COLUMNS)
        for o in rows:
            writer.writerow([o.run_id, o.replicate_id, f'{o.time_s:.3f}', o.channel, f'{o.value:.8f}', o.unit, o.source, o.modality])

def generate_demo(directory: Path) -> Tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    baseline: List[Observation] = []
    run: List[Observation] = []
    channels = {'barrier_index': (1.0, 'relative_index', 'sensor_feature'), 'oxygen_index': (0.82, 'relative_index', 'sensor_feature'), 'flow_index': (1.0, 'relative_index', 'sensor_feature')}
    for rep in range(3):
        for step in range(24):
            t = step * 300.0
            phase = 0.17 * step + 0.41 * rep
            for ch, (center, unit, modality) in channels.items():
                amplitude = {'barrier_index': 0.025, 'oxygen_index': 0.018, 'flow_index': 0.012}[ch]
                v = center + amplitude * math.sin(phase + {'barrier_index': 0.0, 'oxygen_index': 0.5, 'flow_index': 1.1}[ch])
                baseline.append(Observation('baseline_demo', f'b{rep + 1}', t, ch, v, unit, 'synthetic_public_demo', modality))
    for rep in range(3):
        for step in range(24):
            if rep == 1 and step == 11:
                continue
            t = step * 300.0
            phase = 0.17 * step + 0.41 * rep
            for ch, (center, unit, modality) in channels.items():
                amplitude = {'barrier_index': 0.025, 'oxygen_index': 0.018, 'flow_index': 0.012}[ch]
                v = center + amplitude * math.sin(phase + {'barrier_index': 0.0, 'oxygen_index': 0.5, 'flow_index': 1.1}[ch])
                if ch == 'barrier_index' and step >= 12:
                    v -= 0.105 + 0.008 * rep
                if ch == 'oxygen_index':
                    v -= 0.0035 * step
                if ch == 'flow_index' and rep == 2:
                    v += 0.045
                run.append(Observation('candidate_demo', f'r{rep + 1}', t, ch, v, unit, 'synthetic_public_demo', modality))
    baseline_path = directory / 'baseline.csv'
    run_path = directory / 'candidate.csv'
    write_csv(baseline_path, baseline)
    write_csv(run_path, run)
    return (baseline_path, run_path)

def cmd_analyze(args: argparse.Namespace) -> int:
    report = analyze(Path(args.baseline), Path(args.run), min_points=args.min_points, min_baseline_points=args.min_baseline_points)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    if args.html:
        Path(args.html).write_text(render_html(report), encoding='utf-8')
    print(json.dumps({'overall_state': report['overall_state'], 'receipt_sha256': report['receipt_sha256'], 'out': str(out)}, sort_keys=True))
    return 0

def cmd_verify(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.report).read_text(encoding='utf-8'))
    ok = verify_report(report)
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 2

def cmd_demo(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    baseline, run = generate_demo(directory)
    report = analyze(baseline, run)
    report_path = directory / 'report.json'
    html_path = directory / 'report.html'
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    html_path.write_text(render_html(report), encoding='utf-8')
    print(json.dumps({'overall_state': report['overall_state'], 'report': str(report_path), 'html': str(html_path), 'receipt_sha256': report['receipt_sha256']}, sort_keys=True))
    return 0

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('analyze', help='assess a candidate experiment run against a baseline')
    a.add_argument('--baseline', required=True)
    a.add_argument('--run', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--html')
    a.add_argument('--min-points', type=int, default=6)
    a.add_argument('--min-baseline-points', type=int, default=12)
    a.set_defaults(func=cmd_analyze)
    v = sub.add_parser('verify', help='verify a report receipt without re-running analysis')
    v.add_argument('report')
    v.set_defaults(func=cmd_verify)
    d = sub.add_parser('demo', help='generate deterministic synthetic fixtures and a judge report')
    d.add_argument('--directory', default='chiptrace_demo')
    d.set_defaults(func=cmd_demo)
    return p

def main(argv: Sequence[str] | None=None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(f'ERROR: {exc}')
        return 2
if __name__ == '__main__':
    raise SystemExit(main())
