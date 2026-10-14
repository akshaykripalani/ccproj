import { useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  CircleAlert,
  Clock3,
  LoaderCircle,
  RotateCcw,
  Thermometer,
  Unplug,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "./api";
import { ago, modeName, motorName, number, when } from "./format";
import { usePoll } from "./hooks";
import type { Control, Device, Mode, Reading } from "./types";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" />
      {children}
    </span>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <CircleAlert size={18} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <Activity size={26} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
export function Loading({ label = "Loading live data…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={20} className="spin" />
      {label}
    </div>
  );
}
export function Heading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function PanelHead({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-head">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function MotorDrawing({
  active = true,
  small = false,
}: {
  active?: boolean;
  small?: boolean;
}) {
  return (
    <svg
      className={`motor-drawing ${small ? "small" : ""} ${active ? "running" : ""}`}
      viewBox="0 0 220 100"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M26 84H191"
        stroke="currentColor"
        strokeOpacity=".16"
        strokeWidth="2"
      />
      <path
        d="M53 70V82H79V71M128 70V82H154V71"
        fill="currentColor"
        fillOpacity=".2"
      />
      <rect
        x="45"
        y="26"
        width="113"
        height="47"
        rx="8"
        fill="currentColor"
        fillOpacity=".12"
        stroke="currentColor"
        strokeOpacity=".4"
      />
      <rect
        x="78"
        y="12"
        width="36"
        height="14"
        rx="3"
        fill="currentColor"
        fillOpacity=".18"
        stroke="currentColor"
        strokeOpacity=".4"
      />
      <path
        d="M72 33V65M82 33V65M92 33V65M102 33V65M112 33V65M122 33V65M132 33V65"
        stroke="currentColor"
        strokeOpacity=".32"
        strokeWidth="3"
      />
      <rect
        x="150"
        y="35"
        width="20"
        height="29"
        rx="3"
        fill="currentColor"
        fillOpacity=".22"
        stroke="currentColor"
        strokeOpacity=".4"
      />
      <path d="M170 49H193" stroke="currentColor" strokeWidth="8" />
      <circle
        cx="54"
        cy="49"
        r="16"
        fill="var(--card)"
        stroke="currentColor"
        strokeOpacity=".5"
      />
      <g className="rotor">
        <path
          d="M54 38V60M43 49H65"
          stroke="currentColor"
          strokeOpacity=".5"
          strokeWidth="3"
        />
        <circle cx="54" cy="49" r="4" fill="currentColor" />
      </g>
      <path
        d="M188 40V58"
        stroke="currentColor"
        strokeOpacity=".3"
        strokeWidth="2"
      />
    </svg>
  );
}

export function deviceCondition(device: Device) {
  if (!device.online) return { label: "Offline", tone: "neutral" };
  if (Object.values(device.latest?.rules ?? {}).some((rule) => rule.active))
    return { label: "Fault active", tone: "danger" };
  if (Object.values(device.latest?.rules ?? {}).some((rule) => rule.above > 0))
    return { label: "Threshold breach", tone: "warning" };
  if (device.latest?.operatingState === "stopped")
    return { label: "Stopped", tone: "neutral" };
  return { label: "Healthy", tone: "success" };
}

export function ControlStatus({ control }: { control: Control }) {
  return (
    <div className={`control-status ${control.status}`}>
      {control.status === "pending" ? (
        <Clock3 size={15} />
      ) : control.status === "failed" ? (
        <CircleAlert size={15} />
      ) : (
        <Check size={15} />
      )}
      <div>
        <span>
          Requested: <strong>{modeName(control.requestedMode)}</strong>
        </span>
        <span>
          Applied: <strong>{modeName(control.appliedMode)}</strong>
        </span>
        <small>
          {control.status === "pending"
            ? "Waiting for simulator acknowledgement"
            : control.status === "failed"
              ? control.reason || "Acknowledgement timed out"
              : `Acknowledged ${when(control.appliedAt)}`}
        </small>
      </div>
    </div>
  );
}

export function Controls({
  device,
  operator,
  refresh,
}: {
  device: Device;
  operator: boolean;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState<Control>();
  const [error, setError] = useState("");
  const control =
    requested &&
    requested.requestId !== device.control.requestId &&
    Date.parse(requested.requestedAt ?? "") >
      Date.parse(device.control.requestedAt ?? "1970-01-01")
      ? requested
      : device.control;
  async function change(mode: Mode) {
    setBusy(true);
    setError("");
    try {
      setRequested(
        await api<Control>(`/controls/${device.deviceId}`, {
          method: "POST",
          body: { mode },
        }),
      );
      refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Command could not be sent. Check current mode before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="controls"
      aria-label={`${motorName(device.deviceId)} controls`}
    >
      <ControlStatus control={control} />
      {operator ? (
        <div className="control-buttons">
          <button
            onClick={() => void change("overheat")}
            disabled={busy}
            className="control-button"
          >
            <Thermometer size={15} />
            Overheat
          </button>
          <button
            onClick={() => void change("vibration")}
            disabled={busy}
            className="control-button"
          >
            <Activity size={15} />
            Vibration fault
          </button>
          <button
            onClick={() => void change("disconnect")}
            disabled={busy}
            className="control-button"
          >
            <Unplug size={15} />
            Disconnect
          </button>
          <button
            onClick={() => void change("normal")}
            disabled={busy}
            className="control-button reset"
          >
            <RotateCcw size={15} />
            Reset
          </button>
        </div>
      ) : (
        <p className="muted tiny">
          Viewer access · An operator can change motor modes.
        </p>
      )}
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

export function MotorCard({
  device,
  now,
  operator,
  refresh,
}: {
  device: Device;
  now: number;
  operator: boolean;
  refresh: () => void;
}) {
  const condition = deviceCondition(device);
  return (
    <article
      className={`motor-card panel ${condition.tone}`}
      data-testid={device.deviceId}
    >
      <div className="motor-card-head">
        <div>
          <span className="eyebrow">
            EQUIPMENT / {device.deviceId.slice(-2)}
          </span>
          <h2>
            <a href={`#/devices/${device.deviceId}`}>
              {motorName(device.deviceId)} <ArrowRight size={16} />
            </a>
          </h2>
        </div>
        <Badge tone={condition.tone}>{condition.label}</Badge>
      </div>
      <div className="motor-visual">
        <MotorDrawing
          active={device.online && device.latest?.operatingState === "running"}
        />
        <span className="motor-subtitle">
          Factory gateway · {device.latest?.operatingState ?? "Awaiting data"}
        </span>
      </div>
      <div className="motor-metrics">
        <div>
          <Thermometer size={15} />
          <span>Temperature</span>
          <strong>
            {number(device.latest?.temperatureC)}
            <small> °C</small>
          </strong>
        </div>
        <div>
          <Activity size={15} />
          <span>Vibration</span>
          <strong>
            {number(device.latest?.vibrationMmS, 2)}
            <small> mm/s</small>
          </strong>
        </div>
        <div>
          <Zap size={15} />
          <span>Power</span>
          <strong>
            {number(device.latest?.powerWatts, 0)}
            <small> W</small>
          </strong>
        </div>
      </div>
      <div className="freshness">
        <span className={`status-dot ${device.online ? "online" : ""}`} />
        Last received {ago(device.lastSeen, now)}
        <span title={when(device.latest?.observedAt)}>
          Observed {ago(device.latest?.observedAt, now)}
        </span>
      </div>
      <Controls device={device} operator={operator} refresh={refresh} />
    </article>
  );
}

export const metrics = {
  temperatureC: {
    title: "Temperature",
    unit: "°C",
    color: "#237b68",
    threshold: 75,
  },
  vibrationMmS: {
    title: "Vibration",
    unit: "mm/s",
    color: "#bf7840",
    threshold: 4.5,
  },
  powerWatts: {
    title: "Power draw",
    unit: "W",
    color: "#6478b2",
    threshold: undefined,
  },
};

export function TelemetryChart({
  readings,
  field,
  id,
  threshold = true,
}: {
  readings: Reading[];
  field: keyof typeof metrics;
  id: string;
  threshold?: boolean;
}) {
  const metric = metrics[field];
  const ordered = [...readings].sort((a, b) =>
    a.observedAt.localeCompare(b.observedAt),
  );
  const points: {
    time: number;
    temperatureC: number | null;
    vibrationMmS: number | null;
    powerWatts: number | null;
  }[] = [];
  for (const [index, reading] of ordered.entries()) {
    const time = Date.parse(reading.observedAt);
    if (index && time - Date.parse(ordered[index - 1].observedAt) > 25000) {
      points.push({
        time: time - 1,
        temperatureC: null,
        vibrationMmS: null,
        powerWatts: null,
      });
    }
    points.push({ ...reading, time });
  }
  if (!points.length)
    return (
      <Empty
        title="No readings in this window"
        text="Readings appear here as the motor reports. Try a wider time range."
      />
    );
  return (
    <div
      className="chart"
      role="img"
      aria-label={`${metric.title} chart with ${readings.length} readings in ${metric.unit}`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <AreaChart
          data={points}
          margin={{ top: 18, right: 12, bottom: 0, left: -20 }}
          accessibilityLayer
        >
          <defs>
            <linearGradient
              id={`fill-${id}-${field}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" stopColor={metric.color} stopOpacity={0.2} />
              <stop offset="100%" stopColor={metric.color} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="#e8ebe5"
            vertical={false}
            strokeDasharray="3 4"
          />
          <XAxis
            dataKey="time"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(time) =>
              new Date(time).toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
              })
            }
            tick={{ fontSize: 11, fill: "#78847c" }}
            axisLine={false}
            tickLine={false}
            minTickGap={45}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 11, fill: "#78847c" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            labelFormatter={(time) => new Date(Number(time)).toLocaleString()}
            formatter={(value) => [
              `${number(value, field === "vibrationMmS" ? 2 : 1)} ${metric.unit}`,
              metric.title,
            ]}
          />
          {threshold && metric.threshold !== undefined && (
            <ReferenceLine
              y={metric.threshold}
              ifOverflow="extendDomain"
              stroke="#c0775c"
              strokeDasharray="4 4"
              label={{
                value: `Limit ${metric.threshold}`,
                position: "insideTopRight",
                fill: "#a8614b",
                fontSize: 11,
              }}
            />
          )}
          <Area
            type="monotone"
            dataKey={field}
            stroke={metric.color}
            strokeWidth={2}
            fill={`url(#fill-${id}-${field})`}
            isAnimationActive={false}
            dot={false}
            connectNulls={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RecentCharts({
  deviceId,
  compact = false,
}: {
  deviceId: string;
  compact?: boolean;
}) {
  const [hours, setHours] = useState("1");
  const retained = useRef<{ key: string; readings: Reading[] }>({
    key: "",
    readings: [],
  });
  const recent = usePoll(
    async (signal) => {
      const now = Date.now();
      const key = deviceId + hours;
      const prior =
        retained.current.key === key ? retained.current.readings : [];
      const windowStart = now - Number(hours) * 3600000 + 10000;
      const latest = Math.max(
        0,
        ...prior.map((reading) => Date.parse(reading.observedAt)),
      );
      // Initial window is fully paginated; subsequent refreshes read only a short overlap.
      const from = prior.length
        ? Math.max(windowStart, latest - 30000)
        : windowStart;
      const params = new URLSearchParams({
        from: new Date(from).toISOString(),
        to: new Date(now).toISOString(),
        limit: "1000",
      });
      const values: Reading[] = [];
      let cursor: string | null = null;
      // Pagination retains all 24h readings. Requests abort on navigation/range changes.
      do {
        if (cursor) params.set("cursor", cursor);
        const page: { readings: Reading[]; nextCursor: string | null } =
          await api(`/devices/${deviceId}/readings?${params}`, { signal });
        values.push(...page.readings);
        cursor = page.nextCursor;
      } while (cursor && values.length < 10000);
      const merged = [
        ...new Map(
          [...prior, ...values].map((reading) => [reading.eventId, reading]),
        ).values(),
      ].filter((reading) => Date.parse(reading.observedAt) >= windowStart);
      if (!signal.aborted) retained.current = { key, readings: merged };
      return merged;
    },
    10000,
    deviceId + hours,
  );
  const fields: (keyof typeof metrics)[] = compact
    ? ["temperatureC"]
    : ["temperatureC", "vibrationMmS", "powerWatts"];
  return (
    <section className={`panel recent-panel ${compact ? "compact" : ""}`}>
      <PanelHead
        title={compact ? "Temperature trend" : "Recent telemetry"}
        subtitle={`${motorName(deviceId)} · ${recent.data?.length ?? 0} readings · times in your timezone`}
        action={
          <label className="sr-only-label">
            <span>Chart time range</span>
            <select
              aria-label="Chart time range"
              value={hours}
              onChange={(event) => setHours(event.target.value)}
            >
              <option value="0.25">Last 15 minutes</option>
              <option value="1">Last hour</option>
              <option value="6">Last 6 hours</option>
              <option value="24">Last 24 hours</option>
            </select>
          </label>
        }
      />
      {recent.error && (
        <ErrorNotice
          message={recent.error + " Charts may show older data."}
          retry={recent.refresh}
        />
      )}
      {!recent.data ? (
        <Loading label="Loading recent readings…" />
      ) : (
        <div className={compact ? "" : "charts-grid"}>
          {fields.map((field) => (
            <div className="chart-section" key={field}>
              {!compact && (
                <div className="chart-title">
                  <h3>{metrics[field].title}</h3>
                  <span>{metrics[field].unit}</span>
                </div>
              )}
              <TelemetryChart
                readings={recent.data!}
                field={field}
                id={deviceId}
              />
            </div>
          ))}
        </div>
      )}
      <div className="panel-foot">
        <span>
          <span className="status-dot online" />
          Refreshes every 10 seconds
        </span>
        <span>
          Recorded measurements · no interpolation across missing data
        </span>
      </div>
    </section>
  );
}
