import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Live Traces" },
  { to: "/traces", label: "Trace History" },
  { to: "/evals", label: "Evaluations" },
  { to: "/admin", label: "Admin" },
];

export function Sidebar() {
  return (
    <aside className="w-48 min-h-screen bg-gray-900 border-r border-gray-800 flex flex-col pt-6 shrink-0">
      <div className="px-4 mb-8">
        <span className="text-brand-500 font-bold text-sm tracking-widest uppercase">
          AgentObs
        </span>
      </div>
      <nav className="flex flex-col gap-1 px-2">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === "/"}
            className={({ isActive }) =>
              `px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? "bg-brand-700 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-100"
              }`
            }
          >
            {l.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
