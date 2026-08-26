import { Search, Bell, Settings, User } from "lucide-react";

export default function Topbar() {
  return (
    <header className="h-16 bg-white border-b border-ink-200 flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-tight text-ink-900 flex items-center gap-2">
          <span className="text-blue-600">
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
          </span>
          SpillTrace
        </h1>
        <span className="text-xs text-ink-500 hidden sm:inline-block border-l border-ink-300 pl-4 ml-2">
          AI-Powered Maritime Intelligence
        </span>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
          <input
            type="text"
            placeholder="Search anything..."
            className="pl-9 pr-4 py-1.5 bg-ink-50 border border-ink-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-64"
          />
        </div>
        
        <div className="flex items-center gap-2 border-l border-ink-200 pl-4 ml-2">
          <button className="p-2 text-ink-500 hover:text-ink-900 rounded-full hover:bg-ink-100 transition-colors">
            <Bell className="w-5 h-5" />
          </button>
          <button className="p-2 text-ink-500 hover:text-ink-900 rounded-full hover:bg-ink-100 transition-colors">
            <Settings className="w-5 h-5" />
          </button>
          <button className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-medium ml-2">
            A
          </button>
        </div>
      </div>
    </header>
  );
}
