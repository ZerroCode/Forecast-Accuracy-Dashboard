import assert from "node:assert/strict";
import test from "node:test";
import { getComparison, loadLatestReport } from "../src/public_reports.mjs";

const selection = { metric: "high", cohort: "daily_late", outcomeSource: "kalshi_settlement:The Weather Company" };
const group = {
  station_id: "all", metric: "high", cohort: "daily_late", outcome_source: selection.outcomeSource,
  common_cases: 18, distinct_dates: 5, status: "scored",
  metrics: [
    { provider: "open_meteo", mae_f: 2, bias_f: -1 },
    { provider: "nws", mae_f: 0, bias_f: 0 },
  ],
};

function report(time, overrides = {}) {
  return {
    schema_version: 1, generated_at_utc: time, status: "complete", ranking_status: "available",
    excluded_providers: [], groups: [group], ...overrides,
  };
}

function serve(t, daily, market) {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.pathname.endsWith("/daily/accuracy.json")) return daily.clone();
    if (url.pathname.endsWith("/market/accuracy.json")) return market.clone();
    throw new Error(`Unexpected file ${url.pathname}`);
  });
}

const older = "2026-11-23T12:00:00Z";
const newer = "2026-11-23T13:00:00Z";

test("the newest report wins, including a partial report with a smaller roster", async t => {
  const partial = report(newer, { status: "partial", excluded_providers: ["visual_crossing"] });
  const fullGroup = { ...group, metrics: [...group.metrics, { provider: "visual_crossing", mae_f: 1, bias_f: -1 }] };
  serve(t, Response.json(report(older, { groups: [fullGroup] })), Response.json(partial));
  const latest = await loadLatestReport();
  assert.equal(latest.workflow, "market");
  assert.deepEqual(latest.unavailableWorkflows, []);
  assert.deepEqual(latest.report, partial);
  const comparison = getComparison(latest.report, selection);
  assert.equal(comparison.reportStatus, "partial");
  assert.deepEqual(comparison.excludedProviders, ["visual_crossing"]);
  assert.equal(comparison.status, "scored");
  assert.equal(comparison.commonCases, 18);
  assert.equal(comparison.distinctDates, 5);
  assert.deepEqual(comparison.scores, [...group.metrics].reverse());
});

test("daily wins when newer and when timestamps tie", async t => {
  for (const marketTime of [older, newer]) {
    await t.test(marketTime, async t => {
      serve(t, Response.json(report(newer)), Response.json(report(marketTime)));
      assert.equal((await loadLatestReport()).workflow, "daily");
    });
  }
});

test("one unusable publication is identified and two unusable publications fail", async t => {
  for (const invalid of [new Response("missing", { status: 404 }), new Response("{"),
    Response.json(report("bad timestamp")), Response.json(report(newer, { schema_version: 2 }))]) {
    await t.test(async t => {
      serve(t, invalid, Response.json(report(older)));
      const latest = await loadLatestReport();
      assert.equal(latest.workflow, "market");
      assert.deepEqual(latest.unavailableWorkflows, ["daily"]);
    });
  }
  serve(t, new Response("", { status: 503 }), new Response("", { status: 404 }));
  await assert.rejects(loadLatestReport(), /Neither published accuracy report is available/);
});

test("only the exact station, metric, window and outcome source can supply scores", () => {
  const pending = { ...group, station_id: "nyc_central_park", status: "insufficient_common_history",
    common_cases: 4, distinct_dates: 4, metrics: [{ provider: "nws", mae_f: null, bias_f: null }] };
  const snapshot = report(newer, { groups: [group, pending] });
  for (const change of [{ stationId: pending.station_id }, { metric: "low" },
    { cohort: "market_near_open" }, { outcomeSource: "noaa_ncei_daily_summaries" }]) {
    const comparison = getComparison(snapshot, { ...selection, ...change });
    assert.equal(comparison.status, "pending");
    assert.equal(comparison.message, "Waiting for more comparable dates.");
    assert.equal(comparison.distinctDates, change.stationId ? 4 : 0);
    assert.deepEqual(comparison.scores, []);
  }
});

test("a malformed scored group falls back to the other publication", async t => {
  for (const metrics of [null, [null], [{ provider: "nws", mae_f: null, bias_f: 0 }]]) {
    await t.test(async t => {
      serve(t, Response.json(report(older)), Response.json(report(newer, { groups: [{ ...group, metrics }] })));
      const latest = await loadLatestReport();
      assert.deepEqual(latest.unavailableWorkflows, ["market"]);
      assert.equal(latest.workflow, "daily");
      assert.equal(getComparison(latest.report, selection).status, "scored");
    });
  }
});

test("a newer blocked snapshot takes precedence over older published scores", async t => {
  serve(t, Response.json(report(newer, {
    status: "partial", ranking_status: "blocked_by_unreadable_archive", groups: [],
  })), Response.json(report(older)));
  const comparison = getComparison((await loadLatestReport()).report, selection);
  assert.equal(comparison.status, "blocked");
  assert.deepEqual(comparison.scores, []);
});
