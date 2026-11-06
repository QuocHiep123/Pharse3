// ICE lab: real Chromium, real coturn servers, and one impairment proxy per TURN.
// Results describe a local lab. The relay-to-relay leg has no added delay, and all peers run in one browser.
const dgram = require('dgram'), net = require('net'), os = require('os'), fs = require('fs'), path = require('path');
const { spawn } = require('child_process');
const { chromium } = require('playwright-core');

const IP = os.networkInterfaces().eth0.find(a => a.family === 'IPv4').address;
const N = 8;
const TURN_BASE = 40000, UDP_PROXY_BASE = 41000, TCP_PROXY_BASE = 42000, RELAY_BASE = 50000;
const REPS = process.env.REPS ? +process.env.REPS : null;
const reps = (n) => REPS || n;
const impair = Array.from({ length: N * 2 }, () => ({ delay: 0, loss: 0, down: false, pkts: 0 }));

const coturn = [];
const coturnEnv = { ...process.env, LD_LIBRARY_PATH: process.env.COTURN_LIB || process.env.LD_LIBRARY_PATH || '' };
for (let i = 0; i < N; i++) {
  coturn.push(spawn(process.env.COTURN_BIN || 'turnserver', ['-n', '--no-tls', '--no-dtls', '--no-cli', '--lt-cred-mech', '--user', 'u:p', '--realm', 'lab',
    '--listening-ip', IP, '--relay-ip', IP, '--listening-port', String(TURN_BASE + i), '--min-port', String(RELAY_BASE + i * 1000), '--max-port', String(RELAY_BASE + i * 1000 + 999),
    '--relay-threads', '1', '--log-file', '/dev/null', '--simple-log', '--pidfile', path.join(os.tmpdir(), `lab_turn_${process.pid}_${i}.pid`)], { env: coturnEnv, stdio: 'ignore' }));
  startUdpProxy(i);
  startUdpProxy(i + N); // second proxy to the same TURN, so one side can lose a TURN while the other keeps it
  startTcpProxy(i);
}
process.on('exit', () => coturn.forEach(p => p.kill()));

function pass(i) { const c = impair[i]; c.pkts++; return !c.down && Math.random() >= c.loss; }
function later(i, f) { const d = impair[i].delay; d > 0 ? setTimeout(f, d) : f(); }

function startUdpProxy(i) {
  const front = dgram.createSocket('udp4'); const clients = new Map();
  front.on('message', (m, r) => {
    if (!pass(i)) return;
    const k = r.address + ':' + r.port; let b = clients.get(k);
    if (!b) {
      b = dgram.createSocket('udp4'); clients.set(k, b);
      b.on('message', (mm) => { if (pass(i)) later(i, () => front.send(mm, r.port, r.address)); });
      b.bind(0, IP);
    }
    later(i, () => b.send(m, TURN_BASE + i % N, IP));
  });
  front.bind(UDP_PROXY_BASE + i, IP);
}

function startTcpProxy(i) {
  net.createServer((c) => {
    c.setNoDelay(true);
    const b = dgram.createSocket('udp4'); b.bind(0, IP);
    let buf = Buffer.alloc(0), closed = false;
    b.on('message', (m) => {
      if (!pass(i)) return;
      const pad = (4 - m.length % 4) % 4;
      later(i, () => { if (!c.destroyed) c.write(pad ? Buffer.concat([m, Buffer.alloc(pad)]) : m); });
    });
    c.on('data', (d) => {
      buf = Buffer.concat([buf, d]);
      while (buf.length >= 4) {
        const stun = buf[0] < 0x40, len = buf.readUInt16BE(2), n = stun ? 20 + len : 4 + len, tot = stun ? n : n + (4 - n % 4) % 4;
        if (buf.length < tot) break;
        const m = buf.subarray(0, n); buf = buf.subarray(tot);
        if (pass(i)) later(i, () => { if (!closed) b.send(m, TURN_BASE + i, IP); });
      }
    });
    c.on('error', () => {});
    c.on('close', () => { closed = true; b.close(); });
  }).listen(TCP_PROXY_BASE + i, IP);
}

