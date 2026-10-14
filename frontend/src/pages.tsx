import { useEffect, useState } from "react";
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
  AllMotorTrend,
  PanelHead,
  RecentCharts,
  deviceCondition,
} from "./components";
import { modeName, motorName, number, utcDate, when } from "./format";
import { usePoll } from "./hooks";
import type {
  Account,
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
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function reset() {
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
        onClick={() => void reset()}
      >
        Reset all motors
      </button>
      {message && (
        <p className="tiny" role="status">
          {message}
        </p>
      )}
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

function statusHeadline(devices: Device[]) {
  const attention = devices.filter((device) =>
    ["danger", "warning"].includes(deviceCondition(device).tone),
  );
  const offline = devices.filter((device) => !device.online);
  const stopped = devices.filter(
    (device) => device.online && device.latest?.operatingState === "stopped",
  );
  if (attention.length > 1)
    return {
      title: `${attention.length} motors need attention`,
      detail:
        attention
          .map(
            (device) =>
              `${motorName(device.deviceId)}: ${deviceCondition(device).label.toLowerCase()}`,
          )
          .join(". ") + ".",
    };
  if (attention.length) {
    const device = attention[0],
      state = deviceCondition(device).label;
    const temperature =
      device.latest!.temperatureC >
      (device.thresholds.temperature?.value ?? 75);
    const vibration =
      device.latest!.vibrationMmS > (device.thresholds.vibration?.value ?? 4.5);
    return {
      title:
        state === "Recovering"
          ? `${motorName(device.deviceId)} is recovering`
          : temperature && vibration
            ? `${motorName(device.deviceId)} is over its temperature and vibration limits`
            : `${motorName(device.deviceId)} is over its ${temperature ? "temperature" : "vibration"} limit`,
      detail:
        state === "Recovering"
          ? "Readings have returned below the limit. Waiting for recovery confirmation."
          : `${number(temperature ? device.latest!.temperatureC : device.latest!.vibrationMmS, temperature ? 1 : 2)} ${temperature ? "°C" : "mm/s"} against a ${temperature ? (device.thresholds.temperature?.value ?? 75) : (device.thresholds.vibration?.value ?? 4.5)} ${temperature ? "°C" : "mm/s"} limit.`,
    };
  }
  if (offline.length)
    return {
      title:
        offline.length === 1
          ? `${motorName(offline[0].deviceId)} is not reporting`
          : `${offline.length} motors are not reporting`,
      detail: "Check the last-seen times below.",
    };
  if (stopped.length)
    return {
      title:
        stopped.length === 1
          ? `${motorName(stopped[0].deviceId)} is stopped`
          : `${stopped.length} motors are stopped`,
      detail: "Equipment is still reporting.",
    };
  if (!devices.length || devices.some((device) => !device.latest))
    return { title: "Waiting for equipment readings", detail: "" };
  return {
    title: "All motors are running normally",
    detail: "Temperature and vibration are within limits.",
  };
}

function Events({ devices }: { devices: Device[] }) {
  const alerts = usePoll((signal) => api<AlertResponse>("/alerts", { signal }));
  const events: {
    id: string;
    time: string;
    title: string;
    problem?: boolean;
  }[] = [];
  for (const alert of alerts.data?.alerts ?? []) {
    events.push({
      id: `${alert.alertId}:active`,
      time: alert.activatedAt,
      title: `${motorName(alert.pk)} ${alert.rule === "temperature" ? "over temperature" : "high vibration"}. Alert activated.`,
      problem: alert.state === "active",
    });
    if (alert.resolvedAt)
      events.push({
        id: `${alert.alertId}:resolved`,
        time: alert.resolvedAt,
        title: `${motorName(alert.pk)} ${alert.rule} fault resolved.`,
      });
  }
  for (const device of devices) {
    const control = device.control;
    if (control.appliedAt)
      events.push({
        id: `${device.deviceId}:applied:${control.appliedAt}`,
        time: control.appliedAt,
        title: `${motorName(device.deviceId)} ${modeName(control.appliedMode).toLowerCase()} mode applied.`,
      });
    if (control.status === "pending" && control.requestedAt)
      events.push({
        id: `${device.deviceId}:request:${control.requestId}`,
        time: control.requestedAt,
        title: `${motorName(device.deviceId)} ${modeName(control.requestedMode).toLowerCase()} requested.`,
      });
  }
  events.sort((a, b) => b.time.localeCompare(a.time));
  return (
    <section className="panel events-panel">
      <PanelHead title="Events" action={<a href="#/alerts">View all</a>} />
      {alerts.error && (
        <ErrorNotice message={alerts.error} retry={alerts.refresh} />
      )}
      {!alerts.data && !events.length ? (
        <Loading />
      ) : events.length ? (
        <ol className="event-log">
          {events.slice(0, 6).map((event) => (
            <li key={event.id}>
              <time dateTime={event.time}>{when(event.time)}</time>
              <span className={event.problem ? "problem" : ""}>
                {event.title}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <Empty title="No events in the last 24 hours" />
      )}
    </section>
  );
}

export function Overview({ devices, operator, now, refresh }: LiveProps) {
  const headline = statusHeadline(devices);
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
  return (
    <section aria-label="Plant overview">
      <div className="overview-heading">
        <div>
          <h1>{headline.title}</h1>
          {headline.detail && <p>{headline.detail}</p>}
          <p className="plant-summary">
            {devices.filter((device) => device.online).length} /{" "}
            {devices.length} online <span>·</span> {active} active{" "}
            {active === 1 ? "fault" : "faults"} <span>·</span>{" "}
            {reporting.length
              ? `${number(power / 1000, 2)} kW total draw`
              : "Power unavailable"}
          </p>
        </div>
        {operator && <ResetAll refresh={refresh} />}
      </div>
      <MotorTable
        devices={devices}
        operator={operator}
        now={now}
        refresh={refresh}
      />
      {operator && <DemoControls devices={devices} refresh={refresh} />}
      <div className="overview-bottom">
        <AllMotorTrend devices={devices} now={now} />
        <Events devices={devices} />
      </div>
    </section>
  );
}

export function Equipment(props: LiveProps & { deviceId?: string }) {
  if (!props.deviceId)
    return (
      <>
        <Heading
          title="Equipment"
          action={props.operator && <ResetAll refresh={props.refresh} />}
        />
        <MotorTable {...props} />
        {props.operator && (
          <DemoControls devices={props.devices} refresh={props.refresh} />
        )}
      </>
    );
  const device = props.devices.find((item) => item.deviceId === props.deviceId);
  if (!device)
    return (
      <Empty
        title="Equipment not found"
        text="Choose a motor from Equipment."
      />
    );
  return (
    <>
      <a href="#/devices" className="breadcrumb">
        ← Equipment
      </a>
      <Heading title={motorName(device.deviceId)} />
      <MotorTable {...props} devices={[device]} links={false} />
      {props.operator && (
        <DemoControls devices={[device]} refresh={props.refresh} />
      )}
      <details className="equipment-details panel">
        <summary>Equipment details</summary>
        <dl>
          <div>
            <dt>Device identifier</dt>
            <dd>{device.deviceId}</dd>
          </div>
          <div>
            <dt>Last received</dt>
            <dd>{when(device.lastSeen)}</dd>
          </div>
          <div>
            <dt>Observed at</dt>
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
            <dt>Recent history</dt>
            <dd>24 hours</dd>
          </div>
        </dl>
      </details>
      <RecentCharts deviceId={device.deviceId} />
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
  const [device, setDevice] = useState("");
  const [state, setState] = useState("");
  const [days, setDays] = useState("1");
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
    10000,
    device + state + days,
  );
  return (
    <>
      <Heading title="Alerts & events" />
      <section className="panel">
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
                    fill={index === 0 ? "#14181b" : "#8c969b"}
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

export function Reports() {
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
      setReport(
        await api<Report>("/reports", { method: "POST", body: parameters }),
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
      {!report && !busy && (
        <div className="report-placeholder">
          <h3>No report generated</h3>
        </div>
      )}
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
        <span>Forge</span>
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
