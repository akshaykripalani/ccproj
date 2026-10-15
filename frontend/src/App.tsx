import { useEffect, useState } from "react";
import type { User } from "oidc-client-ts";
import { RefreshCw } from "lucide-react";
import { api } from "./api";
import { auth, finishSignIn, rolesFromToken, signIn, signOut } from "./auth";
import { ErrorNotice, Loading, TelemetrySkeleton } from "./components";
import { useClock, usePoll, useRoute } from "./hooks";
import {
  Alerts,
  Equipment,
  Overview,
  Reports,
  UserManagement,
  Welcome,
} from "./pages";
import type { DeviceResponse } from "./types";
import "./styles.css";
import "./entry.css";

const navigation = [
  { route: "overview", title: "Overview" },
  { route: "devices", title: "Equipment" },
  { route: "alerts", title: "Alerts" },
  { route: "reports", title: "Reports" },
  { route: "users", title: "Team" },
];

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let disposed = false;
    let unsubscribe = () => {};
    void (async () => {
      try {
        const client = await auth();
        const loaded = (value: User) => {
          if (!disposed) {
            setUser(value);
            setError("");
          }
        };
        const expired = () => {
          if (!disposed) {
            setUser(null);
            setError("Your session has expired. Sign in again to continue.");
          }
        };
        const removed = () => {
          if (!disposed) setUser(null);
        };
        client.events.addUserLoaded(loaded);
        client.events.addUserUnloaded(removed);
        client.events.addSilentRenewError(expired);
        client.events.addAccessTokenExpired(expired);
        window.addEventListener("forge:session-expired", expired);
        unsubscribe = () => {
          client.events.removeUserLoaded(loaded);
          client.events.removeUserUnloaded(removed);
          client.events.removeSilentRenewError(expired);
          client.events.removeAccessTokenExpired(expired);
          window.removeEventListener("forge:session-expired", expired);
        };
        const value =
          location.pathname === "/callback"
            ? await finishSignIn()
            : await client.getUser();
        if (value?.expired) {
          try {
            loaded((await client.signinSilent())!);
          } catch {
            await client.removeUser();
            expired();
          }
        } else if (!disposed) setUser(value);
        client.startSilentRenew();
      } catch (err) {
        if (!disposed)
          setError(
            err instanceof Error
              ? err.message
              : "Application could not be loaded.",
          );
      } finally {
        if (!disposed) setLoading(false);
      }
    })();
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);
  async function login() {
    setBusy(true);
    setError("");
    try {
      await signIn();
    } catch {
      setError("Sign-in could not be opened. Please try again.");
      setBusy(false);
    }
  }
  if (loading)
    return (
      <div className="boot">
        <div className="brand-mark">Forge</div>
        <Loading label="Opening your dashboard…" />
      </div>
    );
  if (!user)
    return <Welcome onSignIn={() => void login()} error={error} busy={busy} />;
  return <Dashboard user={user} />;
}

