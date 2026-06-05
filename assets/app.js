const DATA_PATHS = {
  index: "data/processed/tokyo_livability_index.csv",
  estat: "data/raw/estat_data.csv",
  spatial: "data/raw/spatial_data.csv",
  crime: "data/raw/crime_data.csv",
  poi: "data/raw/osm_poi_data.csv",
  area: "data/raw/area_data.csv",
  geojson: "data/raw/gis/tokyo_23wards.geojson",
};

const SCORE_METRICS = [
  {
    key: "score_accessibility",
    weightKey: "accessibility",
    label: "アクセス",
    detailLabel: "交通アクセス",
    positive: "人口あたりの駅・路線が多い",
    caution: "人口あたりの駅・路線は控えめ",
  },
  {
    key: "score_safety",
    weightKey: "safety",
    label: "治安",
    detailLabel: "治安",
    positive: "人口あたりの犯罪件数が少ない",
    caution: "犯罪件数は要確認",
  },
  {
    key: "score_convenience",
    weightKey: "convenience",
    label: "生活利便性",
    detailLabel: "生活利便性",
    positive: "生活施設が多い",
    caution: "生活施設は控えめ",
  },
  {
    key: "score_resilience",
    weightKey: "resilience",
    label: "避難所",
    detailLabel: "避難所",
    positive: "人口あたりの避難所が多い",
    caution: "人口あたりの避難所は控えめ",
  },
];

const PRESETS = {
  balanced: [],
  safety: ["safety", "resilience", "convenience", "accessibility"],
  access: ["accessibility", "convenience", "safety", "resilience"],
  convenience: ["convenience", "accessibility", "safety", "resilience"],
  resilience: ["resilience", "safety", "accessibility", "convenience"],
};

const MOBILE_RANKING_LIMIT = 4;
const mobileRankingQuery = window.matchMedia("(max-width: 640px)");

const state = {
  rows: [],
  geojson: null,
  priority: [...PRESETS.balanced],
  compareCodes: [],
  selectedCode: null,
  isRankingExpanded: false,
};

const elements = {
  advancedSettingsPanel: document.querySelector("#advanced-settings-panel"),
  advancedSettingsToggle: document.querySelector("#advanced-settings-toggle"),
  priorityBuilder: document.querySelector("#priority-builder"),
  rankingList: document.querySelector("#ranking-list"),
  resultCount: document.querySelector("#result-count"),
  sortMode: document.querySelector("#sort-mode"),
  mapMetric: document.querySelector("#map-metric"),
  wardMap: document.querySelector("#ward-map"),
  mapTooltip: document.querySelector("#map-tooltip"),
  compareContent: document.querySelector("#compare-content"),
  clearCompare: document.querySelector("#clear-compare"),
  drawer: document.querySelector("#detail-drawer"),
  drawerContent: document.querySelector("#drawer-content"),
};

function parseCsv(text) {
  const cleanText = text.replace(/^\uFEFF/, "").trim();
  if (!cleanText) {
    return [];
  }

  const [headerLine, ...lines] = cleanText.split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines.map((line) => {
    const values = line.split(",");
    return headers.reduce((row, header, index) => {
      row[header] = values[index] ?? "";
      return row;
    }, {});
  });
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ja-JP").format(Math.round(value));
}

function formatDecimal(value, digits = 1) {
  return Number(value).toFixed(digits);
}

function perCapitaRate(count, population, scale) {
  return population > 0 ? (count / population) * scale : 0;
}

function densityPerKm2(count, areaKm2) {
  return areaKm2 > 0 ? count / areaKm2 : 0;
}

function metricByKey(key) {
  return SCORE_METRICS.find((metric) => metric.key === key);
}

function availableScoreMetrics(row = state.rows[0]) {
  if (!row) {
    return SCORE_METRICS;
  }
  return SCORE_METRICS.filter((metric) => Number.isFinite(row[metric.key]));
}

