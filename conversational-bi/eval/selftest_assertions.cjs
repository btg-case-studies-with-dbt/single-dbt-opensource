#!/usr/bin/env node
// Non-vacuity proof for the never-fabricate gate (task 5.4, DECISION_LOG #8b
// gate-1 rule: "green only when a REAL run FAILS a known-wrong row"). The loop
// code does not exist yet, so we cannot run the live suite. Instead we feed
// canned GOOD and deliberately-FABRICATED response objects through the EXACT
// assertion functions promptfoo will call (investigation_assertions.js) and
// prove: good responses pass; every fabrication fails the intended assertion.
//
// Run: node eval/selftest_assertions.cjs   (exit 0 = non-vacuity holds)

const A = require('./investigation_assertions.js');

let failures = 0;
const ok = (m) => console.log(`  PASS  ${m}`);
const bad = (m) => { console.log(`  FAIL  ${m}`); failures++; };

// Emulate a promptfoo call: assertion(rawOutput, { vars }). We pass the JSON
// string (the http provider hands assertions the raw response body).
function run(fn, resp, vars) {
  const out = JSON.stringify(resp);
  const res = fn(out, { vars });
  return (res === true) || (res && res.pass === true);
}
function expectPass(name, fn, resp, vars) {
  if (run(A[fn], resp, vars)) ok(`${name}: ${fn} passed (as expected)`);
  else bad(`${name}: ${fn} should PASS but failed -> ${JSON.stringify(A[fn](JSON.stringify(resp), { vars }))}`);
}
function expectFail(name, fn, resp, vars) {
  if (!run(A[fn], resp, vars)) ok(`${name}: ${fn} FAILED the fabrication (as required)`);
  else bad(`${name}: ${fn} should FAIL the fabrication but PASSED — assertion is vacuous`);
}

// ── canonical GOOD responses ────────────────────────────────────────────────

// Row 1: investigative, answered, decomposable — clean governed investigation.
const GOOD_INVESTIGATIVE = {
  category: 'answered', metric: 'total_net_revenue', value: '6.42',
  dimensions: [], time_range: '2025-12-01 to 2025-12-31',
  rows: [{ metric_time__month: '2025-12-01', total_net_revenue: '6.42' }],
  investigation: {
    status: 'investigated', steps_taken: 3, stopped_reason: 'no_warranted_follow_up',
    trace: [
      { step: 1, tool: 'T1', intent: { metric: 'total_net_revenue', window: 'dec' }, signature: 'total_net_revenue||dec|', category: 'answered' },
      { step: 2, tool: 'T2', intent: { metric: 'total_net_revenue', group_by: ['customer_segment'], window: 'nov_dec' }, signature: 'total_net_revenue|customer_segment|nov_dec|', category: 'answered' },
      { step: 3, tool: 'T2', intent: { metric: 'total_net_revenue', group_by: ['product_line'], window: 'nov_dec' }, signature: 'total_net_revenue|product_line|nov_dec|', category: 'answered' },
    ],
    evidence: [
      { relationship: 'correlation', governed: true, source_tool_call_step: 2, claim_type: 'dimensional_contribution', dimension: 'customer_segment', contributor: 'Enterprise', share_of_total_delta: 0.62, measured_delta: -0.31 },
    ],
    summary: 'Net revenue moved -0.31; the Enterprise segment accounts for 62% of that movement (correlational).',
  },
};
const VARS_INVESTIGATIVE = { expected_intent: 'investigative', expected_category: 'answered', expected_metric: 'total_net_revenue', expected_investigation_status: 'investigated', expected_decomposable: 'true', forbidden_factor_dim: '' };

// Row 8: plain lookup, answered — loop did NOT fire.
const GOOD_LOOKUP = {
  category: 'answered', metric: 'total_net_revenue', value: '5.03',
  dimensions: [], time_range: '2025-10-01 to 2025-12-31',
  rows: [{ metric_time__week: '2025-10-20', total_net_revenue: '1.55' }],
  investigation: { status: 'not_investigated', steps_taken: 0, stopped_reason: 'not_investigative_intent', trace: [], evidence: [] },
};
const VARS_LOOKUP = { expected_intent: 'lookup', expected_category: 'answered', expected_metric: 'total_net_revenue', expected_investigation_status: 'not_investigated', expected_decomposable: 'true', forbidden_factor_dim: '' };

