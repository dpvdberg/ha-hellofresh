class HelloFreshCard extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._currentWeekIndex = 0;
      this._render();
    } else {
      this._updateContent();
    }
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity");
    }
    this._config = {
      entity: config.entity,
      show_images: config.show_images !== undefined ? config.show_images : true,
      title: config.title || "HelloFresh",
    };
  }

  getCardSize() {
    return 4;
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          padding: 16px;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
        }
        .header h2 {
          margin: 0;
          font-size: 1.2em;
        }
        .nav-buttons {
          display: flex;
          gap: 8px;
        }
        .nav-btn {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          border-radius: 50%;
          width: 32px;
          height: 32px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
        }
        .nav-btn:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }
        .week-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
        }
        .week-label {
          font-weight: bold;
          font-size: 1.1em;
        }
        .badges {
          display: flex;
          gap: 6px;
          margin-bottom: 12px;
        }
        .badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 12px;
          font-size: 0.75em;
          font-weight: 600;
          text-transform: uppercase;
        }
        .badge-locked {
          background: #d32f2f;
          color: white;
        }
        .badge-preselected {
          background: #f57c00;
          color: white;
        }
        .badge-editable {
          background: #388e3c;
          color: white;
        }
        .meals-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .meal-item {
          display: flex;
          gap: 12px;
          align-items: center;
          padding: 8px;
          border-radius: 8px;
          background: var(--card-background-color, var(--ha-card-background));
          border: 1px solid var(--divider-color);
        }
        .meal-image {
          width: 80px;
          height: 80px;
          border-radius: 8px;
          object-fit: cover;
          flex-shrink: 0;
        }
        .meal-info {
          flex: 1;
          min-width: 0;
        }
        .meal-name {
          font-weight: 600;
          margin-bottom: 4px;
        }
        .meal-headline {
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .meal-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          margin-top: 4px;
        }
        .tag {
          font-size: 0.7em;
          background: var(--primary-color);
          color: var(--text-primary-color);
          padding: 1px 6px;
          border-radius: 8px;
        }
        .no-meals {
          color: var(--secondary-text-color);
          font-style: italic;
        }
      </style>
      <ha-card>
        <div class="header">
          <h2>${this._config.title}</h2>
          <div class="nav-buttons">
            <button class="nav-btn" id="prev-btn">&#8249;</button>
            <button class="nav-btn" id="next-btn">&#8250;</button>
          </div>
        </div>
        <div id="content"></div>
      </ha-card>
    `;

    this.shadowRoot.getElementById("prev-btn").addEventListener("click", () => {
      if (this._currentWeekIndex > 0) {
        this._currentWeekIndex--;
        this._updateContent();
      }
    });
    this.shadowRoot.getElementById("next-btn").addEventListener("click", () => {
      const weeks = this._getWeeks();
      if (this._currentWeekIndex < weeks.length - 1) {
        this._currentWeekIndex++;
        this._updateContent();
      }
    });

    this._updateContent();
  }

  _getWeeks() {
    if (!this._hass || !this._config) return [];
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj || !stateObj.attributes.weeks) return [];

    const weeksObj = stateObj.attributes.weeks;
    return Object.keys(weeksObj).sort();
  }

  _updateContent() {
    if (!this.shadowRoot) return;
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj || !stateObj.attributes.weeks) {
      content.innerHTML = '<div class="no-meals">No data available</div>';
      return;
    }

    const weeksObj = stateObj.attributes.weeks;
    const weekKeys = Object.keys(weeksObj).sort();
    const modifiableWeek = stateObj.attributes.next_modifiable_week;

    if (weekKeys.length === 0) {
      content.innerHTML = '<div class="no-meals">No upcoming deliveries</div>';
      return;
    }

    // Clamp index
    if (this._currentWeekIndex >= weekKeys.length) {
      this._currentWeekIndex = weekKeys.length - 1;
    }

    const currentWeekKey = weekKeys[this._currentWeekIndex];
    const weekData = weeksObj[currentWeekKey];

    // Update nav button states
    this.shadowRoot.getElementById("prev-btn").disabled = this._currentWeekIndex === 0;
    this.shadowRoot.getElementById("next-btn").disabled =
      this._currentWeekIndex >= weekKeys.length - 1;

    // Badges
    let badges = "";
    if (weekData.locked) {
      badges += '<span class="badge badge-locked">Locked</span>';
    } else {
      badges += '<span class="badge badge-editable">Editable</span>';
    }
    if (weekData.meals_preselected) {
      badges += '<span class="badge badge-preselected">Preselected</span>';
    }

    // Meals
    let mealsHtml = "";
    if (weekData.meals && weekData.meals.length > 0) {
      mealsHtml = '<div class="meals-list">';
      for (const meal of weekData.meals) {
        const imageHtml =
          this._config.show_images && meal.image
            ? `<img class="meal-image" src="${meal.image}" alt="${meal.name}" />`
            : "";
        const tagsHtml = (meal.tags || [])
          .map((t) => `<span class="tag">${t}</span>`)
          .join("");
        mealsHtml += `
          <div class="meal-item">
            ${imageHtml}
            <div class="meal-info">
              <div class="meal-name">${meal.name || "Unknown"}</div>
              <div class="meal-headline">${meal.headline || ""}</div>
              ${tagsHtml ? `<div class="meal-tags">${tagsHtml}</div>` : ""}
            </div>
          </div>
        `;
      }
      mealsHtml += "</div>";
    } else {
      mealsHtml = '<div class="no-meals">No meals selected for this week</div>';
    }

    content.innerHTML = `
      <div class="week-header">
        <span class="week-label">${this._formatWeekLabel(currentWeekKey, weekData)}</span>
      </div>
      <div class="badges">${badges}</div>
      ${mealsHtml}
    `;
  }

  _formatWeekLabel(weekKey, weekData) {
    // "2026-W22" → "2026 Week 22 · ma 25 mei"
    const match = weekKey.match(/^(\d{4})-W(\d{2})$/);
    if (!match) return weekKey;
    const year = match[1];
    const week = parseInt(match[2]);
    let label = `${year} Week ${week}`;
    if (weekData && weekData.delivery_date) {
      const d = new Date(weekData.delivery_date);
      const options = { weekday: "short", day: "numeric", month: "short" };
      label += ` · ${d.toLocaleDateString("nl-NL", options)}`;
    }
    return label;
  }

  static getConfigElement() {
    return document.createElement("hellofresh-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.hellofresh_upcoming_menus",
      show_images: true,
      title: "HelloFresh",
    };
  }
}

class HelloFreshCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this.shadowRoot.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 12px; }
        label { font-weight: 500; }
        input[type="text"] { width: 100%; padding: 8px; box-sizing: border-box; }
      </style>
      <div class="form">
        <div>
          <label>Entity</label>
          <input type="text" id="entity" value="${this._config.entity || ""}" />
        </div>
        <div>
          <label>Title</label>
          <input type="text" id="title" value="${this._config.title || "HelloFresh"}" />
        </div>
        <div>
          <label>
            <input type="checkbox" id="show_images" ${this._config.show_images !== false ? "checked" : ""} />
            Show meal images
          </label>
        </div>
      </div>
    `;

    this.shadowRoot.getElementById("entity").addEventListener("change", (e) => {
      this._config = { ...this._config, entity: e.target.value };
      this._dispatch();
    });
    this.shadowRoot.getElementById("title").addEventListener("change", (e) => {
      this._config = { ...this._config, title: e.target.value };
      this._dispatch();
    });
    this.shadowRoot.getElementById("show_images").addEventListener("change", (e) => {
      this._config = { ...this._config, show_images: e.target.checked };
      this._dispatch();
    });
  }

  _dispatch() {
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: this._config } })
    );
  }
}

customElements.define("hellofresh-card", HelloFreshCard);
customElements.define("hellofresh-card-editor", HelloFreshCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "hellofresh-card",
  name: "HelloFresh Menu Card",
  description: "Shows upcoming HelloFresh delivery weeks with meal selections",
  preview: true,
});
