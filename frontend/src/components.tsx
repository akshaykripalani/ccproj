import { useEffect, useRef, useState } from "react";
import { CircleAlert, LoaderCircle } from "lucide-react";
import {
  Line,
  LineChart,
  CartesianGrid,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "./api";
import { ago, modeName, motorName, number, when } from "./format";
import { usePoll } from "./hooks";
import type { Control, Device, Mode, Reading } from "./types";
import { readingPath, timeLabel } from "./telemetry";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
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
export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={20} className="spin" />
      {label}
    </div>
  );
}

export function TelemetrySkeleton() {
  return (
    <div
      className="telemetry-skeleton"
      role="status"
      aria-label="Loading equipment readings"
    >
      <span className="sr-only">Loading equipment readings</span>
      {[0, 1, 2].map((row) => (
        <div key={row} className="skeleton-row" aria-hidden="true">
          {[0, 1, 2, 3].map((cell) => (
            <span key={cell} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function AnimatedNumber({
  value,
  decimals = 1,
}: {
  value?: number;
  decimals?: number;
}) {
  const [shown, setShown] = useState(value);
  const previous = useRef(value);
  useEffect(() => {
    const from = previous.current;
    previous.current = value;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    if (
      from === undefined ||
      value === undefined ||
      from === value ||
      media.matches
    ) {
      setShown(value);
      return;
    }
    const started = performance.now();
    function draw(time: number) {
      const progress = Math.min(1, (time - started) / 300);
      setShown(from! + (value! - from!) * (1 - (1 - progress) ** 3));
      if (progress < 1) frame = requestAnimationFrame(draw);
    }
    function reduce() {
      if (media.matches) {
        cancelAnimationFrame(frame);
        setShown(value);
      }
    }
    media.addEventListener("change", reduce);
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      media.removeEventListener("change", reduce);
    };
  }, [value]);
  return (
    <span className="value-flash" key={value}>
      {number(shown, decimals)}
    </span>
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

export function Gauge({
  value,
  unit,
  limit,
  scale,
}: {
  value?: number;
  unit: string;
  limit?: number;
  scale: number;
}) {
  const maximum = Math.max(scale, value ?? 0);
  const breached = value !== undefined && limit !== undefined && value > limit;
  return (
    <div className={`gauge ${breached ? "problem" : ""}`}>
      <strong>
        <AnimatedNumber
          value={value}
          decimals={unit === "mm/s" ? 2 : unit === "W" ? 0 : 1}
        />{" "}
        <small>{unit}</small>
      </strong>
      <div className="gauge-track" aria-hidden="true">
        <span
          style={{
            width: `${Math.max(0, Math.min(100, ((value ?? 0) / maximum) * 100))}%`,
          }}
        />
        {limit !== undefined && (
          <i style={{ left: `${(limit / maximum) * 100}%` }} />
        )}
        {Array.from(
          {
            length: Math.floor(
              maximum / (unit === "°C" ? 10 : unit === "mm/s" ? 1 : 100),
            ),
          },
          (_, index) => (
            <b
              key={index}
              style={{
                left: `${(((index + 1) * (unit === "°C" ? 10 : unit === "mm/s" ? 1 : 100)) / maximum) * 100}%`,
              }}
            />
          ),
        )}
      </div>
    </div>
  );
}

function Sparkline({
  device,
  readings,
  now,
}: {
  device: Device;
  readings: Reading[];
  now: number;
}) {
  const values = readings
    .filter(
      (r) =>
        r.deviceId === device.deviceId &&
        Date.parse(r.observedAt) >= now - 1800000,
    )
    .sort((a, b) => a.observedAt.localeCompare(b.observedAt));
  const min = Math.min(40, ...values.map((r) => r.temperatureC));
  const max = Math.max(90, ...values.map((r) => r.temperatureC));
  const from = Math.min(
    now - 60000,
    Date.parse(values[0]?.observedAt ?? new Date(now).toISOString()),
  );
  const path = readingPath(
    values,
    (t) => 2 + ((t - from) / (now - from)) * 116,
    (v) => 35 - ((v - min) / (max - min)) * 30,
  );
  return (
    <svg
      className="sparkline"
      viewBox="0 0 120 40"
      preserveAspectRatio="none"
      role="img"
      aria-label={`${motorName(device.deviceId)} temperature over the last 30 minutes`}
    >
      <line
        x1="0"
        x2="120"
        y1={35 - ((75 - min) / (max - min)) * 30}
        y2={35 - ((75 - min) / (max - min)) * 30}
        className="spark-limit"
      />
      {path && (
        <path
          d={path}
          fill="none"
          className={
            device.latest && device.latest.temperatureC > 75
              ? "spark-fault"
              : ""
          }
        />
      )}
      {!path && (
        <text x="60" y="25" textAnchor="middle">
          No history
        </text>
      )}
    </svg>
  );
}

function MotorRow({
  device,
  now,
  operator,
  refresh,
  links,
  readings,
}: {
  device: Device;
  now: number;
  operator: boolean;
  refresh: () => void;
  links: boolean;
  readings: Reading[];
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [requested, setRequested] = useState<Control>();
  const control =
    requested &&
    requested.requestId !== device.control.requestId &&
    Date.parse(requested.requestedAt ?? "") >
      Date.parse(device.control.requestedAt ?? "1970-01-01")
      ? requested
      : device.control;
  const condition = deviceCondition(device);
  const attention = condition.tone === "danger" || condition.tone === "warning";
  async function reset() {
    setBusy(true);
    setError("");
    try {
      setRequested(
        await api<Control>(`/controls/${device.deviceId}`, {
          method: "POST",
          body: { mode: "normal" },
        }),
      );
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
    <tr
      data-testid={device.deviceId}
      className={[
        attention ? "fault-row" : "",
        !device.online ? "offline-row" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <th scope="row">
        {links ? (
          <a href={`#/devices/${device.deviceId}`}>
            {motorName(device.deviceId)}
          </a>
        ) : (
          motorName(device.deviceId)
        )}
      </th>
      <td>
        <span className={`equipment-state ${attention ? "problem" : ""}`}>
          <i
            key={device.latest?.eventId}
            className={device.online ? "heartbeat" : ""}
            aria-hidden="true"
          />
          {condition.label}
        </span>
        {!device.online && (
          <small className="cell-sub">Last-known readings</small>
        )}
        {control.status !== "applied" && (
          <small className={`row-command ${control.status}`} role="status">
            {control.status === "pending"
              ? `${modeName(control.requestedMode)} requested → Applying change…`
              : "Change not confirmed. Try again."}
          </small>
        )}
        {error && <ErrorNotice message={error} />}
      </td>
      <td data-label="Temperature">
        <Gauge
          value={device.latest?.temperatureC}
          unit="°C"
          limit={device.thresholds.temperature?.value ?? 75}
          scale={90}
        />
      </td>
      <td data-label="Vibration">
        <Gauge
          value={device.latest?.vibrationMmS}
          unit="mm/s"
          limit={device.thresholds.vibration?.value ?? 4.5}
          scale={6}
        />
      </td>
      <td data-label="Power">
        <Gauge value={device.latest?.powerWatts} unit="W" scale={600} />
      </td>
      <td className="trend-cell">
        <Sparkline device={device} readings={readings} now={now} />
      </td>
      <td
        className="numeric seen"
        title={`Last received ${when(device.lastSeen)}`}
      >
        <span className="mobile-label">Last reading </span>
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
  links = true,
  readings = [],
}: {
  devices: Device[];
  now: number;
  operator: boolean;
  refresh: () => void;
  links?: boolean;
  readings?: Reading[];
}) {
  return (
    <section className="panel motor-table" aria-label="Motors">
      <p className="mobile-limit-caption">Limits: 75 °C · 4.5 mm/s</p>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Motor readings"
      >
        <table>
          <thead>
            <tr>
              <th>Motor</th>
              <th>State</th>
              <th>
                Temperature<span className="column-limit">75 °C limit</span>
              </th>
              <th>
                Vibration<span className="column-limit">4.5 mm/s limit</span>
              </th>
              <th>Power</th>
              <th>Temperature · 30 min</th>
              <th>Last reading</th>
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
                links={links}
                readings={readings}
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
    color: "#1d5c7a",
    threshold: 75,
  },
  vibrationMmS: {
    title: "Vibration",
    unit: "mm/s",
    color: "#1d5c7a",
    threshold: 4.5,
  },
  powerWatts: {
    title: "Power draw",
    unit: "W",
    color: "#1d5c7a",
    threshold: undefined,
  },
};

export function TelemetryChart({
  readings,
  field,
  threshold = true,
  syncId,
}: {
  readings: Reading[];
  field: keyof typeof metrics;
  threshold?: boolean;
  syncId?: string;
}) {
  const metric = metrics[field];
  const ordered = [...readings].sort((a, b) =>
    a.observedAt.localeCompare(b.observedAt),
  );
  const domain: [number, number] =
    field === "temperatureC"
      ? [
          Math.floor(Math.min(40, ...readings.map((r) => r[field])) / 10) * 10,
          Math.ceil(Math.max(90, ...readings.map((r) => r[field])) / 10) * 10,
        ]
      : [
          0,
          field === "vibrationMmS"
            ? Math.max(
                6,
                Math.ceil(Math.max(0, ...readings.map((r) => r[field]))),
              )
            : Math.max(
                600,
                Math.ceil(Math.max(0, ...readings.map((r) => r[field])) / 100) *
                  100,
              ),
        ];
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
          margin={{ top: 18, right: 28, bottom: 0, left: -12 }}
          syncId={syncId}
          syncMethod="value"
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
              timeLabel(
                Number(time),
                Date.parse(ordered.at(-1)!.observedAt) -
                  Date.parse(ordered[0].observedAt) <
                  600000,
              )
            }
            padding={{ left: 8, right: 20 }}
            tick={{ fontSize: 13, fill: "#4a5459" }}
            axisLine={false}
            tickLine={false}
            minTickGap={45}
          />
          <YAxis
            domain={domain}
            ticks={
              field === "temperatureC"
                ? Array.from(
                    { length: (domain[1] - domain[0]) / 10 + 1 },
                    (_, index) => domain[0] + index * 10,
                  )
                : undefined
            }
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
            <ReferenceArea
              y1={metric.threshold}
              y2={domain[1]}
              fill="#a8340a"
              fillOpacity={0.06}
            />
          )}
          {threshold && metric.threshold !== undefined && (
            <ReferenceLine
              y={metric.threshold}
              ifOverflow="extendDomain"
              stroke="#a8340a"
              strokeDasharray="4 4"
              label={{
                value: `Limit ${metric.threshold}`,
                position: "insideTopRight",
                fill: "#a8340a",
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
        title={compact ? "Temperature trend" : "Recent readings"}
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
              <TelemetryChart
                readings={recent.data!}
                field={field}
                syncId={`recent-${deviceId}`}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function useReadingHistory(deviceIds: string[], hours: string) {
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
