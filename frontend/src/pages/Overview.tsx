export default function Overview() {
  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-ink-900 mb-6">Overview Dashboard</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total Incidents", value: "12", color: "text-blue-600" },
          { label: "Active Incidents", value: "7", color: "text-blue-600" },
          { label: "Under Investigation", value: "4", color: "text-slick-500" },
          { label: "Critical Alerts", value: "3", color: "text-alert-500" },
        ].map((stat, i) => (
          <div key={i} className="bg-white p-6 rounded-lg border border-ink-200 shadow-sm flex flex-col">
            <span className="text-sm font-medium text-ink-500">{stat.label}</span>
            <span className={`text-3xl font-bold mt-2 ${stat.color}`}>{stat.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
