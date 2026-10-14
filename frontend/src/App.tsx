import { useEffect, useState } from "react";
import type { User } from "oidc-client-ts";
import {
  Activity,
  Bell,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  Menu,
  RefreshCw,
  Settings2,
  Users,
} from "lucide-react";
import { api } from "./api";
import { auth, finishSignIn, rolesFromToken, signIn, signOut } from "./auth";
import { Badge, ErrorNotice, Loading } from "./components";
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
  { route: "overview", title: "Overview", icon: LayoutDashboard },
  { route: "devices", title: "Equipment", icon: Settings2 },
  { route: "alerts", title: "Alerts & events", icon: Bell },
  { route: "reports", title: "Historical reports", icon: Activity },
  { route: "users", title: "Team & permissions", icon: Users },
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
        <div className="brand-mark">F</div>
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
  const [open, setOpen] = useState(false);
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
  useEffect(() => {
    setOpen(false);
    document.title = `${title} — Forge`;
    window.scrollTo(0, 0);
  }, [route, title]);
  async function logout() {
    try {
      await signOut();
    } catch {
      setLogoutError(
        "Hosted sign-out could not be reached. Your local session has been cleared.",
      );
    }
  }
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
      {open && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <a className="brand" href="#/overview">
          <div className="brand-mark">F</div>
          <span>
            forge<span className="brand-period">.</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">
            <Settings2 size={19} />
          </span>
          <div>
            <strong>Factory workspace</strong>
          </div>
          <ChevronRight size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation
            .filter((item) => operator || item.route !== "users")
            .map((item) => (
              <a
                key={item.route}
                className={section === item.route ? "active" : ""}
                href={`#/${item.route}`}
                aria-current={section === item.route ? "page" : undefined}
              >
                <item.icon size={18} />
                <span>{item.title}</span>
                {item.route === "alerts" && active > 0 && (
                  <span className="nav-count">{active}</span>
                )}
              </a>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-user">
            <span className="avatar">
              {String(email).slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong title={String(email)}>{email}</strong>
              <span>
                {operator
                  ? roles.includes("viewer")
                    ? "Operator & viewer"
                    : "Operator"
                  : "Viewer"}
              </span>
            </div>
            <button
              aria-label="Sign out"
              title="Sign out"
              onClick={() => void logout()}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <div>
            <span className="header-date">
              {new Date(now).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
            <Badge
              tone={
                live.error || (live.updatedAt && now - live.updatedAt > 30000)
                  ? "warning"
                  : "success"
              }
            >
              {live.error
                ? "Connection interrupted"
                : live.updatedAt
                  ? now - live.updatedAt > 30000
                    ? "Updates delayed"
                    : "Live connection"
                  : "Connecting"}
            </Badge>
            <button
              className="icon-button"
              aria-label="Refresh telemetry"
              onClick={live.refresh}
            >
              <RefreshCw size={17} className={live.loading ? "spin" : ""} />
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          {logoutError && <ErrorNotice message={logoutError} />}
          {live.error && (
            <ErrorNotice
              message={`${live.error} ${live.data ? "Showing the last available readings." : ""}`}
              retry={live.refresh}
            />
          )}
          {live.updatedAt > 0 &&
            now - live.updatedAt > 30000 &&
            !live.error && (
              <div className="notice warning" role="status">
                Updates delayed. Last refreshed{" "}
                {Math.round((now - live.updatedAt) / 1000)} seconds ago.
              </div>
            )}
          {section === "alerts" ? (
            <Alerts />
          ) : section === "reports" ? (
            <Reports />
          ) : section === "users" ? (
            <UserManagement operator={operator} username={username} />
          ) : !live.data ? (
            <Loading />
          ) : section === "devices" ? (
            <Equipment {...props} deviceId={route.split("/")[1]} />
          ) : (
            <Overview {...props} />
          )}
        </main>
      </div>
    </div>
  );
}
