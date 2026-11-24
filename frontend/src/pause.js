// Timed pause: units, preset periods and display helpers shared by Config, AppConfig and Dashboard.

export const PAUSE_UNITS = ['minutes', 'hours', 'days', 'months'];

// Mirrors MAX_PAUSE_VALUE and MAX_PRESETS in backend/pause.py
export const MAX_PAUSE_VALUE = { minutes: 525600, hours: 8760, days: 365, months: 12 };
export const MAX_PRESETS = 10;

export const DEFAULT_PRESETS = [
    { value: 30, unit: 'minutes' },
    { value: 1, unit: 'hours' },
    { value: 1, unit: 'days' },
    { value: 1, unit: 'months' },
];

export const isValidPeriod = (p) =>
    PAUSE_UNITS.includes(p?.unit) && Number.isInteger(p?.value) && p.value >= 1 && p.value <= MAX_PAUSE_VALUE[p.unit];

// The backend stores the list sanitized; this only guards against a missing section
export const pausePresets = (appConfig) => {
    const presets = appConfig?.pause?.presets;
    return Array.isArray(presets) ? presets.filter(isValidPeriod) : DEFAULT_PRESETS;
};

export const formatDuration = (value, unit) => {
    const n = Number(value);
    return `${n} ${n === 1 ? unit.replace(/s$/, '') : unit}`;
};

const pad = (n) => String(n).padStart(2, '0');

// DD/MM/YYYY HH:mm in the browser's local time
export const formatPausedUntil = (epochSeconds) => {
    const d = new Date(epochSeconds * 1000);
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
