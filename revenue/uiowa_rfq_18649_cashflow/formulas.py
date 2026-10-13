"""Independent formula sheet for workbook parity.

Weekly columns:
  A week
  B cash_cost
  C receipts
  D pre_receipt = previous_closing - cash_cost (week 0 uses opening)
  E closing = pre_receipt + receipts
"""

from __future__ import annotations

from decimal import Decimal

CENT = Decimal("0.01")


def weekly_formula_sheet(projection):
    opening = projection["opening_liquidity_usd"]
    rows = []
    for i, w in enumerate(projection["weekly"]):
        if i == 0:
            pre_formula = "opening-B%d" % i
        else:
            pre_formula = "E%d-B%d" % (i - 1, i)
        close_formula = "D%d+C%d" % (i, i)
        rows.append(
            {
                "week": w["week"],
                "B_cash_cost": w["cash_cost"],
                "C_receipts": w["receipts"],
                "D_pre_receipt_formula": pre_formula,
                "E_closing_formula": close_formula,
                "D_engine": w["pre_receipt_cash"],
                "E_engine": w["closing_cash"],
            }
        )
    return {"opening": opening, "rows": rows}


def eval_sheet(sheet):
    """Evaluate the D/E formulas against B/C and opening."""
    env = {"opening": sheet["opening"]}
    out = []
    for i, row in enumerate(sheet["rows"]):
        env["B%d" % i] = row["B_cash_cost"]
        env["C%d" % i] = row["C_receipts"]
        d = _eval_expr(row["D_pre_receipt_formula"], env).quantize(CENT)
        env["D%d" % i] = d
        e = _eval_expr(row["E_closing_formula"], env).quantize(CENT)
        env["E%d" % i] = e
        out.append({"week": row["week"], "D": d, "E": e})
    return out


def _eval_expr(expr, env):
    # Only identifier, identifier-identifier, identifier+identifier.
    if "-" in expr:
        left, right = expr.split("-", 1)
        return env[left] - env[right]
    if "+" in expr:
        left, right = expr.split("+", 1)
        return env[left] + env[right]
    return env[expr]


def assert_parity(projection):
    sheet = weekly_formula_sheet(projection)
    got = eval_sheet(sheet)
    for row, computed in zip(sheet["rows"], got):
        if computed["D"] != row["D_engine"] or computed["E"] != row["E_engine"]:
            raise FormulaParityError(
                "week %s formula D/E %s/%s != engine %s/%s"
                % (row["week"], computed["D"], computed["E"], row["D_engine"], row["E_engine"])
            )
    return True


class FormulaParityError(Exception):
    pass
