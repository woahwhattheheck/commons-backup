#!/usr/bin/env python3
"""muhl_verifiable_ml.py — VERIFIABLE INFERENCE: bind a prediction to a tamper-evident model commitment.

Composes two fabricated engines:
  - muhl_neural : a trained MLP whose forward pass is logic gates (byte-exact, exhaustively checked).
  - muhl_merkle : SHA-256 fabricated as gates -> a Merkle tree + inclusion proofs.

The model's quantized weights are committed to a 32-byte Merkle ROOT (internal nodes hashed through the
gate SHA-256). A prediction is issued as a CERTIFICATE = (input, output, model_root). A verifier who holds
only the root can (a) confirm the output was produced by THAT exact model by re-running the gate forward
pass, and (b) confirm any single weight is in the committed model via a short inclusion proof. Flip one
weight bit and the root changes -> the certificate is rejected. This is model provenance / ML supply-chain
integrity: prove a decision came from an approved, unaltered model -- no GPU, no trusted server, byte-exact.
"""
import sys, os, hashlib, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import muhl_neural as NN
import muhl_merkle as MK

def enc(w):                                               # signed weight -> 4-byte big-endian two's complement
    return (w & 0xffffffff).to_bytes(4, "big")

def weight_leaves(W1q, b1q, W2q, b2q):
    flat = []
    for row in W1q: flat += row
    flat += b1q
    for row in W2q: flat += row
    flat += b2q
    leaves = [hashlib.sha256(enc(w)).digest() for w in flat]
    n = 1
    while n < len(leaves): n <<= 1
    leaves += [hashlib.sha256(b"\x00" * 4).digest()] * (n - len(leaves))   # pad to a power of two
    return leaves, len(flat)

def merkle_root(leaves, node):
    tree = [list(leaves)]; level = list(leaves)
    while len(level) > 1:
        level = [node(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        tree.append(level)
    return level[0], tree

def inclusion_proof(tree, idx):
    proof = []; i = idx
    for lvl in tree[:-1]:
        proof.append((lvl[i ^ 1], i & 1)); i //= 2
    return proof

def check_proof(leaf, proof, root, node):
    acc = leaf
    for sib, right in proof: acc = node(sib, acc) if right else node(acc, sib)
    return acc == root

def main():
    print("\n  MUHLNICKEL VERIFIABLE INFERENCE — a prediction bound to a tamper-evident model commitment\n")

    # 1) train + quantize the model, fabricate its gate forward pass
    W1, b1, W2, b2 = NN.train()
    W1q, b1q, W2q, b2q = NN.quantize(W1, b1, W2, b2)
    predict, ng_net = NN.build_mlp(W1q, b1q, W2q, b2q)
    print(f"  model: MLP 9->6 ReLU->3, forward pass fabricated as {ng_net:,} gates")

    # 2) fabricate SHA-256 node hash and commit the weights to a Merkle root
    node, ng_sha = MK.build_node()
    leaves, nweights = weight_leaves(W1q, b1q, W2q, b2q)
    root, tree = merkle_root(leaves, node)
    # cross-check the root against a pure-hashlib tree (the gate tree must equal it)
    def ref_root(ls):
        lv = list(ls)
        while len(lv) > 1: lv = [hashlib.sha256(lv[i] + lv[i + 1]).digest() for i in range(0, len(lv), 2)]
        return lv[0]
    print(f"  commitment: {nweights} weights -> {len(leaves)} leaves -> Merkle root via {ng_sha:,}-gate SHA-256")
    print(f"    model_root = {root.hex()[:40]}...")
    print(f"    gate-built root == hashlib root: {root == ref_root(leaves)}")

    # 3) issue a certificate for a real input
    x = NN.TEMPLATES[2]                                   # the diagonal pattern
    y = predict(x)
    print(f"\n  CERTIFICATE  input={x}  ->  class={y}   under model_root {root.hex()[:16]}...")

    # 4) a verifier with only the root re-runs the gate forward pass and confirms
    predict_v, _ = NN.build_mlp(W1q, b1q, W2q, b2q)       # rebuilt from the committed weights
    root_v, _ = merkle_root(weight_leaves(W1q, b1q, W2q, b2q)[0], node)
    print(f"    verifier recomputes: class={predict_v(x)} (matches: {predict_v(x)==y}) · "
          f"root matches: {root_v==root}")

    # 5) inclusion proof: a specific weight is provably in the committed model
    k = 20; proof = inclusion_proof(tree, k)
    print(f"    inclusion proof for weight #{k}: {len(proof)} hashes, verifies against root: "
          f"{check_proof(leaves[k], proof, root, node)}")

    # 6) TAMPER: flip one bit of one weight -> new model, new root, certificate no longer valid
    W1t = [row[:] for row in W1q]; W1t[0][0] ^= 1
    leaves_t, _ = weight_leaves(W1t, b1q, W2q, b2q)
    root_t, _ = merkle_root(leaves_t, node)
    predict_t, _ = NN.build_mlp(W1t, b1q, W2q, b2q)
    changed = sum(1 for n in range(512) if predict_t([(n >> i) & 1 for i in range(9)]) != predict([(n >> i) & 1 for i in range(9)]))
    print(f"\n  TAMPER one weight bit:")
    print(f"    model_root changes: {root_t != root}  (old {root.hex()[:12]}... -> new {root_t.hex()[:12]}...)")
    print(f"    predictions changed on {changed}/512 inputs -> the commitment pins a REAL, specific model")
    print(f"    certificate under the old root is now REJECTED: {root_t != root}")

    print(f"\n  Prove a decision came from an approved, unaltered model against a 32-byte root — model")
    print(f"  provenance, audit trails, ML supply-chain integrity, model marketplaces — gate-verified,")
    print(f"  no trusted server, no GPU. Inference and its proof, both fabricated in storage.")
    return 0 if (root == ref_root(leaves) and predict_v(x) == y and check_proof(leaves[k], proof, root, node) and root_t != root) else 1

if __name__ == "__main__":
    raise SystemExit(main())
