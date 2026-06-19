/**
 * WebAuthn / Passkey helpers.
 *
 * The WebAuthn API uses ArrayBuffers, but JSON uses strings, so we need to
 * convert back and forth. base64url is the encoding the server uses.
 */

function _b64urlToBuffer(b64url) {
  const padded = b64url.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded);
  const buf = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) buf[i] = binary.charCodeAt(i);
  return buf.buffer;
}

function _bufferToB64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/** Convert all base64url binary fields in WebAuthn options from strings to ArrayBuffers. */
function _decodeRegistrationOptions(opts) {
  opts.challenge = _b64urlToBuffer(opts.challenge);
  opts.user.id = _b64urlToBuffer(opts.user.id);
  if (opts.excludeCredentials) {
    opts.excludeCredentials = opts.excludeCredentials.map((c) => ({
      ...c,
      id: _b64urlToBuffer(c.id),
    }));
  }
  return opts;
}

function _decodeAuthenticationOptions(opts) {
  opts.challenge = _b64urlToBuffer(opts.challenge);
  if (opts.allowCredentials) {
    opts.allowCredentials = opts.allowCredentials.map((c) => ({
      ...c,
      id: _b64urlToBuffer(c.id),
    }));
  }
  return opts;
}

/** Serialise the registration response back to JSON-safe format. */
function _encodeRegistrationCredential(cred) {
  return {
    id: cred.id,
    rawId: _bufferToB64url(cred.rawId),
    type: cred.type,
    response: {
      attestationObject: _bufferToB64url(cred.response.attestationObject),
      clientDataJSON: _bufferToB64url(cred.response.clientDataJSON),
      transports: cred.response.getTransports ? cred.response.getTransports() : [],
    },
  };
}

/** Serialise the authentication assertion back to JSON-safe format. */
function _encodeAuthenticationCredential(cred) {
  return {
    id: cred.id,
    rawId: _bufferToB64url(cred.rawId),
    type: cred.type,
    response: {
      authenticatorData: _bufferToB64url(cred.response.authenticatorData),
      clientDataJSON: _bufferToB64url(cred.response.clientDataJSON),
      signature: _bufferToB64url(cred.response.signature),
      userHandle: cred.response.userHandle ? _bufferToB64url(cred.response.userHandle) : null,
    },
  };
}

/**
 * Register a new passkey for the currently logged-in user.
 *
 * @param {object} opts
 * @param {string} opts.beginUrl     - POST endpoint that returns options
 * @param {string} opts.completeUrl  - POST endpoint that verifies + stores
 * @param {string} opts.csrfToken
 * @param {function} opts.onSuccess  - called after successful registration
 * @param {string} [opts.name]       - human label for the passkey
 */
async function registerPasskey({ beginUrl, completeUrl, csrfToken, onSuccess, name }) {
  if (!window.PublicKeyCredential) {
    alert("Your browser does not support passkeys.");
    return;
  }

  try {
    // Step 1: get options from server
    const beginResp = await fetch(beginUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
    });
    if (!beginResp.ok) throw new Error("Failed to start passkey registration.");
    const options = await beginResp.json();
    _decodeRegistrationOptions(options);

    // Step 2: ask the browser / device for a credential
    const credential = await navigator.credentials.create({ publicKey: options });
    const encoded = _encodeRegistrationCredential(credential);
    if (name) encoded.name = name;

    // Step 3: send result to server for verification + storage
    const completeResp = await fetch(completeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(encoded),
    });
    const result = await completeResp.json();
    if (result.error) throw new Error(result.error);

    if (onSuccess) onSuccess();
  } catch (err) {
    if (err.name !== "NotAllowedError") {
      // NotAllowedError = user cancelled — don't show an error for that
      alert("Passkey registration failed: " + err.message);
    }
  }
}

/**
 * Authenticate with a passkey (login flow).
 *
 * @param {object} opts
 * @param {string} opts.beginUrl     - POST endpoint that returns challenge
 * @param {string} opts.completeUrl  - POST endpoint that verifies
 * @param {string} opts.csrfToken
 */
async function authenticatePasskey({ beginUrl, completeUrl, csrfToken }) {
  if (!window.PublicKeyCredential) {
    alert("Your browser does not support passkeys.");
    return;
  }

  try {
    // Step 1: get challenge from server
    const beginResp = await fetch(beginUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
    });
    if (!beginResp.ok) throw new Error("Failed to start passkey authentication.");
    const { options, challenge_key } = await beginResp.json();
    _decodeAuthenticationOptions(options);

    // Step 2: browser selects and uses a stored passkey
    const credential = await navigator.credentials.get({ publicKey: options });
    const encoded = _encodeAuthenticationCredential(credential);

    // Step 3: verify on server
    const completeResp = await fetch(completeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ challenge_key, credential: encoded }),
    });
    const result = await completeResp.json();
    if (result.error) throw new Error(result.error);

    window.location.href = result.redirect;
  } catch (err) {
    if (err.name !== "NotAllowedError") {
      alert("Passkey authentication failed: " + err.message);
    }
  }
}
