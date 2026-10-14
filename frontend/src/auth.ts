import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { Config } from "./types";

let configPromise: Promise<Config> | undefined;
let manager: UserManager | undefined;

export function getConfig(): Promise<Config> {
  return (configPromise ??= fetch("/config.json", { cache: "no-store" })
    .then(async (response) => {
      if (!response.ok)
        throw new Error(
          "Application configuration could not be loaded. Please try again.",
        );
      const config: Config = await response.json();
      for (const key of [
        "apiUrl",
        "loginDomain",
        "callbackUrl",
        "logoutUrl",
      ] as const) {
        if (
          new URL(config[key]).protocol !== "https:" &&
          new URL(config[key]).hostname !== "localhost"
        ) {
          throw new Error("Application configuration requires HTTPS.");
        }
      }
      if (!config.clientId || !config.userPoolId || !config.region)
        throw new Error("Application configuration is incomplete.");
      return config;
    })
    .catch((error) => {
      configPromise = undefined;
      throw error;
    }));
}

export async function auth() {
  if (manager) return manager;
  const config = await getConfig();
  if (manager) return manager;
  const issuer = `https://cognito-idp.${config.region}.amazonaws.com/${config.userPoolId}`;
  manager = new UserManager({
    authority: issuer,
    client_id: config.clientId,
    redirect_uri: config.callbackUrl,
    response_type: "code",
    scope: "openid email profile",
    metadata: {
      issuer,
      authorization_endpoint: `${config.loginDomain}/oauth2/authorize`,
      token_endpoint: `${config.loginDomain}/oauth2/token`,
      revocation_endpoint: `${config.loginDomain}/oauth2/revoke`,
      jwks_uri: `${issuer}/.well-known/jwks.json`,
    },
    // Per-tab storage survives the hosted redirect and reload; no persistent localStorage.
    userStore: new WebStorageStateStore({ store: sessionStorage }),
    stateStore: new WebStorageStateStore({ store: sessionStorage }),
    automaticSilentRenew: true,
    accessTokenExpiringNotificationTimeInSeconds: 60,
    monitorSession: false,
    loadUserInfo: false,
  });
  return manager;
}

export async function signIn() {
  const client = await auth();
  await client.clearStaleState();
  await client.signinRedirect({ state: { returnTo: location.hash } });
}

export async function finishSignIn() {
  try {
    const user = await (await auth()).signinRedirectCallback(location.href);
    const state = user.state as { returnTo?: string } | undefined;
    const returnTo = state?.returnTo?.startsWith("#/")
      ? state.returnTo
      : "#/overview";
    history.replaceState(null, "", "/" + returnTo);
    return user;
  } catch {
    history.replaceState(null, "", "/");
    throw new Error(
      "Sign-in could not be completed. Start a new sign-in from this page.",
    );
  }
}

export async function signOut() {
  const client = await auth();
  client.stopSilentRenew();
  // Local session clears even when revocation is unreachable; hosted logout clears its cookie.
  try {
    await client.revokeTokens(["refresh_token"]);
  } catch {
    /* hosted logout still proceeds */
  }
  await client.removeUser();
  const config = await getConfig();
  const params = new URLSearchParams({
    client_id: config.clientId,
    logout_uri: config.logoutUrl,
  });
  location.assign(`${config.loginDomain}/logout?${params}`);
}

export function sessionExpired() {
  window.dispatchEvent(new Event("forge:session-expired"));
}

let renewal: Promise<import("oidc-client-ts").User | null> | undefined;
export async function accessToken(forceRenew = false) {
  const client = await auth();
  let user = await client.getUser();
  if (!user) {
    sessionExpired();
    throw new Error("Your session has ended. Please sign in again.");
  }
  if (forceRenew || user.expired) {
    try {
      renewal ??= client.signinSilent().finally(() => {
        renewal = undefined;
      });
      user = await renewal;
    } catch {
      await client.removeUser();
      sessionExpired();
      throw new Error("Your session has expired. Please sign in again.");
    }
  }
  if (!user || user.expired) {
    sessionExpired();
    throw new Error("Your session has expired. Please sign in again.");
  }
  return user.access_token;
}

// Claims here personalize the UI only. API Gateway and Lambda enforce permissions.
export function rolesFromToken(token: string): string[] {
  try {
    const segment = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(segment));
    return Array.isArray(claims["cognito:groups"])
      ? claims["cognito:groups"]
      : [];
  } catch {
    return [];
  }
}