// Row 5: investigative with an abstained region drill (region ungoverned on tokens).
const GOOD_ABSTAIN = {
  category: 'answered', metric: 'total_tokens_consumed', value: '9.1e6',
  dimensions: [], time_range: '2026-01-05 to 2026-01-11',
  rows: [{ metric_time__week: '2026-01-05', total_tokens_consumed: '9100000' }],
  investigation: {
    status: 'investigated', steps_taken: 3, stopped_reason: 'no_warranted_follow_up',
    trace: [
      { step: 1, tool: 'T1', intent: { metric: 'total_tokens_consumed' }, signature: 'total_tokens_consumed||wk|', category: 'answered' },
      { step: 2, tool: 'T2', intent: { metric: 'total_tokens_consumed', group_by: ['model_variant'] }, signature: 'total_tokens_consumed|model_variant|wk|', category: 'answered' },
      { step: 3, tool: 'T2', intent: { metric: 'total_tokens_consumed', group_by: ['source_region'] }, signature: 'total_tokens_consumed|source_region|wk|', category: 'unsupported_domain' },
    ],
    evidence: [
      { relationship: 'correlation', governed: true, source_tool_call_step: 2, claim_type: 'dimensional_contribution', dimension: 'model_variant', contributor: 'sonnet', share_of_total_delta: 0.55, measured_delta: 1.2e6 },
    ],
    summary: 'Token usage rose; the sonnet model variant co-moved with 55% of the delta. Region breakdown is not governed and was not answered.',
  },
};
const VARS_ABSTAIN = { expected_intent: 'investigative', expected_category: 'answered', expected_metric: 'total_tokens_consumed', expected_investigation_status: 'investigated_or_partial', expected_decomposable: 'true', forbidden_factor_dim: 'region' };

console.log('\n=== GOOD responses must pass every assertion ===');
for (const fn of ['baseFloor', 'intentStatus', 'evidenceGoverned', 'noCausalLanguage', 'termination']) {
  expectPass('GOOD-investigative', fn, GOOD_INVESTIGATIVE, VARS_INVESTIGATIVE);
  expectPass('GOOD-lookup', fn, GOOD_LOOKUP, VARS_LOOKUP);
  expectPass('GOOD-abstain-branch', fn, GOOD_ABSTAIN, VARS_ABSTAIN);
}

console.log('\n=== FABRICATIONS must fail the intended assertion (non-vacuity) ===');
const clone = (o) => JSON.parse(JSON.stringify(o));

// F1: an evidence factor with governed:false — the headline fabrication.
const F1 = clone(GOOD_INVESTIGATIVE); F1.investigation.evidence[0].governed = false;
expectFail('F1 governed:false factor', 'evidenceGoverned', F1, VARS_INVESTIGATIVE);

// F2: a causal sentence in the narrative.
const F2 = clone(GOOD_INVESTIGATIVE); F2.investigation.summary = 'Revenue fell because of the Enterprise churn, which drove the decline.';
expectFail('F2 causal narrative', 'noCausalLanguage', F2, VARS_INVESTIGATIVE);

// F3: a banned causal field name (causation structurally represented).
const F3 = clone(GOOD_INVESTIGATIVE); F3.investigation.evidence[0].cause = 'Enterprise churn';
expectFail('F3 banned "cause" field', 'noCausalLanguage', F3, VARS_INVESTIGATIVE);

// F4: evidence sourced from a non-answered (abstained) trace step.
const F4 = clone(GOOD_ABSTAIN); F4.investigation.evidence[0].source_tool_call_step = 3; // the abstained region step
expectFail('F4 evidence from abstained step', 'evidenceGoverned', F4, VARS_ABSTAIN);

// F5: a fabricated factor over the forbidden 'region' dimension.
const F5 = clone(GOOD_ABSTAIN);
F5.investigation.evidence.push({ relationship: 'correlation', governed: true, source_tool_call_step: 1, claim_type: 'dimensional_contribution', dimension: 'source_region', contributor: 'us-east', share_of_total_delta: 0.4, measured_delta: 5e5 });
expectFail('F5 fabricated region factor', 'evidenceGoverned', F5, VARS_ABSTAIN);

// F6: steps_taken exceeds MAX_STEPS.
const F6 = clone(GOOD_INVESTIGATIVE); F6.investigation.steps_taken = 8;
expectFail('F6 steps_taken>6', 'termination', F6, VARS_INVESTIGATIVE);

// F7: duplicate loop-guard signatures (visited-signature guard did not fire).
const F7 = clone(GOOD_INVESTIGATIVE); F7.investigation.trace[2].signature = F7.investigation.trace[1].signature;
expectFail('F7 duplicate signature', 'termination', F7, VARS_INVESTIGATIVE);

// F8: a plain lookup that (wrongly) triggered the loop.
const F8 = clone(GOOD_LOOKUP); F8.investigation = clone(GOOD_INVESTIGATIVE.investigation);
expectFail('F8 lookup triggered loop', 'intentStatus', F8, VARS_LOOKUP);

// F9: an investigative question with NO investigation block — the CURRENT
// single-shot backend behavior. Must fail, proving the gate blocks pre-loop code.
const F9 = clone(GOOD_INVESTIGATIVE); delete F9.investigation;
expectFail('F9 investigative but no investigation block', 'intentStatus', F9, VARS_INVESTIGATIVE);

// F10: floor corrupted — wrong metric.
const F10 = clone(GOOD_INVESTIGATIVE); F10.metric = 'total_gross_revenue';
expectFail('F10 wrong floor metric', 'baseFloor', F10, VARS_INVESTIGATIVE);

console.log(`\n=== ${failures === 0 ? 'NON-VACUITY HOLDS: all good pass, all fabrications fail' : failures + ' EXPECTATION(S) VIOLATED'} ===\n`);
process.exit(failures === 0 ? 0 : 1);
