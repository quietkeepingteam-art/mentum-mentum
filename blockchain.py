"""
Core blockchain logic for Mentum.

Every node runs this exact same code, so every node computes the exact
same genesis block and validates new blocks the exact same way. That
shared agreement — not a central server — is what lets independent
copies on different computers stay in sync.

Attribution: every block carries the public key of whoever mined or
logged it, and a signature proving the holder of the matching private
key actually produced this exact block. The public key is also baked
into the hash itself, so the proof-of-work is tied to that identity —
you can't take someone else's mined block and relabel it as yours
without redoing the mining.
"""

import hashlib
import time
from typing import List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

GENESIS_PREV_HASH = "0" * 64
GENESIS_TIMESTAMP = "1970-01-01T00:00:00Z"  # fixed, so every node's genesis hash is identical
GENESIS_PUBLIC_KEY = "0" * 64
GENESIS_SIGNATURE = "0" * 128


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def block_payload(index, timestamp, name, type_, coins, note, prev_hash, nonce, miner_public_key, miner_name) -> str:
    return (
        f"{index}|{timestamp}|{name}|{type_}|{coins}|{note or ''}|"
        f"{prev_hash}|{nonce}|{miner_public_key}|{miner_name or ''}"
    )


# ---------- identity / signing ----------

def generate_keypair():
    """Returns (private_key_hex, public_key_hex)."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_hex = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    pub_hex = pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return priv_hex, pub_hex


def load_private_key(priv_hex: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))


def sign_hash(private_key: Ed25519PrivateKey, hash_hex: str) -> str:
    return private_key.sign(bytes.fromhex(hash_hex)).hex()


def verify_signature(public_key_hex: str, signature_hex: str, hash_hex: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pub.verify(bytes.fromhex(signature_hex), bytes.fromhex(hash_hex))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------- block ----------

class Block:
    def __init__(self, index, timestamp, name, type_, coins, note, prev_hash, nonce,
                 pow_difficulty, miner_public_key, miner_name, signature, hash_=None):
        self.index = index
        self.timestamp = timestamp
        self.name = name
        self.type = type_
        self.coins = coins
        self.note = note
        self.prev_hash = prev_hash
        self.nonce = nonce
        self.pow_difficulty = pow_difficulty
        self.miner_public_key = miner_public_key
        self.miner_name = miner_name
        self.signature = signature
        self.hash = hash_ or self.compute_hash()

    def compute_hash(self) -> str:
        return sha256_hex(block_payload(
            self.index, self.timestamp, self.name, self.type, self.coins, self.note,
            self.prev_hash, self.nonce, self.miner_public_key, self.miner_name,
        ))

    def to_dict(self):
        return {
            "index": self.index, "timestamp": self.timestamp, "name": self.name,
            "type": self.type, "coins": self.coins, "note": self.note,
            "prevHash": self.prev_hash, "nonce": self.nonce,
            "powDifficulty": self.pow_difficulty,
            "minerPublicKey": self.miner_public_key, "minerName": self.miner_name,
            "signature": self.signature, "hash": self.hash,
        }

    @staticmethod
    def from_dict(d):
        return Block(
            d["index"], d["timestamp"], d["name"], d["type"], d["coins"],
            d.get("note", ""), d["prevHash"], d["nonce"], d.get("powDifficulty", 0),
            d.get("minerPublicKey", GENESIS_PUBLIC_KEY), d.get("minerName", ""),
            d.get("signature", GENESIS_SIGNATURE), d["hash"],
        )


def make_genesis() -> Block:
    return Block(0, GENESIS_TIMESTAMP, "Genesis", "earn", 0, "", GENESIS_PREV_HASH, 0, 0,
                 GENESIS_PUBLIC_KEY, "", GENESIS_SIGNATURE)


def is_block_valid(block: Block, prev_block: Optional[Block]) -> bool:
    if block.hash != block.compute_hash():
        return False
    if prev_block is not None:
        if block.prev_hash != prev_block.hash:
            return False
        if block.index != prev_block.index + 1:
            return False
    if block.pow_difficulty > 0 and not block.hash.startswith("0" * block.pow_difficulty):
        return False
    if not verify_signature(block.miner_public_key, block.signature, block.hash):
        return False
    return True


def verify_chain(chain: List[Block]) -> dict:
    if not chain:
        return {"valid": False, "brokenAt": None, "reason": "empty chain"}
    if chain[0].hash != make_genesis().hash:
        return {"valid": False, "brokenAt": 0, "reason": "genesis block doesn't match"}
    for i in range(1, len(chain)):
        if not is_block_valid(chain[i], chain[i - 1]):
            return {"valid": False, "brokenAt": chain[i].index,
                    "reason": "hash, link, proof-of-work, or signature check failed"}
    return {"valid": True, "brokenAt": None, "reason": None}


def is_chain_valid(chain: List[Block]) -> bool:
    return verify_chain(chain)["valid"]


def mine_block(index, name, type_, coins, note, prev_hash, difficulty,
               miner_public_key, miner_name, private_key) -> Block:
    """Brute-force a nonce until the block's hash starts with `difficulty` zeros,
    then sign the resulting hash with the miner's private key."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target = "0" * difficulty
    nonce = 0
    while True:
        h = sha256_hex(block_payload(index, timestamp, name, type_, coins, note, prev_hash,
                                      nonce, miner_public_key, miner_name))
        if h.startswith(target):
            signature = sign_hash(private_key, h)
            return Block(index, timestamp, name, type_, coins, note, prev_hash, nonce,
                         difficulty, miner_public_key, miner_name, signature, h)
        nonce += 1


def log_block(index, name, type_, coins, note, prev_hash,
              miner_public_key, miner_name, private_key) -> Block:
    """Instant, unmined block — used for spend entries. Still signed by whoever logged it."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    h = sha256_hex(block_payload(index, timestamp, name, type_, coins, note, prev_hash,
                                  0, miner_public_key, miner_name))
    signature = sign_hash(private_key, h)
    return Block(index, timestamp, name, type_, coins, note, prev_hash, 0, 0,
                 miner_public_key, miner_name, signature, h)
