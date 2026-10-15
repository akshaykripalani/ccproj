import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "./api";
import {
  Badge,
  Empty,
  ErrorNotice,
  Heading,
  Loading,
  MotorTable,
  DemoControls,
  PanelHead,
  RecentCharts,
  deviceCondition,
  Gauge,
  AnimatedNumber,
  useReadingHistory,
} from "./components";
import { modeName, motorName, number, utcDate, when } from "./format";
import { LIVE_INTERVAL_MS, useClock, usePoll } from "./hooks";
import { AllMotorTrend } from "./FleetChart";
import { equipmentEvents, timeLabel, type EquipmentEvent } from "./telemetry";
import { ago } from "./format";
import type {
  Account,
  Alert,
  AlertResponse,
  Control,
  Device,
  Report,
  ReportKind,
  ReportParameters,
  Role,
} from "./types";

interface LiveProps {
  devices: Device[];
  operator: boolean;
  now: number;
  refresh: () => void;
}

function ResetAll({ refresh }: { refresh: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function reset() {
    dialog.current?.close();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api<{ controls: Control[] }>("/controls/reset-all", {
        method: "POST",
      });
      setMessage("Reset requested for all motors.");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send reset.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="reset-all">
      <button
        className="button secondary"
        disabled={busy}
        onClick={() => dialog.current?.showModal()}
      >
        Reset all motors
      </button>
      <dialog
        ref={dialog}
        className="confirm-dialog"
        aria-labelledby="reset-confirm-title"
      >
        <h2 id="reset-confirm-title">Reset all three motors?</h2>
        <p>Each motor will return to normal mode.</p>
        <div>
          <button
            className="button secondary"
            autoFocus
            onClick={() => dialog.current?.close()}
          >
            Cancel
          </button>
          <button className="button primary" onClick={() => void reset()}>
            Confirm reset
          </button>
        </div>
      </dialog>
      {message && (
        <p className="tiny" role="status">
          {message}
        </p>
      )}
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

function Events({
  events,
  error,
  loading,
  retry,
  selected,
  select,
}: {
  events: EquipmentEvent[];
  error: string;
  loading: boolean;
  retry: () => void;
  selected?: string;
  select: (id?: string) => void;
}) {
  return (
    <section className="panel events-panel">
      <PanelHead title="Events" action={<a href="#/alerts">View all</a>} />
      {error && <ErrorNotice message={error} retry={retry} />}
      {loading && !events.length ? (
        <Loading />
      ) : events.length ? (
        <ol className="event-log">
          {events.slice(0, 6).map((event, index) => {
            const day = new Date(event.time).toLocaleDateString(undefined, {
              day: "numeric",
              month: "short",
            });
            const priorDay = index
              ? new Date(events[index - 1].time).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                })
              : "";
            return (
              <li
                key={event.id}
                className={selected === event.id ? "event-selected" : ""}
                onPointerEnter={() => select(event.id)}
                onPointerLeave={() => select(undefined)}
              >
                {day !== priorDay && <span className="event-day">{day}</span>}
                <time dateTime={event.time} title={when(event.time)}>
                  {timeLabel(event.time, true)}
                </time>
                <span className={event.problem ? "problem" : ""}>
                  {event.title}
                </span>
              </li>
            );
          })}
        </ol>
      ) : (
        <Empty title="No events in the last 24 hours" />
      )}
    </section>
  );
}

export function Overview({ devices, operator, now, refresh }: LiveProps) {
  const [hours, setHours] = useState("0.5");
  const history = useReadingHistory(
    devices.map((device) => device.deviceId),
    hours,
  );
  const alerts = usePoll((signal) => api<AlertResponse>("/alerts", { signal }));
  const [selected, setSelected] = useState<string>();
  const events = equipmentEvents(devices, alerts.data?.alerts ?? [], now);
  const reporting = devices.filter((device) => device.online && device.latest);
  const active = devices.reduce(
    (sum, device) =>
      sum +
      Object.values(device.latest?.rules ?? {}).filter((rule) => rule.active)
        .length,
    0,
  );
  const power = reporting.reduce(
    (sum, device) => sum + (device.latest?.powerWatts ?? 0),
    0,
  );
  const hottest = reporting.reduce<Device | undefined>(
    (hot, device) =>
      !hot || device.latest!.temperatureC > hot.latest!.temperatureC
        ? device
        : hot,
    undefined,
  );
  const margin = hottest
    ? (hottest.thresholds.temperature?.value ?? 75) -
      hottest.latest!.temperatureC
    : undefined;
  return (
    <section aria-label="Plant overview">
      <div className="overview-heading">
        <h1>Overview</h1>
        {operator && <ResetAll refresh={refresh} />}
      </div>
      <div className="readout-strip plant-summary">
        <div>
          <span>Total draw</span>
          <strong>
            <AnimatedNumber
              value={reporting.length ? power / 1000 : undefined}
              decimals={2}
            />{" "}
            <small>kW</small>
          </strong>
          <small>{reporting.length} motors reporting</small>
        </div>
        <div>
          <span>
            Hottest · {hottest ? motorName(hottest.deviceId) : "No readings"}
          </span>
          <strong
            className={margin !== undefined && margin < 0 ? "problem" : ""}
          >
            <AnimatedNumber value={hottest?.latest?.temperatureC} />{" "}
            <small>°C</small>
          </strong>
          <small
            className={margin !== undefined && margin < 0 ? "problem" : ""}
          >
            {margin === undefined
              ? "—"
              : margin === 0
                ? "At limit"
                : `${number(Math.abs(margin))}° ${margin < 0 ? "over" : "below"} limit`}
          </small>
        </div>
        <div>
          <span>Motors online</span>
          <strong>
            {reporting.length}
            <small> / {devices.length}</small>
          </strong>
          <small className={active ? "problem" : ""}>
            {active} active {active === 1 ? "fault" : "faults"}
          </small>
        </div>
      </div>
      <MotorTable
        devices={devices}
        operator={operator}
        now={now}
        refresh={refresh}
        readings={history.data}
      />
      <div className="overview-bottom">
        <AllMotorTrend
          devices={devices}
          now={now}
          history={history}
          hours={hours}
          setHours={setHours}
          events={events}
          selectedEvent={selected}
          selectEvent={setSelected}
        />
        <Events
          events={events}
          error={alerts.error}
          loading={!alerts.data}
          retry={alerts.refresh}
          selected={selected}
          select={setSelected}
        />
      </div>
      {operator && (
        <div className="operator-tools">
          <DemoControls devices={devices} refresh={refresh} />
        </div>
      )}
    </section>
  );
}

function EquipmentList(props: LiveProps) {
  const history = useReadingHistory(
    props.devices.map((d) => d.deviceId),
    "0.5",
  );
  return (
    <>
      <Heading
        title="Equipment"
        action={props.operator && <ResetAll refresh={props.refresh} />}
      />
      <MotorTable {...props} readings={history.data} />
      {history.error && (
        <ErrorNotice message={history.error} retry={history.refresh} />
      )}
      {props.operator && (
        <div className="operator-tools">
          <DemoControls devices={props.devices} refresh={props.refresh} />
        </div>
      )}
    </>
  );
}

export function Equipment(props: LiveProps & { deviceId?: string }) {
  if (!props.deviceId) return <EquipmentList {...props} />;
  const device = props.devices.find((item) => item.deviceId === props.deviceId);
  return device ? (
    <EquipmentDetail {...props} device={device} />
  ) : (
    <Empty title="Equipment not found" text="Choose a motor from Equipment." />
  );
}

function EquipmentDetail({
  device,
  operator,
  now,
  refresh,
}: LiveProps & { device: Device }) {
  const alerts = usePoll(
    (signal) =>
      api<AlertResponse>(`/alerts?deviceId=${device.deviceId}`, { signal }),
    LIVE_INTERVAL_MS,
    device.deviceId,
  );
  const condition = deviceCondition(device);
  const [requested, setRequested] = useState<Control>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const control =
    requested &&
    requested.requestId !== device.control.requestId &&
    Date.parse(requested.requestedAt ?? "") >
      Date.parse(device.control.requestedAt ?? "1970-01-01")
      ? requested
      : device.control;
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
      setError(err instanceof Error ? err.message : "Could not request reset.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <a href="#/devices" className="breadcrumb">
        ← Equipment
      </a>
      <div className="page-heading detail-heading">
        <div>
          <h1>{motorName(device.deviceId)}</h1>
          <span
            className={`equipment-state ${condition.tone === "danger" || condition.tone === "warning" ? "problem" : ""}`}
          >
            <i
              key={device.latest?.eventId}
              className={device.online ? "heartbeat" : ""}
              aria-hidden="true"
            />
            {condition.label}
          </span>
        </div>
        {operator && (
          <button
            className="button secondary"
            disabled={busy || control.status === "pending"}
            onClick={() => void reset()}
          >
            Reset
          </button>
        )}
      </div>
      {control.status !== "applied" && (
        <p className="row-command" role="status">
          {control.status === "pending"
            ? `${modeName(control.requestedMode)} requested → Applying change…`
            : "Change not confirmed. Try again."}
        </p>
      )}
      {error && <ErrorNotice message={error} />}
      <div className={`detail-readouts ${!device.online ? "offline-row" : ""}`}>
        <div>
          <span>Temperature</span>
          <Gauge
            value={device.latest?.temperatureC}
            unit="°C"
            limit={device.thresholds.temperature?.value ?? 75}
            scale={90}
          />
        </div>
        <div>
          <span>Vibration</span>
          <Gauge
            value={device.latest?.vibrationMmS}
            unit="mm/s"
            limit={device.thresholds.vibration?.value ?? 4.5}
            scale={6}
          />
        </div>
        <div>
          <span>Power</span>
          <Gauge value={device.latest?.powerWatts} unit="W" scale={600} />
        </div>
      </div>
      <div className="detail-layout">
        <div className="detail-main">
          <RecentCharts deviceId={device.deviceId} />
          <section className="panel motor-alerts">
            <PanelHead
              title="Recent alerts"
              action={<a href="#/alerts">View all</a>}
            />
            {alerts.error && (
              <ErrorNotice message={alerts.error} retry={alerts.refresh} />
            )}
            {!alerts.data ? (
              <Loading />
            ) : alerts.data.alerts.length ? (
              <ul className="motor-alert-list">
                {alerts.data.alerts.slice(0, 5).map((alert) => (
                  <li key={alert.alertId}>
                    <span className={alert.state === "active" ? "problem" : ""}>
                      {alert.rule === "temperature"
                        ? "Over temperature"
                        : "High vibration"}{" "}
                      · {alert.state}
                    </span>
                    <time title={when(alert.activatedAt)}>
                      {when(alert.activatedAt)}
                    </time>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="No recent alerts" />
            )}
          </section>
        </div>
        <aside className="panel equipment-details">
          <PanelHead title="Equipment details" />
          <dl>
            <div>
              <dt>Device</dt>
              <dd>{device.deviceId}</dd>
            </div>
            <div>
              <dt>Last reading</dt>
              <dd title={when(device.lastSeen)}>
                {ago(device.lastSeen, now)}
                {!device.online && " · last known"}
              </dd>
            </div>
            <div>
              <dt>Observed</dt>
              <dd>{when(device.latest?.observedAt)}</dd>
            </div>
            <div>
              <dt>Temperature limit</dt>
              <dd>&gt; {device.thresholds.temperature?.value ?? 75} °C</dd>
            </div>
            <div>
              <dt>Vibration limit</dt>
              <dd>&gt; {device.thresholds.vibration?.value ?? 4.5} mm/s</dd>
            </div>
            <div>
              <dt>Requested</dt>
              <dd>{modeName(control.requestedMode)}</dd>
            </div>
            <div>
              <dt>Applied</dt>
              <dd>{modeName(control.appliedMode)}</dd>
            </div>
          </dl>
        </aside>
      </div>
      {operator && (
        <div className="operator-tools">
          <DemoControls devices={[device]} refresh={refresh} />
        </div>
      )}
    </>
  );
}

function emailLabel(status: string) {
  return (
    (
      {
        pending: "Notification pending",
        pending_confirmation: "Confirmation pending",
        sns_accepted: "Email accepted",
        suppressed_replay: "Not sent",
      } as Record<string, string>
    )[status] ?? status
  );
}

export function Alerts() {
  const now = useClock();
  const [device, setDevice] = useState("");
  const [state, setState] = useState("");
  const [days, setDays] = useState("1");
  // Include older ongoing episodes that overlap the visible 24-hour timeline.
  const timeline = usePoll((signal) =>
    api<AlertResponse>(
      `/alerts?from=${new Date(Date.now() - 30 * 86400000 + 10000).toISOString()}&to=${new Date().toISOString()}`,
      { signal },
    ),
  );
  const alerts = usePoll(
    (signal) => {
      const params = new URLSearchParams({
        from: new Date(
          Date.now() - Number(days) * 86400000 + 10000,
        ).toISOString(),
        to: new Date().toISOString(),
      });
      if (device) params.set("deviceId", device);
      if (state) params.set("state", state);
      return api<AlertResponse>(`/alerts?${params}`, { signal });
    },
    LIVE_INTERVAL_MS,
    device + state + days,
  );
  return (
    <>
      <Heading title="Alerts & events" />
      <EpisodeTimeline
        alerts={timeline.data?.alerts}
        error={timeline.error}
        retry={timeline.refresh}
        now={now}
      />
      <section className="panel">
        {timeline.data && (
          <div className="alert-context">
            <span>Limits: &gt; 75 °C · &gt; 4.5 mm/s</span>
            <span>
              Email subscriptions:{" "}
              <strong>{timeline.data.subscriptions.confirmed} confirmed</strong>{" "}
              · {timeline.data.subscriptions.pending} pending
            </span>
          </div>
        )}
        <div className="filters">
          <label>
            Equipment
            <select
              value={device}
              onChange={(event) => setDevice(event.target.value)}
            >
              <option value="">All motors</option>
              {["motor-01", "motor-02", "motor-03"].map((id) => (
                <option value={id} key={id}>
                  {motorName(id)}
                </option>
              ))}
            </select>
          </label>
          <label>
            State
            <select
              value={state}
              onChange={(event) => setState(event.target.value)}
            >
              <option value="">All states</option>
              <option value="active">Active</option>
              <option value="resolved">Resolved</option>
            </select>
          </label>
          <label>
            Time window
            <select
              value={days}
              onChange={(event) => setDays(event.target.value)}
            >
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
            </select>
          </label>
          <span className="filter-count">
            {alerts.data?.alerts.length ?? "—"} episodes
          </span>
        </div>
        {alerts.error && (
          <ErrorNotice message={alerts.error} retry={alerts.refresh} />
        )}
        {!alerts.data ? (
          <Loading />
        ) : (
          <>
            {!alerts.data.alerts.length ? (
              <Empty
                title="No alerts match these filters"
                text="Try a wider time window."
              />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Equipment / rule</th>
                      <th>Reading at activation</th>
                      <th>State</th>
                      <th>Activated / resolved</th>
                      <th>Email notification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.data.alerts.map((alert) => (
                      <tr
                        key={alert.alertId}
                        className={
                          alert.state === "active" ? "fault-row" : undefined
                        }
                      >
                        <td>
                          <a
                            className="table-primary"
                            href={`#/devices/${alert.pk}`}
                          >
                            {motorName(alert.pk)}
                          </a>
                          <span className="cell-sub">
                            {alert.rule === "temperature"
                              ? "Temperature above 75 °C"
                              : "Vibration above 4.5 mm/s"}
                          </span>
                        </td>
                        <td>
                          {alert.rule === "temperature"
                            ? `${number(alert.reading.temperatureC)} °C`
                            : `${number(alert.reading.vibrationMmS, 2)} mm/s`}
                        </td>
                        <td>
                          <Badge
                            tone={
                              alert.state === "active" ? "danger" : "success"
                            }
                          >
                            {alert.state}
                          </Badge>
                        </td>
                        <td>
                          {when(alert.activatedAt)}
                          <span className="cell-sub">
                            {alert.resolvedAt
                              ? `Resolved ${when(alert.resolvedAt)}`
                              : "Ongoing"}
                          </span>
                        </td>
                        <td>
                          <span
                            className="email-status"
                            title={
                              alert.emailStatus === "sns_accepted"
                                ? "Accepted for sending; inbox delivery is not confirmed."
                                : undefined
                            }
                          >
                            {emailLabel(alert.emailStatus)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}

function EpisodeTimeline({
  alerts,
  error,
  retry,
  now,
}: {
  alerts?: Alert[];
  error: string;
  retry: () => void;
  now: number;
}) {
  const [selected, setSelected] = useState<string>();
  const start = now - 86400000;
  const episodes = (alerts ?? []).filter(
    (alert) =>
      Date.parse(alert.activatedAt) <= now &&
      (!alert.resolvedAt || Date.parse(alert.resolvedAt) >= start),
  );
  const chosen = episodes.find((a) => a.alertId === selected);
  return (
    <section
      className="panel episode-timeline"
      aria-label="Alert episodes in the last 24 hours"
    >
      <PanelHead
        title="Last 24 hours"
        action={<span className="muted">{episodes.length} episodes</span>}
      />
      {error && <ErrorNotice message={error} retry={retry} />}
      {alerts === undefined ? (
        <Loading />
      ) : (
        <div className="episode-rows">
          {["motor-01", "motor-02", "motor-03"].map((id) => (
            <div className="episode-row" key={id}>
              <a href={`#/devices/${id}`}>{motorName(id)}</a>
              <div className="episode-track">
                {episodes
                  .filter((a) => a.pk === id)
                  .map((alert) => {
                    const left = Math.max(
                      0,
                      ((Date.parse(alert.activatedAt) - start) / 86400000) *
                        100,
                    );
                    const end = Math.min(
                      100,
                      (((alert.resolvedAt
                        ? Date.parse(alert.resolvedAt)
                        : now) -
                        start) /
                        86400000) *
                        100,
                    );
                    return (
                      <span
                        key={alert.alertId}
                        tabIndex={0}
                        role="img"
                        className={`episode-bar ${alert.state}`}
                        aria-label={`${motorName(id)} ${alert.rule} ${alert.state}, ${when(alert.activatedAt)}${alert.resolvedAt ? ` to ${when(alert.resolvedAt)}` : " ongoing"}`}
                        title={`${alert.rule} · ${when(alert.activatedAt)} → ${alert.resolvedAt ? when(alert.resolvedAt) : "Ongoing"}`}
                        onPointerEnter={() => setSelected(alert.alertId)}
                        onPointerLeave={() => setSelected(undefined)}
                        onFocus={() => setSelected(alert.alertId)}
                        onBlur={() => setSelected(undefined)}
                        style={{
                          left: `${left}%`,
                          width: `${Math.max(0.15, end - left)}%`,
                          maxWidth: `${100 - left}%`,
                        }}
                      />
                    );
                  })}
              </div>
            </div>
          ))}
          <div className="episode-axis">
            <span>{timeLabel(start)}</span>
            <span>{timeLabel(now - 43200000)}</span>
            <span>Now</span>
          </div>
          <p className="episode-caption">
            {chosen
              ? `${motorName(chosen.pk)} · ${chosen.rule} · ${chosen.state} · ${when(chosen.activatedAt)}`
              : episodes.length
                ? ""
                : "No fault episodes in this window."}
          </p>
        </div>
      )}
    </section>
  );
}

const reportDescriptions = {
  temperature: {
    title: "Temperature",
    description: "Daily average, peak & reading count",
  },
  vibration: {
    title: "Vibration",
    description: "Readings above the 4.5 mm/s threshold",
  },
  power: {
    title: "Power usage",
    description: "Average power while the motor runs",
  },
};
const columnLabels: Record<string, string> = {
  deviceid: "Motor",
  day: "Date (UTC)",
  average_temperature_c: "Average (°C)",
  maximum_temperature_c: "Peak (°C)",
  reading_count: "Readings",
  breached_readings: "Breached readings",
  average_running_power_watts: "Running average (W)",
  running_reading_count: "Running readings",
};

function ReportResults({ result, kind }: { result: Report; kind: ReportKind }) {
  const rows = result.rows ?? [];
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const keys =
    kind === "temperature"
      ? ["average_temperature_c", "maximum_temperature_c"]
      : kind === "vibration"
        ? ["breached_readings"]
        : ["average_running_power_watts"];
  const chartRows = rows.map((row) => ({
    ...row,
    label: `${row.day} · ${motorName(row.deviceid ?? "")}`,
    ...Object.fromEntries(
      keys.map((key) => [key, row[key] === null ? null : Number(row[key])]),
    ),
  }));
  function exportCsv() {
    const quote = (cell: unknown) =>
      `"${String(cell ?? "").replace(/"/g, '""')}"`;
    const csv = [
      columns.map((key) => columnLabels[key] ?? key),
      ...rows.map((row) => columns.map((key) => row[key])),
    ]
      .map((row) => row.map(quote).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `forge-${kind}-${utcDate()}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section className="panel report-results">
      <PanelHead
        title="Report results"
        subtitle={`${result.parameters?.start} — ${result.parameters?.end}`}
        action={
          rows.length > 0 && (
            <button className="button secondary" onClick={exportCsv}>
              Export CSV
            </button>
          )
        }
      />
      {!rows.length ? (
        <Empty
          title="No readings in this range"
          text="Choose dates when the motors were reporting, or include all motors."
        />
      ) : (
        <>
          <div
            className="report-chart chart"
            role="img"
            aria-label={`${reportDescriptions[kind].title} report chart`}
          >
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <BarChart
                data={chartRows}
                margin={{ top: 20, right: 20, bottom: 10, left: 0 }}
                accessibilityLayer
              >
                <CartesianGrid vertical={false} stroke="#d5d9db" />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 13 }}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 13 }} />
                <Tooltip />
                <Legend
                  formatter={(value) => (
                    <span className="legend-label">{value}</span>
                  )}
                />
                {keys.map((key, index) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    name={columnLabels[key]}
                    fill={index === 0 ? "#1d5c7a" : "#4b7b8d"}
                    radius={[1, 1, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {columns.map((key) => (
                    <th key={key}>{columnLabels[key] ?? key}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    {columns.map((key) => (
                      <td key={key}>
                        {key === "deviceid"
                          ? motorName(row[key] ?? "")
                          : key === "day"
                            ? row[key]
                            : row[key] === null
                              ? "—"
                              : number(
                                  row[key],
                                  key.includes("count") ||
                                    key === "breached_readings"
                                    ? 0
                                    : 2,
                                )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

interface RecentReport {
  reportId: string;
  parameters: ReportParameters;
  createdAt: string;
  status: Report["status"];
}

export function Reports({ username }: { username: string }) {
  const storageKey = `forge.reports.${username}`;
  const [recent, setRecent] = useState<RecentReport[]>(() => {
    try {
      const stored: unknown = JSON.parse(
        sessionStorage.getItem(storageKey) ?? "[]",
      );
      return Array.isArray(stored)
        ? stored
            .filter(
              (item) =>
                typeof item?.reportId === "string" &&
                item.parameters &&
                item.createdAt,
            )
            .slice(0, 10)
        : [];
    } catch {
      return [];
    }
  });
  const [kind, setKind] = useState<ReportKind>("temperature");
  const [start, setStart] = useState(utcDate());
  const [end, setEnd] = useState(utcDate());
  const [device, setDevice] = useState("");
  const [report, setReport] = useState<Report>();
  const [submittedKind, setSubmittedKind] = useState<ReportKind>("temperature");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = report?.status === "QUEUED" || report?.status === "RUNNING";
  useEffect(() => {
    sessionStorage.setItem(storageKey, JSON.stringify(recent));
  }, [recent, storageKey]);
  useEffect(() => {
    if (report)
      setRecent((items) =>
        items.map((item) =>
          item.reportId === report.reportId
            ? { ...item, status: report.status }
            : item,
        ),
      );
  }, [report]);
  useEffect(() => {
    if (!running || !report) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setReport(
          await api<Report>(`/reports/${report.reportId}`, {
            signal: controller.signal,
          }),
        );
        setError("");
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not check report status.",
          );
          setReport((value) => value && { ...value });
        }
      }
    }, 3000);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [report, running]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const distance = (Date.parse(end) - Date.parse(start)) / 86400000;
    if (
      !start ||
      !end ||
      distance < 0 ||
      distance > 6 ||
      start < utcDate(-29) ||
      end > utcDate()
    ) {
      setError("Choose up to 7 days within the last 30 days.");
      return;
    }
    setBusy(true);
    setReport(undefined);
    setSubmittedKind(kind);
    const parameters: ReportParameters = {
      report: kind,
      start,
      end,
      ...(device ? { deviceId: device } : {}),
    };
    try {
      const created = await api<Report>("/reports", {
        method: "POST",
        body: parameters,
      });
      setReport(created);
      setRecent((items) =>
        [
          {
            reportId: created.reportId,
            parameters,
            status: created.status,
            createdAt: new Date().toISOString(),
          },
          ...items.filter((item) => item.reportId !== created.reportId),
        ].slice(0, 10),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Report could not be started.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading title="Reports" />
      <form
        onSubmit={(event) => void submit(event)}
        className="panel report-form"
      >
        <PanelHead title="Build a report" />
        <div className="date-presets" aria-label="Date presets">
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setStart(utcDate());
              setEnd(utcDate());
            }}
          >
            Today
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setStart(utcDate(-6));
              setEnd(utcDate());
            }}
          >
            Last 7 days
          </button>
        </div>
        <div
          className="report-options"
          role="radiogroup"
          aria-label="Report type"
        >
          {(Object.keys(reportDescriptions) as ReportKind[]).map((key) => {
            const item = reportDescriptions[key];
            return (
              <label
                className={`report-option ${kind === key ? "selected" : ""}`}
                key={key}
              >
                <input
                  type="radio"
                  name="report-kind"
                  value={key}
                  checked={kind === key}
                  onChange={() => setKind(key)}
                />

                <strong>{item.title}</strong>
                <span>{item.description}</span>
              </label>
            );
          })}
        </div>
        <div className="report-fields">
          <label>
            Start date (UTC)
            <input
              type="date"
              value={start}
              min={utcDate(-29)}
              max={utcDate()}
              required
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label>
            End date (UTC)
            <input
              type="date"
              value={end}
              min={start || utcDate(-29)}
              max={utcDate()}
              required
              onChange={(event) => setEnd(event.target.value)}
            />
          </label>
          <label>
            Equipment
            <select
              value={device}
              onChange={(event) => setDevice(event.target.value)}
            >
              <option value="">All motors</option>
              {["motor-01", "motor-02", "motor-03"].map((id) => (
                <option key={id} value={id}>
                  {motorName(id)}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button primary"
            disabled={busy || running}
            type="submit"
          >
            {busy ? "Starting…" : "Generate report"}
          </button>
        </div>
      </form>
      {error && (
        <ErrorNotice
          message={error}
          retry={
            running
              ? () => setReport((value) => value && { ...value })
              : undefined
          }
        />
      )}
      {running && (
        <section className="panel report-progress" role="status">
          <Loading
            label={
              report.status === "QUEUED"
                ? "Your report is queued…"
                : "Generating report…"
            }
          />
        </section>
      )}
      {report?.status === "SUCCEEDED" && (
        <ReportResults result={report} kind={submittedKind} />
      )}
      {(report?.status === "FAILED" || report?.status === "CANCELLED") && (
        <ErrorNotice
          message={
            report.error ||
            "The historical query did not complete. Try a smaller date range."
          }
        />
      )}
      <section className="panel recent-reports">
        <PanelHead title="Recent reports" />
        {!recent.length ? (
          <p className="recent-empty">No reports in this session.</p>
        ) : (
          <ul>
            {recent.map((item) => (
              <li key={item.reportId}>
                <button
                  className="text-button"
                  disabled={busy || running}
                  onClick={() => {
                    setBusy(true);
                    setError("");
                    setSubmittedKind(item.parameters.report);
                    void api<Report>(`/reports/${item.reportId}`)
                      .then(setReport)
                      .catch((err: unknown) =>
                        setError(
                          err instanceof Error
                            ? err.message
                            : "Could not open report.",
                        ),
                      )
                      .finally(() => setBusy(false));
                  }}
                >
                  {reportDescriptions[item.parameters.report]?.title ??
                    "Report"}{" "}
                  · {item.parameters.start}
                  {item.parameters.start !== item.parameters.end &&
                    ` – ${item.parameters.end}`}
                </button>
                <span>{item.status.toLowerCase()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function AccountRow({
  account,
  ownUsername,
  onSaved,
}: {
  account: Account;
  ownUsername: string;
  onSaved: () => void;
}) {
  const email =
    account.attributes.find((attribute) => attribute.Name === "email")?.Value ??
    account.username;
  const [roles, setRoles] = useState<Role[]>(account.roles);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setRoles(account.roles);
  }, [account.roles]);
  const changed = [...roles].sort().join() !== [...account.roles].sort().join();
  const self = account.username === ownUsername || email === ownUsername;
  function toggle(role: Role) {
    setRoles((value) =>
      value.includes(role)
        ? value.filter((item) => item !== role)
        : [...value, role],
    );
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      await api("/users", { method: "PUT", body: { email, roles } });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save roles.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <tr>
      <td>
        <div className="user-name">
          <span className="avatar small">
            {email.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{email}</strong>
            {self && <span className="cell-sub">Your account</span>}
          </div>
        </div>
        {error && <ErrorNotice message={error} />}
      </td>
      <td>
        <Badge tone={account.enabled ? "success" : "neutral"}>
          {account.enabled ? "Enabled" : "Disabled"}
        </Badge>
        <span className="cell-sub">
          {account.status === "FORCE_CHANGE_PASSWORD"
            ? "Invitation sent · password setup required"
            : account.status.replaceAll("_", " ").toLowerCase()}
        </span>
      </td>
      <td>
        <div className="role-checkboxes">
          {(["viewer", "operator"] as Role[]).map((role) => (
            <label key={role}>
              <input
                type="checkbox"
                checked={roles.includes(role)}
                disabled={busy || (self && role === "operator")}
                onChange={() => toggle(role)}
              />
              {role}
            </label>
          ))}
        </div>
      </td>
      <td>
        <button
          className="button secondary small"
          disabled={!changed || !roles.length || busy}
          onClick={() => void save()}
        >
          {busy ? "Saving…" : "Save roles"}
        </button>
      </td>
    </tr>
  );
}

export function UserManagement({
  operator,
  username,
}: {
  operator: boolean;
  username: string;
}) {
  if (!operator)
    return (
      <>
        <Heading title="Operator access required" />
      </>
    );
  return <UserManagementContent username={username} />;
}
function UserManagementContent({ username }: { username: string }) {
  const accounts = usePoll(
    (signal) => api<{ users: Account[] }>("/users", { signal }),
    0,
  );
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState<Role[]>(["viewer"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function invite(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api("/users", {
        method: "POST",
        body: { email: email.trim(), roles },
      });
      setSuccess(`Invitation sent to ${email.trim()}.`);
      setEmail("");
      accounts.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not invite user.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading title="Team" />
      <form
        className="panel invite-form"
        onSubmit={(event) => void invite(event)}
      >
        <PanelHead title="Invite a team member" />
        <div className="invite-fields">
          <label>
            Email address
            <input
              type="email"
              required
              maxLength={254}
              placeholder="teammate@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <fieldset className="role-checkboxes">
            <legend>Roles</legend>
            {(["viewer", "operator"] as Role[]).map((role) => (
              <label key={role}>
                <input
                  type="checkbox"
                  checked={roles.includes(role)}
                  onChange={() =>
                    setRoles((value) =>
                      value.includes(role)
                        ? value.filter((item) => item !== role)
                        : [...value, role],
                    )
                  }
                />
                {role}
              </label>
            ))}
          </fieldset>
          <button className="button primary" disabled={busy || !roles.length}>
            {busy ? "Inviting…" : "Send invitation"}
          </button>
        </div>
        {error && <ErrorNotice message={error} />}
        {success && (
          <div className="notice success" role="status">
            <Check size={17} />
            <span>{success}</span>
          </div>
        )}
      </form>
      <section className="panel">
        <PanelHead
          title="Team members"
          subtitle={`${accounts.data?.users.length ?? "—"} accounts`}
          action={
            <button className="text-button" onClick={accounts.refresh}>
              Refresh
            </button>
          }
        />
        {accounts.error && (
          <ErrorNotice message={accounts.error} retry={accounts.refresh} />
        )}
        {!accounts.data ? (
          <Loading label="Loading team members…" />
        ) : !accounts.data.users.length ? (
          <Empty
            title="No accounts found"
            text="Invite your first team member above."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Team member</th>
                  <th>Account status</th>
                  <th>Roles</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {accounts.data.users.map((account) => (
                  <AccountRow
                    key={account.username}
                    account={account}
                    ownUsername={username}
                    onSaved={accounts.refresh}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export function Welcome({
  onSignIn,
  error,
  busy,
}: {
  onSignIn: () => void;
  error: string;
  busy: boolean;
}) {
  return (
    <div className="entry-page">
      <header className="entry-header">
        <span className="brand">Forge</span>
      </header>
      <main className="entry-main">
        <section className="entry-card" aria-labelledby="entry-title">
          <div className="entry-card-body">
            <h1 id="entry-title">Equipment monitoring</h1>
            <p>Sign in to view motor readings, alerts and reports.</p>
            <button className="entry-signin" onClick={onSignIn} disabled={busy}>
              <span>{busy ? "Opening sign-in…" : "Sign in"}</span>
              <ArrowRight size={18} />
            </button>
            {error && <ErrorNotice message={error} />}
            <details className="entry-help">
              <summary>First sign-in or password trouble?</summary>
              <p>
                For a new account, use the temporary password in your invitation
                email. You’ll choose your own password after signing in.
              </p>
              <p>
                Once your account is set up and your email verified, use “Forgot
                password” on the sign-in screen to request a reset code.
              </p>
            </details>
          </div>
          <div className="entry-card-bottom">
            <span>Invited accounts only</span>
          </div>
        </section>
      </main>
    </div>
  );
}
