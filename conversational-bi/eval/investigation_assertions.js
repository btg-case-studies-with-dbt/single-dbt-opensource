// Never-fabricate assertions for the Agentic Investigation Loop (task 5.4).
// SINGLE SOURCE OF TRUTH: referenced by eval_investigation.yaml (promptfoo)
// AND by selftest_assertions.cjs (non-vacuity proof, runnable before the loop
// exists). Design: docs/05.DETAILED_DESIGN.md "Agentic Investigation Loop"
// (APPROVED gate-2 2026-07-11) + DECISION_LOG #13/#14. Decision 1 = (A):
// the loop fires on investigative intent only.
//
// Response contract asserted (additive extension of the five-category `answered`):
//   answered  -> { category, metric, value, dimensions, time_range, rows,
//                  investigation? }
//   investigation = {
//     status: "investigated" | "partial" | "not_investigated",
//     steps_taken: <int>,          // number of governed tool calls (base + drills)
//     stopped_reason: <str>,       // termination cause (NOT a causal claim)
//     trace: [ { step:<int>, tool:"T1|T2|T3|T4", intent:{...},
//                signature:<str>, category:<five-category str> } ],
//     evidence: [ { relationship:"correlation", governed:true,
//                   source_tool_call_step:<int>, claim_type:<str>,
//                   dimension?:<str>, contributor?:<str>,
//                   share_of_total_delta?:<num>, measured_delta?:<num> } ],
//     summary?: <str>              // optional user-facing prose; linted, never causal
//   }
// Non-answered base categories are byte-for-byte unchanged (no investigation,
// or investigation.status:"not_investigated") — the short-circuit in 5.1.

// ── shared helpers ──────────────────────────────────────────────────────────

function parse(output) {
  if (output === null || output === undefined) return {};
  if (typeof output === 'string') {
    try { return JSON.parse(output); } catch (e) { return { __unparseable: output }; }
  }
  // promptfoo may hand us { raw, output } shapes; unwrap common ones.
  if (typeof output === 'object' && output.category === undefined) {
    if (typeof output.raw === 'string') { try { return JSON.parse(output.raw); } catch (e) {} }
    if (typeof output.output === 'string') { try { return JSON.parse(output.output); } catch (e) {} }
    if (output.output && typeof output.output === 'object') return output.output;
  }
  return output;
}

function getInv(r) {
  return (r && typeof r.investigation === 'object' && r.investigation) ? r.investigation : null;
}

function fail(reason) { return { pass: false, score: 0, reason }; }
function pass() { return { pass: true, score: 1, reason: 'Assertion passed' }; }

function isNa(v) {
  return v === null || v === undefined || v === '' || v === 'null';
}

// Recursively collect every string VALUE reachable in an object/array.
function collectStrings(obj, out) {
  out = out || [];
  if (obj === null || obj === undefined) return out;
  if (typeof obj === 'string') { out.push(obj); return out; }
  if (Array.isArray(obj)) { for (const v of obj) collectStrings(v, out); return out; }
  if (typeof obj === 'object') { for (const k of Object.keys(obj)) collectStrings(obj[k], out); }
  return out;
}

// Recursively collect every KEY name reachable in an object/array (lowercased).
function collectKeys(obj, out) {
  out = out || [];
  if (obj === null || obj === undefined || typeof obj !== 'object') return out;
  if (Array.isArray(obj)) { for (const v of obj) collectKeys(v, out); return out; }
  for (const k of Object.keys(obj)) { out.push(String(k).toLowerCase()); collectKeys(obj[k], out); }
  return out;
}

// Causal connectives forbidden in ANY narrative string (design §145 core list +
// tight extensions). Correlational governed vocabulary
// (contributor / share_of_total_delta / coincident / correlation / co-moved) is
// deliberately NOT matched.
const CAUSAL_VALUE_RE =
  /\b(caused|because\s+of|because|drove|driven\s+by|led\s+to|due\s+to|resulted\s+in|responsible\s+for)\b/i;

// Field names that would make causation representable at all (design §138/§140):
// causation must be structurally impossible to express. `stopped_reason`/`reason`
// (a termination cause) is explicitly allowed.
const BANNED_KEYS = new Set(['cause', 'driver', 'drivers', 'root_cause', 'causal', 'causality', 'narrative', 'why']);

