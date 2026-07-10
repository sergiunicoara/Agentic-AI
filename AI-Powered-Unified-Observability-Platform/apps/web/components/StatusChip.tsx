import clsx from "clsx";

type Variant = "active" | "inactive" | "maintenance" | "decommissioned" | "critical" | "warning" | "info" | "pending" | "ticketed" | "rejected" | "approved";

const MAP: Record<Variant, string> = {
  active:          "bg-green-950 text-green-400 border-green-900",
  inactive:        "bg-gray-800 text-gray-400 border-gray-700",
  maintenance:     "bg-amber-950 text-amber-400 border-amber-900",
  decommissioned:  "bg-red-950/60 text-red-500 border-red-900/60",
  critical:        "bg-red-950 text-red-400 border-red-900",
  warning:         "bg-amber-950 text-amber-400 border-amber-900",
  info:            "bg-blue-950 text-blue-400 border-blue-900",
  pending:         "bg-purple-950 text-purple-400 border-purple-900",
  ticketed:        "bg-green-950 text-green-400 border-green-900",
  rejected:        "bg-gray-800 text-gray-500 border-gray-700",
  approved:        "bg-blue-950 text-blue-400 border-blue-900",
};

interface Props {
  value: string;
  variant?: Variant;
}

export default function StatusChip({ value, variant }: Props) {
  const v = (variant ?? value) as Variant;
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border", MAP[v] ?? MAP.info)}>
      {value}
    </span>
  );
}
