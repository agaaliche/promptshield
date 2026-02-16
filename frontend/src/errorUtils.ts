/**
 * Safely extract an error message from an unknown caught value.
 *
 * Usage:
 *   catch (e: unknown) { console.error(toErrorMessage(e)); }
 */
export function toErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  if (
    err !== null &&
    typeof err === "object" &&
    "message" in err &&
    typeof (err as { message: unknown }).message === "string"
  ) {
    return (err as { message: string }).message;
  }
  return String(err);
}
