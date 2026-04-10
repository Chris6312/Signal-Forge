/* eslint-disable @typescript-eslint/no-unused-vars */
declare module '@tanstack/react-query' {
  // Minimal, permissive shims for build until proper types are wired
  export type QueryObserverResult<T = any> = any
  export function useQuery<T = any>(opts: any): { data: T | undefined; isLoading?: boolean; isRefetching?: boolean; refetch?: () => Promise<any> }
  export function useMutation(opts: any): any
  export function useQueryClient(): any
}

declare module '@tanstack/react-table' {
  // Very small set of shims to allow using generics in source without full types
  export type SortingState = any
  export function createColumnHelper<T = any>(): any
  export function flexRender(a: any, b: any): any
  export function getCoreRowModel(): any
  export function getSortedRowModel(): any
  export function getFilteredRowModel(): any
  export function useReactTable(opts: any): any
}
