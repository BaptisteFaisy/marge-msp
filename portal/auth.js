/* Marge portal — Cognito Hosted UI sign-in (idea 61).
 *
 * The portal is a static page: it cannot hold a client secret, so it uses the
 * implicit flow. The id token comes back in the URL fragment, is kept in
 * sessionStorage for the tab, and is sent as a Bearer token. The API verifies
 * its RS256 signature against the pool JWKS (marge.api.cognito_jwks) and reads
 * the role from cognito:groups — the portal never decides who you are.
 */
"use strict";

const AUTH_STORAGE_KEY = "marge.idToken";
const AUTH_CONFIG_KEY = "marge.authConfig";

function authConfig() {
  try {
    return JSON.parse(sessionStorage.getItem(AUTH_CONFIG_KEY) || "null");
  } catch (err) {
    return null;
  }
}

function bearerToken() {
  return sessionStorage.getItem(AUTH_STORAGE_KEY) || "";
}

function isCognito() {
  const config = authConfig();
  return !!(config && config.mode === "cognito" && config.cognito);
}

function decodeClaims(token) {
  /* Display only: the server re-verifies the signature. */
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(decodeURIComponent(escape(atob(part))));
  } catch (err) {
    return null;
  }
}

function captureTokenFromFragment() {
  /* Implicit flow: #id_token=…&token_type=Bearer&expires_in=3600 */
  if (!window.location.hash || window.location.hash.indexOf("id_token=") < 0) return;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get("id_token");
  if (params.get("error")) {
    setStatus("Sign-in refused: " + params.get("error_description"));
  } else if (token) {
    sessionStorage.setItem(AUTH_STORAGE_KEY, token);
  }
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
}

function signInUrl() {
  const config = authConfig();
  if (!config || !config.cognito) return "";
  const base = "https://" + config.cognito.domain + "/login";
  const redirect = window.location.origin + window.location.pathname;
  return (
    base +
    "?client_id=" + encodeURIComponent(config.cognito.client_id) +
    "&response_type=token" +
    "&scope=" + encodeURIComponent(config.cognito.scopes || "openid email profile") +
    "&redirect_uri=" + encodeURIComponent(redirect)
  );
}

function signOutUrl() {
  const config = authConfig();
  if (!config || !config.cognito) return "";
  const redirect = window.location.origin + window.location.pathname;
  return (
    "https://" + config.cognito.domain + "/logout" +
    "?client_id=" + encodeURIComponent(config.cognito.client_id) +
    "&logout_uri=" + encodeURIComponent(redirect)
  );
}

function renderAuthBox() {
  const box = $("auth-box");
  if (!box) return;
  const token = bearerToken();
  if (!isCognito()) {
    box.innerHTML = "";
    box.appendChild(devSelectorNote());
    return;
  }
  box.innerHTML = "";
  if (token) {
    const claims = decodeClaims(token) || {};
    const who = document.createElement("span");
    who.className = "auth-who";
    who.textContent = (claims["cognito:username"] || claims.sub || "signed in") +
      " · " + ((claims["cognito:groups"] || []).join(", ") || "no group");
    const out = document.createElement("button");
    out.type = "button";
    out.textContent = "Sign out";
    out.addEventListener("click", () => {
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
      const url = signOutUrl();
      if (url) window.location.assign(url);
    });
    box.appendChild(who);
    box.appendChild(out);
    return;
  }
  const signIn = document.createElement("button");
  signIn.type = "button";
  signIn.textContent = "Sign in with Cognito";
  signIn.addEventListener("click", () => window.location.assign(signInUrl()));
  box.appendChild(signIn);
}

function devSelectorNote() {
  const note = document.createElement("span");
  note.className = "auth-note";
  note.textContent = "dev mode: identity comes from the headers below (demo accounts)";
  return note;
}

function lockDevSelectors() {
  /* In cognito mode the headers are ignored by the API: grey them out so nobody
   * believes they can pick a role. */
  const locked = isCognito();
  ["actor-id", "actor-role"].forEach((id) => {
    const field = $(id);
    if (field) field.disabled = locked;
  });
}

async function initAuth() {
  try {
    const response = await fetch(apiBase() + "/v1/auth/config");
    if (response.ok) sessionStorage.setItem(AUTH_CONFIG_KEY, await response.text());
  } catch (err) {
    /* No config: stay in dev mode, the API decides anyway. */
  }
  captureTokenFromFragment();
  renderAuthBox();
  lockDevSelectors();
}
