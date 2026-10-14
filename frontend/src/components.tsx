import { useEffect, useRef, useState } from "react";
import { CircleAlert, LoaderCircle } from "lucide-react";
import {
  Line,
  LineChart,
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
export function Empty({ title, text }: { title: string; text?: string }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {text && <p>{text}</p>}
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
  title,
  action,
}: {
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
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

export function deviceCondition(device: Device) {
  if (!device.online) return { label: "Offline", tone: "neutral" };
  const temperature =
    device.latest &&
    device.latest.temperatureC > (device.thresholds.temperature?.value ?? 75);
  const vibration =
    device.latest &&
    device.latest.vibrationMmS > (device.thresholds.vibration?.value ?? 4.5);
  const active = Object.values(device.latest?.rules ?? {}).some(
    (rule) => rule.active,
  );
  if (temperature && vibration)
    return { label: "Temperature + vibration", tone: "danger" };
  if (temperature)
    return { label: "Over temperature", tone: active ? "danger" : "warning" };
  if (vibration)
    return { label: "High vibration", tone: active ? "danger" : "warning" };
  if (active) return { label: "Recovering", tone: "danger" };
  if (device.latest?.operatingState === "stopped")
    return { label: "Stopped", tone: "neutral" };
  return {
    label: device.latest ? "Running" : "Awaiting data",
    tone: "neutral",
  };
}

export function ControlStatus({ control }: { control: Control }) {
  return (
    <div className={`control-status ${control.status}`}>
      <span>
        Requested: <strong>{modeName(control.requestedMode)}</strong>
      </span>
      <span>
        Applied: <strong>{modeName(control.appliedMode)}</strong>
      </span>
      <small>
        {control.status === "pending"
          ? "Applying change…"
          : control.status === "failed"
            ? "Change not confirmed. Try again."
            : `Applied ${when(control.appliedAt)}`}
      </small>
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
            Overheat
          </button>
          <button
            onClick={() => void change("vibration")}
            disabled={busy}
            className="control-button"
          >
            Vibration fault
          </button>
          <button
            onClick={() => void change("disconnect")}
            disabled={busy}
            className="control-button"
          >
            Disconnect
          </button>
          <button
            onClick={() => void change("normal")}
            disabled={busy}
            className="control-button reset"
          >
            Reset
          </button>
        </div>
      ) : null}
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

function Gauge({
  value,
  unit,
  limit,
  scale,
}: {
  value?: number;
  unit: string;
  limit: number;
  scale: number;
}) {
  const maximum = Math.max(scale, value ?? 0);
  const breached = value !== undefined && value > limit;
  return (
    <div className={`gauge ${breached ? "problem" : ""}`}>
      <strong>
        {number(value, unit === "mm/s" ? 2 : 1)} <small>{unit}</small>
      </strong>
      <div className="gauge-track" aria-hidden="true">
        <span
          style={{
            width: `${Math.max(0, Math.min(100, ((value ?? 0) / maximum) * 100))}%`,
          }}
        />
        <i style={{ left: `${(limit / maximum) * 100}%` }} />
      </div>
    </div>
  );
}

function MotorRow({
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const condition = deviceCondition(device);
  const attention = condition.tone === "danger" || condition.tone === "warning";
  async function reset() {
    setBusy(true);
    setError("");
    try {
      await api(`/controls/${device.deviceId}`, {
        method: "POST",
        body: { mode: "normal" },
      });
      refresh();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Reset could not be requested.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <tr data-testid={device.deviceId} className={attention ? "fault-row" : ""}>
      <th scope="row">
        <a href={`#/devices/${device.deviceId}`}>
          {motorName(device.deviceId)}
        </a>
      </th>
      <td>
        <span className={`equipment-state ${attention ? "problem" : ""}`}>
          <i aria-hidden="true" />
          {condition.label}
        </span>
        {(device.control.status !== "applied" ||
          device.control.appliedMode !== "normal") && (
          <ControlStatus control={device.control} />
        )}
        {error && <ErrorNotice message={error} />}
      </td>
      <td>
        <Gauge
          value={device.latest?.temperatureC}
          unit="°C"
          limit={device.thresholds.temperature?.value ?? 75}
          scale={90}
        />
      </td>
      <td>
        <Gauge
          value={device.latest?.vibrationMmS}
          unit="mm/s"
          limit={device.thresholds.vibration?.value ?? 4.5}
          scale={6}
        />
      </td>
      <td className="numeric">
        {number(device.latest?.powerWatts, 0)} <small>W</small>
      </td>
      <td
        className="numeric seen"
        title={`Last received ${when(device.lastSeen)}`}
      >
        {ago(device.lastSeen, now)}
      </td>
      <td>
        <div className="row-actions">
          {operator &&
            (attention ||
              !device.online ||
              device.control.requestedMode !== "normal") && (
              <button
                className="button signal"
                disabled={busy}
                onClick={() => void reset()}
              >
                {busy ? "Resetting…" : "Reset"}
              </button>
            )}
          <a
            href={`#/devices/${device.deviceId}`}
            aria-label={`${motorName(device.deviceId)} details`}
          >
            Details
          </a>
        </div>
      </td>
    </tr>
  );
}

export function MotorTable({
  devices,
  now,
  operator,
  refresh,
}: {
  devices: Device[];
  now: number;
  operator: boolean;
  refresh: () => void;
}) {
  return (
    <section className="panel motor-table" aria-label="Motors">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Motor</th>
              <th>State</th>
              <th>Temp · limit 75 °C</th>
              <th>Vibration · limit 4.5 mm/s</th>
              <th>Power</th>
              <th>Seen</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => (
              <MotorRow
                key={device.deviceId}
                device={device}
                now={now}
                operator={operator}
                refresh={refresh}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function DemoControls({
  devices,
  refresh,
}: {
  devices: Device[];
  refresh: () => void;
}) {
  const [selected, setSelected] = useState(devices[0]?.deviceId ?? "motor-01");
  const device =
    devices.find((item) => item.deviceId === selected) ?? devices[0];
  if (!device) return null;
  return (
    <details className="demo-controls">
      <summary>
        Fault simulation <small>demo only</small>
      </summary>
      <div className="demo-content">
        <label>
          Motor
          <select
            value={device.deviceId}
            onChange={(event) => setSelected(event.target.value)}
          >
            {devices.map((item) => (
              <option value={item.deviceId} key={item.deviceId}>
                {motorName(item.deviceId)}
              </option>
            ))}
          </select>
        </label>
        <Controls
          key={device.deviceId}
          device={device}
          operator
          refresh={refresh}
        />
      </div>
    </details>
  );
}

export const metrics = {
  temperatureC: {
    title: "Temperature",
    unit: "°C",
    color: "#14181b",
    threshold: 75,
  },
  vibrationMmS: {
    title: "Vibration",
    unit: "mm/s",
    color: "#5e686d",
    threshold: 4.5,
  },
  powerWatts: {
    title: "Power draw",
    unit: "W",
    color: "#8c969b",
    threshold: undefined,
  },
};

export function TelemetryChart({
  readings,
  field,
  threshold = true,
}: {
  readings: Reading[];
  field: keyof typeof metrics;
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
        text="Try a wider time range."
      />
    );
  return (
    <div
      className="chart"
      role="img"
      aria-label={`${metric.title} chart with ${readings.length} readings in ${metric.unit}`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart
          data={points}
          margin={{ top: 18, right: 12, bottom: 0, left: -20 }}
          accessibilityLayer
        >
          <CartesianGrid
            stroke="#d5d9db"
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
            tick={{ fontSize: 13, fill: "#4a5459" }}
            axisLine={false}
            tickLine={false}
            minTickGap={45}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 13, fill: "#4a5459" }}
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
              stroke="#14181b"
              strokeDasharray="4 4"
              label={{
                value: `Limit ${metric.threshold}`,
                position: "insideTopRight",
                fill: "#14181b",
                fontSize: 13,
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey={field}
            stroke={
              metric.threshold !== undefined &&
              Number(ordered.at(-1)?.[field]) > metric.threshold
                ? "#a8340a"
                : metric.color
            }
            strokeWidth={2}
            isAnimationActive={false}
            dot={false}
            connectNulls={false}
          />
        </LineChart>
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
  const recent = useReadingHistory([deviceId], hours);
  const fields: (keyof typeof metrics)[] = compact
    ? ["temperatureC"]
    : ["temperatureC", "vibrationMmS", "powerWatts"];
  return (
    <section className={`panel recent-panel ${compact ? "compact" : ""}`}>
      <PanelHead
        title={compact ? "Temperature trend" : "Recent telemetry"}
        subtitle={compact ? motorName(deviceId) : undefined}
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
              <TelemetryChart readings={recent.data!} field={field} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function useReadingHistory(deviceIds: string[], hours: string) {
  const key = deviceIds.join(",") + ":" + hours;
  const retained = useRef<{ key: string; readings: Reading[] }>({
    key: "",
    readings: [],
  });
  return usePoll(
    async (signal) => {
      const now = Date.now();
      const windowStart = now - Number(hours) * 3600000 + 10000;
      const prior =
        retained.current.key === key ? retained.current.readings : [];
      const batches = await Promise.all(
        deviceIds.map(async (id) => {
          const old = prior.filter((reading) => reading.deviceId === id);
          const latest = Math.max(
            0,
            ...old.map((reading) => Date.parse(reading.observedAt)),
          );
          const params = new URLSearchParams({
            from: new Date(
              old.length ? Math.max(windowStart, latest - 30000) : windowStart,
            ).toISOString(),
            to: new Date(now).toISOString(),
            limit: "1000",
          });
          const values: Reading[] = [];
          let cursor: string | null = null;
          do {
            if (cursor) params.set("cursor", cursor);
            const page: { readings: Reading[]; nextCursor: string | null } =
              await api(`/devices/${id}/readings?${params}`, { signal });
            values.push(...page.readings);
            cursor = page.nextCursor;
          } while (cursor && values.length < 10000);
          return values;
        }),
      );
      const merged = [
        ...new Map(
          [...prior, ...batches.flat()].map((reading) => [
            reading.eventId,
            reading,
          ]),
        ).values(),
      ].filter((reading) => Date.parse(reading.observedAt) >= windowStart);
      if (!signal.aborted) retained.current = { key, readings: merged };
      return merged;
    },
    10000,
    key,
  );
}

export function AllMotorTrend({
  devices,
  now,
}: {
  devices: Device[];
  now: number;
}) {
  const [hours, setHours] = useState("1");
  const history = useReadingHistory(
    devices.map((device) => device.deviceId),
    hours,
  );
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(260, entry.contentRect.width)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const values = history.data ?? [];
  const minimum =
    Math.floor(
      Math.min(50, ...values.map((reading) => reading.temperatureC)) / 10,
    ) * 10;
  const maximum =
    Math.ceil(
      Math.max(90, ...values.map((reading) => reading.temperatureC)) / 10,
    ) * 10;
  const left = 36,
    right = width - 115,
    top = 24,
    bottom = 230;
  const from = now - Number(hours) * 3600000;
  const x = (time: number) =>
    left +
    (right - left) * Math.max(0, Math.min(1, (time - from) / (now - from)));
  const y = (value: number) =>
    bottom - ((value - minimum) / (maximum - minimum)) * (bottom - top);
  const series = devices.map((device, index) => {
    const readings = values
      .filter((reading) => reading.deviceId === device.deviceId)
      .sort((a, b) => a.observedAt.localeCompare(b.observedAt));
    const last = readings.at(-1);
    const condition = deviceCondition(device);
    const color =
      condition.tone === "danger" || condition.tone === "warning"
        ? "#a8340a"
        : ["#14181b", "#5e686d", "#8c969b"][index % 3];
    const path = readings
      .map(
        (reading, i) =>
          `${!i || Date.parse(reading.observedAt) - Date.parse(readings[i - 1].observedAt) > 25000 ? "M" : "L"}${x(Date.parse(reading.observedAt)).toFixed(1)},${y(reading.temperatureC).toFixed(1)}`,
      )
      .join(" ");
    return {
      id: device.deviceId,
      readings,
      last,
      color,
      path,
      labelY: last ? y(last.temperatureC) : bottom,
    };
  });
  const labels = series
    .filter((item) => item.last)
    .sort((a, b) => a.labelY - b.labelY);
  for (let i = 0; i < labels.length; i++)
    labels[i].labelY = Math.max(
      top + 8,
      labels[i].labelY,
      i ? labels[i - 1].labelY + 18 : top + 8,
    );
  const overflow = Math.max(0, (labels.at(-1)?.labelY ?? 0) - bottom);
  for (const label of labels) label.labelY -= overflow;
  return (
    <section className="panel comparison-panel">
      <PanelHead
        title="Temperature, all motors"
        action={
          <label className="range-picker">
            <span className="sr-only">Chart time range</span>
            <select
              aria-label="Chart time range"
              value={hours}
              onChange={(event) => setHours(event.target.value)}
            >
              <option value="1">Last hour</option>
              <option value="6">Last 6 hours</option>
              <option value="24">Last 24 hours</option>
            </select>
          </label>
        }
      />
      {history.error && (
        <ErrorNotice
          message={history.error + " Chart may show older data."}
          retry={history.refresh}
        />
      )}
      <div className="comparison-chart" ref={container}>
        {!history.data ? (
          <Loading label="Loading recent readings…" />
        ) : !values.length ? (
          <Empty title="No readings in this window" />
        ) : (
          <svg
            viewBox={`0 0 ${width} 270`}
            role="img"
            aria-label={`Temperature chart with ${values.length} readings across all motors in °C`}
          >
            {[0, 1, 2, 3, 4].map((index) => {
              const value = minimum + ((maximum - minimum) * index) / 4;
              return (
                <g key={index}>
                  <line
                    x1={left}
                    x2={right}
                    y1={y(value)}
                    y2={y(value)}
                    stroke="#d5d9db"
                  />
                  <text x={left - 9} y={y(value) + 4} textAnchor="end">
                    {number(value, 0)}
                  </text>
                </g>
              );
            })}
            <line
              x1={left}
              x2={right}
              y1={y(75)}
              y2={y(75)}
              stroke="#14181b"
              strokeDasharray="5 4"
            />
            <text x={left + 3} y={y(75) - 7} className="limit-label">
              Limit 75 °C
            </text>
            {series.map((item) => (
              <path
                key={item.id}
                d={item.path}
                fill="none"
                stroke={item.color}
                strokeWidth={item.color === "#a8340a" ? 2.8 : 1.8}
              />
            ))}
            {labels.map((item) => (
              <g
                key={item.id}
                fill={item.color === "#a8340a" ? "#a8340a" : "#4a5459"}
              >
                <circle
                  cx={x(Date.parse(item.last!.observedAt))}
                  cy={y(item.last!.temperatureC)}
                  r="3"
                >
                  <title>
                    {motorName(item.id)} · {number(item.last!.temperatureC)} °C
                    · {when(item.last!.observedAt)}
                  </title>
                </circle>
                <text x={right + 10} y={item.labelY + 4}>
                  {motorName(item.id)} {number(item.last!.temperatureC)}
                </text>
              </g>
            ))}
            {[0, 0.5, 1].map((fraction) => (
              <text
                key={fraction}
                x={left + (right - left) * fraction}
                y="260"
                textAnchor="middle"
              >
                {new Date(from + (now - from) * fraction).toLocaleTimeString(
                  undefined,
                  { hour: "2-digit", minute: "2-digit" },
                )}
              </text>
            ))}
          </svg>
        )}
      </div>
    </section>
  );
}
