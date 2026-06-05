const DATA_PATHS = {
  index: "data/processed/tokyo_livability_index.csv",
  estat: "data/raw/estat_data.csv",
  spatial: "data/raw/spatial_data.csv",
  crime: "data/raw/crime_data.csv",
  poi: "data/raw/osm_poi_data.csv",
  geojson: "data/raw/gis/tokyo_23wards.geojson",
};

const SCORE_METRICS = [
  {
    key: "score_accessibility",
    weightKey: "accessibility",
    label: "アクセス",
    detailLabel: "鉄道アクセス",
    positive: "人口あたりの駅数が多い",
    caution: "人口あたりの駅数は控えめ",
  },
  {
    key: "score_safety",
    weightKey: "safety",
    label: "治安",
    detailLabel: "治安",
    positive: "人口あたりの犯罪件数が少ない",
    caution: "人口あたりの犯罪件数は要確認",
  },
  {
    key: "score_convenience",
    weightKey: "convenience",
    label: "生活利便性",
    detailLabel: "生活利便性",
    positive: "人口あたりの生活施設が多い",
    caution: "人口あたりの生活施設は控えめ",
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
  safety: ["safety", "resilience", "accessibility", "convenience"],
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

function perCapitaRate(count, population, scale) {
  return population > 0 ? (count / population) * scale : 0;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ja-JP").format(Math.round(value));
}

function formatDecimal(value, digits = 1) {
  return Number(value).toFixed(digits);
}

function metricByKey(key) {
  return SCORE_METRICS.find((metric) => metric.key === key);
}

async function loadData() {
  const { indexText, estatText, spatialText, crimeText, poiText, geojson } =
    await loadSourceData();

  const estatByCode = Object.fromEntries(parseCsv(estatText).map((row) => [row.code, row]));
  const spatialByCode = Object.fromEntries(parseCsv(spatialText).map((row) => [row.code, row]));
  const crimeByCode = Object.fromEntries(parseCsv(crimeText).map((row) => [row.code, row]));
  const poiByCode = Object.fromEntries(parseCsv(poiText).map((row) => [row.code, row]));

  state.rows = parseCsv(indexText).map((row) => {
    const merged = {
      ...row,
      ...estatByCode[row.code],
      ...spatialByCode[row.code],
      ...crimeByCode[row.code],
      ...poiByCode[row.code],
      ward_name: row.ward_name,
    };

    [
      "population",
      "score_accessibility",
      "score_safety",
      "score_convenience",
      "score_resilience",
      "station_count",
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
    merged.station_rate_per_100000 = perCapitaRate(
      merged.station_count,
      merged.population,
      100000,
    );
    merged.shelter_rate_per_100000 = perCapitaRate(
      merged.shelter_count,
      merged.population,
      100000,
    );
    merged.convenience_rate_per_100000 = perCapitaRate(
      merged.convenience_count,
      merged.population,
      100000,
    );
    merged.supermarket_rate_per_100000 = perCapitaRate(
      merged.supermarket_count,
      merged.population,
      100000,
    );
    merged.medical_rate_per_100000 = perCapitaRate(
      merged.medical_facility_count,
      merged.population,
      100000,
    );
    merged.daily_facility_rate_per_100000 = perCapitaRate(
      merged.daily_facility_count,
      merged.population,
      100000,
    );

    return merged;
  });

  state.geojson = geojson;
}

async function loadSourceData() {
  try {
    const [indexText, estatText, spatialText, crimeText, poiText, geojson] =
      await Promise.all([
        fetchText(DATA_PATHS.index),
        fetchText(DATA_PATHS.estat),
        fetchText(DATA_PATHS.spatial),
        fetchText(DATA_PATHS.crime),
        fetchText(DATA_PATHS.poi),
        fetchJson(DATA_PATHS.geojson),
      ]);

    return { indexText, estatText, spatialText, crimeText, poiText, geojson };
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
  const activeMetrics =
    state.priority.length === 0
      ? SCORE_METRICS
      : state.priority
          .map((weightKey) =>
            SCORE_METRICS.find((metric) => metric.weightKey === weightKey),
          )
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
    stationRate: { key: "station_rate_per_100000", direction: "desc" },
    totalCrime: { key: "crime_rate_per_1000", direction: "asc" },
    seriousCrime: { key: "serious_crime_rate_per_10000", direction: "asc" },
    supermarketRate: { key: "supermarket_rate_per_100000", direction: "desc" },
    medicalRate: { key: "medical_rate_per_100000", direction: "desc" },
    dailyFacilityRate: { key: "daily_facility_rate_per_100000", direction: "desc" },
    shelterRate: { key: "shelter_rate_per_100000", direction: "desc" },
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
    {
      label: "人口あたりの駅数が多い",
      softLabel: "駅アクセスは比較的良い",
      rank: ranks.stationRate[row.code],
    },
    {
      label: "人口あたりの犯罪件数が少ない",
      softLabel: "犯罪件数は比較的少ない",
      rank: ranks.totalCrime[row.code],
    },
    {
      label: "人口あたりの重大犯罪件数が少ない",
      softLabel: "重大犯罪件数は比較的少ない",
      rank: ranks.seriousCrime[row.code],
    },
    {
      label: "人口あたりのスーパーが多い",
      softLabel: "スーパーは比較的多い",
      rank: ranks.supermarketRate[row.code],
    },
    {
      label: "人口あたりの医療施設が多い",
      softLabel: "医療施設は比較的多い",
      rank: ranks.medicalRate[row.code],
    },
    {
      label: "人口あたりの日常施設が多い",
      softLabel: "日常施設は比較的多い",
      rank: ranks.dailyFacilityRate[row.code],
    },
    {
      label: "人口あたりの避難所が多い",
      softLabel: "避難所は比較的多い",
      rank: ranks.shelterRate[row.code],
    },
  ];

  const detailedStrengths = detailCandidates
    .filter((strength) => strength.rank <= 5)
    .map((strength) => strength.label);
  const relativeStrengths = detailCandidates
    .filter((strength) => strength.rank > 5 && strength.rank <= 12)
    .sort((a, b) => a.rank - b.rank)
    .map((strength) => strength.softLabel);
  const scoreStrengths = [...SCORE_METRICS]
    .sort((a, b) => row[b.key] - row[a.key])
    .filter((metric) => row[metric.key] >= 75)
    .map((metric) => metric.positive);

  return uniqueList([
    ...detailedStrengths,
    ...scoreStrengths,
    ...relativeStrengths,
  ]).slice(0, 4);
}

function getCautions(row, ranks) {
  const detailedCautions = [
    { label: "人口あたりの駅数は控えめ", active: ranks.stationRate[row.code] >= 19 },
    { label: "人口あたりの犯罪件数は要確認", active: ranks.totalCrime[row.code] >= 19 },
    { label: "人口あたりのスーパーは控えめ", active: ranks.supermarketRate[row.code] >= 19 },
    { label: "人口あたりの医療施設は控えめ", active: ranks.medicalRate[row.code] >= 19 },
    { label: "人口あたりの避難所は控えめ", active: ranks.shelterRate[row.code] >= 19 },
  ]
    .filter((caution) => caution.active)
    .map((caution) => caution.label);
  const scoreCautions = [...SCORE_METRICS]
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
      ${SCORE_METRICS.map(
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
      ).join("")}
    </div>
    <div class="priority-list-wrap">
      <div class="priority-list-heading">
        <span>優先順位</span>
        <small>選んだ観点だけを上から順に重く見ます。未選択時は全観点を均等に見ます。</small>
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
    const metric = SCORE_METRICS.find((item) => item.weightKey === weightKey);
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
  state.priority = [...(PRESETS[presetName] ?? PRESETS.balanced)];
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

  if (rows.length === 0) {
    elements.rankingList.innerHTML =
      '<div class="empty-state">表示できる実取得データがありません。</div>';
    return;
  }

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
        <div><span>人口</span><strong>${formatNumber(row.population)}人</strong></div>
        <div><span>治安</span><strong>${row.score_safety.toFixed(1)}</strong></div>
        <div><span>アクセス</span><strong>${row.score_accessibility.toFixed(1)}</strong></div>
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
      : `さらに${rows.length - MOBILE_RANKING_LIMIT}区を見る`;
    elements.rankingList.append(toggleButton);
  }
}

function renderTags(items, className, emptyLabel = "") {
  if (items.length === 0) {
    return emptyLabel ? `<span class="${className}">${emptyLabel}</span>` : "";
  }
  return items.map((item) => `<span class="${className}">${item}</span>`).join("");
}

function renderMap() {
  if (!state.geojson || state.rows.length === 0) {
    return;
  }

  const metric = elements.mapMetric.value;
  const rowsByCode = Object.fromEntries(state.rows.map((row) => [row.code, row]));
  const features = state.geojson.features;
  const bounds = getGeoBounds(features);
  const width = 520;
  const height = 520;
  const padding = 18;
  const scale = Math.min(
    (width - padding * 2) / (bounds.maxX - bounds.minX),
    (height - padding * 2) / (bounds.maxY - bounds.minY),
  );

  elements.wardMap.setAttribute("viewBox", `0 0 ${width} ${height}`);
  elements.wardMap.innerHTML = features
    .map((feature) => {
      const code = feature.properties.code;
      const row = rowsByCode[code];
      if (!row) {
        return "";
      }
      const path = geometryToPath(feature.geometry, bounds, scale, height, padding);
      const isSelected = state.selectedCode === code;
      return `
        <path
          d="${path}"
          fill="${colorScale(row[metric])}"
          class="ward-shape ${isSelected ? "selected" : ""}"
          data-code="${code}"
          tabindex="0"
          role="button"
          aria-label="${row.ward_name} ${row[metric].toFixed(1)}"
        ></path>
      `;
    })
    .join("");

  elements.wardMap.querySelectorAll(".ward-shape").forEach((shape) => {
    shape.addEventListener("mouseenter", (event) => {
      const row = rowsByCode[event.currentTarget.dataset.code];
      showTooltip(event, row, metric);
    });
    shape.addEventListener("mousemove", (event) => {
      positionTooltip(event);
    });
    shape.addEventListener("mouseleave", hideTooltip);
    shape.addEventListener("click", (event) => {
      openDrawer(event.currentTarget.dataset.code);
    });
    shape.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDrawer(event.currentTarget.dataset.code);
      }
    });
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
  elements.mapTooltip.hidden = false;
  elements.mapTooltip.innerHTML = `
    <strong>${row.ward_name}</strong><br>
    ${metricLabel}: ${row[metric].toFixed(1)}<br>
    人口: ${formatNumber(row.population)}人<br>
    強み: ${(row.strengths[0] ?? "バランス型")}
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
    elements.compareContent.textContent =
      "比較したい区をランキングから追加してください。";
    return;
  }

  elements.compareContent.className = "compare-table-wrap";
  const metrics = [
    ["おすすめ度", "personalizedScore"],
    ["人口", "population", formatNumber],
    ...SCORE_METRICS.map((metric) => [metric.label, metric.key]),
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
          .map(([label, key, formatter]) => {
            const bestValue = Math.max(...rows.map((row) => row[key]));
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
          <span class="score-pill">${formatDecimal(row.crime_rate_per_1000, 2)}件<span>犯罪/千人</span></span>
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
  const center = 120;
  const maxRadius = 92;
  const points = SCORE_METRICS.map((metric, index) => {
    const angle = (Math.PI * 2 * index) / SCORE_METRICS.length - Math.PI / 2;
    const radius = maxRadius * (row[metric.key] / 100);
    return [center + Math.cos(angle) * radius, center + Math.sin(angle) * radius];
  });
  const gridPolygons = [0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const gridPoints = SCORE_METRICS.map((_, index) => {
        const angle = (Math.PI * 2 * index) / SCORE_METRICS.length - Math.PI / 2;
        return [
          center + Math.cos(angle) * maxRadius * ratio,
          center + Math.sin(angle) * maxRadius * ratio,
        ];
      });
      return `<polygon points="${gridPoints.map((point) => point.join(",")).join(" ")}" fill="none" stroke="#d8d0c3" />`;
    })
    .join("");

  const labels = SCORE_METRICS.map((metric, index) => {
    const angle = (Math.PI * 2 * index) / SCORE_METRICS.length - Math.PI / 2;
    const x = center + Math.cos(angle) * 112;
    const y = center + Math.sin(angle) * 112;
    return `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="700">${metric.label}</text>`;
  }).join("");

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
      evidence: [
        {
          label: "駅数",
          value: `${formatNumber(row.station_count)}駅`,
          scoreLabel: "人口10万人あたり駅数",
          weight: 1,
        },
      ],
      note: "OpenStreetMap / Overpass APIで取得した駅数を、人口あたりに変換して評価しています。",
    },
    {
      metric: "score_safety",
      evidence: [
        {
          label: "人口1,000人あたり犯罪件数",
          value: `${formatDecimal(row.crime_rate_per_1000, 2)}件`,
          scoreLabel: "総犯罪件数の少なさ",
          weight: 0.7,
        },
        {
          label: "人口10,000人あたり重大犯罪件数",
          value: `${formatDecimal(row.serious_crime_rate_per_10000, 2)}件`,
          scoreLabel: "重大犯罪件数の少なさ",
          weight: 0.3,
        },
      ],
      note: "警視庁CSVから取得した犯罪件数を、e-Stat人口で人口あたりに変換しています。",
    },
    {
      metric: "score_convenience",
      evidence: [
        {
          label: "コンビニ",
          value: `${formatNumber(row.convenience_count)}件`,
          scoreLabel: "人口10万人あたりコンビニ",
          weight: 0.25,
        },
        {
          label: "スーパー",
          value: `${formatNumber(row.supermarket_count)}件`,
          scoreLabel: "人口10万人あたりスーパー",
          weight: 0.25,
        },
        {
          label: "医療施設",
          value: `${formatNumber(row.medical_facility_count)}件`,
          scoreLabel: "人口10万人あたり医療施設",
          weight: 0.3,
        },
        {
          label: "日常施設",
          value: `${formatNumber(row.daily_facility_count)}件`,
          scoreLabel: "人口10万人あたり日常施設",
          weight: 0.2,
        },
      ],
      note: "OpenStreetMap / Overpass APIで取得した施設数を、人口あたりに変換して評価しています。",
    },
    {
      metric: "score_resilience",
      evidence: [
        {
          label: "避難所数",
          value: `${formatNumber(row.shelter_count)}か所`,
          scoreLabel: "人口10万人あたり避難所",
          weight: 1,
        },
      ],
      note: "OpenStreetMap / Overpass APIで取得した避難所数のみを使っています。固定の災害リスク値は使っていません。",
    },
  ];

  return details
    .map((detail) => {
      const metric = metricByKey(detail.metric);
      return `
        <details class="drilldown-card">
          <summary>
            <span>${metric.detailLabel}</span>
            <span>${row[metric.key].toFixed(1)}</span>
          </summary>
          <div class="drilldown-body">
            <div class="evidence-grid">
              ${detail.evidence
                .map(
                  (item) => `
                    <div>
                      <span>${item.label}</span>
                      <strong>${item.value}</strong>
                      <small>${item.scoreLabel}</small>
                    </div>
                  `,
                )
                .join("")}
            </div>
            ${renderScoreFormula(row, detail)}
            <p>${detail.note}</p>
          </div>
        </details>
      `;
    })
    .join("");
}

function renderScoreFormula(row, detail) {
  const metric = metricByKey(detail.metric);
  const formula = detail.evidence
    .map((item) => `${formatDecimal(item.weight, 2)} x ${item.scoreLabel}(0-100点)`)
    .join(" + ");

  return `
    <div class="score-formula">
      <span>計算方法</span>
      <strong>現在のスコア: ${row[metric.key].toFixed(1)}点</strong>
      <p>各根拠データを23区内で0-100点に正規化してから、重み付けして合成しています。</p>
      <p>スコア = ${formula}</p>
    </div>
  `;
}

function update() {
  enrichRows();
  renderRanking();
  renderMap();
  renderCompare();
}

function toggleAdvancedSettings() {
  const shouldShow = elements.advancedSettingsPanel.hidden;
  elements.advancedSettingsPanel.hidden = !shouldShow;
  elements.advancedSettingsToggle.setAttribute("aria-expanded", `${shouldShow}`);
  elements.advancedSettingsToggle.textContent = shouldShow ? "閉じる" : "表示する";
}

function watchMediaQuery(mediaQueryList, handler) {
  if (typeof mediaQueryList.addEventListener === "function") {
    mediaQueryList.addEventListener("change", handler);
    return;
  }

  if (typeof mediaQueryList.addListener === "function") {
    mediaQueryList.addListener(handler);
  }
}

function bindEvents() {
  document.querySelectorAll(".preset-button").forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  });

  elements.advancedSettingsToggle.addEventListener("click", toggleAdvancedSettings);
  elements.priorityBuilder.addEventListener("click", syncPriorityFromInteraction);

  [elements.sortMode, elements.mapMetric].forEach((element) => {
    element.addEventListener("change", () => {
      if (element !== elements.mapMetric) {
        state.isRankingExpanded = false;
      }
      update();
    });
  });

  elements.rankingList.addEventListener("click", (event) => {
    const toggleButton = event.target.closest("[data-ranking-toggle]");
    const detailButton = event.target.closest("[data-detail]");
    const compareButton = event.target.closest("[data-compare]");
    if (toggleButton) {
      toggleRankingExpansion();
      return;
    }
    if (detailButton) {
      openDrawer(detailButton.dataset.detail);
    }
    if (compareButton) {
      toggleCompare(compareButton.dataset.compare);
    }
  });

  elements.clearCompare.addEventListener("click", () => {
    state.compareCodes = [];
    update();
  });

  document.querySelectorAll("[data-close-drawer]").forEach((element) => {
    element.addEventListener("click", closeDrawer);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawer();
    }
  });

  watchMediaQuery(mobileRankingQuery, renderRanking);
}

async function init() {
  try {
    renderPriorityBuilder();
    bindEvents();
    await loadData();
    update();
  } catch (error) {
    document.querySelector("main").innerHTML = `
      <div class="load-error">
        データの読み込みに失敗しました。実取得データが生成されているか確認してください。
      </div>
    `;
    console.error(error);
  }
}

init();
