import argparse
import json
import os
import socket
import uuid

import requests
from flask import Flask, jsonify, render_template, request

from blockchain import (
    Block, generate_keypair, load_private_key, is_block_valid,
    make_genesis, mine_block, log_block, verify_chain,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
CHAIN_FILE = os.path.join(DATA_DIR, "chain.json")
RULES_FILE = os.path.join(DATA_DIR, "rules.json")
PEERS_FILE = os.path.join(DATA_DIR, "peers.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
IDENTITY_FILE = os.path.join(DATA_DIR, "identity.json")  # private key lives ONLY here, never sent over the API

app = Flask(__name__)


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_chain():
    raw = load_json(CHAIN_FILE, None)
    if raw is None:
        chain = [make_genesis()]
        save_chain(chain)
        return chain
    return [Block.from_dict(b) for b in raw]


def save_chain(chain):
    save_json(CHAIN_FILE, [b.to_dict() for b in chain])


def load_rules():
    return load_json(RULES_FILE, [
        {"id": "r1", "name": "Woke up early", "type": "earn", "coins": 10},
        {"id": "r2", "name": "Planned the day", "type": "earn", "coins": 5},
        {"id": "r3", "name": "Beer", "type": "spend", "coins": 20},
        {"id": "r4", "name": "Food delivery order", "type": "spend", "coins": 30},
    ])


def load_peers():
    return load_json(PEERS_FILE, [])


def load_settings():
    return load_json(SETTINGS_FILE, {"difficulty": 4})


# ---------- identity ----------

def load_identity():
    data = load_json(IDENTITY_FILE, None)
    if data is None:
        priv_hex, pub_hex = generate_keypair()
        data = {"privateKey": priv_hex, "publicKey": pub_hex, "name": socket.gethostname()}
        save_json(IDENTITY_FILE, data)
    return data


def get_signing_identity():
    """Returns (private_key_object, public_key_hex, name). Private key never leaves this function."""
    d = load_identity()
    return load_private_key(d["privateKey"]), d["publicKey"], d["name"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/identity", methods=["GET"])
def get_identity():
    d = load_identity()
    return jsonify({"publicKey": d["publicKey"], "name": d["name"]})


@app.route("/identity", methods=["POST"])
def set_identity_name():
    d = load_identity()
    name = (request.json or {}).get("name", "").strip()
    if name:
        d["name"] = name[:40]
        save_json(IDENTITY_FILE, d)
    return jsonify({"publicKey": d["publicKey"], "name": d["name"]})


# ---------- chain ----------

@app.route("/chain", methods=["GET"])
def get_chain():
    return jsonify([b.to_dict() for b in load_chain()])


@app.route("/verify", methods=["GET"])
def verify():
    chain = load_chain()
    result = verify_chain(chain)
    result["length"] = len(chain)
    return jsonify(result)


# ---------- rules (local to this node — not synced) ----------

@app.route("/rules", methods=["GET"])
def get_rules():
    return jsonify(load_rules())


@app.route("/rules", methods=["POST"])
def add_rule():
    rules = load_rules()
    body = request.json
    rule = {"id": uuid.uuid4().hex[:8], "name": body["name"], "type": body["type"], "coins": int(body["coins"])}
    rules.append(rule)
    save_json(RULES_FILE, rules)
    return jsonify(rule)


@app.route("/rules/<rid>", methods=["PATCH"])
def update_rule(rid):
    rules = load_rules()
    for r in rules:
        if r["id"] == rid and "coins" in request.json:
            r["coins"] = int(request.json["coins"])
    save_json(RULES_FILE, rules)
    return jsonify({"ok": True})


@app.route("/rules/<rid>", methods=["DELETE"])
def delete_rule(rid):
    rules = [r for r in load_rules() if r["id"] != rid]
    save_json(RULES_FILE, rules)
    return jsonify({"ok": True})


# ---------- peers ----------

@app.route("/peers", methods=["GET"])
def get_peers():
    return jsonify(load_peers())


@app.route("/peers", methods=["POST"])
def add_peer():
    peers = load_peers()
    url = request.json["url"].rstrip("/")
    if url not in peers:
        peers.append(url)
        save_json(PEERS_FILE, peers)
    return jsonify(peers)


@app.route("/peers/<int:i>", methods=["DELETE"])
def delete_peer(i):
    peers = load_peers()
    if 0 <= i < len(peers):
        peers.pop(i)
        save_json(PEERS_FILE, peers)
    return jsonify(peers)


# ---------- settings ----------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        s = load_settings()
        s["difficulty"] = max(1, min(6, int(request.json.get("difficulty", 4))))
        save_json(SETTINGS_FILE, s)
        return jsonify(s)
    return jsonify(load_settings())


# ---------- mining / logging ----------

@app.route("/mine", methods=["POST"])
def mine():
    body = request.json
    rules = {r["id"]: r for r in load_rules()}
    rule = rules.get(body.get("rule_id"))
    if not rule:
        return jsonify({"error": "unknown rule"}), 400
    note = body.get("note", "")
    chain = load_chain()
    prev = chain[-1]
    private_key, pub_hex, name = get_signing_identity()

    if rule["type"] == "earn":
        difficulty = load_settings()["difficulty"]
        block = mine_block(prev.index + 1, rule["name"], rule["type"], rule["coins"], note,
                            prev.hash, difficulty, pub_hex, name, private_key)
    else:
        block = log_block(prev.index + 1, rule["name"], rule["type"], rule["coins"], note,
                           prev.hash, pub_hex, name, private_key)

    chain.append(block)
    save_chain(chain)
    broadcast_block(block)
    return jsonify(block.to_dict())


def broadcast_block(block):
    for peer in load_peers():
        try:
            requests.post(f"{peer}/receive_block", json=block.to_dict(), timeout=3)
        except requests.RequestException:
            pass  # peer offline — it'll catch up next time it syncs


@app.route("/receive_block", methods=["POST"])
def receive_block():
    chain = load_chain()
    incoming = Block.from_dict(request.json)
    if incoming.index == chain[-1].index + 1 and is_block_valid(incoming, chain[-1]):
        chain.append(incoming)
        save_chain(chain)
        return jsonify({"ok": True, "appended": True})
    # We're behind, ahead, diverged, or the block failed validation (bad signature,
    # forged attribution, etc.) — fall back to full chain consensus either way.
    resolved = resolve_internal()
    return jsonify({"ok": True, "appended": False, "resolved": resolved})


@app.route("/resolve", methods=["POST", "GET"])
def resolve():
    return jsonify(resolve_internal())


def resolve_internal():
    """Longest-valid-chain consensus: ask every peer for their chain, adopt
    the longest one that passes verify_chain() — hashes, links, proof-of-work,
    AND every block's signature. This is what lets nodes that were offline
    (or mined conflicting blocks at the same time) converge."""
    chain = load_chain()
    best = chain
    for peer in load_peers():
        try:
            r = requests.get(f"{peer}/chain", timeout=4)
            candidate = [Block.from_dict(b) for b in r.json()]
            if len(candidate) > len(best) and verify_chain(candidate)["valid"]:
                best = candidate
        except requests.RequestException:
            continue
    replaced = best is not chain
    if replaced:
        save_chain(best)
    return {"replaced": replaced, "length": len(best)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    ident = load_identity()
    print(f"Mentum Mentum node running at http://localhost:{args.port}  (LAN: http://<this-computer's-IP>:{args.port})")
    print(f"Identity: {ident['name']}  (public key {ident['publicKey'][:16]}…)")
    app.run(host=args.host, port=args.port, threaded=True)
