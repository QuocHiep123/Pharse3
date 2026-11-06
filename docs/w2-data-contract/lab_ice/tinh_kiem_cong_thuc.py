"""Hand checks for the report claims. Uses the libwebrtc priority formulas read from source."""
import math

TYPE = {"udp": 2, "tcp": 1, "tls": 0}

def cand_prio(proto, slot, n, nic=127, addr=30, component=1):
    relay_pref = n - slot  # slot 0 gets n
    local = ((nic << 8) | addr) + relay_pref
    return (TYPE[proto] << 24) | (local << 8) | (256 - component)

def pair_prio(g, d):
    return (min(g, d) << 32) + 2 * max(g, d) + (1 if g > d else 0)

def rank(caller, callee, nic_a=127, nic_b=127):
    """caller/callee are lists of (turn, proto). Returns ordered pairs by pair priority."""
    out = []
    for i, (t, p) in enumerate(caller):
        for j, (u, q) in enumerate(callee):
            g = cand_prio(p, i, len(caller), nic_a)
            d = cand_prio(q, j, len(callee), nic_b)
            out.append((pair_prio(g, d), f"{t}/{p}", f"{u}/{q}"))
    return sorted(out, reverse=True)

def show(title, rows, k=10):
    print(f"\n{title} (total pairs {len(rows)}, distinct priorities {len({r[0] for r in rows})})")
    for n, r in enumerate(rows[:k], 1):
        print(f"  {n:2d}. caller {r[1]:10s} callee {r[2]:10s}")

U = "udp"
a = [("T1", U), ("T2", U), ("T3", U), ("T4", U), ("T5", U), ("T6", U), ("T7", "tcp"), ("T8", "tls")]
b = [("T2", U), ("T1", U), ("T3", U), ("T4", U), ("T5", U), ("T6", U), ("T7", "tcp"), ("T8", "tls")]
show("Bridged plan, both sides NIC preference 127", rank(a, b))
show("Bridged plan, callee NIC preference 126", rank(a, b, 127, 126))
show("Bridged plan, caller NIC preference 126", rank(a, b, 126, 127))
same = [("T*", U)] + a[1:]
show("Shared plan", rank(same, same), 6)
rows = rank(a, b)
print("\nBy relay transport of the two candidates (1.4):")
cnt = {}
for _, x, y in rows:
    k = "/".join(sorted([x.split('/')[1], y.split('/')[1]]))
    cnt[k] = cnt.get(k, 0) + 1
print(" ", cnt, "total", sum(cnt.values()))
print("  Sweep at 48 ms per check, all 64:", 64 * 48, "ms")
print("  TLS at slot 1, UDP at slot 2 same list, order:")
show("  mixed", rank([("TL", "tls"), ("TU", U)], [("TL", "tls"), ("TU", U)]), 4)

print("\n=== Confidence saturation: C = 1 - prod(1 - alpha_l), alpha = n/(n+kappa) ===")
def alpha(n, kappa): return n / (n + kappa)
cases = {
    "cold-start ISP, 0 sample at levels 0-1, country 5000, region 200000": [0, 0, 5000, 200000],
    "3 samples leaf, 3 ISP, country 5000, region 200000": [3, 3, 5000, 200000],
    "200 leaf, 500 ISP, country 5000, region 200000": [200, 500, 5000, 200000],
    "Rare country: 0,0,30,2000": [0, 0, 30, 2000],
}
for k in (5, 20, 50):
    print(f" kappa={k}")
    for name, ns in cases.items():
        al = [alpha(n, k) for n in ns]
        c = 1 - math.prod(1 - x for x in al)
        w, rem = [], 1.0
        for x in al:
            w.append(rem * x); rem *= 1 - x
        print(f"  {name:66s} C={c:.6f} weights fine->coarse={[round(x, 3) for x in w]} left_for_prior={rem:.1e}")

print("\n=== Effective sample size under exponential decay ===")
def decay(n_per_day, days, half_life):
    lam = math.log(2) / half_life
    w = [math.exp(-lam * d) for d in range(days) for _ in range(n_per_day)]
    s, s2 = sum(w), sum(x * x for x in w)
    return s, s * s / s2
for hl in (1, 3, 7):
    s, kish = decay(100, 30, hl)
    print(f"  100 calls/day, 30 days, half-life {hl}d: sum weights={s:.0f}, Kish n_eff={kish:.0f}, ratio={s/kish:.2f}")

print("\n=== Wilson lower bound z=1.96 ===")
def wilson(p, n, z=1.96):
    if n == 0: return 0.0
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d
for p, n in [(1.0, 5), (1.0, 20), (1.0, 100), (0.97, 1000), (0.99, 1000), (0.95, 20), (1.0, 300)]:
    print(f"  p={p} n={n}: LB={wilson(p, n):.3f}")
# shrink-then-Wilson vs posterior
kappa, parent = 20, 0.97
for s, n in [(5, 5), (20, 20), (19, 20), (95, 100)]:
    shr = (s + kappa * parent) / (n + kappa)
    print(f"  leaf {s}/{n}, parent {parent}, kappa {kappa}: shrunk={shr:.3f}, Wilson(shrunk, n)={wilson(shr, n):.3f}, Wilson(shrunk, n+kappa)={wilson(shr, n + kappa):.3f}")

print("\n=== Normalisation by VIA thresholds: linear score = rtt/320 + loss/1.2 + jitter/12, equal weights ===")
def q(r, l, j): return r / 320 + l / 1.2 + j / 12
items = [("domestic A: 25ms,0.2%,3ms", 25, .2, 3), ("domestic B: 45ms,0.2%,2ms", 45, .2, 2),
         ("low-RTT lossy: 40ms,1.4%,3ms", 40, 1.4, 3), ("very high RTT clean: 480ms,0.1%,2ms", 480, .1, 2),
         ("international C: 180ms,0.3%,5ms", 180, .3, 5)]
for n, r, l, j in items:
    print(f"  {n:38s} score={q(r, l, j):.3f}  violates={[m for m, x, t in (('rtt', r, 320), ('loss', l, 1.2), ('jitter', j, 12)) if x >= t]}")

print("\n=== Composition checks ===")
ps = [.01, .005, .01]
print("  independent loss:", 1 - math.prod(1 - p for p in ps), "sum:", sum(ps))
print("  jitter rss vs sum for 3,3,6:", math.sqrt(9 + 9 + 36), 12)
# p95 sum vs p95 of sum (lognormal legs)
import random
random.seed(1)
legs = [(math.log(30), .3), (math.log(40), .1), (math.log(15), .6)]
xs = [[random.lognormvariate(m, s) for m, s in legs] for _ in range(200000)]
p = lambda a, q: sorted(a)[int(len(a) * q)]
tot = [sum(x) for x in xs]
print("  p50 sum of legs", round(sum(p([x[i] for x in xs], .5) for i in range(3)), 1), "p50 of total", round(p(tot, .5), 1))
print("  p95 sum of legs", round(sum(p([x[i] for x in xs], .95) for i in range(3)), 1), "p95 of total", round(p(tot, .95), 1))

print("\n=== Role bonus versus quality gap (needs report's real scale; illustrative) ===")
for gap_name, gap in (("domestic: A vs B above", q(45, .2, 2) - q(25, .2, 3)), ("domestic mid", q(60, .4, 3) - q(25, .2, 3)), ("international", q(250, .5, 6) - q(180, .3, 5))):
    print(f"  {gap_name}: quality gap={abs(gap):.3f}; bonus 0.1 overrides={0.1 > abs(gap)}; bonus 0.3 overrides={0.3 > abs(gap)}")
