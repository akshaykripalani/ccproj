import { useEffect, useState } from "react";
import { api } from "./api";
import { usePoll } from "./hooks";
import { motorName, number, when } from "./format";
import type { Control, Device, FailureProfile } from "./types";

export const deviceIds = [
  "motor-01",
  "motor-02",
  "motor-03",
  "pump-01",
  "compressor-01",
  "fan-01",
  "generator-01",
];

export function currentPrediction(device: Device) {
  const prediction = device.prediction;
  return device.online &&
    prediction &&
    Date.now() - Date.parse(prediction.at) < 60000
    ? prediction
    : undefined;
}

export function PredictionLine({ device }: { device: Device }) {
  const prediction = currentPrediction(device);
  const action = device.control.maintenanceAction;
  return (
    <>
      {action && (
        <small className="cell-sub maintenance-action">{action}</small>
      )}
      {prediction?.warning && (
        <small className="cell-sub problem">
          {prediction.faultType === "vibration"
            ? "Mechanical fault"
            : "Overheating"}{" "}
          risk · next 5 simulated min
        </small>
      )}
    </>
  );
}

export function ProfileEditor({
  device,
  refresh,
}: {
  device: Device;
  refresh: () => void;
}) {
  const [profile, setProfile] = useState<FailureProfile>(
    device.profile ?? {
      enabled: true,
      failureAfterMinutes: 30,
      faultMode: "alternating",
      speed: 1,
    },
  );
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (device.profile) setProfile(device.profile);
  }, [device.deviceId]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api<Control>(`/profiles/${device.deviceId}`, {
        method: "POST",
        body: profile,
      });
      setMessage("Profile requested. A new cycle starts when applied.");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save profile.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="profile-form" onSubmit={(event) => void save(event)}>
      <h3>Failure profile</h3>
      <label className="profile-enabled">
        <input
          type="checkbox"
          checked={profile.enabled}
          onChange={(e) =>
            setProfile({ ...profile, enabled: e.target.checked })
          }
        />{" "}
        Automatic deterioration
      </label>
      <div className="profile-fields">
        <label>
          Failure mode
          <select
            value={profile.faultMode}
            onChange={(e) =>
              setProfile({
                ...profile,
                faultMode: e.target.value as FailureProfile["faultMode"],
              })
            }
          >
            <option value="alternating">
              Alternate overheating / mechanical
            </option>
            <option value="overheat">Recoverable overheating</option>
            <option value="vibration">Mechanical fault</option>
            <option value="persistent_overheat">Persistent overheating</option>
          </select>
        </label>
        <label>
          Cycle length (simulated min)
          <input
            type="number"
            min="10"
            max="120"
            step="1"
            required
            value={profile.failureAfterMinutes}
            onChange={(e) =>
              setProfile({
                ...profile,
                failureAfterMinutes: Number(e.target.value),
              })
            }
          />
        </label>
        <label>
          Demo speed
          <select
            value={profile.speed}
            onChange={(e) =>
              setProfile({ ...profile, speed: Number(e.target.value) })
            }
          >
            <option value="1">Normal · 1×</option>
            <option value="5">Fast · 5×</option>
            <option value="10">Presentation · 10×</option>
          </select>
        </label>
        <button className="button secondary" disabled={busy}>
          {busy ? "Saving…" : "Apply profile"}
        </button>
      </div>
      {message && (
        <p className="tiny" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

const measurementNames: Record<string, [string, string]> = {
  loadPercent: ["Load", "%"],
  rpm: ["Speed", "rpm"],
  flowLitresMin: ["Flow", "L/min"],
  pressureBar: ["Pressure", "bar"],
  airflowM3Min: ["Airflow", "m³/min"],
  outputPowerWatts: ["Generated power", "W"],
  voltage: ["Voltage", "V"],
  frequencyHz: ["Frequency", "Hz"],
};

export function EquipmentMetrics({ device }: { device: Device }) {
  const prediction = currentPrediction(device);
  return (
    <section className="panel equipment-signals">
      <div className="panel-head">
        <h2>Equipment readings</h2>
        <span className="tiny">{device.profile?.speed ?? 1}× simulation</span>
      </div>
      <dl>
        {Object.entries(device.latest?.metrics ?? {}).map(([key, value]) => (
          <div key={key}>
            <dt>{measurementNames[key]?.[0] ?? key}</dt>
            <dd>
              {number(value, key === "rpm" ? 0 : 1)}{" "}
              <small>{measurementNames[key]?.[1]}</small>
            </dd>
          </div>
        ))}
      </dl>
      <div className="prediction-detail">
        <strong>Next 5 simulated minutes</strong>
        <p>
          {prediction
            ? prediction.warning
              ? `${prediction.faultType === "vibration" ? "Mechanical fault" : "Overheating"} risk. ${prediction.faultType === "vibration" ? "Plan a mechanical inspection." : "Monitor load and cooling."}`
              : "No approaching fault detected."
            : "Prediction updating as readings arrive."}
        </p>
        {prediction && (
          <small>
            Risk score {number(prediction.riskScore * 100, 0)}/100 · model{" "}
            {prediction.modelVersion} · {when(prediction.at)}
          </small>
        )}
        {device.control.maintenanceAction && (
          <p className="maintenance-action">
            {device.control.maintenanceAction}
          </p>
        )}
      </div>
    </section>
  );
}

interface MaintenanceEvent {
  deviceId: string;
  action: string;
  at: string;
  sk: string;
  faultType?: string;
}
interface ModelInfo {
  version: string;
  evaluation: {
    episodes?: number;
    heldOut?: { precision: number; recall: number; f1: number };
    warningLeadMinutes?: { median: number };
  };
}

export function MaintenancePanel({ deviceId }: { deviceId?: string }) {
  const events = usePoll(
    (signal) =>
      api<{ events: MaintenanceEvent[] }>(
        `/maintenance${deviceId ? `?deviceId=${deviceId}` : ""}`,
        { signal },
      ),
    10000,
    deviceId,
  );
  const model = usePoll(
    (signal) => api<ModelInfo>("/model", { signal }),
    60000,
  );
  return (
    <section className="panel maintenance-panel">
      <div className="panel-head">
        <h2>Predictive maintenance</h2>
        <span className="tiny">5-minute outlook</span>
      </div>
      {events.error && (
        <p className="notice error" role="alert">
          {events.error}
        </p>
      )}
      {!events.data ? (
        <p className="maintenance-empty">Loading maintenance history…</p>
      ) : events.data.events.length ? (
        <ol className="maintenance-log">
          {events.data.events.slice(0, 8).map((event) => (
            <li key={event.deviceId + event.sk}>
              <a href={`#/devices/${event.deviceId}`}>
                {motorName(event.deviceId)}
              </a>
              <span
                className={event.action === "Repair needed" ? "problem" : ""}
              >
                {event.action}
                {event.faultType
                  ? ` · ${event.faultType === "vibration" ? "mechanical" : "overheating"}`
                  : ""}
              </span>
              <time dateTime={event.at}>{when(event.at)}</time>
            </li>
          ))}
        </ol>
      ) : (
        <p className="maintenance-empty">No maintenance events yet.</p>
      )}
      <details className="model-details">
        <summary>
          Model details{model.data ? ` · ${model.data.version}` : ""}
        </summary>
        {model.error ? (
          <p role="alert">{model.error}</p>
        ) : (
          <p>
            Dataset of {model.data?.evaluation.episodes ?? "—"} simulated runs.
            Held-out precision{" "}
            {number((model.data?.evaluation.heldOut?.precision ?? 0) * 100, 1)}
            %, recall{" "}
            {number((model.data?.evaluation.heldOut?.recall ?? 0) * 100, 1)}%.
            Median warning{" "}
            {number(model.data?.evaluation.warningLeadMinutes?.median, 1)}{" "}
            simulated minutes. Risk scores describe this simulator; they are not
            guarantees for real equipment.
          </p>
        )}
      </details>
    </section>
  );
}
