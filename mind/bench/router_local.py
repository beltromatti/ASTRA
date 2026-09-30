"""Would a small classifier trained on our own examples beat the rules + one small model? (no network, no cost)

    cd mind && .venv/bin/python -m bench.router_local

A logistic regression over hashed character n-grams of the words (accents stripped, typed or spoken, five languages) plus the
channel state (is an exchange going on, is it a fleet channel), trained with plain numpy on the labelled sets and scored by
5-fold cross-validation over the utterances that have a live channel — the only ones where the router decides anything. It is the
best a local model of this kind could do on this data: what it gets wrong is what a trained classifier would get wrong, and it is
compared with what the rules and the small model get right (bench.router_eval, bench.router_models). It needs a few thousand
labelled examples to compete with words a model reads with understanding; we have five hundred."""
from __future__ import annotations

import random
import re
import zlib

import numpy as np

from astra_mind import router

from .router_eval import make_ctx
from .router_set import ALL
from .router_test2_set import TEST2
from .router_test_set import TEST

DIM = 1 << 15


def features(text: str, chan: str) -> np.ndarray:
    v = np.zeros(DIM + 4, dtype=np.float32)
    t = " " + re.sub(r"[^a-z' ]+", " ", router.norm(text)) + " "
    for n in (2, 3, 4, 5):
        for i in range(len(t) - n + 1):
            v[zlib.crc32(t[i:i + n].encode()) % DIM] += 1.0
    v[:DIM] /= max(1.0, float(np.linalg.norm(v[:DIM])))
    v[DIM] = 1.0 if chan in ("live", "fleet_live") else 0.0
    v[DIM + 1] = 1.0 if chan.startswith("fleet") else 0.0
    v[DIM + 2] = min(len(t.split()), 20) / 20.0
    v[DIM + 3] = 1.0                                     # bias
    return v


def train(X: np.ndarray, y: np.ndarray, epochs: int = 200, lr: float = 0.8, l2: float = 1e-4) -> np.ndarray:
    w = np.zeros(X.shape[1], dtype=np.float32)
    for _ in range(epochs):
        p = 1.0 / (1.0 + np.exp(-X @ w))
        w -= lr * (X.T @ (p - y) / len(y) + l2 * w)
    return w


def main() -> None:
    items = [i for i in ALL + TEST + TEST2 if i.chan in ("enemy", "live", "fleet", "fleet_live") and i.dest in ("crew", "external")]
    X = np.stack([features(i.text, i.chan) for i in items])
    y = np.array([1.0 if i.dest == "external" else 0.0 for i in items], dtype=np.float32)
    idx = list(range(len(items)))
    random.Random(3).shuffle(idx)
    folds = [idx[k::5] for k in range(5)]
    correct = 0
    wrong_ext = wrong_crew = 0
    for k in range(5):
        test = set(folds[k])
        tr = [i for i in idx if i not in test]
        w = train(X[tr], y[tr])
        for i in folds[k]:
            pred = 1.0 if (X[i] @ w) > 0 else 0.0
            correct += pred == y[i]
            if pred != y[i]:
                wrong_ext += pred == 1.0                       # a crew order sent to the party: the costly mistake
                wrong_crew += pred == 0.0                      # words for the party kept aboard
    n = len(items)
    print(f"{n} utterances with a live channel (crew or party only): 5-fold cross-validated accuracy of the local classifier "
          f"{100 * correct / n:.1f}% ({wrong_ext} crew orders sent to the party, {wrong_crew} words for the party kept aboard)")
    rules = 0
    rules_ok = 0
    for it in items:
        r = router.quick(it.text, make_ctx(it))
        eff = "crew" if r is None else r.dest
        rules += 1
        rules_ok += eff == it.dest
    print(f"the same utterances, the rules alone (what they leave open counted as crew): {100 * rules_ok / rules:.1f}%")


if __name__ == "__main__":
    main()