const udp = (i) => ({ urls: `turn:${IP}:${UDP_PROXY_BASE + i}?transport=udp`, username: 'u', credential: 'p' });
const tcp = (i) => ({ urls: `turn:${IP}:${TCP_PROXY_BASE + i}?transport=tcp`, username: 'u', credential: 'p' });
const setAll = (d) => impair.forEach((c, i) => Object.assign(c, { delay: d[i] ?? 0, loss: 0, down: false }));
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const median = (v) => { const s = v.filter(x => x !== null && x !== undefined).sort((a, b) => a - b); return s.length ? s[s.length >> 1] : null; };

// ---- browser side ----
const PAGE_HELPERS = () => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  window.turnOf = (port) => Math.floor((port - 50000) / 1000);
  window.calls = {};
  const negotiate = async (c, ring) => {
    const { a, b, sig } = c;
    c.aReady = false; c.bReady = false;
    await a.setLocalDescription(await a.createOffer());
    await wait(sig);
    await b.setRemoteDescription(a.localDescription);
    c.bReady = true; c.qb.splice(0).forEach(x => b.addIceCandidate(x).catch(() => {}));
    if (ring) await wait(ring);
    c.answerAt = performance.now() - c.t0;
    await b.setLocalDescription(await b.createAnswer());
    await wait(sig);
    await a.setRemoteDescription(b.localDescription);
    c.aReady = true; c.qa.splice(0).forEach(x => a.addIceCandidate(x).catch(() => {}));
  };
  window.startCall = (id, callerServers, calleeServers, opt) => {
    const a = new RTCPeerConnection({ iceServers: callerServers, iceTransportPolicy: 'relay' });
    const b = new RTCPeerConnection({ iceServers: calleeServers, iceTransportPolicy: 'relay' });
    const c = { a, b, sig: opt.sig || 0, t0: performance.now(), events: [], connectedAt: null, cand: [], qa: [], qb: [], gatherDone: {} };
    window.calls[id] = c;
    const now = () => Math.round(performance.now() - c.t0);
    a.onicecandidate = e => {
      if (!e.candidate) return;
      c.cand.push([performance.now() - c.t0, turnOf(e.candidate.port)]);
      const x = e.candidate; setTimeout(() => { c.bReady ? b.addIceCandidate(x).catch(() => {}) : c.qb.push(x); }, c.sig);
    };
    b.onicecandidate = e => {
      if (!e.candidate) return;
      const x = e.candidate; setTimeout(() => { c.aReady ? a.addIceCandidate(x).catch(() => {}) : c.qa.push(x); }, c.sig);
    };
    a.onicegatheringstatechange = () => { if (a.iceGatheringState === 'complete') c.gatherDone.a = now(); };
    b.onicegatheringstatechange = () => { if (b.iceGatheringState === 'complete') c.gatherDone.b = now(); };
    a.onconnectionstatechange = () => { if (a.connectionState === 'connected' && c.connectedAt === null) c.connectedAt = performance.now() - c.t0; c.events.push([now(), 'conn', a.connectionState]); };
    a.oniceconnectionstatechange = () => c.events.push([now(), 'ice', a.iceConnectionState]);
    const dc = a.createDataChannel('d', { ordered: false, maxRetransmits: 0 });
    dc.onopen = () => { c.dcOpenAt = performance.now() - c.t0; c.timer = setInterval(() => { try { if (dc.readyState === 'open' && dc.bufferedAmount < 1e6) dc.send(new Uint8Array(800)); } catch (e) {} }, 20); };
    negotiate(c, opt.ring || 0).catch(e => c.events.push([now(), 'negotiate_error', String(e)]));
  };
  window.restartIce = (id) => { const c = window.calls[id]; c.a.restartIce(); negotiate(c, 0).catch(e => c.events.push([0, 'restart_error', String(e)])); };
  window.snap = async (id, who = 'a') => {
    const c = window.calls[id], pc = c[who]; const r = await pc.getStats(); const by = new Map(); r.forEach(s => by.set(s.id, s));
    const pairs = []; let sel = null, changes = null, nLocal = 0;
    r.forEach(s => {
      if (s.type === 'transport') { sel = s.selectedCandidatePairId; changes = s.selectedCandidatePairChanges; }
      if (s.type === 'local-candidate') nLocal++;
    });
    r.forEach(s => {
      if (s.type !== 'candidate-pair') return;
      const l = by.get(s.localCandidateId), m = by.get(s.remoteCandidateId);
      pairs.push({ l: turnOf(l.port), r: turnOf(m.port), lp: l.relayProtocol, lproto: l.protocol, rproto: m.protocol, lprio: l.priority, rprio: m.priority, state: s.state, nom: !!s.nominated,
        req: s.requestsSent, resp: s.responsesReceived, rtt: s.currentRoundTripTime ?? null, sel: s.id === sel, bs: s.bytesSent });
    });
    return { t: performance.now() - c.t0, changes, nLocal, connectedAt: c.connectedAt, answerAt: c.answerAt, dcOpenAt: c.dcOpenAt, gatherDone: c.gatherDone, ice: pc.iceConnectionState, conn: pc.connectionState, pairs };
  };
  window.getCand = (id) => window.calls[id].cand;
  window.endCall = (id) => { const c = window.calls[id]; clearInterval(c.timer); c.a.close(); c.b.close(); return c.events; };
};
const selPair = (s) => s.pairs.find(x => x.sel) || null;
const selOf = (s) => { const p = selPair(s); return p ? `T${p.l}->T${p.r}` : 'none'; };
const rttOf = (s) => { const p = selPair(s); return p && p.rtt !== null ? Math.round(p.rtt * 1000) : null; };

