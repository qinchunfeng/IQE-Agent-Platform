export type IconName =
  | "dashboard"
  | "canvas"
  | "traces"
  | "data"
  | "plugins"
  | "knowledge"
  | "experiment"
  | "play"
  | "arrow"
  | "refresh"
  | "check"
  | "close"
  | "alert"
  | "clock"
  | "ticket"
  | "cpu"
  | "search"
  | "settings"
  | "plus"
  | "external"
  | "stop"
  | "spark"
  | "shield"
  | "layers";

const PATHS: Record<IconName, string[]> = {
  dashboard: [
    "M3 3h7v7H3z",
    "M14 3h7v4h-7z",
    "M14 11h7v10h-7z",
    "M3 14h7v7H3z",
  ],
  canvas: [
    "M5 6h5v5H5z",
    "M14 5h5v5h-5z",
    "M9 16h5v5H9z",
    "M10 8.5h4",
    "M7.5 11v5",
    "M16.5 10v3l-5 3",
  ],
  traces: ["M3 12h4l2-7 4 14 2-7h6"],
  data: [
    "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z",
    "M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6",
    "M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  ],
  plugins: [
    "M10 3h4v3a2 2 0 0 0 2 2h3v4h-3a2 2 0 0 0-2 2v3h-4v-3a2 2 0 0 0-2-2H5V8h3a2 2 0 0 0 2-2V3z",
  ],
  knowledge: [
    "M4 5a3 3 0 0 1 3-3h13v17H7a3 3 0 0 0-3 3z",
    "M4 5v15",
    "M8 7h8",
    "M8 11h6",
  ],
  experiment: [
    "M4 20V10",
    "M10 20V4",
    "M16 20v-7",
    "M22 20H2",
  ],
  play: ["M8 5l11 7-11 7z"],
  arrow: ["M5 12h14", "M13 6l6 6-6 6"],
  refresh: ["M20 7v5h-5", "M4 17v-5h5", "M6.1 8a7 7 0 0 1 11.5-1L20 12", "M4 12l2.4 5a7 7 0 0 0 11.5-1"],
  check: ["M4 12l5 5L20 6"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  alert: ["M12 3l10 18H2z", "M12 9v5", "M12 17.5v.5"],
  clock: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7v5l3 2"],
  ticket: [
    "M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z",
    "M9 6v12",
  ],
  cpu: [
    "M7 7h10v10H7z",
    "M9 3v2M15 3v2M9 19v2M15 19v2M3 9h2M3 15h2M19 9h2M19 15h2",
  ],
  search: ["M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z", "M20 20l-4-4"],
  settings: [
    "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-4l-.4 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4L6 11a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2-1.5a7 7 0 0 0 .1-1z",
  ],
  plus: ["M12 5v14", "M5 12h14"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"],
  stop: ["M7 7h10v10H7z"],
  spark: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"],
  shield: ["M12 3l8 3v6c0 4.5-3.4 7.5-8 9-4.6-1.5-8-4.5-8-9V6z", "M9 12l2 2 4-4"],
  layers: ["M12 3l9 5-9 5-9-5z", "M3 12l9 5 9-5", "M3 16l9 5 9-5"],
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

export function Icon({ name, size = 18, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {PATHS[name].map((path, index) => (
        <path key={index} d={path} />
      ))}
    </svg>
  );
}
