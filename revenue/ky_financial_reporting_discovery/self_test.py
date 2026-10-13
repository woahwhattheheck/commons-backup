from .parity_probe import compare_rows
from .validation_probe import require_rows

def self_test():
    require_rows([{"id":"A","value":1}])
    same = compare_rows([{"id":"A","value":1}], [{"id":"A","value":1}], ["id"], ["value"])
    drift = compare_rows([{"id":"A","value":1}], [{"id":"A","value":2}], ["id"], ["value"])
    missing = compare_rows([{"id":"A","value":1}], [], ["id"], ["value"])
    assert same == []
    assert drift[0][0] == "VALUE_DRIFT"
    assert missing[0][0] == "MISSING_TARGET_ROW"
    return True

if __name__ == "__main__":
    print("OK" if self_test() else "FAIL")
