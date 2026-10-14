// Vehicle path colours. Blue, amber and red are reserved (lockers, at-risk, critical), so vehicles use a
// separate set. Consecutive vehicles differ in hue (green, purple, burnt orange, teal, ...): the first two
// used to be green and teal, which could not be told apart, least of all on the dark basemap.
export const VEHICLE_COLORS = ["#1d6a46", "#8e3fb0", "#b4531a", "#0f7c86", "#3d4f5c", "#7d8a1f"] as const;
