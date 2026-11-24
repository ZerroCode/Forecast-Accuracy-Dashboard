// Both workflows publish overlapping comparisons. Choose one whole snapshot.
const verificationDirectory = new URL("../data/verification/", import.meta.url);
const workflows = ["daily", "market"];

function isUsableGroup(group) {
  if (!group || typeof group.station_id !== "string" || typeof group.cohort !== "string" ||
      typeof group.outcome_source !== "string" || !["high", "low"].includes(group.metric) ||
      !Number.isInteger(group.common_cases) || !Number.isInteger(group.distinct_dates)) return false;
  if (group.status === "insufficient_common_history") return true;
  return group.status === "scored" && Array.isArray(group.metrics) && group.metrics.length > 0 &&
    group.metrics.every(row => typeof row?.provider === "string" && Number.isFinite(row.mae_f) &&
      Number.isFinite(row.bias_f));
}

export async function loadLatestReport(directory = verificationDirectory) {
  const results = await Promise.allSettled(workflows.map(async (workflow) => {
    const url = new URL(`${workflow}/accuracy.json`, directory);
    const response = await fetch(url, { cache: "no-cache" });
    if (!response.ok) throw new Error(`${workflow} report returned HTTP ${response.status}`);
    const report = await response.json();
    const timestamp = Date.parse(report?.generated_at_utc);
    if (report?.schema_version !== 1 || typeof report.generated_at_utc !== "string" || !Number.isFinite(timestamp) ||
        !Array.isArray(report.groups) || !report.groups.every(isUsableGroup) || !Array.isArray(report.excluded_providers) ||
        !["complete", "partial"].includes(report.status) ||
        !["available", "insufficient_common_history", "blocked_by_unreadable_archive"].includes(report.ranking_status)) {
      throw new Error(`Invalid or unsupported ${workflow} accuracy report`);
    }
    return { workflow, report, timestamp };
  }));

  let latest;
  const unavailableWorkflows = [];
  for (const [index, result] of results.entries()) {
    if (result.status === "rejected") {
      unavailableWorkflows.push(workflows[index]);
    } else if (!latest || result.value.timestamp > latest.timestamp) {
      latest = result.value;
    }
  }
  if (!latest) {
    throw new AggregateError(results.map(result => result.reason), "Neither published accuracy report is available.");
  }
  return { workflow: latest.workflow, report: latest.report, unavailableWorkflows };
}

export function getComparison(report, { stationId = "all", metric, cohort, outcomeSource }) {
  if (!stationId || !["high", "low"].includes(metric) || !cohort || !outcomeSource) {
    throw new TypeError("Select a station, high or low, capture window, and outcome source.");
  }
  const group = report.groups.find(row => row.station_id === stationId && row.metric === metric &&
    row.cohort === cohort && row.outcome_source === outcomeSource);
  const comparison = {
    reportStatus: report.status,
    excludedProviders: report.excluded_providers,
    scores: [],
  };
  if (report.ranking_status === "blocked_by_unreadable_archive") {
    return { ...comparison, status: "blocked", message: "An unreadable archive prevents comparison." };
  }
  comparison.commonCases = group?.common_cases ?? 0;
  comparison.distinctDates = group?.distinct_dates ?? 0;
  if (group?.status !== "scored") {
    return { ...comparison, status: "pending", message: "Waiting for more comparable dates." };
  }
  return {
    ...comparison,
    status: "scored",
    scores: [...group.metrics].sort((a, b) => a.mae_f - b.mae_f || a.provider.localeCompare(b.provider)),
  };
}
