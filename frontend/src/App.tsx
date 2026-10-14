import { useEffect, useState } from "react";
import type { User } from "oidc-client-ts";
import {
  Activity,
  ArrowUpRight,
  Bell,
  ChevronRight,
  CircleHelp,
  LayoutDashboard,
  LogOut,
  Menu,
  Radio,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Users,
  X,
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
  const [help, setHelp] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const operator = rolesFromToken(user.access_token).includes("operator");
  const live = usePoll((signal) => api<DeviceResponse>("/devices", { signal }));
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
      <a className="skip-link" href="#main">
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
            <small>EQUIPMENT INTELLIGENCE</small>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">
            <Settings2 size={19} />
          </span>
          <div>
            <strong>Factory workspace</strong>
            <span>Shared demonstration</span>
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
          <div className="system-card">
            <Radio size={17} />
            <div>
              <strong>Connected to AWS</strong>
              <span>Sydney · ap-southeast-2</span>
            </div>
            <span className="status-dot online" />
          </div>
          <button
            className="sidebar-help"
            onClick={() => setHelp((value) => !value)}
          >
            <CircleHelp size={18} />
            <span>How the demo works</span>
            <ArrowUpRight size={15} />
          </button>
          <div className="sidebar-user">
            <span className="avatar">
              {String(email).slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong title={String(email)}>{email}</strong>
              <span>{operator ? "Operator & viewer" : "Viewer"}</span>
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
                  ? "Live connection"
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
          {help && (
            <section className="notice help-notice">
              <ShieldCheck size={21} />
              <div>
                <strong>A shared, live equipment demonstration</strong>
                <p>
                  All three motors normally run healthy. Operators can trigger a
                  fault or disconnect one motor; other users see the same
                  changes. Faults activate after three breached readings and
                  resolve after three healthy readings. Reset requests normal
                  operation and waits for simulator acknowledgement. The charts
                  retain 24 hours; reports analyze 30 days of archived data.
                </p>
              </div>
              <button
                className="icon-button"
                aria-label="Close demo help"
                onClick={() => setHelp(false)}
              >
                <X size={17} />
              </button>
            </section>
          )}
          {live.error && (
            <ErrorNotice
              message={`${live.error} ${live.data ? "Showing the last successful response; check freshness before relying on these readings." : ""}`}
              retry={live.refresh}
            />
          )}
          {live.updatedAt > 0 &&
            now - live.updatedAt > 30000 &&
            !live.error && (
              <div className="notice warning" role="status">
                Telemetry response is stale. Last refreshed{" "}
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
        <footer className="app-footer">
          <span>Forge · Industrial equipment monitoring</span>
          <span>Near-real-time polling · Shared simulated equipment</span>
        </footer>
      </div>
    </div>
  );
}