function Dashboard({ user }: { user: User }) {
  const route = useRoute();
  const now = useClock();
  const [logoutError, setLogoutError] = useState("");
  const roles = rolesFromToken(user.access_token);
  const operator = roles.includes("operator");
  const live = usePoll(
    (signal) => api<DeviceResponse>("/devices", { signal }),
    (response, receivedAt) => {
      if (!response) return 10000;
      const serverNow =
        Date.parse(response.serverTime) + Date.now() - receivedAt;
      // Use server time, and bound fast retries even if later refreshes fail.
      const pending = response.devices.some(
        ({ control }) =>
          control.status === "pending" &&
          control.requestedAt &&
          serverNow - Date.parse(control.requestedAt) < 60000,
      );
      return pending ? 1000 : 10000;
    },
  );
  const serverOffset = live.data
    ? Date.parse(live.data.serverTime) - live.updatedAt
    : 0;
  const serverNow = now + serverOffset;
  const devices = (live.data?.devices ?? []).map((device) => ({
    ...device,
    online: Boolean(
      device.online &&
      device.lastSeen &&
      serverNow - Date.parse(device.lastSeen) < 60000,
    ),
  }));
  const section = route.split("/")[0];
  const title =
    navigation.find((item) => item.route === section)?.title ?? "Overview";
  const email = String(
    user.profile.email ?? user.profile["cognito:username"] ?? "Team member",
  );
  const username = String(user.profile["cognito:username"] ?? email);
  const active = devices.reduce(
    (sum, device) =>
      sum +
      Object.values(device.latest?.rules ?? {}).filter((rule) => rule.active)
        .length,
    0,
  );
  const props = { devices, operator, now: serverNow, refresh: live.refresh };
  const activeSince = devices
    .flatMap((device) =>
      Object.values(device.latest?.rules ?? {})
        .filter((rule) => rule.active && rule.alertId)
        .map((rule) => Date.parse(rule.alertId!.split("#")[0])),
    )
    .filter(Number.isFinite);
  const elapsed = activeSince.length
    ? Math.max(0, Math.floor((serverNow - Math.min(...activeSince)) / 1000))
    : undefined;
  useEffect(() => {
    document.title = `${active ? `(${active}) ` : ""}${title} — Forge`;
  }, [title, active]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route]);
  async function logout() {
    try {
      await signOut();
    } catch {
      setLogoutError(
        "Hosted sign-out could not be reached. Your local session has been cleared.",
      );
    }
  }
  const delayed = Boolean(
    live.error || (live.updatedAt && now - live.updatedAt > 30000),
  );
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Skip to content
      </a>
      <header className="app-header">
        <a className="brand" href="#/overview">
          Forge
        </a>
        <nav aria-label="Main navigation">
          {navigation
            .filter((item) => operator || item.route !== "users")
            .map((item) => (
              <a
                key={item.route}
                href={`#/${item.route}`}
                aria-current={section === item.route ? "page" : undefined}
              >
                {item.title}
                {item.route === "alerts" && active > 0 && (
                  <span className="nav-count">{active}</span>
                )}
              </a>
            ))}
        </nav>
        <div className="account-bar">
          <span
            className={`connection ${delayed ? "problem" : ""}`}
            role="status"
          >
            {live.error
              ? "Connection interrupted"
              : delayed
                ? "Updates delayed"
                : live.updatedAt
                  ? `Live · updated ${Math.max(0, Math.round((now - live.updatedAt) / 1000))}s ago`
                  : "Connecting…"}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh telemetry"
            onClick={live.refresh}
          >
            <RefreshCw size={17} className={live.loading ? "spin" : ""} />
          </button>
          <span className="account-email" title={email}>
            {email}
          </span>
          <button className="text-button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>
      {active > 0 && (
        <div className="fault-banner" role="status">
          <span className="fault-indicator" aria-hidden="true" />
          <a href="#/alerts">
            {active} active {active === 1 ? "fault" : "faults"}
          </a>
          {elapsed !== undefined && (
            <span>
              Active for{" "}
              <time>
                {String(Math.floor(elapsed / 60)).padStart(2, "0")}:
                {String(elapsed % 60).padStart(2, "0")}
              </time>
            </span>
          )}
        </div>
      )}
      <main id="main" tabIndex={-1}>
        {logoutError && <ErrorNotice message={logoutError} />}
        {live.error && (
          <ErrorNotice
            message={`${live.error} ${live.data ? "Showing the last available readings." : ""}`}
            retry={live.refresh}
          />
        )}
        {live.updatedAt > 0 && now - live.updatedAt > 30000 && !live.error && (
          <div className="notice warning" role="status">
            Updates delayed. Last refreshed{" "}
            {Math.round((now - live.updatedAt) / 1000)} seconds ago.
          </div>
        )}
        {section === "alerts" ? (
          <Alerts />
        ) : section === "reports" ? (
          <Reports key={username} username={username} />
        ) : section === "users" ? (
          <UserManagement operator={operator} username={username} />
        ) : !live.data ? (
          <TelemetrySkeleton />
        ) : section === "devices" ? (
          <Equipment {...props} deviceId={route.split("/")[1]} />
        ) : (
          <Overview {...props} />
        )}
      </main>
    </div>
  );
}
