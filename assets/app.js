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
    key: "score_affordability",
    weightKey: "affordability",
    label: "家賃",
    detailLabel: "家賃・コスト",
    positive: "家賃負担が軽い",
    caution: "家賃負担が重い",
  },
  {
    key: "score_accessibility",
    weightKey: "accessibility",
    label: "アクセス",
    detailLabel: "交通アクセス",
    positive: "アクセスが良い",
    caution: "アクセスは控えめ",
  },
  {
    key: "score_safety",
    weightKey: "safety",
    label: "治安",
    detailLabel: "治安",
    positive: "治安が良い",
    caution: "治安は要確認",
  },
  {
    key: "score_convenience",
    weightKey: "convenience",
    label: "生活利便性",
    detailLabel: "生活利便性",
    positive: "生活利便性が高い",
    caution: "生活利便性は控えめ",
  },
  {
    key: "score_livability",
    weightKey: "livability",
    label: "居住快適性",
    detailLabel: "一人暮らし快適性",
    positive: "居住快適性が高い",
    caution: "居住快適性は控えめ",
  },
  {
    key: "score_resilience",
    weightKey: "resilience",
    label: "防災",
    detailLabel: "防災・災害リスク",
    positive: "防災面が強い",
    caution: "災害リスクは要確認",
  },
];

const PRESETS = {
  balanced: [],
  budget: ["affordability", "safety", "livability", "convenience"],
  safety: ["safety", "resilience", "affordability", "convenience"],
  access: ["accessibility", "convenience", "affordability", "safety"],
  convenience: ["convenience", "accessibility", "affordability", "safety"],
  resilience: ["resilience", "safety", "livability", "affordability"],
};

const state = {
  rows: [],
  geojson: null,
  priority: [...PRESETS.balanced],
  compareCodes: [],
  selectedCode: null,
};

const elements = {
  priorityBuilder: document.querySelector("#priority-builder"),
  rankingList: document.querySelector("#ranking-list"),
  resultCount: document.querySelector("#result-count"),
  rentLimit: document.querySelector("#rent-limit"),
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

function densityPerKm2(count, areaKm2) {
  return areaKm2 > 0 ? count / areaKm2 : 0;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ja-JP").format(Math.round(value));
}

function formatRent(value) {
  return `${formatNumber(value)}円`;
}

function formatDecimal(value, digits = 1) {
  return Number(value).toFixed(digits);
}

function formatPercent(value) {
  return `${formatDecimal(value * 100, 1)}%`;
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
      "households",
      "single_household_rate",
      "single_households",
      "average_rent",
      "average_floor_space",
      "ward_area_km2",
      "income_proxy",
      "score_affordability",
      "score_accessibility",
      "score_safety",
      "score_convenience",
      "score_livability",
      "score_resilience",
      "station_count",
      "line_count",
      "average_access_time_min",
      "flood_risk_area_rate",
      "earthquake_hazard_rank",
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
    merged.convenience_density = densityPerKm2(
      merged.convenience_count,
      merged.ward_area_km2,
    );
    merged.supermarket_density = densityPerKm2(
      merged.supermarket_count,
      merged.ward_area_km2,
    );
    merged.medical_density = densityPerKm2(
      merged.medical_facility_count,
      merged.ward_area_km2,
    );
    merged.daily_facility_density = densityPerKm2(
      merged.daily_facility_count,
      merged.ward_area_km2,
    );
    merged.rent_burden_index =
      merged.income_proxy > 0 ? merged.average_rent / (merged.income_proxy * 10000) : 0;

    return merged;
  });

  state.geojson = geojson;
}

