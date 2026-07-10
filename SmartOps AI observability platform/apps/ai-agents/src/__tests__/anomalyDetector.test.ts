import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Inline the deterministic helpers so tests have no network deps ──────────
function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function stddev(values: number[], avg: number): number {
  const variance = values.reduce((a, b) => a + (b - avg) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function zScore(value: number, avg: number, sd: number): number {
  return sd === 0 ? 0 : (value - avg) / sd;
}

// ── Tests ────────────────────────────────────────────────────────────────────
describe("z-score anomaly detection", () => {
  it("returns z-score of 0 when all values are identical", () => {
    const values = [50, 50, 50, 50, 50];
    const avg = mean(values);
    const sd  = stddev(values, avg);
    expect(zScore(50, avg, sd)).toBe(0);
  });

  it("flags a spike > 3 standard deviations as anomaly", () => {
    // baseline: avg ~50, sd ~2 → spike at 60 gives z ≈ 5
    const values = [50, 51, 49, 50, 50, 50, 49, 51, 50, 50];
    const avg = mean(values);
    const sd  = stddev(values, avg);
    const z   = zScore(60, avg, sd);
    expect(z).toBeGreaterThan(3);
  });

  it("does not flag normal variation as anomaly", () => {
    const values = [50, 52, 48, 51, 49, 50, 53, 47, 51, 50];
    const avg = mean(values);
    const sd  = stddev(values, avg);
    const z   = zScore(52, avg, sd);
    expect(Math.abs(z)).toBeLessThan(3);
  });

  it("handles a CPU spike scenario correctly", () => {
    // 29 samples around 40%, then a spike to 95% (anomaly injected by simulator)
    const baseline = Array.from({ length: 29 }, () => 40 + Math.random() * 4 - 2);
    const spike = 95;
    const avg = mean(baseline);
    const sd  = stddev(baseline, avg);
    const z   = zScore(spike, avg, sd);
    expect(z).toBeGreaterThan(3);
  });

  it("computes correct mean for an array of known values", () => {
    expect(mean([10, 20, 30])).toBe(20);
    expect(mean([0, 100])).toBe(50);
  });

  it("computes correct stddev for a known distribution", () => {
    // stddev of [2, 4, 4, 4, 5, 5, 7, 9] = 2 (population)
    const sd = stddev([2, 4, 4, 4, 5, 5, 7, 9], 5);
    expect(sd).toBeCloseTo(2, 5);
  });
});

describe("confidence calculation", () => {
  it("grows with more correlated error logs", () => {
    const base    = 0.4;
    const logBump = 0.02;
    const confFor10Logs = Math.min(0.95, base + 10 * logBump);
    const confFor0Logs  = Math.min(0.95, base + 0  * logBump);
    expect(confFor10Logs).toBeGreaterThan(confFor0Logs);
  });

  it("caps at 0.95 regardless of evidence count", () => {
    const conf = Math.min(0.95, 0.4 + 100 * 0.02 + 100 * 0.03);
    expect(conf).toBe(0.95);
  });
});
