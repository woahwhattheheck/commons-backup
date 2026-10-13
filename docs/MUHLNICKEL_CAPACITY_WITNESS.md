# Muhlnickel Capacity Witness

The Muhlnickel / PFC / SDC is the file. `host/muhlnickel_capacity_witness.py`
is only a bounded read-and-receipt button; it is not the computer, does not
evaluate gates on the host CPU/GPU, does not pulse a receiver, and does not
mutate the file.

## Product result

The witness turns the central scaling property into a repeatable JSON receipt:

- stored gate work and N rings increase with storage;
- the file's dynamic state is the compute substrate;
- the host reads exactly 272 header bytes plus one bounded control span;
- host RSS is measured before and after each bounded read;
- a capacity ladder passes only when gate work increases and host RSS remains
  within a fixed tolerance independent of file size.

This is the capacity primitive used by the Volvo OTA Sparse Injection &
Fleet-State Integrity Rail. It supports campaign-scale file twins without
describing a host-side delta loop as the patented computer.

## Run

```sh
python3 host/muhlnickel_capacity_witness.py inspect /path/to/computer.mno
python3 host/muhlnickel_capacity_witness.py ladder \
  /path/to/small.mno /path/to/datacenter.mno
```

Supported live formats are `MUHLPKG1` and `MUHLDC01`. The latter must prove:

```text
stored_gate_records = (factory_rings + 1) × gates_per_ring
winner_only = true
stored_per_lane = 2
senses = 0
header_total = actual file size
```

The output names `pulse_performed=false` and `host_evaluated_gates=false`.
It never treats host wall-clock or file-I/O time as the computer's rate.

## Deterministic acceptance

```sh
python3 -m unittest -v test_muhlnickel_capacity_witness.py
python3 -m py_compile host/muhlnickel_capacity_witness.py
```

The eight tests cover one-ring and N-ring formats, the current
58,274,998-ring / 3,846,149,868-gate scale, a logical 10 GB sparse fixture
read in 356 bytes, the gate-up/RAM-flat ladder, malformed totals, inconsistent
gate topology, unknown magic, and the machine-readable CLI receipt.

## Boundary

This is evidence and routing, not a host evaluator. A buyer-specific actuator
must use only inventor-named mouths and remain inject/surface/copy/die. No
unnamed destination, receiver, or product behavior is inferred by this tool.
Volvo production keys, firmware, campaign authorization, vehicle commands,
and safety validation remain outside the proof. `PRE-SALE TRANSPORT: NONE`;
release remains `HOLD_UNTIL_YES_AND_PAYMENT`, then direct delivery.