(async () => {
  await sleep(1500); // let coturn bind its ports
  let browser, page;
  const fresh = async () => {
    if (browser) await browser.close().catch(() => {});
    browser = await chromium.launch({ executablePath: process.env.CHROME_BIN, args: ['--no-sandbox', '--disable-dev-shm-usage'], headless: true });
    page = await browser.newPage(); await page.goto('about:blank'); await page.evaluate(PAGE_HELPERS);
  };
  await fresh();
  console.log('version', browser.version(), 'ip', IP);
  const out = { version: browser.version(), turn: 'coturn' }; const save = () => fs.writeFileSync(process.env.OUT, JSON.stringify(out, null, 1));
  let id = 0;
  const start = async (a, b, opt = {}) => { const k = 'c' + (++id); await page.evaluate(([k, a, b, o]) => startCall(k, a, b, o), [k, a, b, opt]); return k; };
  const snap = (k, w = 'a') => page.evaluate(([k, w]) => snap(k, w), [k, w]);
  const end = (k) => page.evaluate((k) => endCall(k), k);
  const only = process.env.ONLY ? process.env.ONLY.split(',') : null; const on = (n) => !only || only.includes(n);
  const scenario = async (name, body) => {
    if (!on(name)) return;
    await fresh();
    try { await body(); } catch (e) { console.log(name, 'ABORTED', String(e).split('\n')[0]); out[name + '_aborted'] = String(e).split('\n')[0]; save(); }
  };
  const waitConnected = async (k, ms = 15000) => { const t = Date.now(); let s; do { await sleep(40); s = await snap(k); } while (!s.dcOpenAt && Date.now() - t < ms); return s; };
  // Records each change of selected pair, in ms after the answer, so a late upgrade is visible.
  const watchSel = async (k, ms) => { const t = Date.now(), tl = []; let last = null; while (Date.now() - t < ms) { const s = await snap(k), v = selOf(s); if (v !== last) { tl.push([Math.round(s.t - s.answerAt), v]); last = v; } await sleep(100); } return tl; };

  // R1: slot 1 has a higher delay. Which pair wins, as a function of signaling delay and ringing time?
  await scenario('R1', async () => {
    out.R1 = [];
    for (const d of [15, 60]) for (const sig of [0, 100]) for (const ring of [0, 3000]) {
      const rows = [];
      for (let r = 0; r < reps(3); r++) {
        setAll([d, 5, 5, 5]); const l = [0, 1, 2, 3].map(udp); const k = await start(l, l, { sig, ring });
        await waitConnected(k); const timeline = await watchSel(k, 12000); const s = await snap(k), sb = await snap(k, 'b');
        rows.push({ timeline, caller: selOf(s), callee: selOf(sb), rtt: rttOf(s), changes: s.changes, nLocalA: s.nLocal, nLocalB: sb.nLocal, setup: s.connectedAt - s.answerAt }); await end(k); await sleep(200);
      }
      const row = { slot1Delay: d, sig, ring, finals: rows.map(x => x.caller), timelines: rows.map(x => x.timeline), rtt: median(rows.map(x => x.rtt)), setup: Math.round(median(rows.map(x => x.setup))), nLocalA: rows[0].nLocalA, nLocalB: rows[0].nLocalB, changes: rows.map(x => x.changes) };
      out.R1.push(row); console.log('R1', JSON.stringify(row)); save();
    }
  });
  // R2: with a realistic flow, how many pairs get a ping or an RTT, and do the others stay alive?
  await scenario('R2', async () => { for (const len of [8, 4]) {
    setAll([30, 5, 10, 15, 20, 25, 35, 40]); const l = [0, 1, 2, 3, 4, 5, 6, 7].slice(0, len).map(udp); const k = await start(l, l, { sig: 100, ring: 3000 }); const series = [];
    let prev = impair.map(c => c.pkts);
    for (const t of [4, 5, 7, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90]) {
      while ((await snap(k)).t < t * 1000) await sleep(100);
      const s = await snap(k), cur = impair.map(c => c.pkts);
      const row = { t, nLocal: s.nLocal, total: s.pairs.length, pinged: s.pairs.filter(p => p.req > 0).length, responded: s.pairs.filter(p => p.resp > 0).length, withRtt: s.pairs.filter(p => p.rtt !== null).length, sel: selOf(s), rtt: rttOf(s), ice: s.ice, conn: s.conn, proxyPktDelta: cur.map((x, i) => x - prev[i]) };
      prev = cur; series.push(row); console.log('R2 len' + len, JSON.stringify(row));
    }
    out['R2_len' + len] = { series, events: await end(k) }; save();
  } });
  // R3: pair count and protocols with mixed transports.
  await scenario('R3', async () => {
    setAll([5, 5, 5, 5, 5, 5, 5, 5]); const l = [0, 1, 2, 3, 4, 5].map(udp).concat([6, 7].map(tcp));
    const k = await start(l, l, { sig: 100, ring: 3000 }); await sleep(6000); const s = await snap(k);
    out.R3_mixed8 = { total: s.pairs.length, localProto: [...new Set(s.pairs.map(p => p.lproto))], remoteProto: [...new Set(s.pairs.map(p => p.rproto))], sel: selOf(s) }; await end(k); console.log('R3 mixed8', JSON.stringify(out.R3_mixed8));
    const l4 = [0, 1, 2].map(udp).concat([tcp(6)]); const k4 = await start(l4, l4, { sig: 100, ring: 3000 }); await sleep(6000); const s4 = await snap(k4);
    out.R3_mixed4 = { total: s4.pairs.length, sel: selOf(s4) }; await end(k4); console.log('R3 mixed4', JSON.stringify(out.R3_mixed4));
    const k2 = await start([tcp(6)], l4, { sig: 100, ring: 3000 }); await sleep(6000); const s2 = await snap(k2), p2 = selPair(s2);
    out.R3_callerTcpOnly = { total: s2.pairs.length, sel: selOf(s2), localRelayProtocol: p2 && p2.lp }; await end(k2); console.log('R3 callerTcpOnly', JSON.stringify(out.R3_callerTcpOnly));
    const k3 = await start([tcp(6), udp(0)], [tcp(6), udp(0)], { sig: 100, ring: 3000 }); await sleep(6000); const s3 = await snap(k3);
    out.R3_tcpListedFirst = { sel: selOf(s3) }; await end(k3); console.log('R3 tcpListedFirst', JSON.stringify(out.R3_tcpListedFirst)); save();
  });
  // R4: the TURN in use dies at different call ages. Does ICE recover alone? If not, how long does an ICE restart take?
  await scenario('R4', async () => {
    out.R4 = [];
    for (const len of [4, 8]) for (const killAt of [3, 8, 25, 70]) {
      setAll(Array(8).fill(5)); const order = [0, 1, 2, 3, 4, 5, 6, 7].slice(0, len); const b = [1, 0].concat(order.slice(2));
      const k = await start(order.map(udp), b.map(udp), { sig: 50 }); await waitConnected(k); const c0 = await snap(k);
      await sleep(Math.max(0, killAt * 1000 - (c0.t - c0.answerAt)));
      const before = await snap(k); impair[0].down = true; const t0 = Date.now();
      const row = { len, killAt, before: selOf(before), pairsAliveBefore: before.pairs.length, autoRecoveredMs: null, afterAuto: null, disconnectedMs: null, failedMs: null, restartMs: null, afterRestart: null };
      while (Date.now() - t0 < 20000) {
        await sleep(200); const s = await snap(k), p = selPair(s), e = Date.now() - t0;
        if (row.disconnectedMs === null && s.ice === 'disconnected') row.disconnectedMs = e;
        if (row.failedMs === null && s.ice === 'failed') row.failedMs = e;
        if (p && p.l !== 0 && p.r !== 0 && s.ice === 'connected' && p.resp > 0) { row.autoRecoveredMs = e; row.afterAuto = selOf(s); break; }
      }
      if (row.autoRecoveredMs === null) {
        const t1 = Date.now(); await page.evaluate((k) => restartIce(k), k);
        while (Date.now() - t1 < 15000) {
          await sleep(50); const s = await snap(k), p = selPair(s);
          if (p && p.l !== 0 && p.r !== 0 && (s.ice === 'connected' || s.ice === 'completed') && p.resp > 0) { row.restartMs = Date.now() - t1; row.afterRestart = selOf(s); break; }
        }
      }
      row.events = await end(k); out.R4.push(row); console.log('R4', JSON.stringify({ ...row, events: undefined })); save(); await sleep(300);
    }
  });
  // R5: setup time after answering, by list length and dead TURNs. Gathering-complete shows the cost without trickle ICE.
  await scenario('R5', async () => {
    out.R5 = [];
    for (const [name, n, dead] of [['len1', 1, 0], ['len2', 2, 0], ['len4', 4, 0], ['len8', 8, 0], ['len4_slot1_dead', 4, 1], ['len8_slot1_dead', 8, 1], ['len4_half_dead', 4, 2], ['len8_half_dead', 8, 4], ['len4_last_only', 4, 3], ['len8_last_only', 8, 7]]) {
      const rows = [];
      for (let r = 0; r < reps(12); r++) {
        setAll(Array(8).fill(10)); for (let i = 0; i < dead; i++) impair[i].down = true;
        const l = Array.from({ length: n }, (_, i) => udp(i)); const k = await start(l, l, { sig: 100 }); const s = await waitConnected(k, 30000);
        rows.push({ setup: s.connectedAt === null ? null : s.connectedAt - s.answerAt, dc: s.dcOpenAt ? s.dcOpenAt - s.answerAt : null, sel: selOf(s) }); await end(k); await sleep(250);
      }
      const v = rows.map(x => x.setup).filter(x => x !== null).sort((a, b) => a - b);
      const row = { name, ok: v.length, of: rows.length, setupMedian: Math.round(median(v)), setupMin: Math.round(v[0]), setupMax: Math.round(v[v.length - 1]), dcMedian: Math.round(median(rows.map(x => x.dc))), sels: [...new Set(rows.map(x => x.sel))] };
      out.R5.push(row); console.log('R5', JSON.stringify(row)); save();
    }
    out.R5_gather = [];
    for (const [name, n, dead] of [['len4_all_alive', 4, 0], ['len4_one_dead', 4, 1], ['len8_one_dead', 8, 1]]) {
      setAll(Array(8).fill(10)); for (let i = 0; i < dead; i++) impair[i].down = true;
      const l = Array.from({ length: n }, (_, i) => udp(i)); const k = await start(l, l, { sig: 100, ring: 70000 }); const t = Date.now(); let s;
      do { await sleep(200); s = await snap(k); } while (s.gatherDone.a === undefined && Date.now() - t < 65000);
      const row = { name, callerGatherCompleteMs: s.gatherDone.a ?? null }; await end(k); out.R5_gather.push(row); console.log('R5 gather', JSON.stringify(row)); save();
    }
  });
  // R6: the selected TURN degrades while the call is up. Does ICE leave it?
  await scenario('R6', async () => {
    out.R6 = [];
    for (const [name, cfg] of [['rtt_plus_300', { delay: 80 }], ['loss_30', { loss: 0.3 }], ['loss_60', { loss: 0.6 }], ['loss_90', { loss: 0.9 }]]) {
      setAll([5, 5]); const l = [0, 1].map(udp); const k = await start(l, l, { sig: 50 }); await sleep(6000); const before = await snap(k); Object.assign(impair[0], cfg); const t0 = Date.now();
      let sw = null, disc = null, s;
      while (Date.now() - t0 < 45000) { await sleep(500); s = await snap(k); if (!sw && !selOf(s).startsWith('T0->T0')) sw = [Date.now() - t0, selOf(s)]; if (!disc && s.ice !== 'connected') disc = [Date.now() - t0, s.ice]; }
      const row = { name, before: selOf(before), beforeRtt: rttOf(before), switchAt: sw, firstNotConnected: disc, finalSel: selOf(s), finalRtt: rttOf(s), finalIce: s.ice, alivePairs: s.pairs.length }; await end(k); out.R6.push(row); console.log('R6', JSON.stringify(row)); save();
    }
  });
  // R7: does the time to get each relay candidate track the client-to-TURN delay? A long ring lets all candidates arrive.
  await scenario('R7', async () => {
    out.R7 = []; const delays = [5, 10, 20, 40, 60, 80, 100, 150];
    for (let r = 0; r < reps(6); r++) {
      setAll(delays); const l = [0, 1, 2, 3, 4, 5, 6, 7].map(udp); const k = await start(l, l, { sig: 100, ring: 3000 }); await sleep(2500);
      const cand = await page.evaluate((k) => getCand(k), k); await end(k); out.R7.push(cand); await sleep(200);
    }
    const byTurn = delays.map((d, i) => ({ oneWayDelay: d, candidateMs: Math.round(median(out.R7.map(c => (c.find(x => x[1] === i) || [null])[0]))) }));
    out.R7_summary = byTurn; console.log('R7', JSON.stringify(byTurn)); save();
  });
  // R8: list placement plans, with healthy TURNs and with the first TURN dead from the start.
  await scenario('R8', async () => {
    out.R8 = []; const plans = { bridged: [[0, 1, 2, 3], [1, 0, 2, 3]], shared: [[2, 0, 1, 3], [2, 1, 0, 3]] };
    for (const [plan, [a, b]] of Object.entries(plans)) for (const ring of [0, 3000]) for (const dead of [null, a[0]]) {
      const rows = [];
      for (let r = 0; r < reps(2); r++) {
        setAll(Array(8).fill(5)); if (dead !== null) impair[dead].down = true;
        const k = await start(a.map(udp), b.map(udp), { sig: 100, ring }); await waitConnected(k); const timeline = await watchSel(k, 12000); const s = await snap(k), sb = await snap(k, 'b');
        rows.push({ timeline, caller: selOf(s), callee: selOf(sb), alivePairs: s.pairs.map(p => [p.l, p.r, p.state, p.req]) }); await end(k); await sleep(200);
      }
      const row = { plan, ring, deadTurn: dead, runs: rows }; out.R8.push(row); console.log('R8', JSON.stringify(row)); save();
    }
  });
  // R9: the caller's TURNs die during ringing, after allocation. This is the case where a longer list forces more failing checks.
  await scenario('R9', async () => {
    out.R9 = [];
    for (const [name, n, dead] of [['len4_alive', 4, 0], ['len8_alive', 8, 0], ['len4_slot1', 4, 1], ['len8_slot1', 8, 1], ['len4_half', 4, 2], ['len8_half', 8, 4], ['len4_last_only', 4, 3], ['len8_last_only', 8, 7]]) {
      const rows = [];
      for (let r = 0; r < reps(6); r++) {
        setAll(Array(N * 2).fill(5)); const idx = Array.from({ length: n }, (_, i) => i);
        const k = await start(idx.map(udp), idx.map(i => udp(i + N)), { sig: 100, ring: 3000 }); await sleep(2000); for (let i = 0; i < dead; i++) impair[i].down = true;
        const s = await waitConnected(k, 25000); rows.push({ setup: s.connectedAt === null ? null : s.connectedAt - s.answerAt, dc: s.dcOpenAt ? s.dcOpenAt - s.answerAt : null, sel: selOf(s), pairs: s.pairs.length }); await end(k); await sleep(250);
      }
      const v = rows.map(x => x.setup).filter(x => x !== null).sort((a, b) => a - b);
      const row = { name, ok: v.length, of: rows.length, setupMedian: Math.round(median(v)), setupMin: Math.round(v[0]), setupMax: Math.round(v[v.length - 1]), dcMedian: Math.round(median(rows.map(x => x.dc))), pairs: rows[0].pairs, sels: [...new Set(rows.map(x => x.sel))] };
      out.R9.push(row); console.log('R9', JSON.stringify(row)); save();
    }
  });

  // R10: find the call age after which ICE no longer fails over by itself.
  await scenario('R10', async () => {
    out.R10 = [];
    for (const killAt of [2, 4, 5, 6, 7, 8, 9, 12]) for (let r = 0; r < reps(2); r++) {
      setAll(Array(N * 2).fill(5)); const a = [0, 1, 2, 3], b = [1, 0, 2, 3];
      const k = await start(a.map(udp), b.map(udp), { sig: 50 }); await waitConnected(k); const c0 = await snap(k);
      await sleep(Math.max(0, killAt * 1000 - (c0.t - c0.answerAt))); const before = await snap(k); impair[0].down = true; const t0 = Date.now();
      const row = { killAt, pairsAliveBefore: before.pairs.length, autoRecoveredMs: null, afterAuto: null };
      while (Date.now() - t0 < 16000) { await sleep(200); const s = await snap(k), p = selPair(s); if (p && p.l !== 0 && p.r !== 0 && s.ice === 'connected' && p.resp > 0) { row.autoRecoveredMs = Date.now() - t0; row.afterAuto = selOf(s); break; } }
      out.R10.push(row); console.log('R10', JSON.stringify(row)); await end(k); save(); await sleep(250);
    }
  });

  // R11: how much slower can the callee's first TURN be and still survive the stop-gathering race?
  await scenario('R11', async () => {
    out.R11 = [];
    for (const sig of [50, 300]) for (const d of [5, 10, 15, 20, 30, 40, 60, 80, 120]) {
      let kept = 0; const finals = [], reps_ = reps(3);
      for (let r = 0; r < reps_; r++) {
        setAll(Array(N * 2).fill(5)); impair[N].delay = d; const idx = [0, 1, 2, 3];
        const k = await start(idx.map(udp), idx.map(i => udp(i + N)), { sig, ring: 2000 }); await waitConnected(k); await sleep(2500); const s = await snap(k), sb = await snap(k, 'b');
        if (sb.pairs.some(p => p.l === 0)) kept++; finals.push(selOf(s)); await end(k); await sleep(200);
      }
      const row = { sig, calleeSlot1Delay: d, extraAllocateMs: (d - 5) * 4, keptRuns: kept, of: reps_, finals }; out.R11.push(row); console.log('R11', JSON.stringify(row)); save();
    }
  });

  await browser.close(); console.log('DONE'); process.exit(0);
})().catch(e => { console.error('ERR', e); process.exit(1); });