async function loadData() {
  const { indexText, estatText, spatialText, crimeText, poiText, areaText, geojson } =
    await loadSourceData();

  const estatByCode = Object.fromEntries(parseCsv(estatText).map((row) => [row.code, row]));
  const spatialByCode = Object.fromEntries(parseCsv(spatialText).map((row) => [row.code, row]));
  const crimeByCode = Object.fromEntries(parseCsv(crimeText).map((row) => [row.code, row]));
  const poiByCode = Object.fromEntries(parseCsv(poiText).map((row) => [row.code, row]));
  const areaByCode = Object.fromEntries(parseCsv(areaText).map((row) => [row.code, row]));

  state.rows = parseCsv(indexText).map((row) => {
    const merged = {
      ...row,
      ...estatByCode[row.code],
      ...spatialByCode[row.code],
      ...crimeByCode[row.code],
      ...poiByCode[row.code],
      ...areaByCode[row.code],
      ward_name: row.ward_name,
    };

    [
      "population",
      "ward_area_km2",
      "score_accessibility",
      "score_safety",
      "score_convenience",
      "score_resilience",
      "station_count",
      "line_count",
      "shelter_count",
      "total_crime_cases",
      "serious_crime_cases",
      "violent_crime_cases",
      "theft_crime_cases",
      "other_crime_cases",
      "convenience_count",
      "supermarket_count",
      "medical_facility_count",
      "daily_facility_count",
    ].forEach((key) => {
      merged[key] = toNumber(merged[key]);
    });

    merged.crime_rate_per_1000 = perCapitaRate(
      merged.total_crime_cases,
      merged.population,
      1000,
    );
    merged.serious_crime_rate_per_10000 = perCapitaRate(
      merged.serious_crime_cases,
      merged.population,
      10000,
    );
    merged.shelter_rate_per_10000 = perCapitaRate(
      merged.shelter_count,
      merged.population,
      10000,
    );
    merged.station_density = densityPerKm2(merged.station_count, merged.ward_area_km2);
    merged.line_density = densityPerKm2(merged.line_count, merged.ward_area_km2);
    merged.daily_facility_density = densityPerKm2(
      merged.daily_facility_count,
      merged.ward_area_km2,
    );

    return merged;
  });

  state.geojson = geojson;
}

async function loadSourceData() {
  try {
    const [indexText, estatText, spatialText, crimeText, poiText, areaText, geojson] =
      await Promise.all([
        fetchText(DATA_PATHS.index),
        fetchText(DATA_PATHS.estat),
        fetchText(DATA_PATHS.spatial),
        fetchText(DATA_PATHS.crime),
        fetchText(DATA_PATHS.poi),
        fetchText(DATA_PATHS.area),
        fetchJson(DATA_PATHS.geojson),
      ]);

    return { indexText, estatText, spatialText, crimeText, poiText, areaText, geojson };
  } catch (error) {
    if (window.TOKYO_LIVABILITY_EMBEDDED_DATA) {
      console.info("Using embedded data fallback.", error);
      return window.TOKYO_LIVABILITY_EMBEDDED_DATA;
    }

    throw error;
  }
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.text();
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json();
}

function calculatePersonalizedScore(row) {
  const metrics = availableScoreMetrics(row);
  const activeMetrics =
    state.priority.length === 0
      ? metrics
      : state.priority
          .map((weightKey) => metrics.find((metric) => metric.weightKey === weightKey))
          .filter(Boolean);
  const weightTotal = activeMetrics.reduce((sum, _metric, index) => {
    return sum + (activeMetrics.length - index);
  }, 0);

  if (weightTotal === 0) {
    return 0;
  }

  return activeMetrics.reduce((sum, metric, index) => {
    const priorityWeight = activeMetrics.length - index;
    return sum + row[metric.key] * priorityWeight;
  }, 0) / weightTotal;
}

function enrichRows() {
  const ranks = buildRanks(state.rows);
  state.rows.forEach((row) => {
    row.personalizedScore = calculatePersonalizedScore(row);
    row.strengths = getStrengths(row, ranks);
    row.cautions = getCautions(row, ranks);
  });
}