// ── A1 base-floor (gate d) ──────────────────────────────────────────────────
// The base metric answer is the GUARANTEED FLOOR: correct category, and — when
// answered — the correct metric with a real value and rows, even if the
// investigation is partial or absent. Investigation is strictly additive; it may
// never corrupt or replace the floor.
function baseFloor(output, context) {
  const v = context.vars || {};
  const r = parse(output);
  if (r.__unparseable !== undefined) return fail(`response did not parse as JSON: ${String(r.__unparseable).slice(0, 120)}`);
  if (r.category !== v.expected_category) {
    return fail(`floor category mismatch: expected '${v.expected_category}', got '${r.category}'`);
  }
  if (r.category !== 'answered') return pass(); // non-answer floors have no metric/value to check
  if (!isNa(v.expected_metric) && r.metric !== v.expected_metric) {
    return fail(`floor metric mismatch: expected '${v.expected_metric}', got '${r.metric}'`);
  }
  if (isNa(r.value)) return fail('floor answered but value is empty/null');
  if (!Array.isArray(r.rows) || r.rows.length < 1) return fail('floor answered but rows[] is empty');
  return pass();
}

// ── A2 intent → status (gate e + the Decision-1(A) trigger) ─────────────────
// Plain lookups MUST NOT trigger the loop (not_investigated, empty trace/evidence).
// Investigative intents on an ANSWERED base MUST run it (investigated|partial).
// A non-answered base short-circuits: no investigation regardless of intent (5.1).
function intentStatus(output, context) {
  const v = context.vars || {};
  const r = parse(output);
  const inv = getInv(r);
  const status = inv ? inv.status : 'not_investigated';

  // Short-circuit: a non-answered base never investigates.
  if (r.category !== 'answered') {
    if (inv && status !== 'not_investigated') {
      return fail(`non-answered base ('${r.category}') must not investigate; got status '${status}'`);
    }
    return pass();
  }

  const intent = String(v.expected_intent || '').toLowerCase();

  if (intent === 'lookup') {
    if (status !== 'not_investigated') {
      return fail(`plain lookup must NOT trigger the loop; expected status 'not_investigated', got '${status}'`);
    }
    if (inv) {
      const tr = Array.isArray(inv.trace) ? inv.trace : [];
      const ev = Array.isArray(inv.evidence) ? inv.evidence : [];
      if (tr.length > 0 || ev.length > 0) {
        return fail(`lookup carried a non-empty investigation (trace=${tr.length}, evidence=${ev.length})`);
      }
    }
    return pass();
  }

  if (intent === 'investigative') {
    if (!inv) return fail('investigative intent on answered base but no investigation block present');
    // Accept an explicit allow-list, e.g. "investigated" or "investigated_or_partial".
    const allowed = String(v.expected_investigation_status || 'investigated_or_partial')
      .toLowerCase().split('_or_');
    if (!allowed.includes(status)) {
      return fail(`investigative status '${status}' not in allowed {${allowed.join(', ')}}`);
    }
    if (!(Number.isInteger(inv.steps_taken) && inv.steps_taken >= 1)) {
      return fail(`investigative run must record steps_taken>=1; got ${inv.steps_taken}`);
    }
    return pass();
  }

  return pass(); // row declared no intent expectation
}

