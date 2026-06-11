export default function Loading() {
  return (
    <div className="space-y-8 animate-pulse">
      {/* Page header */}
      <div className="space-y-2">
        <div className="h-8 w-48 bg-forge-elevated rounded-lg" />
        <div className="h-4 w-96 bg-forge-elevated rounded" />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card p-5 space-y-3">
            <div className="h-4 w-24 bg-forge-elevated rounded" />
            <div className="h-8 w-20 bg-forge-elevated rounded" />
          </div>
        ))}
      </div>

      {/* Chart skeleton */}
      <div className="card p-6">
        <div className="h-5 w-32 bg-forge-elevated rounded mb-4" />
        <div className="h-64 bg-forge-elevated rounded-lg" />
      </div>

      {/* Table skeleton */}
      <div className="card p-6 space-y-3">
        <div className="h-5 w-40 bg-forge-elevated rounded mb-4" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 bg-forge-elevated rounded" />
        ))}
      </div>
    </div>
  );
}
