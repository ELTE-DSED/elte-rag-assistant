import { shouldInjectOnHostname } from "./host";

describe("shouldInjectOnHostname", () => {
  it("allows inf.elte.hu and www.inf.elte.hu", () => {
    expect(shouldInjectOnHostname("inf.elte.hu")).toBe(true);
    expect(shouldInjectOnHostname("www.inf.elte.hu")).toBe(true);
  });

  it("rejects other ELTE subdomains and unrelated hosts", () => {
    expect(shouldInjectOnHostname("people.inf.elte.hu")).toBe(false);
    expect(shouldInjectOnHostname("elte.hu")).toBe(false);
    expect(shouldInjectOnHostname("example.com")).toBe(false);
  });
});
