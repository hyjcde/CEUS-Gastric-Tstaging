declare module 'opencc-js' {
  export type ConverterFn = (text: string) => string;
  export function Converter(options: { from: string; to: string }): ConverterFn;
  export function ConverterFactory(...args: unknown[]): ConverterFn;
  export function CustomConverter(...args: unknown[]): ConverterFn;
  export function HTMLConverter(...args: unknown[]): unknown;
  export const Locale: Record<string, unknown>;
  export const Trie: unknown;
}
