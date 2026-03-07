import { TraceViewer } from "../components/TraceViewer/TraceViewer";
import { TokenUsageChart } from "../components/TokenUsageChart";
import { LatencyChart } from "../components/LatencyChart";
import { TaskOutcomes } from "../components/TaskOutcomes";

export function LivePage() {
  return (
    <div className="flex flex-col gap-6 h-full">
      <TaskOutcomes />
      <div className="grid grid-cols-2 gap-4">
        <TokenUsageChart />
        <LatencyChart />
      </div>
      <div className="flex-1 min-h-0">
        <TraceViewer />
      </div>
    </div>
  );
}
