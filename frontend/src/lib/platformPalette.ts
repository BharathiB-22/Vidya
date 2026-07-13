/**
 * Colour helpers for the Platform Console.
 *
 * The console builds soft tints and hairline borders from an accent colour by
 * appending a hex alpha suffix — `accentColor + '18'`. That trick only works on
 * a literal hex, and it silently produces garbage the moment the colour becomes
 * a CSS variable (`var(--pc-info)18` is not a colour). Since theming turns those
 * accents into tokens, the tint has to be computed in CSS instead of in JS.
 *
 * `color-mix()` does exactly that, and accepts a hex and a `var()` alike — so
 * the same call sites keep working whether they are handed a token or a raw
 * tenant brand colour picked in the branding form.
 */

/** A translucent wash of `color` at `percent` opacity, over whatever is behind it. */
export function tint(color: string, percent: number): string {
  return `color-mix(in srgb, ${color} ${percent}%, transparent)`
}
