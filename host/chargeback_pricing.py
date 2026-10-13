#!/usr/bin/env python3
"""Price and liquidity scenarios; assumptions are never observed account facts.

No provider calls, money movement, price changes, or public admission controls.
Amounts use the currency selected by the operator; default fees illustrate
Stripe US standard domestic-card pricing, not the merchant's verified tariff.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

D = Decimal


def number(value: str) -> Decimal:
    try:
        result = D(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("must be a finite decimal") from exc
    if not result.is_finite() or result < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative decimal")
    return result


def money(value: Decimal, ceiling: bool = False) -> str:
    return str(value.quantize(D("0.01"), rounding=ROUND_CEILING if ceiling else ROUND_HALF_UP))


def fees(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--processing-rate", type=number, default=D("0.029"))
    parser.add_argument("--processing-fixed", type=number, default=D("0.30"))
    parser.add_argument("--received-fee", type=number, default=D("15"))
    parser.add_argument("--countered-fee", type=number, default=D("15"))
    parser.add_argument("--labor-per-dispute", type=number, default=D("30"))
    parser.add_argument("--cost-per-order", type=number, required=True,
                        help="delivery cost actually budgeted by the operator")


def quote(args: argparse.Namespace) -> dict:
    q, r, a = args.lost_dispute_rate, args.refund_rate, args.processing_rate
    if q >= 1 or r >= 1 or q + r >= 1 or a >= 1 or a + q + r >= 1:
        raise ValueError("rates leave no positive retained-revenue denominator")
    p = args.baseline_price
    baseline_net = p * (1 - a) - args.processing_fixed - args.cost_per_order
    target = baseline_net if args.target_net is None else args.target_net
    overhead = q * (args.received_fee + args.countered_fee + args.labor_per_dispute)
    overhead += r * args.labor_per_refund + args.extra_cost_per_order
    required = (target + args.cost_per_order + args.processing_fixed + overhead) / (1 - a - q - r)
    if required < 0:
        raise ValueError("target net and cost combination produces a negative price")
    scenario_net = p * (1 - a - q - r) - args.processing_fixed - args.cost_per_order - overhead
    return {
        "kind": "CHARGEBACK_PRICE_SCENARIO", "account_data": "NOT_READ",
        "currency": args.currency.upper(), "baseline_price": money(p),
        "baseline_net_per_order": money(baseline_net),
        "scenario_net_at_baseline_price": money(scenario_net),
        "target_net_per_order": money(target), "required_price": money(required, True),
        "price_increase": money(max(D(0), required - p), True),
        "assumptions": {
            "processing_rate": str(a), "processing_fixed": money(args.processing_fixed),
            "lost_dispute_fraction": str(q), "full_refund_fraction": str(r),
            "received_fee": money(args.received_fee), "countered_fee": money(args.countered_fee),
            "labor_per_dispute": money(args.labor_per_dispute),
            "labor_per_refund": money(args.labor_per_refund),
            "cost_per_order": money(args.cost_per_order),
            "extra_cost_per_order": money(args.extra_cost_per_order),
            "all_disputed_orders_lost_and_manually_countered": True,
            "refund_and_dispute_fractions_are_mutually_exclusive": True,
            "all_orders_incur_delivery_cost": True,
        },
        "limits": [
            "This is expected contribution economics, not a dispute-rate forecast or network metric.",
            "Won disputes also count toward monitoring; loss fraction is not total dispute activity.",
            "Higher price does not repair excessive dispute counts or guarantee processing access.",
            "Tax, international cards, conversion, provider reserves and other fees need separate inputs.",
        ],
    }


def stress(args: argparse.Namespace) -> dict:
    n, k, p = args.captured_orders, args.disputed_orders, args.price
    if k > n:
        raise ValueError("disputed orders cannot exceed captured orders")
    if args.processing_rate >= 1:
        raise ValueError("processing rate must be less than one")
    provider_debit = D(k) * (p + args.received_fee + args.countered_fee)
    labor = D(k) * args.labor_per_dispute
    processing = D(n) * (p * args.processing_rate + args.processing_fixed)
    delivery = D(n) * args.cost_per_order
    remaining = D(n) * p - provider_debit - processing - delivery - labor
    return {
        "kind": "CHARGEBACK_LIQUIDITY_STRESS", "account_data": "NOT_READ",
        "currency": args.currency.upper(), "price": money(p),
        "captured_orders": n, "disputed_orders": k,
        "scenario_order_dispute_fraction": str(D(k) / D(n)) if n else None,
        "provider_reversal_and_fees": money(provider_debit),
        "dispute_labor": money(labor), "processing_cost": money(processing),
        "delivery_cost": money(delivery), "remaining_contribution": money(remaining),
        "cash_buffer_shortfall": money(max(D(0), provider_debit - args.available_buffer)),
        "assumptions": {
            "all_disputes_lost_and_manually_countered": True,
            "available_buffer": money(args.available_buffer),
            "processing_rate": str(args.processing_rate),
            "processing_fixed": money(args.processing_fixed),
            "received_fee": money(args.received_fee), "countered_fee": money(args.countered_fee),
            "labor_per_dispute": money(args.labor_per_dispute),
            "cost_per_order": money(args.cost_per_order),
        },
        "limits": [
            "Provider debit is gross liquidity required if original sale proceeds were already spent.",
            "Remaining contribution already subtracts reversal; do not subtract principal twice.",
            "Scenario fraction is not Stripe activity, cohort rate, or VAMP.",
            "No fraud, payment method or tariff facts were fetched from an account.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    q = sub.add_parser("quote", help="preserve baseline contribution under explicit loss assumptions")
    fees(q)
    q.add_argument("--baseline-price", type=number, required=True)
    q.add_argument("--lost-dispute-rate", type=number, required=True, help="fraction, e.g. 0.005")
    q.add_argument("--refund-rate", type=number, default=D("0"))
    q.add_argument("--labor-per-refund", type=number, default=D("0"))
    q.add_argument("--extra-cost-per-order", type=number, default=D("0"))
    q.add_argument("--target-net", type=number)
    s = sub.add_parser("stress", help="gross reversal liquidity and contribution of a captured-order scenario")
    fees(s)
    s.add_argument("--price", type=number, required=True)
    s.add_argument("--captured-orders", type=int, required=True)
    s.add_argument("--disputed-orders", type=int, required=True)
    s.add_argument("--available-buffer", type=number, default=D("0"))
    args = parser.parse_args()
    try:
        if args.command == "stress" and (args.captured_orders < 0 or args.disputed_orders < 0):
            raise ValueError("order counts must be nonnegative")
        print(json.dumps(quote(args) if args.command == "quote" else stress(args), indent=2))
        return 0
    except (ValueError, ArithmeticError) as exc:
        print("chargeback_pricing: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