function buildRanks(rows) {
  const rankDefinitions = {
    stationCount: { key: "station_count", direction: "desc" },
    lineCount: { key: "line_count", direction: "desc" },
    totalCrime: { key: "crime_rate_per_1000", direction: "asc" },
    seriousCrime: { key: "serious_crime_rate_per_10000", direction: "asc" },
    supermarket: { key: "supermarket_count", direction: "desc" },
    medical: { key: "medical_facility_count", direction: "desc" },
    dailyFacility: { key: "daily_facility_count", direction: "desc" },
    shelter: { key: "shelter_rate_per_10000", direction: "desc" },
  };

  return Object.fromEntries(
    Object.entries(rankDefinitions).map(([name, definition]) => {
      const sortedRows = [...rows].sort((a, b) => {
        const diff = a[definition.key] - b[definition.key];
        return definition.direction === "asc" ? diff : -diff;
      });
      return [
        name,
        Object.fromEntries(sortedRows.map((row, index) => [row.code, index + 1])),
      ];
    }),
  );
}

function getStrengths(row, ranks) {
  const detailCandidates = [
    { label: "駅が多い", softLabel: "駅数は比較的多め", rank: ranks.stationCount[row.code] },
    { label: "路線が多い", softLabel: "路線数は比較的多め", rank: ranks.lineCount[row.code] },
    { label: "犯罪率が低い", softLabel: "犯罪率は比較的低め", rank: ranks.totalCrime[row.code] },
    {
      label: "重大犯罪率が低い",
      softLabel: "重大犯罪率は比較的低め",
      rank: ranks.seriousCrime[row.code],
    },
    {
      label: "スーパーが多い",
      softLabel: "スーパーは比較的多め",
      rank: ranks.supermarket[row.code],
    },
    {
      label: "医療施設が多い",
      softLabel: "医療施設は比較的多め",
      rank: ranks.medical[row.code],
    },
    {
      label: "日常施設が多い",
      softLabel: "日常施設は比較的多め",
      rank: ranks.dailyFacility[row.code],
    },
    {
      label: "避難所が多い",
      softLabel: "避難所は比較的多め",
      rank: ranks.shelter[row.code],
    },
  ];

  const detailedStrengths = detailCandidates
    .filter((strength) => strength.rank <= 5)
    .map((strength) => strength.label);
  const relativeStrengths = detailCandidates
    .filter((strength) => strength.rank > 5 && strength.rank <= 12)
    .sort((a, b) => a.rank - b.rank)
    .map((strength) => strength.softLabel);
  const scoreStrengths = availableScoreMetrics(row)
    .sort((a, b) => row[b.key] - row[a.key])
    .filter((metric) => row[metric.key] >= 75)
    .map((metric) => metric.positive);

  return uniqueList([...detailedStrengths, ...scoreStrengths, ...relativeStrengths]).slice(
    0,
    4,
  );
}

function getCautions(row, ranks) {
  const detailedCautions = [
    { label: "駅数は少なめ", active: ranks.stationCount[row.code] >= 19 },
    { label: "路線数は少なめ", active: ranks.lineCount[row.code] >= 19 },
    { label: "犯罪率は要確認", active: ranks.totalCrime[row.code] >= 19 },
    { label: "スーパー少なめ", active: ranks.supermarket[row.code] >= 19 },
    { label: "医療施設少なめ", active: ranks.medical[row.code] >= 19 },
    { label: "避難所少なめ", active: ranks.shelter[row.code] >= 19 },
  ]
    .filter((caution) => caution.active)
    .map((caution) => caution.label);
  const scoreCautions = availableScoreMetrics(row)
    .sort((a, b) => row[a.key] - row[b.key])
    .filter((metric) => row[metric.key] < 45)
    .map((metric) => metric.caution);

  return uniqueList([...detailedCautions, ...scoreCautions]).slice(0, 4);
}

function uniqueList(items) {
  return [...new Set(items)];
}

function getFilteredRows() {
  const sortMode = elements.sortMode.value;
  return [...state.rows].sort((a, b) => {
    if (sortMode === "safety") {
      return b.score_safety - a.score_safety;
    }
    if (sortMode === "accessibility") {
      return b.score_accessibility - a.score_accessibility;
    }
    if (sortMode === "convenience") {
      return b.score_convenience - a.score_convenience;
    }
    if (sortMode === "resilience") {
      return b.score_resilience - a.score_resilience;
    }
    return b.personalizedScore - a.personalizedScore;
  });
}

