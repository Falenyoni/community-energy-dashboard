// Fixed categorical order -- per the data-viz skill's non-negotiable rule,
// color follows the entity (the channel), never its sorted rank, so a
// channel keeps the same color in the ranking chart, the breakdown chart,
// and anywhere else it appears.
export const CHANNEL_ORDER = ['geyser', 'cooking', 'plugs', 'lighting', 'background', 'fridge'];

export const CHANNEL_COLOR_VAR = {
  geyser: '--series-1',
  cooking: '--series-2',
  plugs: '--series-3',
  lighting: '--series-4',
  background: '--series-5',
  fridge: '--series-6',
};

export function channelFromDeviceId(deviceId) {
  // device_id looks like "SITE-001-GEYSER"
  const suffix = deviceId.split('-').pop().toLowerCase();
  return CHANNEL_ORDER.includes(suffix) ? suffix : null;
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
