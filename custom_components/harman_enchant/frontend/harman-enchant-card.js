// SPDX-License-Identifier: AGPL-3.0-only
// Dashboard card of the Harman Kardon Enchant integration. It finds the
// entities of the speaker it is pointed at and shows only what that speaker has.

const DOMAIN = "harman_enchant";
const CARD_TYPE = "harman-enchant-card";

// MediaPlayerEntityFeature bits.
const PAUSE = 1;
const VOLUME_SET = 4;
const VOLUME_MUTE = 8;
const PREVIOUS_TRACK = 16;
const NEXT_TRACK = 32;
const TURN_ON = 128;
const TURN_OFF = 256;
const SELECT_SOURCE = 2048;
const PLAY = 16384;

const SOURCE_ICONS = {
  tv: "mdi:television",
  hdmi: "mdi:video-input-hdmi",
  bluetooth: "mdi:bluetooth",
  airplay: "mdi:cast-audio-variant",
  google_cast: "mdi:cast",
  spotify: "mdi:spotify",
  dlna: "mdi:dlna",
};
const INPUT_ICONS = { TV: "mdi:television", HDMI: "mdi:video-input-hdmi", Bluetooth: "mdi:bluetooth" };
const TOGGLES = [
  ["smart_mode", "mdi:brain"],
  ["listen_mode", "mdi:account-voice"],
  ["pure_voice", "mdi:account-tie-voice"],
  ["feedback_tones", "mdi:bell"],
];
const TIMER_PRESETS = [0, 15, 30, 60, 90, 120];
const TABS = [
  ["sound", "Sound", "mdi:tune-variant"],
  ["equalizer", "Equalizer", "mdi:equalizer"],
  ["timer", "Timer", "mdi:av-timer"],
  ["info", "Info", "mdi:information-outline"],
];
const HIDEABLE = [
  ["volume", "Volume"],
  ["inputs", "Inputs"],
  ["sound", "Sound tab"],
  ["equalizer", "Equalizer tab"],
  ["timer", "Timer tab"],
  ["info", "Info tab"],
];
const CHANNEL_GROUPS = {
  front: "Front",
  side: "Surround",
  back: "Rear",
  top_front: "Height front",
  top_middle: "Height middle",
  top_back: "Height rear",
};
const NO_VALUE = ["unknown", "unavailable"];
const PENDING_MS = 5000;
const CONFIRM_MS = 6000;

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