function renderPriorityBuilder() {
  const selectedKeys = new Set(state.priority);
  elements.priorityBuilder.innerHTML = `
    <div class="condition-picker" role="group" aria-label="詳細設定の観点">
      ${availableScoreMetrics()
        .map(
          (metric) => `
            <button
              class="condition-chip ${selectedKeys.has(metric.weightKey) ? "active" : ""}"
              type="button"
              data-condition="${metric.weightKey}"
              aria-pressed="${selectedKeys.has(metric.weightKey)}"
            >
              ${metric.label}
            </button>
          `,
        )
        .join("")}
    </div>
    <div class="priority-list-wrap">
      <div class="priority-list-heading">
        <span>優先順位</span>
        <small>選んだ観点だけを並べます。未選択時は全観点を均等に見ます。</small>
      </div>
      <div class="priority-list" id="priority-list"></div>
    </div>
  `;

  const priorityList = elements.priorityBuilder.querySelector("#priority-list");
  const template = document.querySelector("#priority-template");
  if (state.priority.length === 0) {
    priorityList.innerHTML =
      '<div class="priority-empty">まだ重視軸を選んでいません。全観点を均等に見ておすすめ度を計算しています。</div>';
    return;
  }

  state.priority.forEach((weightKey, index) => {
    const metric = availableScoreMetrics().find((item) => item.weightKey === weightKey);
    if (!metric) {
      return;
    }

    const fragment = template.content.cloneNode(true);
    const item = fragment.querySelector(".priority-item");
    const rank = fragment.querySelector(".priority-rank");
    const label = fragment.querySelector(".priority-label");
    const upButton = fragment.querySelector('[data-direction="up"]');
    const downButton = fragment.querySelector('[data-direction="down"]');

    item.dataset.condition = weightKey;
    rank.textContent = `${index + 1}`;
    label.textContent = metric.label;
    upButton.disabled = index === 0;
    downButton.disabled = index === state.priority.length - 1;
    priorityList.append(fragment);
  });
}

function setActivePreset(presetName) {
  document.querySelectorAll(".preset-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.preset === presetName);
  });
}

function applyPreset(presetName) {
  state.priority = [...(PRESETS[presetName] ?? [])];
  state.isRankingExpanded = false;
  setActivePreset(presetName);
  renderPriorityBuilder();
  update();
}

function renderRanking() {
  const rows = getFilteredRows();
  const shouldLimitRows =
    mobileRankingQuery.matches &&
    !state.isRankingExpanded &&
    rows.length > MOBILE_RANKING_LIMIT;
  const visibleRows = shouldLimitRows ? rows.slice(0, MOBILE_RANKING_LIMIT) : rows;
  elements.resultCount.textContent = `${rows.length}区`;
  elements.rankingList.innerHTML = "";

  visibleRows.forEach((row, index) => {
    const card = document.createElement("article");
    card.className = "ward-card";
    card.classList.toggle("is-selected", row.code === state.selectedCode);
    card.innerHTML = `
      <div class="card-top">
        <div>
          <p class="rank-line">#${index + 1}</p>
          <h3>${row.ward_name}</h3>
        </div>
        <div class="score-pill">
          ${row.personalizedScore.toFixed(1)}
          <span>おすすめ度</span>
        </div>
      </div>
      <div class="tag-row">
        ${renderTags(row.strengths, "tag", "バランス型")}
        ${renderTags(row.cautions, "tag warning")}
      </div>
      <div class="mini-metrics">
        <div><span>治安</span><strong>${row.score_safety.toFixed(1)}</strong></div>
        <div><span>アクセス</span><strong>${row.score_accessibility.toFixed(1)}</strong></div>
        <div><span>避難所/万人</span><strong>${formatDecimal(row.shelter_rate_per_10000)}</strong></div>
      </div>
      <div class="card-actions">
        <button class="detail-button" type="button" data-detail="${row.code}">詳しく見る</button>
        <button class="compare-button ${state.compareCodes.includes(row.code) ? "active" : ""}" type="button" data-compare="${row.code}">
          ${state.compareCodes.includes(row.code) ? "比較中" : "比較に追加"}
        </button>
      </div>
    `;
    elements.rankingList.append(card);
  });

  if (mobileRankingQuery.matches && rows.length > MOBILE_RANKING_LIMIT) {
    const toggleButton = document.createElement("button");
    toggleButton.className = "ranking-toggle";
    toggleButton.type = "button";
    toggleButton.dataset.rankingToggle = "true";
    toggleButton.setAttribute(
      "aria-expanded",
      state.isRankingExpanded ? "true" : "false",
    );
    toggleButton.textContent = state.isRankingExpanded
      ? "表示を減らす"
      : `すべて表示（${rows.length}区）`;
    elements.rankingList.append(toggleButton);
  }
}

