/** EULA version and acceptance check — shared between EulaDialog and App. */

// Bump this when the TOS text changes materially — forces re-acceptance.
export const EULA_VERSION = "1.0";

const STORAGE_KEY = "eula_accepted_version";

/** Returns true if the user has already accepted the current EULA version. */
export function hasAcceptedEula(): boolean {
  return localStorage.getItem(STORAGE_KEY) === EULA_VERSION;
}

/** Record that the user accepted the current EULA version. */
export function recordEulaAcceptance(): void {
  localStorage.setItem(STORAGE_KEY, EULA_VERSION);
}
