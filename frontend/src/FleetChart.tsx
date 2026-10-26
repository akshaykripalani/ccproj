import { useEffect, useRef, useState } from "react";
import {
  Empty,
  ErrorNotice,
  PanelHead,
  TelemetrySkeleton,
  useReadingHistory,
} from "./components";
import { motorName, number, when } from "./format";
import { readingPath, timeLabel, type EquipmentEvent } from "./telemetry";
import type { Device } from "./types";

export function AllMotorTrend({
  devices,
  now,
  history,
  hours,
  setHours,
  events,
  selectedEvent,
  selectEvent,
}: {
  devices: Device[];
  now: number;
  history: ReturnType<typeof useReadingHistory>;
  hours: string;
  setHours: (hours: string) => void;
  events: EquipmentEvent[];
  selectedEvent?: string;
  selectEvent: (id?: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number>();
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
    Math.floor(Math.min(40, ...values.map((r) => r.temperatureC)) / 10) * 10;
  const maximum =
    Math.ceil(Math.max(90, ...values.map((r) => r.temperatureC)) / 10) * 10;
  const narrow = width < 470;
  const left = 34,
    right = width - (narrow ? 12 : 130),
    top = 24,
    bottom = narrow ? 265 : 245;
  const availableStart = Math.min(
    ...values.map((r) => Date.parse(r.observedAt)),
  );
  const from = Math.max(
    now - Number(hours) * 3600000,
    Math.min(now - 60000, availableStart),
  );
  const x = (t: number) =>
    left + (right - left) * Math.max(0, Math.min(1, (t - from) / (now - from)));
  const y = (v: number) =>
    bottom - ((v - minimum) / (maximum - minimum)) * (bottom - top);
  const times = [...new Set(values.map((r) => Date.parse(r.observedAt)))].sort(
    (a, b) => a - b,
  );
  const selectedTime =
    hover === undefined
      ? undefined
      : times.reduce(
          (a, b) => (Math.abs(b - hover) < Math.abs(a - hover) ? b : a),
          times[0],
        );
  const series = devices.map((device, index) => {
    const readings = values
      .filter((r) => r.deviceId === device.deviceId)
      .sort((a, b) => a.observedAt.localeCompare(b.observedAt));
    const last = readings.at(-1);
    const fault =
      device.online &&
      !!device.latest &&
      device.latest.temperatureC > (device.thresholds.temperature?.value ?? 75);
    const color = fault
      ? "#a8340a"
      : [
          "#1d5c7a",
          "#30738c",
          "#406d82",
          "#517889",
          "#256064",
          "#5b677a",
          "#476b55",
        ][index % 7];
    const nearest =
      selectedTime === undefined || !readings.length
        ? undefined
        : readings.reduce((a, b) =>
            Math.abs(Date.parse(b.observedAt) - selectedTime) <
            Math.abs(Date.parse(a.observedAt) - selectedTime)
              ? b
              : a,
          );
    return {
      id: device.deviceId,
      last,
      color,
      path: readingPath(readings, x, y),
      selected:
        nearest &&
        Math.abs(Date.parse(nearest.observedAt) - selectedTime!) <= 15000
          ? nearest
          : undefined,
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
      i ? labels[i - 1].labelY + 20 : top + 8,
    );
  const overflow = Math.max(0, (labels.at(-1)?.labelY ?? 0) - bottom);
  for (const label of labels) label.labelY -= overflow;
  const markers = events.filter(
    (event) => Date.parse(event.time) >= from && Date.parse(event.time) <= now,
  );
  const highlighted = events.find((event) => event.id === selectedEvent);
  return (
    <section className="panel comparison-panel">
      <PanelHead
        title="Temperature, all equipment"
        action={
          <label className="range-picker">
            <span className="sr-only">Chart time range</span>
            <select
              aria-label="Chart time range"
              value={hours}
              onChange={(e) => {
                setHover(undefined);
                setHours(e.target.value);
              }}
            >
              <option value="0.5">Last 30 minutes</option>
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
          <TelemetrySkeleton />
        ) : !values.length ? (
          <Empty title="No readings in this window" />
        ) : (
          <>
            <div
              className={`chart-readout ${selectedTime !== undefined ? "inspecting" : ""}`}
              aria-live="off"
            >
              <time>
                {selectedTime !== undefined
                  ? timeLabel(selectedTime, true)
                  : "Latest"}
              </time>
              {series.map((s) => (
                <span key={s.id} style={{ color: s.color }}>
                  {motorName(s.id)}{" "}
                  <strong>
                    {number(
                      (selectedTime === undefined ? s.last : s.selected)
                        ?.temperatureC,
                    )}{" "}
                    °C
                  </strong>
                </span>
              ))}
            </div>
            <svg
              viewBox={`0 0 ${width} ${bottom + 35}`}
              role="img"
              data-window-start={from}
              data-window-end={now}
              aria-label={`Temperature chart with ${values.length} readings across all equipment in °C`}
              onPointerMove={(event) => {
                const bounds = event.currentTarget.getBoundingClientRect();
                const px =
                  ((event.clientX - bounds.left) / bounds.width) * width;
                setHover(
                  from +
                    Math.max(0, Math.min(1, (px - left) / (right - left))) *
                      (now - from),
                );
              }}
              onPointerLeave={() => {
                setHover(undefined);
                selectEvent(undefined);
              }}
            >
              <rect
                className="danger-zone"
                x={left}
                y={top}
                width={right - left}
                height={Math.max(0, y(75) - top)}
              />
              {Array.from(
                { length: (maximum - minimum) / 10 + 1 },
                (_, index) => minimum + index * 10,
              ).map((value) => (
                <g key={value}>
                  <line
                    x1={left}
                    x2={right}
                    y1={y(value)}
                    y2={y(value)}
                    stroke="#d5dfe4"
                  />
                  <text x={left - 9} y={y(value) + 4} textAnchor="end">
                    {number(value, 0)}
                  </text>
                </g>
              ))}
              <line
                x1={left}
                x2={right}
                y1={y(75)}
                y2={y(75)}
                stroke="#a8340a"
                strokeDasharray="5 4"
              />
              <text x={left + 4} y={y(75) - 7} className="limit-label">
                Limit 75 °C
              </text>
              {series.map((item, index) => (
                <path
                  className="fleet-line"
                  key={item.id}
                  d={item.path}
                  fill="none"
                  stroke={item.color}
                  strokeWidth={item.color === "#a8340a" ? 2.8 : 2}
                  strokeDasharray={
                    index === 1 ? "6 3" : index === 2 ? "2 2" : undefined
                  }
                />
              ))}
              {markers.map((event) => (
                <g
                  key={event.id}
                  className="event-marker"
                  onPointerEnter={() => selectEvent(event.id)}
                >
                  <title>
                    {event.title} · {when(event.time)}
                  </title>
                  <line
                    x1={x(Date.parse(event.time))}
                    x2={x(Date.parse(event.time))}
                    y1={bottom - 12}
                    y2={bottom + 3}
                    stroke={event.problem ? "#a8340a" : "#1d5c7a"}
                    strokeWidth={selectedEvent === event.id ? 4 : 2}
                  />
                  <rect
                    x={x(Date.parse(event.time)) - 5}
                    y={bottom - 18}
                    width="10"
                    height="24"
                    fill="transparent"
                  />
                </g>
              ))}
              {highlighted && Date.parse(highlighted.time) >= from && (
                <line
                  className="event-guide"
                  x1={x(Date.parse(highlighted.time))}
                  x2={x(Date.parse(highlighted.time))}
                  y1={top}
                  y2={bottom}
                />
              )}
              {labels.map((item) => (
                <g key={item.id} fill={item.color}>
                  <circle
                    cx={x(Date.parse(item.last!.observedAt))}
                    cy={y(item.last!.temperatureC)}
                    r="3"
                  />
                  {!narrow && (
                    <>
                      <path
                        className="label-leader"
                        d={`M${x(Date.parse(item.last!.observedAt)) + 4},${y(item.last!.temperatureC)} L${right + 7},${item.labelY} L${right + 12},${item.labelY}`}
                        stroke={item.color}
                        fill="none"
                      />
                      <text x={right + 16} y={item.labelY + 4}>
                        {motorName(item.id)} {number(item.last!.temperatureC)}
                      </text>
                    </>
                  )}
                </g>
              ))}
              {selectedTime !== undefined && (
                <g className="chart-crosshair">
                  <line
                    x1={x(selectedTime)}
                    x2={x(selectedTime)}
                    y1={top}
                    y2={bottom}
                  />
                  {series
                    .filter((s) => s.selected)
                    .map((s) => (
                      <circle
                        key={s.id}
                        cx={x(selectedTime)}
                        cy={y(s.selected!.temperatureC)}
                        r="4"
                        fill={s.color}
                      />
                    ))}
                </g>
              )}
              {[0, 0.5, 1].map((fraction) => (
                <text
                  key={fraction}
                  x={left + (right - left) * fraction}
                  y={bottom + 25}
                  textAnchor={
                    fraction === 0 ? "start" : fraction === 1 ? "end" : "middle"
                  }
                >
                  {timeLabel(from + (now - from) * fraction)}
                </text>
              ))}
            </svg>
            <label className="chart-scrubber-label">
              <span className="sr-only">Inspect chart time</span>
              <input
                type="range"
                className="chart-scrubber"
                aria-label="Inspect chart time"
                min="0"
                max={Math.max(0, times.length - 1)}
                value={
                  selectedTime === undefined
                    ? Math.max(0, times.length - 1)
                    : times.indexOf(selectedTime)
                }
                aria-valuetext={
                  selectedTime === undefined
                    ? "Latest readings"
                    : `${timeLabel(selectedTime, true)}, ${series.map((s) => `${motorName(s.id)} ${number(s.selected?.temperatureC)} degrees Celsius`).join(", ")}`
                }
                onChange={(e) => setHover(times[Number(e.target.value)])}
                onFocus={() => setHover(times.at(-1))}
                onBlur={() => setHover(undefined)}
              />
            </label>
            {highlighted && (
              <p className="chart-event-caption">
                {timeLabel(highlighted.time, true)} · {highlighted.title}
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