function renderTags(tags, className, emptyLabel = "") {
  if (tags.length === 0) {
    return emptyLabel ? `<span class="tag">${emptyLabel}</span>` : "";
  }
  return tags.map((tag) => `<span class="${className}">${tag}</span>`).join("");
}

function renderMap() {
  if (!state.geojson || state.rows.length === 0) {
    return;
  }

  const metric = elements.mapMetric.value;
  const features = state.geojson.features;
  const bounds = getGeoBounds(features);
  const width = 760;
  const height = 560;
  const padding = 24;
  const scale = Math.min(
    (width - padding * 2) / (bounds.maxX - bounds.minX),
    (height - padding * 2) / (bounds.maxY - bounds.minY),
  );
  const rowByCode = Object.fromEntries(state.rows.map((row) => [row.code, row]));

  elements.wardMap.setAttribute("viewBox", `0 0 ${width} ${height}`);
  elements.wardMap.innerHTML = "";

  features.forEach((feature) => {
    const code = String(feature.properties.code);
    const row = rowByCode[code];
    if (!row) {
      return;
    }

    const value = row[metric] ?? row.personalizedScore;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", geometryToPath(feature.geometry, bounds, scale, height, padding));
    path.setAttribute("fill", colorScale(value));
    path.classList.add("ward-shape");
    path.classList.toggle("is-selected", row.code === state.selectedCode);
    path.dataset.code = row.code;
    path.setAttribute("tabindex", "0");
    path.setAttribute("aria-label", `${row.ward_name} ${value.toFixed(1)}点`);

    path.addEventListener("mouseenter", (event) => showTooltip(event, row, metric));
    path.addEventListener("mousemove", (event) => positionTooltip(event));
    path.addEventListener("mouseleave", hideTooltip);
    path.addEventListener("click", () => openDrawer(row.code));
    elements.wardMap.append(path);
  });
}

