// Provide a minimal JSX IntrinsicElements mapping so TS accepts standard HTML tags in this environment
declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any
  }
}
