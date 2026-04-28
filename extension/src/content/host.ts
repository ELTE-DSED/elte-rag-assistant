export function shouldInjectOnHostname(hostname: string): boolean {
  const normalizedHostname = hostname.toLowerCase();
  return normalizedHostname === "inf.elte.hu" || normalizedHostname === "www.inf.elte.hu";
}
