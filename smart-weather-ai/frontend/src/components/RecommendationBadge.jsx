const ITEMS = [
  { key: "need_umbrella", label: "Paraguas", icon: "☂️" },
  { key: "need_jacket", label: "Chamarra", icon: "🧥" },
  { key: "need_sunscreen", label: "Protector solar", icon: "🧴" },
];

export default function RecommendationBadge({ recommendations }) {
  if (!recommendations) return null;

  const active = ITEMS.filter((item) => recommendations[item.key]);

  return (
    <section className="card p-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-xl" aria-hidden="true">
          {active.length ? "💡" : "✅"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="card-title">Recomendación</p>
          <p className="mt-1 text-sm font-medium text-slate-800">
            {recommendations.summary ||
              (active.length
                ? "Toma precauciones para salir"
                : "No necesitas precauciones especiales")}
          </p>

          {active.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {active.map((item) => (
                <span
                  key={item.key}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600"
                >
                  <span aria-hidden="true">{item.icon}</span>
                  {item.label}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
