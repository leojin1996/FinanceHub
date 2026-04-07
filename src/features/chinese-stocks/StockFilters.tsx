interface StockFiltersProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSectorChange: (value: string) => void;
  label: string;
  placeholder: string;
  sectorLabel: string;
  sectors: string[];
  selectedSector: string;
}

export function StockFilters({
  query,
  onQueryChange,
  onSectorChange,
  label,
  placeholder,
  sectorLabel,
  sectors,
  selectedSector,
}: StockFiltersProps) {
  return (
    <section className="panel stock-filters">
      <div className="stock-filters__search">
        <label className="stock-filters__label" htmlFor="stock-filter-input">
          {label}
        </label>
        <input
          className="stock-filters__input"
          id="stock-filter-input"
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={placeholder}
          type="search"
          value={query}
        />
      </div>
      <div aria-label={sectorLabel} className="stock-filters__rail" role="group">
        <span className="stock-filters__rail-label">{sectorLabel}</span>
        <div className="stock-filters__chips">
          {sectors.map((sector) => {
            const isActive = selectedSector === sector;

            return (
              <button
                aria-pressed={isActive}
                className={`stock-filters__chip${isActive ? " is-active" : ""}`}
                key={sector}
                onClick={() => onSectorChange(sector)}
                type="button"
              >
                {sector}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
