import { describe, it, expect } from "vitest";

// ── Inline the pure functions from forecastingAgent ───────────────────────
function linearTrend(points: { x: number; y: number }[]): { slope: number; intercept: number } {
  const n    = points.length;
  const sumX  = points.reduce((a, p) => a + p.x, 0);
  const sumY  = points.reduce((a, p) => a + p.y, 0);
  const sumXY = points.reduce((a, p) => a + p.x * p.y, 0);
  const sumX2 = points.reduce((a, p) => a + p.x * p.x, 0);
  const slope     = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX || 1);
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function hoursToSaturation(slope: number, intercept: number, currentX: number, saturation = 100): number | null {
  if (slope <= 0.01) return null;
  const hoursAtSaturation = (saturation - intercept) / slope;
  return Math.max(0, hoursAtSaturation - currentX);
}

// ── Tests ─────────────────────────────────────────────────────────────────
describe("linearTrend", () => {
  it("returns slope=0 for flat data", () => {
    const points = [0, 1, 2, 3, 4].map((x) => ({ x, y: 50 }));
    const { slope } = linearTrend(points);
    expect(slope).toBeCloseTo(0, 5);
  });

  it("returns slope=1 for y=x data", () => {
    const points = [1, 2, 3, 4, 5].map((x) => ({ x, y: x }));
    const { slope } = linearTrend(points);
    expect(slope).toBeCloseTo(1, 5);
  });

  it("returns negative slope for decreasing data", () => {
    const points = [0, 1, 2, 3, 4].map((x) => ({ x, y: 100 - x * 10 }));
    const { slope } = linearTrend(points);
    expect(slope).toBeLessThan(0);
  });

  it("handles single-point degenerate case without throwing", () => {
    const { slope } = linearTrend([{ x: 0, y: 50 }]);
    expect(isFinite(slope)).toBe(true);
  });

  it("correctly identifies a steep upward trend", () => {
    // CPU growing 5% per hour over 24 hours
    const points = Array.from({ length: 24 }, (_, i) => ({ x: i, y: 20 + i * 5 }));
    const { slope } = linearTrend(points);
    expect(slope).toBeCloseTo(5, 1);
  });
});

describe("hoursToSaturation", () => {
  it("returns null for flat/negative slope", () => {
    expect(hoursToSaturation(0, 50, 24)).toBeNull();
    expect(hoursToSaturation(-1, 50, 24)).toBeNull();
  });

  it("calculates time correctly for known linear growth", () => {
    // intercept=20, slope=5 → saturation at x=16h, currently at x=0 → 16h to go
    const hours = hoursToSaturation(5, 20, 0);
    expect(hours).toBeCloseTo(16, 1);
  });

  it("returns 0 (not negative) when already past saturation", () => {
    // slope=5, intercept=20, currently at x=20h (already past saturation at x=16)
    const hours = hoursToSaturation(5, 20, 20);
    expect(hours).toBe(0);
  });

  it("accounts for elapsed time correctly", () => {
    // If total hours to saturation from t=0 is 16, and we're at t=10, expect ~6
    const hours = hoursToSaturation(5, 20, 10);
    expect(hours).toBeCloseTo(6, 1);
  });
});