function getGeoBounds(features) {
  const coordinates = features.flatMap((feature) => flattenCoordinates(feature.geometry.coordinates));
  const xs = coordinates.map(([x]) => x);
  const ys = coordinates.map(([, y]) => y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function flattenCoordinates(coordinates) {
  if (typeof coordinates[0] === "number") {
    return [coordinates];
  }
  return coordinates.flatMap((item) => flattenCoordinates(item));
}

function geometryToPath(geometry, bounds, scale, height, padding) {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons
    .map((polygon) => {
      return polygon
        .map((ring) => {
          return ring
            .map(([longitude, latitude], index) => {
              const x = (longitude - bounds.minX) * scale + padding;
              const y = height - ((latitude - bounds.minY) * scale + padding);
              return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
            })
            .join(" ")
            .concat(" Z");
        })
        .join(" ");
    })
    .join(" ");
}

function colorScale(value) {
  const clamped = Math.max(0, Math.min(100, value));
  const hue = 39 + (174 - 39) * (clamped / 100);
  const lightness = 88 - 48 * (clamped / 100);
  return `hsl(${hue} 48% ${lightness}%)`;
}

function showTooltip(event, row, metric) {
  const metricLabel =
    metric === "personalizedScore" ? "おすすめ度" : metricByKey(metric).label;
  const value = row[metric] ?? row.personalizedScore;
  elements.mapTooltip.hidden = false;
  elements.mapTooltip.innerHTML = `
    <strong>${row.ward_name}</strong><br>
    ${metricLabel}: ${value.toFixed(1)}<br>
    人口: ${formatNumber(row.population)}人<br>
    強み: ${row.strengths[0] ?? "バランス型"}
  `;
  positionTooltip(event);
}

function positionTooltip(event) {
  const rect = event.currentTarget.ownerSVGElement.getBoundingClientRect();
  elements.mapTooltip.style.left = `${event.clientX - rect.left + 14}px`;
  elements.mapTooltip.style.top = `${event.clientY - rect.top + 14}px`;
}

function hideTooltip() {
  elements.mapTooltip.hidden = true;
}

function renderCompare() {
  const rows = state.compareCodes
    .map((code) => state.rows.find((row) => row.code === code))
    .filter(Boolean);

  if (rows.length === 0) {
    elements.compareContent.className = "compare-empty";
    elements.compareContent.textContent = "比較したい区をランキングから追加してください。";
    return;
  }

  elements.compareContent.className = "compare-table-wrap";
  const metrics = [
    ["おすすめ度", "personalizedScore", "higher"],
    ["人口", "population", "higher", formatNumber],
    ["面積(km2)", "ward_area_km2", "higher", (value) => formatDecimal(value, 2)],
    ["駅数", "station_count", "higher", formatNumber],
    ["路線数", "line_count", "higher", formatNumber],
    ["犯罪/千人", "crime_rate_per_1000", "lower", (value) => formatDecimal(value, 2)],
    ["避難所/万人", "shelter_rate_per_10000", "higher", (value) => formatDecimal(value, 2)],
    ...availableScoreMetrics().map((metric) => [metric.label, metric.key, "higher"]),
  ];

  elements.compareContent.innerHTML = `
    <table class="compare-table">
      <thead>
        <tr>
          <th>比較項目</th>
          ${rows.map((row) => `<th>${row.ward_name}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${metrics
          .map(([label, key, direction, formatter]) => {
            const bestValue =
              direction === "lower"
                ? Math.min(...rows.map((row) => row[key]))
                : Math.max(...rows.map((row) => row[key]));
            return `
              <tr>
                <th>${label}</th>
                ${rows
                  .map((row) => {
                    const isWinner = row[key] === bestValue;
                    const value = formatter ? formatter(row[key]) : row[key].toFixed(1);
                    return `<td class="${isWinner ? "winner" : ""}">${value}</td>`;
                  })
                  .join("")}
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function toggleCompare(code) {
  if (state.compareCodes.includes(code)) {
    state.compareCodes = state.compareCodes.filter((item) => item !== code);
  } else {
    state.compareCodes = [...state.compareCodes, code].slice(-4);
  }
  update();
}

function toggleRankingExpansion() {
  state.isRankingExpanded = !state.isRankingExpanded;
  renderRanking();
}

function toggleCondition(weightKey) {
  if (state.priority.includes(weightKey)) {
    state.priority = state.priority.filter((item) => item !== weightKey);
  } else {
    state.priority = [...state.priority, weightKey];
  }
  state.isRankingExpanded = false;
  setActivePreset(null);
  renderPriorityBuilder();
  update();
}

function movePriority(weightKey, direction) {
  const currentIndex = state.priority.indexOf(weightKey);
  if (currentIndex === -1) {
    return;
  }

  if (direction === "remove") {
    toggleCondition(weightKey);
    return;
  }

  const nextIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
  if (nextIndex < 0 || nextIndex >= state.priority.length) {
    return;
  }

  const nextPriority = [...state.priority];
  [nextPriority[currentIndex], nextPriority[nextIndex]] = [
    nextPriority[nextIndex],
    nextPriority[currentIndex],
  ];
  state.priority = nextPriority;
  state.isRankingExpanded = false;
  setActivePreset(null);
  renderPriorityBuilder();
  update();
}

function syncPriorityFromInteraction(event) {
  const priorityButton = event.target.closest("[data-direction]");
  const conditionButton = event.target.closest(".condition-chip[data-condition]");

  if (priorityButton) {
    const item = priorityButton.closest(".priority-item");
    movePriority(item.dataset.condition, priorityButton.dataset.direction);
    return;
  }

  if (conditionButton) {
    toggleCondition(conditionButton.dataset.condition);
  }
}

function openDrawer(code) {
  const row = state.rows.find((item) => item.code === code);
  if (!row) {
    return;
  }

  state.selectedCode = code;
  elements.drawerContent.innerHTML = renderDrawer(row);
  elements.drawer.classList.add("is-open");
  elements.drawer.setAttribute("aria-hidden", "false");
  update();
}

function closeDrawer() {
  elements.drawer.classList.remove("is-open");
  elements.drawer.setAttribute("aria-hidden", "true");
}

function renderDrawer(row) {
  return `
    <div class="drawer-summary">
      <header class="drawer-hero">
        <p class="eyebrow">Ward Detail</p>
        <h2 id="drawer-title">${row.ward_name}</h2>
        <p>${row.recommended_profile}</p>
        <div class="drawer-score-row">
          <span class="score-pill">${row.personalizedScore.toFixed(1)}<span>おすすめ度</span></span>
          <span class="score-pill">${formatNumber(row.population)}人<span>人口</span></span>
          <span class="score-pill">${formatDecimal(row.ward_area_km2, 2)}<span>km2</span></span>
        </div>
        <div class="tag-row">
          ${renderTags(row.strengths, "tag", "バランス型")}
          ${renderTags(row.cautions, "tag warning")}
        </div>
      </header>

      <section class="radar-wrap" aria-label="評価軸レーダーチャート">
        ${renderRadar(row)}
      </section>

      <section>
        <div class="section-heading">
          <p class="eyebrow">Drill Down</p>
          <h3>カテゴリ別の根拠</h3>
        </div>
        <div class="drilldown-grid">
          ${renderDrilldown(row)}
        </div>
      </section>
    </div>
  `;
}

function renderRadar(row) {
  const metrics = availableScoreMetrics(row);
  const center = 120;
  const maxRadius = 92;
  const points = metrics.map((metric, index) => {
    const angle = (Math.PI * 2 * index) / metrics.length - Math.PI / 2;
    const radius = maxRadius * (row[metric.key] / 100);
    return [center + Math.cos(angle) * radius, center + Math.sin(angle) * radius];
  });
  const gridPolygons = [0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const gridPoints = metrics.map((_, index) => {
        const angle = (Math.PI * 2 * index) / metrics.length - Math.PI / 2;
        return [
          center + Math.cos(angle) * maxRadius * ratio,
          center + Math.sin(angle) * maxRadius * ratio,
        ];
      });
      return `<polygon points="${gridPoints.map((point) => point.join(",")).join(" ")}" fill="none" stroke="#d8d0c3" />`;
    })
    .join("");
  const labels = metrics
    .map((metric, index) => {
      const angle = (Math.PI * 2 * index) / metrics.length - Math.PI / 2;
      const x = center + Math.cos(angle) * 112;
      const y = center + Math.sin(angle) * 112;
      return `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="700">${metric.label}</text>`;
    })
    .join("");

  return `
    <svg width="260" height="260" viewBox="0 0 240 240" role="img" aria-label="${row.ward_name}のレーダーチャート">
      ${gridPolygons}
      <polygon points="${points.map((point) => point.join(",")).join(" ")}" fill="rgba(15, 118, 110, 0.28)" stroke="#0f766e" stroke-width="3" />
      ${labels}
    </svg>
  `;
}

function renderDrilldown(row) {
  const details = [
    {
      metric: "score_accessibility",
      source: "OpenStreetMap / Overpass API",
      values: [
        ["駅数", formatNumber(row.station_count)],
        ["路線数", formatNumber(row.line_count)],
        ["駅密度", `${formatDecimal(row.station_density, 2)} / km2`],
      ],
      note: "OSMで取得した駅数と鉄道路線relation数を、同梱GeoJSONから算出した区面積で密度化しています。",
    },
    {
      metric: "score_safety",
      source: "警視庁公開CSV + e-Stat人口",
      values: [
        ["総犯罪件数", formatNumber(row.total_crime_cases)],
        ["犯罪/千人", formatDecimal(row.crime_rate_per_1000, 2)],
        ["凶悪犯/万人", formatDecimal(row.serious_crime_rate_per_10000, 2)],
      ],
      note: "警視庁CSVの件数を、e-Stat人口で人口あたりに変換しています。",
    },
    {
      metric: "score_convenience",
      source: "OpenStreetMap / Overpass API",
      values: [
        ["コンビニ", formatNumber(row.convenience_count)],
        ["スーパー", formatNumber(row.supermarket_count)],
        ["医療施設", formatNumber(row.medical_facility_count)],
      ],
      note: "OSMで取得した生活施設数を、同梱GeoJSONから算出した区面積で密度化しています。",
    },
    {
      metric: "score_resilience",
      source: "OpenStreetMap / Overpass API + e-Stat人口",
      values: [
        ["避難所数", formatNumber(row.shelter_count)],
        ["避難所/万人", formatDecimal(row.shelter_rate_per_10000, 2)],
      ],
      note: "OSMで取得した避難所数のみを使っています。固定の洪水・地震リスク値は使っていません。",
    },
  ];

  return details
    .map((detail) => {
      const metric = metricByKey(detail.metric);
      return `
        <article class="drilldown-card">
          <div class="drilldown-card-head">
            <span>${metric.detailLabel}</span>
            <span>${row[metric.key].toFixed(1)}</span>
          </div>
          <dl>
            ${detail.values
              .map(
                ([label, value]) => `
                  <div>
                    <dt>${label}</dt>
                    <dd>${value}</dd>
                  </div>
                `,
              )
              .join("")}
          </dl>
          <p class="data-note">${detail.note}</p>
          <p class="data-note">出典: ${detail.source}</p>
        </article>
      `;
    })
    .join("");
}

function update() {
  enrichRows();
  renderRanking();
  renderMap();
  renderCompare();
}

function bindEvents() {
  document.querySelectorAll(".preset-button").forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  });

  elements.priorityBuilder.addEventListener("click", syncPriorityFromInteraction);
  elements.sortMode.addEventListener("change", update);
  elements.mapMetric.addEventListener("change", renderMap);
  elements.clearCompare.addEventListener("click", () => {
    state.compareCodes = [];
    update();
  });

  elements.rankingList.addEventListener("click", (event) => {
    const detailButton = event.target.closest("[data-detail]");
    const compareButton = event.target.closest("[data-compare]");
    const rankingToggle = event.target.closest("[data-ranking-toggle]");

    if (detailButton) {
      openDrawer(detailButton.dataset.detail);
      return;
    }
    if (compareButton) {
      toggleCompare(compareButton.dataset.compare);
      return;
    }
    if (rankingToggle) {
      toggleRankingExpansion();
    }
  });

  elements.drawer.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-drawer]")) {
      closeDrawer();
    }
  });

  if (elements.advancedSettingsToggle && elements.advancedSettingsPanel) {
    elements.advancedSettingsToggle.addEventListener("click", () => {
      const willExpand =
        elements.advancedSettingsToggle.getAttribute("aria-expanded") !== "true";
      elements.advancedSettingsToggle.setAttribute("aria-expanded", String(willExpand));
      elements.advancedSettingsToggle.textContent = willExpand ? "隠す" : "表示する";
      elements.advancedSettingsPanel.hidden = !willExpand;
    });
  }
}

function watchMediaQuery(query, callback) {
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", callback);
  } else if (typeof query.addListener === "function") {
    query.addListener(callback);
  }
}

async function init() {
  try {
    await loadData();
    renderPriorityBuilder();
    bindEvents();
    watchMediaQuery(mobileRankingQuery, renderRanking);
    update();
  } catch (error) {
    console.error(error);
    elements.rankingList.innerHTML =
      '<div class="empty-state">データの読み込みに失敗しました。</div>';
  }
}

init();