const clock = (seconds) => {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${m}:${rest}`;
};

const signed = (value) => (value > 0 ? `+${value}` : `${value}`);

const point = ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`;

// "front_left", "front_center", "top_front_left" -> "Front left, center · Height front left"
const channelNames = (channels) => {
  const groups = new Map();
  const other = [];
  for (const channel of channels) {
    const match = /^(.+)_(left|center|right)$/.exec(channel);
    if (channel === "low_frequency") other.push("Subwoofer");
    else if (match) groups.set(match[1], [...(groups.get(match[1]) || []), match[2]]);
    else other.push(channel.replace(/_/g, " "));
  }
  const named = [...groups].map(
    ([group, sides]) => `${CHANNEL_GROUPS[group] || group.replace(/_/g, " ")} ${sides.join(", ")}`
  );
  return [...named, ...other].join(" · ");
};

class HarmanEnchantCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._pending = {};
    this._dragging = false;
    this._signature = "";
    this._tab = null;
    this._confirmUntil = 0;
    this._error = null;
    this._timer = null;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    this.shadowRoot.addEventListener("pointerdown", (ev) => this._onPointerDown(ev));
    this.shadowRoot.addEventListener("keydown", (ev) => this._onKeyDown(ev));
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: { domain: "media_player", integration: DOMAIN } } },
        },
        { name: "name", selector: { text: {} } },
        {
          name: "hide",
          selector: {
            select: { multiple: true, options: HIDEABLE.map(([value, label]) => ({ value, label })) },
          },
        },
      ],
      computeLabel: (field) => ({ entity: "Speaker", name: "Name", hide: "Hide" })[field.name],
    };
  }

  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find(
      (e) => e.platform === DOMAIN && e.entity_id.startsWith("media_player.")
    );
    return { entity: entry ? entry.entity_id : "" };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Set entity to the media player of an Enchant speaker");
    }
    this._config = { hide: [], ...config };
    this._signature = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  connectedCallback() {
    this._timer = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
    this._resize?.disconnect();
  }

  // ---- entities ----

  _find() {
    const hass = this._hass;
    const media = this._config.entity;
    const found = { media, eq: [] };
    const deviceId = hass.entities?.[media]?.device_id;
    if (!deviceId) return found;
    for (const [id, entry] of Object.entries(hass.entities)) {
      if (entry.device_id !== deviceId || entry.platform !== DOMAIN || entry.hidden || !hass.states[id]) continue;
      if (entry.translation_key === "eq_band") found.eq.push(id);
      else if (entry.translation_key) found[entry.translation_key] = id;
    }
    found.eq.sort((a, b) => this._frequency(a) - this._frequency(b));
    found.deviceId = deviceId;
    return found;
  }

  _frequency(id) {
    const value = Number(this._hass.states[id]?.attributes?.frequency);
    if (Number.isFinite(value) && value > 0) return value;
    const match = /([\d.]+)\s*(k?)Hz/i.exec(this._name(id));
    return match ? Number(match[1]) * (match[2] ? 1000 : 1) : 0;
  }

  _name(id) {
    const hass = this._hass;
    const entry = hass.entities?.[id];
    if (entry?.name) return entry.name;
    const full = hass.states[id]?.attributes?.friendly_name || id;
    const device = entry?.device_id ? hass.devices?.[entry.device_id] : null;
    const prefix = device ? device.name_by_user || device.name : "";
    return prefix && full.startsWith(prefix) ? full.slice(prefix.length).trim() : full;
  }

  _format(stateObj, value) {
    if (!stateObj) return "";
    try {
      return this._hass.formatEntityState(stateObj, value);
    } catch (_err) {
      return value ?? stateObj.state;
    }
  }

  _value(id) {
    const pending = this._pending[id];
    const actual = this._hass.states[id]?.state;
    if (pending && Date.now() < pending.until && String(pending.value) !== String(actual)) return pending.value;
    delete this._pending[id];
    return actual;
  }

  _setPending(id, value) {
    this._pending[id] = { value, until: Date.now() + PENDING_MS };
  }

  _call(domain, service, data) {
    return this._hass.callService(domain, service, data).catch((err) => {
      this._error = err?.message || String(err);
      this._render();
    });
  }

  // ---- rendering ----

  _render() {
    if (!this._hass || !this._config || this._dragging) return;
    const ents = this._find();
    const media = this._hass.states[ents.media];
    const ids = [
      ...new Set([ents.media, ...Object.keys(ents).filter((k) => !["media", "eq", "deviceId"].includes(k)).map((k) => ents[k]), ...ents.eq]),
    ];
    const signature = JSON.stringify([
      this._config,
      this._tab,
      this._confirmUntil > Date.now(),
      this._error,
      this._pending.volume?.value,
      ids.map((id) => {
        const s = this._hass.states[id];
        return s ? [id, this._value(id), s.attributes] : [id];
      }),
    ]);
    if (signature === this._signature) return;
    this._signature = signature;
    this.shadowRoot.innerHTML = `<style>${STYLES}</style><ha-card>${
      media ? this._body(ents, media) : this._missing()
    }</ha-card>`;
    this._layoutEq();
    this._tick();
    this._resize?.disconnect();
    const eq = this.shadowRoot.querySelector(".eq");
    if (eq && window.ResizeObserver) {
      this._resize = new ResizeObserver(() => this._drawCurve());
      this._resize.observe(eq);
    }
  }

  _missing() {
    return `<div class="warning">Entity not found: ${esc(this._config.entity)}</div>`;
  }

  _body(ents, media) {
    const a = media.attributes;
    const features = a.supported_features || 0;
    const off = media.state === "off" || NO_VALUE.includes(media.state);
    const hide = new Set(this._config.hide || []);
    const device = this._hass.devices?.[ents.deviceId];
    const name = this._config.name || (device && (device.name_by_user || device.name)) || a.friendly_name;
    const source = this._hass.states[ents.playing_source];
    const sourceKey = source?.state;
    const sourceIcon = SOURCE_ICONS[sourceKey] || INPUT_ICONS[a.source] || "mdi:speaker";
    let sourceLabel = a.source || "";
    if (source && SOURCE_ICONS[sourceKey]) sourceLabel = this._format(source);
    else if (sourceKey === "other") sourceLabel = source.attributes.source_name || sourceLabel;
    const format = this._hass.states[ents.audio_format];
    const formatText = format && !NO_VALUE.includes(format.state) ? format.state : "";
    const picture = !off && a.entity_picture ? a.entity_picture : "";
    const title = !off && a.media_title ? a.media_title : name;
    let subtitle = this._format(media);
    if (!off && a.media_title) subtitle = [a.media_artist, a.media_album_name].filter(Boolean).join(" · ");
    else if (!off && formatText) subtitle = formatText;
    const atmos = this._hass.states[ents.dolby_atmos]?.state === "on";

    let html = `<div class="hero ${picture ? "has-art" : ""}"${
      picture ? ` style="--art: url('${encodeURI(picture).replace(/'/g, "%27")}')"` : ""
    }>
      <div class="art">${
        picture
          ? `<img src="${esc(picture)}" alt="">`
          : `<ha-icon icon="${off ? "mdi:speaker-off" : sourceIcon}"></ha-icon>`
      }</div>
      <div class="meta">
        <div class="title" title="${esc(title)}">${esc(title)}</div>
        <div class="subtitle" title="${esc(subtitle)}">${esc(subtitle)}</div>
        <div class="chips">${
          !off && sourceLabel
            ? `<span class="chip"><ha-icon icon="${sourceIcon}"></ha-icon>${esc(sourceLabel)}</span>`
            : ""
        }${atmos ? `<span class="chip accent"><ha-icon icon="mdi:dolby"></ha-icon>Dolby Atmos</span>` : ""}</div>
      </div>
      ${
        features & (TURN_ON | TURN_OFF)
          ? `<button class="icon power ${off ? "" : "on"}" data-action="power" title="${off ? "Turn on" : "Turn off"}"
               aria-label="${off ? "Turn on" : "Turn off"}"><ha-icon icon="mdi:power"></ha-icon></button>`
          : ""
      }
    </div>`;
    if (this._error) {
      html += `<button class="error" data-action="dismiss">${esc(this._error)}</button>`;
    }
    if (off) return html;

    if (a.media_duration > 0) {
      html += `<div class="progress"><div class="bar"><div class="fill"></div></div>
        <div class="times"><span class="pos"></span><span>${clock(a.media_duration)}</span></div></div>`;
    }

    const playing = media.state === "playing";
    const transport = [];
    if (features & PREVIOUS_TRACK) transport.push(this._iconButton("prev", "mdi:skip-previous", "Previous track"));
    if (features & (PLAY | PAUSE)) {
      transport.push(
        this._iconButton("playpause", playing ? "mdi:pause" : "mdi:play", playing ? "Pause" : "Play", "big")
      );
    }
    if (features & NEXT_TRACK) transport.push(this._iconButton("next", "mdi:skip-next", "Next track"));
    if (ents.moment) {
      transport.push(`<button class="pill" data-action="press" data-entity="${ents.moment}">
        <ha-icon icon="mdi:star-four-points-outline"></ha-icon>${esc(this._name(ents.moment))}</button>`);
    }
    if (transport.length) html += `<div class="transport">${transport.join("")}</div>`;

    if (!hide.has("volume") && features & VOLUME_SET) {
      const volume = Math.round(this._pending.volume?.value ?? (a.volume_level || 0) * 100);
      const muted = a.is_volume_muted;
      html += `<div class="volume">
        ${
          features & VOLUME_MUTE
            ? this._iconButton("mute", muted ? "mdi:volume-off" : "mdi:volume-high", muted ? "Unmute" : "Mute")
            : `<ha-icon icon="mdi:volume-high"></ha-icon>`
        }
        <input type="range" min="0" max="100" step="1" value="${volume}" data-slider="volume" aria-label="Volume">
        <span class="value" data-label="volume">${volume}%</span>
      </div>`;
    }

    if (!hide.has("inputs") && features & SELECT_SOURCE && (a.source_list || []).length) {
      html += `<div class="row inputs">${a.source_list
        .map(
          (src) => `<button class="pill ${src === a.source ? "active" : ""}" data-action="source" data-value="${esc(src)}">
            <ha-icon icon="${INPUT_ICONS[src] || "mdi:import"}"></ha-icon>${esc(src)}</button>`
        )
        .join("")}</div>`;
    }

    const panels = {
      sound: this._soundPanel(ents),
      equalizer: this._equalizerPanel(ents),
      timer: this._timerPanel(ents),
      info: this._infoPanel(ents),
    };
    const tabs = TABS.filter(([key]) => panels[key] && !hide.has(key));
    if (tabs.length) {
      if (!tabs.some(([key]) => key === this._tab)) this._tab = tabs[0][0];
      html += `<div class="tabs" role="tablist">${tabs
        .map(
          ([key, label, icon]) => `<button role="tab" class="tab ${key === this._tab ? "active" : ""}"
            aria-selected="${key === this._tab}" data-action="tab" data-value="${key}">
            <ha-icon icon="${icon}"></ha-icon><span>${label}</span></button>`
        )
        .join("")}</div><div class="panel">${panels[this._tab]}</div>`;
    }
    return html;
  }

  _iconButton(action, icon, label, extra = "") {
    return `<button class="icon ${extra}" data-action="${action}" title="${label}" aria-label="${label}">
      <ha-icon icon="${icon}"></ha-icon></button>`;
  }

  _soundPanel(ents) {
    const parts = [];
    const atmos = this._hass.states[ents.atmos_level];
    if (atmos) {
      const value = this._value(ents.atmos_level);
      parts.push(`<div class="label">${esc(this._name(ents.atmos_level))}</div><div class="segmented">${(
        atmos.attributes.options || []
      )
        .map(
          (opt) => `<button class="${opt === value ? "active" : ""}" data-action="select"
            data-entity="${ents.atmos_level}" data-value="${esc(opt)}">${esc(this._format(atmos, opt))}</button>`
        )
        .join("")}</div>`);
    }
    for (const [key, icon] of TOGGLES) {
      const id = ents[key];
      if (!id) continue;
      const on = this._value(id) === "on";
      parts.push(`<button class="toggle" data-action="toggle" data-entity="${id}" role="switch" aria-checked="${on}">
        <ha-icon icon="${icon}"></ha-icon><span class="name">${esc(this._name(id))}</span>
        <span class="switch ${on ? "on" : ""}"></span></button>`);
    }
    const sync = this._hass.states[ents.audio_sync];
    if (sync) {
      const value = Number(this._value(ents.audio_sync)) || 0;
      const unit = sync.attributes.unit_of_measurement || "ms";
      parts.push(`<div class="label">${esc(this._name(ents.audio_sync))}
        <span class="value" data-label="${ents.audio_sync}">${value} ${esc(unit)}</span></div>
        <input type="range" min="${sync.attributes.min}" max="${sync.attributes.max}" step="${sync.attributes.step}"
          value="${value}" data-slider="number" data-entity="${ents.audio_sync}" data-unit=" ${esc(unit)}"
          aria-label="${esc(this._name(ents.audio_sync))}">`);
    }
    if (ents.calibrate) {
      const confirm = this._confirmUntil > Date.now();
      parts.push(`<button class="pill wide ${confirm ? "warn" : ""}" data-action="calibrate" data-entity="${ents.calibrate}">
        <ha-icon icon="mdi:sine-wave"></ha-icon>${
          confirm ? "Tap again: test tones play for about a minute" : esc(this._name(ents.calibrate))
        }</button>`);
    }
    return parts.join("");
  }

  _equalizerPanel(ents) {
    const preset = this._hass.states[ents.eq_preset];
    if (!preset && !ents.eq.length) return "";
    let html = "";
    if (preset) {
      const value = this._value(ents.eq_preset);
      html += `<div class="row presets">${(preset.attributes.options || [])
        .map(
          (opt) => `<button class="pill ${opt === value ? "active" : ""}" data-action="select"
            data-entity="${ents.eq_preset}" data-value="${esc(opt)}">${esc(this._format(preset, opt))}</button>`
        )
        .join("")}</div>`;
    }
    if (ents.eq.length) {
      html += `<div class="eq"><svg class="curve" aria-hidden="true"><path class="area"></path><path class="line"></path></svg>${ents.eq
        .map((id) => {
          const s = this._hass.states[id];
          const value = Number(this._value(id));
          const known = Number.isFinite(value);
          const { min, max, step } = s.attributes;
          const freq = this._frequency(id);
          const label = freq >= 1000 ? `${freq / 1000}k` : `${freq}`;
          return `<div class="band">
            <span class="gain" data-label="${id}">${known ? signed(value) : "–"}</span>
            <div class="track" data-eq="${id}" data-min="${min}" data-max="${max}" data-step="${step}"
              data-value="${known ? value : 0}" tabindex="0" role="slider" aria-valuemin="${min}"
              aria-valuemax="${max}" aria-valuenow="${known ? value : 0}" aria-label="${esc(this._name(id))}">
              <div class="zero"></div><div class="thumb"></div>
            </div>
            <span class="freq">${label}</span>
          </div>`;
        })
        .join("")}</div><div class="hint">Hz · dB${
        preset && (preset.attributes.options || []).includes("Custom")
          ? ` · changing a band selects ${esc(this._format(preset, "Custom"))}`
          : ""
      }</div>`;
    }
    return html;
  }

  _timerPanel(ents) {
    const timer = this._hass.states[ents.sleep_timer];
    if (!timer) return "";
    const value = Number(this._value(ents.sleep_timer)) || 0;
    const remaining = Number(this._hass.states[ents.sleep_timer_remaining]?.state);
    const max = Number(timer.attributes.max) || 120;
    let hint = "Sleep timer is off";
    if (value && remaining > 0) hint = `Switches to standby in ${Math.round(remaining)} min`;
    else if (value) hint = `Set to ${value} min`;
    return `<div class="row presets">${TIMER_PRESETS.filter((m) => m <= max)
      .map(
        (m) => `<button class="pill ${m === value ? "active" : ""}" data-action="number"
          data-entity="${ents.sleep_timer}" data-value="${m}">${m ? `${m} min` : "Off"}</button>`
      )
      .join("")}</div><div class="hint">${hint}</div>`;
  }

  _infoPanel(ents) {
    const rows = [];
    const add = (id, value) => {
      rows.push(`<div class="info"><span>${esc(this._name(id))}</span><span>${esc(value)}</span></div>`);
    };
    const source = this._hass.states[ents.playing_source];
    if (source) {
      const raw = source.state === "other" ? ` (${source.attributes.source_name})` : "";
      add(ents.playing_source, this._format(source) + raw);
    }
    const format = this._hass.states[ents.audio_format];
    if (format) add(ents.audio_format, this._format(format));
    const atmos = this._hass.states[ents.dolby_atmos];
    if (atmos) add(ents.dolby_atmos, this._format(atmos));
    const layout = this._hass.states[ents.surround_layout];
    if (layout) {
      add(ents.surround_layout, this._format(layout));
      for (const member of layout.attributes.members || []) {
        const channels = channelNames(member.channels || []);
        rows.push(`<div class="info member"><span>${esc(member.name || member.model)}</span><span>${esc(channels)}</span></div>`);
      }
    }
    return rows.length > 1 ? rows.join("") : "";
  }

  _tick() {
    const media = this._hass?.states[this._config?.entity];
    const progress = this.shadowRoot.querySelector(".progress");
    if (!media || !progress) return;
    const a = media.attributes;
    let position = Number(a.media_position) || 0;
    if (media.state === "playing" && a.media_position_updated_at) {
      position += (Date.now() - new Date(a.media_position_updated_at).getTime()) / 1000;
    }
    position = Math.min(position, a.media_duration);
    progress.querySelector(".fill").style.width = `${(100 * position) / a.media_duration}%`;
    progress.querySelector(".pos").textContent = clock(position);
  }

  _layoutEq() {
    for (const track of this.shadowRoot.querySelectorAll(".track")) {
      this._paintBand(track, Number(track.dataset.value), false);
    }
    this._drawCurve();
  }

  _paintBand(track, value, curve = true) {
    const min = Number(track.dataset.min);
    const max = Number(track.dataset.max);
    const pct = (v) => (100 * (max - v)) / (max - min);
    track.querySelector(".thumb").style.top = `${pct(value)}%`;
    track.querySelector(".zero").style.top = `${pct(Math.min(Math.max(0, min), max))}%`;
    track.setAttribute("aria-valuenow", value);
    const label = this.shadowRoot.querySelector(`[data-label="${track.dataset.eq}"]`);
    if (label) label.textContent = signed(value);
    if (curve) this._drawCurve();
  }

  // A smooth line through the band values, filled to the 0 dB line.
  _drawCurve() {
    const eq = this.shadowRoot.querySelector(".eq");
    const svg = eq?.querySelector(".curve");
    if (!svg) return;
    const box = eq.getBoundingClientRect();
    const tracks = [...eq.querySelectorAll(".track")];
    if (!box.width || !tracks.length) return;
    const centre = (el) => {
      const rect = el.getBoundingClientRect();
      return [rect.left + rect.width / 2 - box.left, rect.top + rect.height / 2 - box.top];
    };
    const bands = tracks.map((track) => [centre(track)[0], centre(track.querySelector(".thumb"))[1]]);
    const zero = centre(tracks[0].querySelector(".zero"))[1];
    const pts = [[0, bands[0][1]], ...bands, [box.width, bands[bands.length - 1][1]]];
    let d = `M${point(pts[0])}`;
    for (let i = 0; i < pts.length - 1; i += 1) {
      const p0 = pts[i - 1] || pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] || p2;
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
      const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C${point(c1)} ${point(c2)} ${point(p2)}`;
    }
    svg.setAttribute("viewBox", `0 0 ${box.width.toFixed(1)} ${box.height.toFixed(1)}`);
    svg.querySelector(".line").setAttribute("d", d);
    svg.querySelector(".area").setAttribute("d", `${d} L${point([box.width, zero])} L${point([0, zero])} Z`);
  }

  // ---- events ----

  _onClick(ev) {
    const el = ev.target.closest("[data-action]");
    if (!el) return;
    const media = this._config.entity;
    const state = this._hass.states[media];
    const { action, entity, value } = el.dataset;
    switch (action) {
      case "power":
        this._call("media_player", state.state === "off" ? "turn_on" : "turn_off", { entity_id: media });
        break;
      case "playpause":
        this._call("media_player", state.state === "playing" ? "media_pause" : "media_play", { entity_id: media });
        break;
      case "prev":
        this._call("media_player", "media_previous_track", { entity_id: media });
        break;
      case "next":
        this._call("media_player", "media_next_track", { entity_id: media });
        break;
      case "mute":
        this._call("media_player", "volume_mute", {
          entity_id: media,
          is_volume_muted: !state.attributes.is_volume_muted,
        });
        break;
      case "source":
        this._call("media_player", "select_source", { entity_id: media, source: value });
        break;
      case "select":
        this._setPending(entity, value);
        this._call("select", "select_option", { entity_id: entity, option: value });
        break;
      case "toggle": {
        const on = this._value(entity) === "on";
        this._setPending(entity, on ? "off" : "on");
        this._call("switch", on ? "turn_off" : "turn_on", { entity_id: entity });
        break;
      }
      case "number":
        this._setPending(entity, value);
        this._call("number", "set_value", { entity_id: entity, value: Number(value) });
        break;
      case "press":
        this._call("button", "press", { entity_id: entity });
        break;
      case "calibrate":
        if (this._confirmUntil > Date.now()) {
          this._confirmUntil = 0;
          this._call("button", "press", { entity_id: entity });
        } else {
          this._confirmUntil = Date.now() + CONFIRM_MS;
          setTimeout(() => this._render(), CONFIRM_MS + 50);
        }
        break;
      case "tab":
        this._tab = value;
        break;
      case "dismiss":
        this._error = null;
        break;
      default:
        return;
    }
    this._render();
  }

  _onInput(ev) {
    const el = ev.target;
    if (!el.dataset?.slider) return;
    this._dragging = true;
    const volume = el.dataset.slider === "volume";
    const label = this.shadowRoot.querySelector(`[data-label="${volume ? "volume" : el.dataset.entity}"]`);
    if (label) label.textContent = volume ? `${el.value}%` : `${el.value}${el.dataset.unit || ""}`;
  }

  _onChange(ev) {
    const el = ev.target;
    if (!el.dataset?.slider) return;
    this._dragging = false;
    const value = Number(el.value);
    if (el.dataset.slider === "volume") {
      this._pending.volume = { value };
      this._call("media_player", "volume_set", { entity_id: this._config.entity, volume_level: value / 100 });
      setTimeout(() => {
        delete this._pending.volume;
        this._render();
      }, 1500);
    } else {
      this._setPending(el.dataset.entity, value);
      this._call("number", "set_value", { entity_id: el.dataset.entity, value });
    }
    this._render();
  }

  _bandValue(track, clientY) {
    const rect = track.getBoundingClientRect();
    const min = Number(track.dataset.min);
    const max = Number(track.dataset.max);
    const step = Number(track.dataset.step) || 0.5;
    const ratio = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
    const raw = max - ratio * (max - min);
    return Math.min(max, Math.max(min, Math.round(raw / step) * step));
  }

  _commitBand(track, value) {
    const id = track.dataset.eq;
    track.dataset.value = value;
    if (Number(this._hass.states[id]?.state) === value) return;
    this._setPending(id, value);
    this._call("number", "set_value", { entity_id: id, value });
  }

  _onPointerDown(ev) {
    const track = ev.target.closest(".track");
    if (!track) return;
    ev.preventDefault();
    this._dragging = true;
    track.setPointerCapture(ev.pointerId);
    track.classList.add("dragging");
    let value = this._bandValue(track, ev.clientY);
    this._paintBand(track, value);
    const move = (e) => {
      value = this._bandValue(track, e.clientY);
      this._paintBand(track, value);
    };
    const up = () => {
      track.removeEventListener("pointermove", move);
      track.removeEventListener("pointerup", up);
      track.removeEventListener("pointercancel", up);
      track.classList.remove("dragging");
      this._dragging = false;
      this._commitBand(track, value);
      this._render();
    };
    track.addEventListener("pointermove", move);
    track.addEventListener("pointerup", up);
    track.addEventListener("pointercancel", up);
  }

  _onKeyDown(ev) {
    const track = ev.target.closest?.(".track");
    if (!track || !["ArrowUp", "ArrowDown", "ArrowRight", "ArrowLeft"].includes(ev.key)) return;
    ev.preventDefault();
    const step = Number(track.dataset.step) || 0.5;
    const up = ev.key === "ArrowUp" || ev.key === "ArrowRight";
    const value = Math.min(
      Number(track.dataset.max),
      Math.max(Number(track.dataset.min), Number(track.dataset.value) + (up ? step : -step))
    );
    track.dataset.value = value;
    this._paintBand(track, value);
    clearTimeout(this._keyTimer);
    this._keyTimer = setTimeout(() => this._commitBand(track, value), 600);
  }
}

const STYLES = `
  :host { display: block; }
  ha-card { overflow: hidden; padding-bottom: 12px; }
  button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; padding: 0; }
  button:focus-visible, .track:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  ha-icon { --mdc-icon-size: 20px; }
  .warning { padding: 16px; color: var(--error-color); }
  .error { display: block; width: calc(100% - 32px); margin: 0 16px 8px; padding: 8px; border-radius: 8px; text-align: left;
    font-size: 0.9em; color: var(--error-color); background: var(--secondary-background-color); }
  .hero { position: relative; display: flex; align-items: center; gap: 16px; padding: 16px; isolation: isolate; }
  .hero.has-art::before { content: ""; position: absolute; inset: -40px; z-index: -1; background: var(--art) center / cover;
    filter: blur(40px); opacity: 0.35; }
  .art { flex: none; width: 88px; height: 88px; border-radius: 12px; overflow: hidden; display: flex; align-items: center;
    justify-content: center; background: var(--secondary-background-color); color: var(--state-icon-color, var(--primary-color)); }
  .art img { width: 100%; height: 100%; object-fit: cover; }
  .art ha-icon { --mdc-icon-size: 44px; }
  .meta { flex: 1; min-width: 0; }
  .title { font-size: 1.15em; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .subtitle { color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 0.8em; padding: 2px 8px; border-radius: 12px;
    background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .chip ha-icon { --mdc-icon-size: 14px; }
  .chip.accent { color: var(--primary-color); }
  .icon { width: 40px; height: 40px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
    color: var(--primary-text-color); flex: none; }
  .icon:hover { background: var(--secondary-background-color); }
  .icon.big { width: 56px; height: 56px; background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .icon.big ha-icon { --mdc-icon-size: 32px; }
  .power { align-self: flex-start; color: var(--secondary-text-color); }
  .power.on { color: var(--primary-color); }
  .progress { padding: 0 16px; }
  .bar { height: 4px; border-radius: 2px; background: var(--divider-color); overflow: hidden; }
  .bar .fill { height: 100%; width: 0; background: var(--primary-color); }
  .times { display: flex; justify-content: space-between; font-size: 0.75em; color: var(--secondary-text-color); margin-top: 4px; }
  .transport { display: flex; align-items: center; justify-content: center; gap: 16px; flex-wrap: wrap; padding: 4px 16px 8px; }
  .volume { display: flex; align-items: center; gap: 8px; padding: 0 16px 4px; }
  input[type="range"] { flex: 1; width: 100%; accent-color: var(--primary-color); margin: 8px 0; }
  .value { font-size: 0.85em; color: var(--secondary-text-color); min-width: 3em; text-align: right; }
  .row { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 16px; }
  .pill { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 18px;
    border: 1px solid var(--divider-color); font-size: 0.9em; }
  .pill ha-icon { --mdc-icon-size: 18px; }
  .pill.active { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .pill.wide { width: 100%; justify-content: center; margin-top: 12px; }
  .pill.warn { border-color: var(--warning-color); color: var(--warning-color); }
  .tabs { display: flex; margin: 8px 16px 0; border-bottom: 1px solid var(--divider-color); }
  .tab { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 4px;
    color: var(--secondary-text-color); font-size: 0.8em; border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  .panel { padding: 12px 16px 0; }
  .panel .row { padding: 0 0 8px; }
  .label { display: flex; justify-content: space-between; align-items: baseline; font-size: 0.9em; margin: 8px 0 6px;
    color: var(--secondary-text-color); }
  .segmented { display: flex; border: 1px solid var(--divider-color); border-radius: 18px; overflow: hidden; }
  .segmented button { flex: 1; padding: 8px 4px; font-size: 0.9em; }
  .segmented button + button { border-left: 1px solid var(--divider-color); }
  .segmented button.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .toggle { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 0; text-align: left; }
  .toggle .name { flex: 1; }
  .toggle ha-icon { color: var(--state-icon-color, var(--secondary-text-color)); }
  .switch { position: relative; width: 36px; height: 20px; border-radius: 10px; background: var(--disabled-color, #bdbdbd);
    flex: none; transition: background 0.2s; }
  .switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
    background: #fff; transition: left 0.2s; }
  .switch.on { background: var(--primary-color); }
  .switch.on::after { left: 18px; }
  .eq { position: relative; display: flex; justify-content: space-between; gap: 4px; padding: 4px 0; }
  .curve { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
  .curve .line { fill: none; stroke: var(--primary-color); stroke-width: 2.5; stroke-linejoin: round; }
  .curve .area { fill: var(--primary-color); opacity: 0.18; }
  .band { position: relative; flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
  .gain, .freq { font-size: 0.75em; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .track { position: relative; width: 28px; height: 150px; cursor: pointer; touch-action: none; }
  .track::before { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; transform: translateX(-50%);
    border-radius: 1px; background: var(--divider-color); }
  .zero { position: absolute; left: 4px; right: 4px; height: 1px; background: var(--secondary-text-color); opacity: 0.5; }
  .thumb { position: absolute; left: 50%; width: 18px; height: 18px; border-radius: 50%; transform: translate(-50%, -50%);
    background: var(--primary-color); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3); transition: transform 0.1s; }
  .track.dragging .thumb { transform: translate(-50%, -50%) scale(1.2); }
  .hint { font-size: 0.75em; color: var(--secondary-text-color); text-align: center; padding-bottom: 4px; }
  .info { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; font-size: 0.9em; }
  .info span:first-child { color: var(--secondary-text-color); }
  .info span:last-child { text-align: right; }
  .info.member { padding: 2px 0 2px 12px; font-size: 0.8em; }
`;

const register = () => {
  if (customElements.get(CARD_TYPE)) return;
  customElements.define(CARD_TYPE, HarmanEnchantCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TYPE,
    name: "Harman Kardon Enchant",
    description: "Now playing, volume, input and sound settings of an Enchant soundbar or speaker.",
    preview: true,
    documentationURL: "https://github.com/bazsc20ne/ha-harman-enchant",
  });
};

// The frontend can replace the custom element registry after this module has
// run; a card defined before that is unknown to the dashboards. Register once
// the frontend's root element exists, as the registry is final by then.
customElements.whenDefined("home-assistant").then(register);