async function loadSourceData() {
  try {
    const [indexText, estatText, spatialText, crimeText, poiText, geojson] = await Promise.all([
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
    lowRent: { key: "average_rent", direction: "asc" },
    stationCount: { key: "station_count", direction: "desc" },
    lineCount: { key: "line_count", direction: "desc" },
    accessTime: { key: "average_access_time_min", direction: "asc" },
    totalCrime: { key: "crime_rate_per_1000", direction: "asc" },
    seriousCrime: { key: "serious_crime_rate_per_10000", direction: "asc" },
    supermarket: { key: "supermarket_count", direction: "desc" },
    medical: { key: "medical_facility_count", direction: "desc" },
    dailyFacility: { key: "daily_facility_count", direction: "desc" },
    floodRisk: { key: "flood_risk_area_rate", direction: "asc" },
    earthquakeRisk: { key: "earthquake_hazard_rank", direction: "asc" },
    shelter: { key: "shelter_count", direction: "desc" },
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
      label: "家賃が抑えめ",
      softLabel: "家賃は比較的抑えめ",
      rank: ranks.lowRent[row.code],
    },
    {
      label: "駅が多い",
      softLabel: "駅数は比較的多め",
      rank: ranks.stationCount[row.code],
    },
    {
      label: "路線が多い",
      softLabel: "路線数は比較的多め",
      rank: ranks.lineCount[row.code],
    },
    {
      label: "主要駅に近い",
      softLabel: "主要駅へ比較的出やすい",
      rank: ranks.accessTime[row.code],
    },
    {
      label: "犯罪率が低い",
      softLabel: "犯罪率は比較的低め",
      rank: ranks.totalCrime[row.code],
    },
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
      label: "浸水リスク低め",
      softLabel: "浸水リスクは比較的低め",
      rank: ranks.floodRisk[row.code],
    },
    {
      label: "地震リスク低め",
      softLabel: "地震リスクは比較的低め",
      rank: ranks.earthquakeRisk[row.code],
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
    { label: "家賃高め", active: ranks.lowRent[row.code] >= 19 },
    { label: "駅数は少なめ", active: ranks.stationCount[row.code] >= 19 },
    { label: "主要駅まで遠め", active: ranks.accessTime[row.code] >= 19 },
    { label: "犯罪率は要確認", active: ranks.totalCrime[row.code] >= 19 },
    { label: "スーパー少なめ", active: ranks.supermarket[row.code] >= 19 },
    { label: "医療施設少なめ", active: ranks.medical[row.code] >= 19 },
    { label: "浸水リスク高め", active: ranks.floodRisk[row.code] >= 19 },
    { label: "避難所少なめ", active: ranks.shelter[row.code] >= 19 },
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
  const rentLimit = toNumber(elements.rentLimit.value);
  const sortMode = elements.sortMode.value;

  const rows = state.rows
    .filter((row) => row.average_rent <= rentLimit)
    .sort((a, b) => {
      if (sortMode === "rent") {
        return a.average_rent - b.average_rent;
      }
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

  return rows;
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
  state.priority = [...PRESETS[presetName]];
  setActivePreset(presetName);
  renderPriorityBuilder();
  update();
}

function renderRanking() {
  const rows = getFilteredRows();
  elements.resultCount.textContent = `${rows.length}区`;
  elements.rankingList.innerHTML = "";

  if (rows.length === 0) {
    elements.rankingList.innerHTML =
      '<div class="empty-state">条件に合う区がありません。家賃上限か重視軸を調整してください。</div>';
    return;
  }

  rows.forEach((row, index) => {
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
        <div><span>平均家賃</span><strong>${formatRent(row.average_rent)}</strong></div>
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
}

function renderTags(tags, className, emptyLabel = "") {
  if (tags.length === 0) {
    if (!emptyLabel) {
      return "";
    }
    return `<span class="tag">${emptyLabel}</span>`;
  }
  return tags.map((tag) => `<span class="${className}">${tag}</span>`).join("");
}

function renderMap() {
  if (!state.geojson) {
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

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", geometryToPath(feature.geometry, bounds, scale, height, padding));
    path.setAttribute("fill", colorScale(row[metric]));
    path.classList.add("ward-shape");
    path.classList.toggle("is-selected", row.code === state.selectedCode);
    path.dataset.code = row.code;
    path.setAttribute("tabindex", "0");
    path.setAttribute("aria-label", `${row.ward_name} ${row[metric].toFixed(1)}点`);

    path.addEventListener("mouseenter", (event) => showTooltip(event, row, metric));
    path.addEventListener("mousemove", (event) => positionTooltip(event));
    path.addEventListener("mouseleave", hideTooltip);
    path.addEventListener("click", () => openDrawer(row.code));
    path.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDrawer(row.code);
      }
    });

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
  elements.mapTooltip.hidden = false;
  elements.mapTooltip.innerHTML = `
    <strong>${row.ward_name}</strong><br>
    ${metricLabel}: ${row[metric].toFixed(1)}<br>
    平均家賃: ${formatRent(row.average_rent)}<br>
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
    elements.compareContent.textContent = "比較したい区をランキングから追加してください。";
    return;
  }

  elements.compareContent.className = "compare-table-wrap";
  const metrics = [
    ["おすすめ度", "personalizedScore", "higher"],
    ["平均家賃", "average_rent", "lower", formatRent],
    ...SCORE_METRICS.map((metric) => [metric.label, metric.key, "higher"]),
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

function toggleCondition(weightKey) {
  if (state.priority.includes(weightKey)) {
    state.priority = state.priority.filter((item) => item !== weightKey);
  } else {
    state.priority = [...state.priority, weightKey];
  }
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
          <span class="score-pill">${formatRent(row.average_rent)}<span>平均家賃</span></span>
          <span class="score-pill">${formatNumber(row.population)}人<span>人口</span></span>
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
      metric: "score_affordability",
      evidence: [
        {
          label: "平均家賃",
          value: formatRent(row.average_rent),
          scoreLabel: "家賃の安さ",
          weight: 0.5,
        },
        {
          label: "単身世帯比率",
          value: formatPercent(row.single_household_rate),
          scoreLabel: "単身向き住宅環境",
          weight: 0.3,
        },
        {
          label: "家賃負担指数",
          value: formatDecimal(row.rent_burden_index, 3),
          scoreLabel: "家賃負担の軽さ",
          weight: 0.2,
        },
      ],
      note: "家賃スコアは、平均家賃や家賃負担の軽さを中心に見ています。",
    },
    {
      metric: "score_accessibility",
      evidence: [
        {
          label: "駅密度",
          value: `${formatDecimal(row.station_density, 2)}駅/km²`,
          scoreLabel: "駅密度スコア",
          weight: 0.4,
        },
        {
          label: "路線数",
          value: `${row.line_count}路線`,
          scoreLabel: "路線数スコア",
          weight: 0.2,
        },
        {
          label: "主要駅への平均アクセス",
          value: `${formatDecimal(row.average_access_time_min, 1)}分`,
          scoreLabel: "アクセス時間の短さ",
          weight: 0.4,
        },
      ],
      note: "駅の密度、路線数、主要駅への移動時間から交通アクセスを見ています。",
    },
    {
      metric: "score_safety",
      evidence: [
        {
          label: "人口1,000人あたり犯罪件数",
          value: `${formatDecimal(row.crime_rate_per_1000, 2)}件`,
          scoreLabel: "犯罪件数の少なさ",
          weight: 0.7,
        },
        {
          label: "人口10,000人あたり重大犯罪件数",
          value: `${formatDecimal(row.serious_crime_rate_per_10000, 2)}件`,
          scoreLabel: "重大犯罪の少なさ",
          weight: 0.3,
        },
      ],
      note: "人口あたりの犯罪件数と重大犯罪の少なさを中心に治安を見ています。",
    },
    {
      metric: "score_convenience",
      evidence: [
        {
          label: "コンビニ密度",
          value: `${formatDecimal(row.convenience_density, 2)}件/km²`,
          scoreLabel: "コンビニ密度スコア",
          weight: 0.25,
        },
        {
          label: "スーパー密度",
          value: `${formatDecimal(row.supermarket_density, 2)}件/km²`,
          scoreLabel: "スーパー密度スコア",
          weight: 0.25,
        },
        {
          label: "医療施設密度",
          value: `${formatDecimal(row.medical_density, 2)}件/km²`,
          scoreLabel: "医療施設密度スコア",
          weight: 0.3,
        },
        {
          label: "日常施設密度",
          value: `${formatDecimal(row.daily_facility_density, 2)}件/km²`,
          scoreLabel: "日常施設密度スコア",
          weight: 0.2,
        },
      ],
      note: "日々の買い物や医療アクセスに関わる施設数を見ています。",
    },
    {
      metric: "score_livability",
      evidence: [
        {
          label: "単身世帯比率",
          value: formatPercent(row.single_household_rate),
          scoreLabel: "単身世帯比率スコア",
          weight: 0.3,
        },
        {
          label: "平均住宅面積",
          value: `${formatDecimal(row.average_floor_space, 1)}m²`,
          scoreLabel: "住宅面積スコア",
          weight: 0.25,
        },
        {
          label: "快適性補正",
          value: "単身世帯比率と住宅面積の平均",
          scoreLabel: "快適性補正スコア",
          weight: 0.45,
        },
      ],
      note: "この指標は総合点ではなく、一人暮らしや住居面の快適性に近い評価です。",
    },
    {
      metric: "score_resilience",
      evidence: [
        {
          label: "浸水リスク面積率",
          value: formatPercent(row.flood_risk_area_rate),
          scoreLabel: "浸水リスクの低さ",
          weight: 0.4,
        },
        {
          label: "地震ハザードランク",
          value: formatDecimal(row.earthquake_hazard_rank, 1),
          scoreLabel: "地震リスクの低さ",
          weight: 0.3,
        },
        {
          label: "人口10,000人あたり避難所数",
          value: `${formatDecimal(row.shelter_rate_per_10000, 2)}か所`,
          scoreLabel: "避難所の多さ",
          weight: 0.3,
        },
      ],
      note: "浸水リスク、地震ハザード、避難所数を使って防災面を見ています。",
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
    .map((item) => `${formatDecimal(item.weight, 2)} × ${item.scoreLabel}`)
    .join(" + ");

  return `
    <div class="score-formula">
      <span>計算式</span>
      <strong>現在のスコア: ${row[metric.key].toFixed(1)}点</strong>
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

function bindEvents() {
  document.querySelectorAll(".preset-button").forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  });

  elements.priorityBuilder.addEventListener("click", syncPriorityFromInteraction);

  [elements.rentLimit, elements.sortMode, elements.mapMetric].forEach((element) => {
    element.addEventListener("change", update);
  });

  elements.rankingList.addEventListener("click", (event) => {
    const detailButton = event.target.closest("[data-detail]");
    const compareButton = event.target.closest("[data-compare]");
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
        データの読み込みに失敗しました。ページを再読み込みするか、HTTPサーバー経由で表示してください。
      </div>
    `;
    console.error(error);
  }
}

init();
