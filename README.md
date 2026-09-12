# Mentum Mentum — a decentralized behavior ledger

Each computer runs its own copy of this program. Each one keeps its own full
copy of the chain, mines its own proof-of-work blocks, and independently
follows the same rule — *the longest valid chain wins* — to stay in sync with
the others. There's no central server; if you stop running it on every
computer, the network stops existing, but no single machine is "in charge."

## 1. Install (on every computer)

Requires Python 3.9+.

```
pip install -r requirements.txt
```

## 2. Run a node

```
python app.py --port 5000
```

Open `http://localhost:5000` in a browser on that same computer.

## 3. Find each computer's address on your network

- Mac: `ipconfig getifaddr en0`
- Windows: `ipconfig` (look for "IPv4 Address")
- Linux: `hostname -I`

Both computers need to be reachable from each other — normally that means
being on the same Wi-Fi/LAN. (For syncing over the internet instead, you'd
need port forwarding or a tunnel like Tailscale/ngrok — ask me if you want
help setting that up.)

## 4. Connect the nodes

On Computer A's dashboard, under **Peers**, add:
```
http://<Computer B's IP>:5000
```

On Computer B's dashboard, add Computer A's address the same way. Do this on
both sides — the sync is one-directional per peer entry.

## 5. Everyday use

Once a node is running and open in your browser, here's the whole workflow:

**Set your name** — under **Identity**, type a display name and hit Save.
This is just a label; do it once per computer. Do this before logging
anything, so your entries aren't attributed to "unknown."

**Set up your rules** — under **Rules**, add the behaviors you want to
track. Pick *earn* for good behavior, *spend* for the stuff you're trying to
cut back on, and set how many coins each one is worth. You can edit a coin
value anytime by typing a new number into its box, or remove a rule with the
`×` button. Rules are local to each computer — add the same ones on both if
you want them to match.

**Log something** — find the rule under **Log something** and tap its
button. *Earn* rules say **Mine** — the app has to solve a small
proof-of-work puzzle first, so you'll see a "Mining…" status for a second or
two before it seals. *Spend* rules say **Log** and post immediately. Want a
note attached (e.g. "3rd time this week")? Type it into the note field
before tapping the button — it only applies to the next entry.

**Check your balance** — the big number at the top is always current:
total earned minus total spent, across every entry ever logged on this
chain.

**Review history** — scroll to **History** for a full timeline, newest
first, showing who logged each entry, when, and (for mined ones) the nonce
and difficulty it took to seal it.

**Verify the chain** — tap **Verify chain** anytime you want proof nothing's
been tampered with. It re-checks every block's hash, its link to the
previous block, its proof-of-work, and its signature.

**Sync with peers** — new entries broadcast to connected peers
automatically. If a computer was asleep or offline when something was
mined, open its dashboard and tap **Sync now** — it'll catch up by pulling
the longest valid chain from whichever peers it can reach.

## How the pieces map to "real blockchain"

| Concept | Where it lives |
|---|---|
| Proof-of-work mining | `blockchain.py: mine_block()` — brute-forces a nonce until the hash has enough leading zeros |
| Tamper-evidence | `blockchain.py: verify_chain()` — recomputes every hash and checks the links |
| Decentralization | Each computer runs its own `app.py` with its own `data/chain.json` — nobody's copy is canonical |
| Consensus | `app.py: resolve_internal()` — longest valid chain wins, same rule on every node |
| Networking | Plain HTTP between nodes (`/receive_block`, `/chain`, `/resolve`) — no blockchain-specific protocol needed at this scale |

## Adding a third (or tenth) computer

Install and run the same way, then add its address as a peer on the other
nodes (and add their addresses as peers on it). Nothing else changes — this
is the same design real blockchain networks use to scale to many nodes.