// ── A3 evidence is governed + provenance-linked (gate a) ────────────────────
// EVERY evidence factor must be governed:true, relationship:"correlation", and
// carry a source_tool_call_step pointing at a trace step whose category is
// 'answered'. A factor sourced from a non-answered (abstained) or nonexistent
// step is fabrication — fail.
function evidenceGoverned(output, context) {
  const r = parse(output);
  const inv = getInv(r);
  if (!inv) return pass(); // no investigation -> nothing to govern (A2 owns presence)
  const ev = Array.isArray(inv.evidence) ? inv.evidence : [];
  const trace = Array.isArray(inv.trace) ? inv.trace : [];
  const stepCat = new Map();
  for (const s of trace) if (Number.isInteger(s.step)) stepCat.set(s.step, s.category);

  for (let i = 0; i < ev.length; i++) {
    const f = ev[i];
    if (f.governed !== true) return fail(`evidence[${i}] not governed (governed=${JSON.stringify(f.governed)}) — fabrication`);
    if (f.relationship !== 'correlation') return fail(`evidence[${i}] relationship must be 'correlation', got '${f.relationship}'`);
    if (!Number.isInteger(f.source_tool_call_step)) return fail(`evidence[${i}] missing integer source_tool_call_step`);
    if (!stepCat.has(f.source_tool_call_step)) return fail(`evidence[${i}] source_tool_call_step=${f.source_tool_call_step} points at no trace step`);
    if (stepCat.get(f.source_tool_call_step) !== 'answered') {
      return fail(`evidence[${i}] sourced from a non-answered trace step (category='${stepCat.get(f.source_tool_call_step)}') — abstained branches may not yield evidence`);
    }
    if ('cause' in f || 'driver' in f) return fail(`evidence[${i}] carries a banned causal field`);
  }

  // Optional per-row hard negative: a dimension the loop MUST NOT fabricate a
  // factor for (e.g. ungoverned 'region' on token usage).
  const forbidden = (context.vars || {}).forbidden_factor_dim;
  if (!isNa(forbidden)) {
    const fl = String(forbidden).toLowerCase();
    for (let i = 0; i < ev.length; i++) {
      const dim = String(ev[i].dimension || '').toLowerCase();
      if (dim.includes(fl)) return fail(`evidence[${i}] fabricated a factor over the ungoverned dimension '${forbidden}'`);
    }
  }
  return pass();
}

// ── A4 no causal language, structurally (gate b) ────────────────────────────
// ZERO causal connectives in any narrative string, and ZERO banned causal keys
// anywhere in the investigation. The post-synthesis causal-language linter of §145.
function noCausalLanguage(output, context) {
  const r = parse(output);
  const inv = getInv(r);
  const scope = { investigation: inv };
  if (typeof r.summary === 'string') scope.summary = r.summary;
  if (typeof r.message === 'string') scope.message = r.message;
  if (inv === null && scope.summary === undefined && scope.message === undefined) return pass();

  for (const k of collectKeys(scope)) {
    if (BANNED_KEYS.has(k)) return fail(`banned causal field name present: '${k}' — causation must be structurally unrepresentable`);
  }
  for (const s of collectStrings(scope)) {
    const m = s.match(CAUSAL_VALUE_RE);
    if (m) return fail(`causal connective '${m[0]}' found in narrative: "${s.slice(0, 140)}"`);
  }
  return pass();
}

// ── A5 termination bounds (gate c) ──────────────────────────────────────────
// steps_taken<=MAX_STEPS(6); trace length agrees; no duplicate loop-guard
// signatures; abstained (non-answered) branches contribute no evidence.
const MAX_STEPS = 6;
function termination(output, context) {
  const r = parse(output);
  const inv = getInv(r);
  if (!inv || inv.status === 'not_investigated') return pass();
  const trace = Array.isArray(inv.trace) ? inv.trace : [];
  const ev = Array.isArray(inv.evidence) ? inv.evidence : [];

  if (!(Number.isInteger(inv.steps_taken) && inv.steps_taken <= MAX_STEPS)) {
    return fail(`steps_taken must be an int <= ${MAX_STEPS}; got ${inv.steps_taken}`);
  }
  if (trace.length > MAX_STEPS) return fail(`trace has ${trace.length} steps, exceeds MAX_STEPS ${MAX_STEPS}`);
  if (trace.length !== inv.steps_taken) {
    return fail(`steps_taken (${inv.steps_taken}) disagrees with trace length (${trace.length})`);
  }
  const sigs = trace.map((s) => s.signature).filter((s) => s !== undefined && s !== null);
  if (new Set(sigs).size !== sigs.length) return fail('duplicate loop-guard signature in trace — the visited-signature guard did not fire');

  const answeredSteps = new Set(trace.filter((s) => s.category === 'answered').map((s) => s.step));
  for (let i = 0; i < ev.length; i++) {
    if (!answeredSteps.has(ev[i].source_tool_call_step)) {
      return fail(`evidence[${i}] descends from an abstained/absent branch (step ${ev[i].source_tool_call_step})`);
    }
  }
  return pass();
}

module.exports = {
  baseFloor, intentStatus, evidenceGoverned, noCausalLanguage, termination,
  // exported for the self-test / unit reuse:
  parse, getInv, CAUSAL_VALUE_RE, BANNED_KEYS, MAX_STEPS,
};
