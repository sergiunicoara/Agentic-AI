interface HeaderProps {
  email: string | null;
  role: string | null;
  onLogout: () => void;
}

export function Header({ email, role, onLogout }: HeaderProps) {
  return (
    <header className="h-12 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-6 shrink-0">
      <span className="text-xs text-gray-500 uppercase tracking-wider">
        Agent Observability Dashboard
      </span>
      <div className="flex items-center gap-4 text-xs">
        <span className="text-gray-400">
          {email}{" "}
          <span className="ml-1 px-1.5 py-0.5 rounded bg-brand-900 text-brand-500 font-medium">
            {role}
          </span>
        </span>
        <button
          onClick={onLogout}
          className="text-gray-500 hover:text-red-400 transition-colors"
        >
          Logout
        </button>
      </div>
    </header>
  );
}
