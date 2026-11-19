const integerFormat = new Intl.NumberFormat("en-US");
export const symbol = (decimals) => decimals === 6 ? "USDC" : "WAVAX";
export function units(value, places) {
  if (value == null) return "—";
  const amount = BigInt(value);
  const scale = 10n ** BigInt(places);
  const magnitude = amount < 0n ? -amount : amount;
  const whole = integerFormat.format(magnitude / scale);
  const fraction = (magnitude % scale).toString().padStart(places, "0").replace(/0+$/, "");
  return (amount < 0n ? "−" : "") + whole + (fraction ? "." + fraction : "");
}
